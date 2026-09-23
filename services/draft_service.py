"""Draft vouchers proposed in a thread (docs/redesign/SPEC-flode-verifikationer.md
§5, §6).

`foresla_verifikation` lands here. A proposal is three writes that only make
sense together -- the draft voucher (series A, no number), the `draft` post
that shows it in the thread, and the `thread_drafts` row that ties the two
and follows the draft until it is posted or replaced -- so they are made in
**one** transaction, on the same thread-local connection, the pattern
`ThreadService.record_outcome` uses for a `decision` post and its row.

What this module deliberately does not do:

- Post. The human's press on `Posta` is the approval; a proposal only
  prepares what that press will post (§5.1, §5.4).
- Link traceability at proposal time. `intake_source_ids` and the bank ids
  are checked here with the same checks a direct posting runs, then kept on
  the row (migration 029). A link marks the source processed and the
  transaction booked, which is only true once the voucher is posted, so
  `on_posting` links them, inside the posting's transaction (§8.1, F8).
- Correct. `correction_of` is refused with `not_implemented` until F11
  builds §7's branch.

Layering (AGENTS.md): no SQL here -- every write goes through a repository or
`LedgerService` -- and no HTTP. Errors are `ValidationError`s with the
`{code, message, details}` shape the session already renders for the model.
"""

import logging
from dataclasses import dataclass
from datetime import date as DateType
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from db.database import db
from domain.models import Account, Period, Thread, ThreadDraft, ThreadPost, Voucher
from domain.validation import ValidationError, VoucherValidator
from repositories.account_repo import AccountRepository
from repositories.decision_repo import DecisionRepository
from repositories.intake_repo import IntakeRepository
from repositories.period_repo import PeriodRepository
from repositories.thread_draft_repo import (
    ThreadDraftRepository,
    ThreadDraftTransitionError,
)
from repositories.thread_repo import ThreadRepository
from repositories.voucher_repo import VoucherRepository
from services.idempotency import IdempotencyOutcome, IdempotencyService

logger = logging.getLogger(__name__)

#: Idempotency-key endpoint scope for proposals (§5.5). Its own namespace, so
#: a proposal and a posting from the same user post can never collide.
FORESLA_VERIFIKATION_ENDPOINT = "TOOL foresla_verifikation"

#: The series a plain proposal gets. The model does not choose it: `A`
#: without `correction_of`, `B` with (§5.2) -- and the latter is F11's.
_SERIES = "A"

#: Mirrors fastapi.status.HTTP_201_CREATED for the stored idempotency
#: response; services/ must not import fastapi.status.
_HTTP_201_CREATED = 201

_MONTHS = (
    "januari",
    "februari",
    "mars",
    "april",
    "maj",
    "juni",
    "juli",
    "augusti",
    "september",
    "oktober",
    "november",
    "december",
)


class DraftError(ValidationError):
    """A proposal refused by one of §5.3's checks that `VoucherValidator`
    does not already own."""


class SourceAlreadyBookedError(DraftError):
    """The posting of a thread draft met an underlag or a bank transaction
    that another voucher has booked while the proposal waited (F6's open
    risk). Raised inside the posting's transaction, so the whole posting --
    number, status, links -- rolls back with it."""

    def __init__(
        self,
        *,
        source_kind: str,
        source_id: str,
        voucher_id: Optional[str],
        voucher_number: Optional[str],
    ):
        self.source_kind = source_kind
        self.source_id = source_id
        self.voucher_id = voucher_id
        self.voucher_number = voucher_number
        super().__init__(
            "source_already_booked",
            "The draft's source material is already booked on another voucher",
            details=(
                f"{source_kind}={source_id}, voucher_id={voucher_id}, "
                f"voucher_number={voucher_number}"
            ),
        )

    def booked_by(self) -> dict:
        return {
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "voucher_id": self.voucher_id,
            "voucher_number": self.voucher_number,
        }


