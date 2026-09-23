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
- Link traceability. `intake_source_ids` and the bank ids are checked here
  with the same checks a direct posting runs, then kept on the row
  (migration 029). A link marks the source processed and the transaction
  booked, which is only true once the voucher is posted (F8).
- Correct. `correction_of` is refused with `not_implemented` until F11
  builds §7's branch.

Layering (AGENTS.md): no SQL here -- every write goes through a repository or
`LedgerService` -- and no HTTP. Errors are `ValidationError`s with the
`{code, message, details}` shape the session already renders for the model.
"""

from datetime import date as DateType
from typing import Any, Dict, List, Mapping, Optional, Sequence

from db.database import db
from domain.models import Account, Period, Thread
from domain.validation import ValidationError
from repositories.account_repo import AccountRepository
from repositories.decision_repo import DecisionRepository
from repositories.period_repo import PeriodRepository
from repositories.thread_draft_repo import ThreadDraftRepository
from repositories.thread_repo import ThreadRepository
from repositories.voucher_repo import VoucherRepository
from services.idempotency import IdempotencyOutcome, IdempotencyService

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


class DraftService:
    """Orchestrates thread drafts: `propose` (F6). Posting hooks follow in
    F8, the correction branch in F11."""

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


__all__ = [
    "DraftError",
    "DraftService",
    "FORESLA_VERIFIKATION_ENDPOINT",
    "draft_body",
    "draft_consequence",
    "draft_meta",
    "period_name",
]