class SourceNotLinkableError(DraftError):
    """The posting of a thread draft met an underlag or bank input that can
    no longer be linked for another reason than being booked (removed,
    rejected). Rolls the posting back like `SourceAlreadyBookedError`."""

    def __init__(self, *, source_kind: str, source_id: str, exc: Any):
        self.source_kind = source_kind
        self.source_id = source_id
        super().__init__(
            "source_not_linkable",
            "The draft's source material can no longer be linked to a voucher",
            details=f"{source_kind}={source_id}, {exc.code}: {exc.message}",
        )


def period_name(period: Period) -> str:
    """`september 2026` -- how a period is named to the human."""
    return f"{_MONTHS[period.month - 1]} {period.year}"


def draft_meta(series: str, voucher_date: DateType) -> str:
    """§5.6: there is no number yet to show, so the meta line says what the
    card is instead."""
    return f"Förslag · {series} · {voucher_date.isoformat()}"


def draft_consequence(series: str, period: Period) -> str:
    """§5.6: the server's line, since it is fact about the period and the
    series, not the agent's reasoning."""
    state = "låst" if period.locked else "öppen"
    return (
        f"Låses vid postning · får nästa nummer i {series}-serien · "
        f"period {period_name(period)} {state}"
    )


def draft_body(
    *,
    draft_id: str,
    title: str,
    series: str,
    voucher_date: DateType,
    rows: Sequence[Mapping[str, Any]],
    accounts: Mapping[str, Account],
    footnote: Optional[str],
    period: Period,
    decision_id: Optional[str],
) -> dict:
    """The `draft` post's body -- exactly SPEC-chattyta.md §4.3's keys, which
    `tests/test_flode_verifikationer.py` reads out of the client's fixture."""
    return {
        "draft_id": draft_id,
        "kind": "voucher",
        "title": title,
        "meta": draft_meta(series, voucher_date),
        "rows": [
            {
                "account": row["account"],
                "name": accounts[row["account"]].name,
                "debit_ore": row.get("debit") or None,
                "credit_ore": row.get("credit") or None,
            }
            for row in rows
        ],
        "footnote": footnote,
        "consequence": draft_consequence(series, period),
        "decision_id": decision_id,
    }


#: Trace chips on a receipt (§8.2). Same `{tool, label, detail?,
#: voucher_id?}` shape as `services/thread_service.build_trace`; `tool` names
#: what happened, since no agent tool ran -- the human pressed Posta.
RECEIPT_POSTED_TOOL = "posta_utkast"
RECEIPT_FLAG_TOOL = "kompletteringsflagga"
RECEIPT_WAITING_TOOL = "vantar"


def voucher_label(voucher: Voucher) -> str:
    """`A-118`: series and number, as the thread names a posted voucher."""
    return f"{voucher.series.value}-{voucher.number}"


def receipt_body(voucher: Voucher, accounts: Mapping[str, Account]) -> dict:
    """The `receipt` post's body -- SPEC-chattyta.md §4.3, which
    `tests/test_flode_verifikationer.py` reads out of the client's fixture.

    One row per account, in the voucher's order, both numbers always: the
    account's balance in the fiscal year before and after (§8.2)."""
    return {
        "title": f"{voucher_label(voucher)} postad",
        "labels": ["var", "blir"],
        "rows": [
            {
                "key": code,
                "text": accounts[code].name if code in accounts else code,
                "left_ore": before,
                "right_ore": after,
            }
            for code, before, after in VoucherRepository.account_balances_around(
                voucher.id
            )
        ],
        "voucher_id": voucher.id,
    }


def receipt_traces(voucher: Voucher, waiting: int) -> List[dict]:
    """§8.2's chips. `waiting` is `DecisionService.count_waiting` for the
    thread's view, counted after the posting (§11.3): its `{n} kvar` chip
    comes last. The correction's `rättar {serie}-{nummer}` is F12's."""
    traces: List[dict] = [
        {
            "tool": RECEIPT_POSTED_TOOL,
            "label": "verifikation postad",
            "detail": voucher_label(voucher),
            "voucher_id": voucher.id,
        }
    ]
    # Derived, like SPEC-oversikt.md §3: no row in `attachments`.
    if voucher.missing_attachment:
        traces.append({"tool": RECEIPT_FLAG_TOOL, "label": "kompletteringsflagga satt"})
    traces.append({"tool": RECEIPT_WAITING_TOOL, "label": f"{waiting} kvar"})
    return traces


#: The consequence every failed posting shares: the posting rolled back.
_NOTHING_CHANGED = "Ingenting har ändrats i bokföringen."

#: Failures that are not failures for the thread: the voucher is posted, and
#: the receipt path (`on_posted`) owns what the thread says.
_NOT_A_FAILURE = frozenset({"already_posted"})


def posting_error_body(error: ValidationError, voucher_id: str) -> dict:
    """The `error` post's body for a failed posting of a thread draft (§9.1):
    cause and consequence in bookkeeping terms, built from the failure and
    the ledger's current state -- never a status code. `retry_draft_id` is
    always `None`: none of these can succeed by pressing again."""
    cause, consequence = _posting_error_texts(error, voucher_id)
    return {"cause": cause, "consequence": consequence, "retry_draft_id": None}


def _posting_error_texts(error: ValidationError, voucher_id: str) -> tuple:
    if error.code == "period_locked":
        voucher = VoucherRepository.get(voucher_id)
        period = PeriodRepository.get_period(voucher.period_id) if voucher else None
        if period is not None:
            return _period_locked_texts(period)
    if isinstance(error, SourceAlreadyBookedError):
        return _already_booked_texts(error)
    if isinstance(error, SourceNotLinkableError):
        return (
            f"{_source_phrase(error.source_kind, error.source_id)} kan inte längre "
            "kopplas till en verifikation.",
            f"{_NOTHING_CHANGED} Förslaget ligger kvar men kan inte postas med "
            "det underlaget.",
        )
    as_written = (
        f"{_NOTHING_CHANGED} Förslaget ligger kvar men kan inte postas som det står."
    )
    account = _account_code(error.details)
    if error.code == "inactive_account" and account:
        known = AccountRepository.get(account)
        name = f" {known.name}" if known is not None else ""
        return (
            f"Konto {account}{name} har inaktiverats i kontoplanen sedan "
            "förslaget lades fram.",
            as_written,
        )
    if error.code == "account_not_found" and account:
        return (f"Konto {account} finns inte längre i kontoplanen.", as_written)
    if error.code == "voucher_date_outside_period":
        return ("Verifikationens datum ligger utanför dess period.", as_written)
    return (
        f"Förslaget klarade inte bokföringens kontroller vid postningen "
        f"({error.message}).",
        as_written,
    )


def _period_locked_texts(period: Period) -> tuple:
    name = period_name(period)
    when = f" {period.locked_at.strftime('%Y-%m-%d %H:%M')}" if period.locked_at else ""
    # A lock from before migration 023 has no recorded actor: say nothing
    # rather than guess.
    who = f" av {period.locked_by}" if period.locked_by else ""
    return (
        f"Perioden {name} låstes{when}{who} medan förslaget låg.",
        f"{_NOTHING_CHANGED} Förslaget ligger kvar men kan inte postas i {name}.",
    )


def _already_booked_texts(error: SourceAlreadyBookedError) -> tuple:
    number = error.voucher_number
    on = f"verifikation {number}" if number else "en annan verifikation"
    kept = number or "Den verifikationen"
    return (
        f"{_source_phrase(error.source_kind, error.source_id)} bokfördes på {on} "
        "medan förslaget låg.",
        f"{_NOTHING_CHANGED} Samma underlag bokförs inte två gånger: {kept} står "
        "kvar och förslaget ligger kvar opostat.",
    )


def _source_phrase(source_kind: str, source_id: str) -> str:
    """`Underlaget kvitto.pdf`, `Banktransaktionen` -- the thing, as the
    human knows it."""
    if source_kind == "intake_source":
        source = IntakeRepository.get_source(source_id)
        if source is not None and source.original_filename:
            return f"Underlaget {source.original_filename}"
        return "Underlaget"
    if source_kind == "bank_transaction":
        return "Banktransaktionen"
    return "Bankunderlaget"


def _account_code(details: Optional[str]) -> Optional[str]:
    """`VoucherValidator`'s account errors carry `account_code=6110`."""
    prefix = "account_code="
    if details and details.startswith(prefix):
        return details[len(prefix) :]
    return None


#: `GET /drafts?status=` (§10): the table's three states, or every one.
DRAFT_LIST_STATUSES = ("pending", "posted", "superseded", "all")


@dataclass
class DraftListItem:
    """One row of `GET /drafts` (§10): the `thread_drafts` row and, when it
    is posted, the number the ledger gave it."""

    draft: ThreadDraft
    series: Optional[str] = None
    number: Optional[int] = None


class DraftService:
    """Orchestrates thread drafts: `propose` (F6), the posting's two hooks
    `on_posting`/`on_posted` (F8) and its failure, `on_posting_failed` (F9),
    and the list the card reads its state from, `list_drafts` (F10). The
    correction branch follows in F11."""

    # -- the list (§10) ---------------------------------------------------

    def list_drafts(
        self, *, view_key: str, status: str = "all", limit: Optional[int] = None
    ) -> Tuple[List[DraftListItem], int]:
        """One view's thread drafts, oldest first, and the total before
        `limit`. A posted row carries its series and number, read from the
        ledger in one query for the whole page -- never one per row.

        An unknown `status` is `ValidationError(code="unknown_status")`, the
        same code `DecisionService.list_decisions` uses."""
        if status not in DRAFT_LIST_STATUSES:
            raise ValidationError(
                code="unknown_status",
                message=f"Unknown status: {status!r}",
                details="expected one of: " + ", ".join(DRAFT_LIST_STATUSES),
            )
        drafts, total = ThreadDraftRepository.list(
            view_key=view_key, status=status, limit=limit
        )
        numbers = VoucherRepository.numbers_for(
            [d.voucher_id for d in drafts if d.status == "posted"]
        )
        items = []
        for draft in drafts:
            series, number = (
                numbers.get(draft.voucher_id, (None, None))
                if draft.status == "posted"
                else (None, None)
            )
            items.append(DraftListItem(draft=draft, series=series, number=number))
        return items, total

    # -- posting hooks (§8.1) ---------------------------------------------

    def on_posting(
        self, voucher: Voucher, *, actor: str, _commit: bool = False
    ) -> Optional[ThreadDraft]:
        """Steps 1-3 of §8.1, inside the posting's transaction.

        `voucher` is the just-posted voucher (status and number already set
        in the same, uncommitted transaction). A draft that is not a thread's,
        or whose row is no longer `pending`, is left alone: returns `None`.

        Any failure raises and must roll the posting back with it -- in
        particular `SourceAlreadyBookedError` when the intake flow booked the
        same underlag or bank transaction while the proposal waited: no
        number is taken, the draft stays a draft, the row stays `pending`.
        """
        draft = ThreadDraftRepository.get(voucher.id)
        if draft is None or draft.status != "pending":
            return None

        # 0. The chart of accounts as it is now, not as it was when the
        #    proposal was checked (§9: "kontoplanen ändrad sedan förslaget").
        #    `post_voucher` does not re-run these checks.
        accounts = AccountRepository.get_all_as_dict(active_only=False)
        VoucherValidator.validate_accounts_exist(voucher, accounts)
        VoucherValidator.validate_accounts_active(voucher, accounts)

        # 1. pending -> posted.
        draft = ThreadDraftRepository.mark_posted(
            voucher.id, voucher.posted_at or datetime.now(), _commit=False
        )
        # 2. TODO(F12): if draft.correction_of -- the correction history and,
        #    when draft.correction_note_id is set, the note `applied` (§7),
        #    here, before the traceability, inside the same transaction.
        # 3. Traceability, as a direct posting links it.
        self._link_traceability(draft, voucher, actor)

        if _commit:
            db.commit()
        return draft

    def on_posted(self, voucher: Voucher, *, actor: str) -> Optional[ThreadPost]:
        """Steps 4-5 of §8.1, after the posting has committed.

        Idempotent and resumable: does nothing unless the row is `posted`
        and has no receipt yet, so the route can call it again on every
        replay (`Idempotent-Replay`, `409 already_posted`). Never two
        receipts: the post and `receipt_post_id` commit together, and
        `set_receipt` refuses a second one.

        The caller must not let an exception from here change the posting's
        answer -- the voucher is already committed.
        """
        draft = ThreadDraftRepository.get(voucher.id)
        if (
            draft is None
            or draft.status != "posted"
            or draft.receipt_post_id is not None
        ):
            return None
        post = self._write_receipt(voucher, actor=actor)
        if post is None:
            return None

        from services.thread_stream import (
            EVENT_MESSAGE_COMPLETED,
            EVENT_VIEW_CHANGED,
            get_broker,
            post_event_payload,
        )

        broker = get_broker()
        broker.publish(
            draft.thread_id, EVENT_MESSAGE_COMPLETED, post_event_payload(post)
        )
        broker.publish(
            draft.thread_id,
            EVENT_VIEW_CHANGED,
            {
                "view_key": draft.view_key,
                "changed": {"voucher_id": voucher.id, "kind": "voucher_posted"},
            },
        )
        return post

    def on_posting_failed(
        self, voucher_id: str, error: ValidationError, *, actor: str
    ) -> Optional[ThreadPost]:
        """§9: a refused posting of a thread draft, after the posting's
        transaction has rolled back. Writes one `error` post (§9.1) and
        `last_error_code`/`last_error_post_id`, in a transaction of their own,
        and publishes `message.completed`.

        **One post per draft and code**: when the row already points at a
        post for the same code, nothing is written. `None` then, and for a
        draft that is not a thread's or no longer `pending`.

        The caller must not let an exception from here change the posting's
        answer.
        """
        if error.code in _NOT_A_FAILURE:
            return None
        draft = ThreadDraftRepository.get(voucher_id)
        if draft is None or not _needs_error_post(draft, error.code):
            return None
        body = posting_error_body(error, voucher_id)
        try:
            with db.transaction():
                current = ThreadDraftRepository.get(voucher_id)
                if current is None or not _needs_error_post(current, error.code):
                    return None
                post = ThreadRepository.add_post(
                    thread_id=draft.thread_id,
                    post_type="error",
                    actor=actor,
                    body=body,
                    _commit=False,
                )
                ThreadDraftRepository.set_error(
                    voucher_id, error.code, post.id, _commit=False
                )
        except ThreadDraftTransitionError:
            logger.info("Draft %s left pending meanwhile; no error post", voucher_id)
            return None

        from services.thread_stream import (
            EVENT_MESSAGE_COMPLETED,
            get_broker,
            post_event_payload,
        )

        get_broker().publish(
            draft.thread_id, EVENT_MESSAGE_COMPLETED, post_event_payload(post)
        )
        return post

    def _write_receipt(self, voucher: Voucher, *, actor: str) -> Optional[ThreadPost]:
        """The `receipt` post and `receipt_post_id`, in one transaction.
        `None` when another request wrote the receipt first."""
        draft = ThreadDraftRepository.get(voucher.id)
        if draft is None:
            return None
        body = receipt_body(voucher, AccountRepository.get_all_as_dict())
        from services.decision_service import DecisionService

        # After the posting's commit: this draft no longer waits (§8.2).
        traces = receipt_traces(
            voucher, DecisionService().count_waiting(draft.view_key)
        )
        try:
            with db.transaction():
                post = ThreadRepository.add_post(
                    thread_id=draft.thread_id,
                    post_type="receipt",
                    actor=actor,
                    body=body,
                    traces=traces,
                    _commit=False,
                )
                ThreadDraftRepository.set_receipt(voucher.id, post.id, _commit=False)
        except ThreadDraftTransitionError:
            logger.info("Receipt for %s already written; skipped", voucher.id)
            return None
        return post

    @staticmethod
    def _link_traceability(draft: ThreadDraft, voucher: Voucher, actor: str) -> None:
        """Link the row's underlag and bank transactions to the posted
        voucher, `_commit=False`, exactly as `post_agent_voucher` does. The
        services run their own checks again; a refusal because the thing
        is already booked becomes `SourceAlreadyBookedError`, any other
        refusal a `DraftError` carrying the service's code."""
        from services.bank_inputs import BankInputError, BankInputService
        from services.intake import IntakeError, IntakeService

        intake = IntakeService()
        for source_id in draft.intake_source_ids:
            try:
                intake.link_existing_voucher(
                    source_id=source_id,
                    voucher_id=voucher.id,
                    actor=actor,
                    summary=voucher.description,
                    link_reason="thread_draft_posted",
                    _commit=False,
                )
            except IntakeError as exc:
                link = IntakeRepository.get_link_by_source_id(source_id)
                if link is not None:
                    raise _already_booked("intake_source", source_id, link.voucher_id)
                raise _not_linkable("intake_source", source_id, exc)

        if not (draft.bank_input_ids or draft.bank_transaction_ids):
            return
        bank_inputs = BankInputService()
        try:
            bank_inputs.link_posted_voucher(
                voucher_id=voucher.id,
                bank_input_ids=draft.bank_input_ids,
                bank_transaction_ids=draft.bank_transaction_ids,
                actor=actor,
                _commit=False,
            )
        except BankInputError as exc:
            for transaction_id in draft.bank_transaction_ids:
                transaction = bank_inputs.bank.get_transaction(transaction_id)
                if transaction is not None and (
                    transaction.status == "booked"
                    or transaction.matched_voucher_id is not None
                ):
                    raise _already_booked(
                        "bank_transaction",
                        transaction_id,
                        transaction.matched_voucher_id,
                    )
            raise _not_linkable("bank_input", ",".join(draft.bank_input_ids), exc)

    # -- proposal (§5) ----------------------------------------------------

    def propose(
        self,
        thread: Thread,
        *,
        description: str,
        rows: Sequence[Mapping[str, Any]],
        date: Optional[DateType] = None,
        period_id: Optional[str] = None,
        footnote: Optional[str] = None,
        decision_id: Optional[str] = None,
        replaces_draft_id: Optional[str] = None,
        correction_of: Optional[str] = None,
        correction_note_id: Optional[str] = None,
        intake_source_ids: Sequence[str] = (),
        bank_input_ids: Sequence[str] = (),
        bank_transaction_ids: Sequence[str] = (),
        actor: str = "agent",
        idempotency_key: Optional[str] = None,
    ) -> dict:
        """Check (§5.3), then write draft, post and row in one transaction.

        With `idempotency_key` (the thread path's
        `thread:{thread_id}:{post_id}:{n}`, §5.5) the key is reserved under
        `FORESLA_VERIFIKATION_ENDPOINT` *before* the checks, so a turn run
        again after a crash replays the draft it already made -- even if the
        period has since been locked -- and completed inside the same
        transaction as the writes. A failure releases it.

        Returns the tool result: `draft_id`, `post_id`, `status`, `series`,
        `date`, `period_id`, `description`, `meta`, `consequence`,
        `decision_id`, `replaced_draft_id` (and `idempotent_replay: True` on
        a replay).
        """
        request = {
            "description": description,
            "rows": [dict(row) for row in rows],
            "date": date.isoformat() if date is not None else None,
            "period_id": period_id,
            "footnote": footnote,
            "decision_id": decision_id,
            "replaces_draft_id": replaces_draft_id,
            "correction_of": correction_of,
            "correction_note_id": correction_note_id,
            "intake_source_ids": list(intake_source_ids),
            "bank_input_ids": list(bank_input_ids),
            "bank_transaction_ids": list(bank_transaction_ids),
        }

        idempotency = IdempotencyService()
        if idempotency_key:
            outcome = idempotency.begin(
                key=idempotency_key,
                endpoint=FORESLA_VERIFIKATION_ENDPOINT,
                body={"thread_id": thread.id, **request},
                actor=actor,
            )
            if outcome.kind == IdempotencyOutcome.REPLAY:
                payload = dict(outcome.response_payload or {})
                payload["idempotent_replay"] = True
                return payload
            if outcome.kind == IdempotencyOutcome.MISMATCH:
                raise DraftError(
                    "idempotency_key_reuse",
                    "This proposal slot in the turn was already used for "
                    "different arguments",
                    details=outcome.original_fingerprint,
                )
            if outcome.kind == IdempotencyOutcome.IN_FLIGHT:
                raise DraftError(
                    "request_in_flight",
                    "Another attempt is already writing this proposal",
                )

        try:
            return self._propose(
                thread,
                request=request,
                date=date,
                actor=actor,
                idempotency=idempotency,
                idempotency_key=idempotency_key,
            )
        except Exception:
            if idempotency_key:
                idempotency.release(idempotency_key, FORESLA_VERIFIKATION_ENDPOINT)
            raise

    # -- internals ---------------------------------------------------------

    def _propose(
        self,
        thread: Thread,
        *,
        request: Dict[str, Any],
        date: Optional[DateType],
        actor: str,
        idempotency: IdempotencyService,
        idempotency_key: Optional[str],
    ) -> dict:
        if request["correction_of"] is not None:
            raise DraftError(
                "not_implemented",
                "Corrections through foresla_verifikation are not built yet",
                details="correction_of (SPEC-flode-verifikationer §7)",
            )
        if date is None or request["period_id"] is None:
            raise DraftError(
                "draft_requires_date_and_period",
                "A proposal without correction_of needs date and period_id",
            )

        period = self._open_period(request["period_id"])
        accounts = AccountRepository.get_all_as_dict()
        self._check_decision(thread, request["decision_id"])
        self._check_replaceable(thread, request["replaces_draft_id"])
        self._check_traceability(request)
        rows: List[Dict[str, Any]] = request["rows"]

        # Deferred import (AGENTS.md: service-to-service imports wait until
        # the method runs).
        from services.ledger import LedgerService

        with db.transaction():
            # `create_voucher` runs `validate_complete_voucher` -- the same
            # `VoucherValidator` the posting runs -- before its first write,
            # so an unbalanced or unknown-account proposal raises here with
            # the validator's own code and nothing written.
            voucher = LedgerService().create_voucher(
                series=_SERIES,
                date=date,
                period_id=period.id,
                description=request["description"],
                rows_data=rows,
                created_by="agent",
                _commit=False,
            )
            post = ThreadRepository.add_post(
                thread_id=thread.id,
                post_type="draft",
                actor=actor,
                body=draft_body(
                    draft_id=voucher.id,
                    title=request["description"],
                    series=_SERIES,
                    voucher_date=date,
                    rows=rows,
                    accounts=accounts,
                    footnote=request["footnote"],
                    period=period,
                    decision_id=request["decision_id"],
                ),
                _commit=False,
            )
            ThreadDraftRepository.create(
                voucher_id=voucher.id,
                thread_id=thread.id,
                post_id=post.id,
                view_key=thread.view_key,
                decision_id=request["decision_id"],
                intake_source_ids=_unique(request["intake_source_ids"]),
                bank_input_ids=_unique(request["bank_input_ids"]),
                bank_transaction_ids=_unique(request["bank_transaction_ids"]),
                _commit=False,
            )
            replaced = request["replaces_draft_id"]
            if replaced is not None:
                # §6.2: row first (it guards `pending` itself), then the old
                # draft. No number was ever taken, so no gap is left.
                ThreadDraftRepository.mark_superseded(
                    replaced, voucher.id, _commit=False
                )
                VoucherRepository.delete_draft(replaced, _commit=False)

            result = {
                "draft_id": voucher.id,
                "post_id": post.id,
                "status": "pending",
                "series": _SERIES,
                "date": date.isoformat(),
                "period_id": period.id,
                "description": request["description"],
                "meta": post.body["meta"],
                "consequence": post.body["consequence"],
                "decision_id": request["decision_id"],
                "replaced_draft_id": replaced,
            }
            if idempotency_key:
                idempotency.complete(
                    key=idempotency_key,
                    endpoint=FORESLA_VERIFIKATION_ENDPOINT,
                    response_status=_HTTP_201_CREATED,
                    response_payload=result,
                    entity_type="voucher",
                    entity_id=voucher.id,
                    _commit=False,
                )
        return result

    @staticmethod
    def _open_period(period_id: str) -> Period:
        period = PeriodRepository.get_period(period_id)
        if period is None:
            raise ValidationError(
                "period_not_found", "Period not found", f"period_id={period_id}"
            )
        if period.locked:
            locked_at = period.locked_at.isoformat() if period.locked_at else "okänt"
            raise DraftError(
                "period_locked",
                f"Period {period_name(period)} is locked - cannot propose "
                "vouchers in it",
                details=(
                    f"locked_by={period.locked_by or 'okänd'}, locked_at={locked_at}"
                ),
            )
        return period

    @staticmethod
    def _check_decision(thread: Thread, decision_id: Optional[str]) -> None:
        if decision_id is None:
            return
        decision = DecisionRepository.get(decision_id)
        if decision is None:
            raise DraftError(
                "decision_not_found",
                f"No decision with id {decision_id}",
                details=f"decision_id={decision_id}",
            )
        if decision.thread_id != thread.id:
            raise DraftError(
                "decision_not_in_thread",
                "The decision belongs to another thread",
                details=f"decision_id={decision_id}",
            )
        if decision.status == "superseded":
            raise DraftError(
                "decision_superseded",
                "The decision is no longer current",
                details=f"decision_id={decision_id}",
            )
        if decision.status == "open":
            raise DraftError(
                "decision_still_open",
                "A proposal follows an answer, it does not replace one",
                details=f"decision_id={decision_id}",
            )

    @staticmethod
    def _check_replaceable(thread: Thread, replaces_draft_id: Optional[str]) -> None:
        if replaces_draft_id is None:
            return
        existing = ThreadDraftRepository.get(replaces_draft_id)
        if (
            existing is None
            or existing.thread_id != thread.id
            or existing.status != "pending"
        ):
            state = existing.status if existing is not None else "missing"
            raise DraftError(
                "draft_not_replaceable",
                "replaces_draft_id is not a pending draft in this thread",
                details=f"draft_id={replaces_draft_id}, status={state}",
            )

    @staticmethod
    def _check_traceability(request: Mapping[str, Any]) -> None:
        """The checks a direct posting runs on the same ids
        (`services/voucher_posting.post_agent_voucher`), so a proposal never
        carries ids its posting would refuse. They are run again at posting
        time: a source can be taken in between."""
        from services.bank_inputs import BankInputService
        from services.intake import IntakeService

        intake = IntakeService()
        for source_id in _unique(request["intake_source_ids"]):
            intake.ensure_source_ready_for_voucher_link(source_id)
        BankInputService().ensure_transactions_available(
            _unique(request["bank_input_ids"]),
            _unique(request["bank_transaction_ids"]),
        )


def _unique(values: Sequence[str]) -> List[str]:
    return list(dict.fromkeys(values))


def _already_booked(
    source_kind: str, source_id: str, voucher_id: Optional[str]
) -> SourceAlreadyBookedError:
    booked = VoucherRepository.get(voucher_id) if voucher_id else None
    return SourceAlreadyBookedError(
        source_kind=source_kind,
        source_id=source_id,
        voucher_id=voucher_id,
        voucher_number=(
            voucher_label(booked)
            if booked is not None and booked.number is not None
            else None
        ),
    )


def _not_linkable(source_kind: str, source_id: str, exc: Any) -> DraftError:
    return SourceNotLinkableError(source_kind=source_kind, source_id=source_id, exc=exc)


def _needs_error_post(draft: ThreadDraft, code: str) -> bool:
    """§9.1: pending, and no post yet for this code."""
    if draft.status != "pending":
        return False
    return not (draft.last_error_code == code and draft.last_error_post_id)


__all__ = [
    "DRAFT_LIST_STATUSES",
    "DraftError",
    "DraftListItem",
    "DraftService",
    "FORESLA_VERIFIKATION_ENDPOINT",
    "SourceAlreadyBookedError",
    "SourceNotLinkableError",
    "draft_body",
    "draft_consequence",
    "draft_meta",
    "period_name",
    "posting_error_body",
    "receipt_body",
    "receipt_traces",
    "voucher_label",
]
