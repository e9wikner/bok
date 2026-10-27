"""Link an underlag to an already posted voucher (SPEC-flode-underlag.md §6).

`IntakeLinkService.link` is behind both `koppla_underlag` (the agent's
thirteenth tool) and `POST /api/v1/intake/{id}/link`: the same checks, in
§6.3's order, and the same basis (§6.4) whoever calls. Nothing is written
when a check fails. When they all pass, one transaction writes the link,
the attempt, the source's status and the row in `intake_link_basis`.

A link never creates, changes or removes a voucher (§15 "Aldrig"), and it
is never rewritten or removed: `voucher_intake_sources` and
`intake_link_basis` are append-only in three layers. That is why it needs a
basis, as a posting does -- the latest interpretation's exact match
(`exact_match`, D1) or an answered decision about the source (`decision`).

`IntakeLinkService.unlink` (underlag-ersatt, D10) is the way back: it
writes a row in `voucher_intake_unlinks` saying the link no longer holds,
and leaves the link row where it is. The source can then carry a new link.
An unlink needs a basis too -- a logged-in human, or an answered decision
about the underlag made after the link. Behind `koppla_bort_underlag` and
`POST /api/v1/intake/{id}/unlink`.

No SQL here (AGENTS.md's layering rule): it lives in
`repositories/intake_repo.py`, `repositories/intake_link_repo.py`,
`repositories/interpretation_repo.py`, `repositories/voucher_repo.py` and
`repositories/decision_repo.py`. Errors are `IntakeError` subclasses whose
type is the HTTP status group of §7's table, so the route maps on type,
never on the code string.
"""

import logging
from dataclasses import replace
from typing import List, Optional, Sequence

from db.database import db
from domain.intake_link import (
    IntakeLinkBasis,
    IntakeUnlink,
    LinkBasis,
    LinkResult,
    UnlinkBasis,
    UnlinkResult,
)
from domain.interpretation import Candidate, Interpretation
from domain.models import IntakeSource, ThreadPost, Voucher
from domain.types import IntakeStatus, VoucherStatus
from repositories.decision_repo import DecisionRepository
from repositories.intake_link_repo import (
    IntakeLinkRepository,
    IntakeUnlinkRepository,
    VoucherSourceReferenceRepository,
)
from repositories.intake_repo import IntakeRepository
from repositories.interpretation_repo import InterpretationRepository
from repositories.thread_repo import ThreadRepository
from repositories.voucher_repo import VoucherRepository
from services.intake import IntakeError, IntakeService

logger = logging.getLogger(__name__)

#: Longest reason an unlink takes; it is read by a human in the trace.
UNLINK_REASON_MAX = 500

#: Check 5 (D9): the posting lets only `pending`/`processing` through
#: (`IntakeService._ensure_can_record_outcome`, untouched); a link after the
#: fact also takes the source the intake pass abstained from.
LINKABLE_STATUSES = (
    IntakeStatus.PENDING,
    IntakeStatus.PROCESSING,
    IntakeStatus.FAILED,
    IntakeStatus.NEEDS_ATTENTION,
)


#: The view whose rows the link moves (`Saknar underlag` -> `Postade`).
VIEW_KEY = "bocker.verifikationer"

#: The receipt's chips (§9.3). `kompletteringsflagga` is the posting
#: receipt's own tool name (`services/draft_service.py`), so the chip that
#: set the flag and the one that removes it are the same chip.
RECEIPT_LINK_TOOL = "koppla_underlag"
RECEIPT_UNLINK_TOOL = "koppla_bort_underlag"
RECEIPT_FLAG_TOOL = "kompletteringsflagga"
RECEIPT_MISSING_TOOL = "saknar_underlag"


class IntakeLinkError(IntakeError):
    """A link that was refused. The subclass is §7's status group."""


class LinkNotFoundError(IntakeLinkError):
    """`source_not_found`, `voucher_not_found`, `decision_not_found` (404)."""


class LinkConflictError(IntakeLinkError):
    """The state does not allow the link (409): `source_deleted`,
    `intake_already_linked`, `intake_not_linkable`, `voucher_not_posted`,
    `decision_still_open`, `decision_superseded`, `decision_declined`,
    `decision_already_used`; for an unlink also `source_not_linked`,
    `source_linked_elsewhere` and `decision_predates_link`."""


class LinkRejectedError(IntakeLinkError):
    """The request lacks what a link needs (400): `interpretation_required`,
    `voucher_not_in_interpretation`, `voucher_is_opening_balance`,
    `link_requires_decision`, `decision_not_for_source`,
    `decision_not_in_thread`; for an unlink also `unlink_requires_decision`
    and `unlink_reason_required`."""


class SourceMatchesPostedVoucherError(LinkConflictError):
    """§8: the underlag belongs to an already posted voucher -- link it
    instead of posting it. `409` over `POST /agent/vouchers`."""


def _number(voucher: Voucher) -> Optional[str]:
    if voucher.number is None:
        return None
    return f"{voucher.series.value}-{voucher.number}"


def _interpretation_voucher_ids(interpretation: Interpretation) -> List[str]:
    """Check 8: the vouchers the server set against the underlag -- the
    match, the expected voucher and the candidates -- each once, in that
    order."""
    ids: List[str] = []
    if interpretation.match is not None:
        ids.append(interpretation.match.voucher_id)
    if interpretation.expected_voucher_id is not None:
        ids.append(interpretation.expected_voucher_id)
    ids.extend(c.voucher_id for c in interpretation.candidates)
    return list(dict.fromkeys(ids))


class IntakeLinkService:
    """§6: the checks, the basis, the link."""

    def link(
        self,
        source_id: str,
        voucher_id: str,
        *,
        decision_id: Optional[str] = None,
        actor: str,
        thread_id: Optional[str] = None,
        agent_run_id: Optional[str] = None,
        decisions_allowed: bool = True,
    ) -> LinkResult:
        """Link *source_id* to the posted *voucher_id*, or raise an
        `IntakeLinkError` without writing anything.

        *thread_id* is the thread turn's thread: a decision must then be in
        that thread. `None` for the intake pass and the route. The pass
        passes `decisions_allowed=False` (§6.7: a decision belongs to a
        thread, and the pass has none), so only `exact_match` applies there;
        the route keeps it, and links with a decision answered in any
        thread (§7).

        A second call for a source already linked to the same voucher after
        the fact is a replay (§6.5): the same answer with `replayed: true`,
        nothing written, whatever *decision_id* says."""
        source = self._source(source_id)

        # Checks 3 and 4: an existing link is a replay or a conflict.
        existing = IntakeRepository.get_link_by_source_id(source_id)
        if existing is not None:
            basis = IntakeLinkRepository.get_for_source(source_id)
            linked = VoucherRepository.get(existing.voucher_id)
            if existing.voucher_id == voucher_id and basis is not None:
                assert linked is not None  # a link points at a voucher
                result = self._result(basis, linked, replayed=True)
                if thread_id is not None:
                    # §6.5, §9.3: the receipt again, only if it is missing.
                    self._after_commit(
                        basis,
                        linked,
                        InterpretationRepository.latest_for_source(source_id),
                        was_missing=basis.basis == "exact_match",
                        result=result,
                        thread_id=thread_id,
                    )
                return result
            number = _number(linked) if linked is not None else None
            raise LinkConflictError(
                "intake_already_linked",
                "Intake source is already linked to a voucher",
                f"source_id={source_id}, voucher={number or existing.voucher_id}",
            )

        # Check 5.
        if source.status not in LINKABLE_STATUSES:
            raise LinkConflictError(
                "intake_not_linkable",
                "Intake source cannot be linked in its current status",
                f"source_id={source_id}, status={source.status.value}",
            )

        voucher = self._voucher(voucher_id)
        interpretation = self._interpretation(source_id, voucher)
        if decision_id is not None and decisions_allowed:
            self._decision(decision_id, source_id, thread_id)
            # A decision bases one link. Without this, the decision behind
            # a link that was undone could put it back without anyone
            # having said so again.
            if IntakeLinkRepository.get_by_decision(decision_id) is not None:
                raise LinkConflictError(
                    "decision_already_used",
                    "The decision is already the basis of a link",
                    f"decision_id={decision_id}",
                )
            basis_kind: LinkBasis = "decision"
        else:
            basis_kind = self._exact_match(source_id, voucher, interpretation)

        number = _number(voucher)
        basis = IntakeLinkBasis(
            intake_source_id=source_id,
            voucher_id=voucher_id,
            basis=basis_kind,
            interpretation_id=interpretation.id,
            decision_id=decision_id if basis_kind == "decision" else None,
            actor=actor,
            agent_run_id=agent_run_id,
            thread_id=thread_id,
        )
        with db.transaction():
            _attempt, link = IntakeService().persist_voucher_link(
                source_id,
                voucher_id,
                actor=actor,
                summary=f"Underlag kopplat till {number} ({basis_kind})",
                link_reason=self._link_reason(basis),
            )
            basis = replace(basis, link_id=link.id)
            IntakeLinkRepository.insert(basis, _commit=False)

        result = self._result(basis, voucher, replayed=False)
        self._after_commit(
            basis,
            voucher,
            interpretation,
            was_missing=bool(voucher.missing_attachment),
            result=result,
            thread_id=thread_id,
        )
        return result

    # -- the way back: unlink (underlag-ersatt, D10) --------------------------

    def unlink(
        self,
        source_id: str,
        voucher_id: str,
        *,
        reason: str,
        actor: str,
        human: bool = False,
        decision_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        agent_run_id: Optional[str] = None,
    ) -> UnlinkResult:
        """Undo *source_id*'s current link to *voucher_id*, or raise an
        `IntakeLinkError` without writing anything.

        The basis is *human* (a logged-in user through the route) or an
        answered decision about the source (*decision_id*): answered after
        the link was made, not the link's own basis, not answered with its
        way out, used for no other unlink, and in *thread_id* when given.

        One transaction writes the `voucher_intake_unlinks` row, an attempt
        saying so, and sets the source to `needs_attention`: it has no voucher now, it is not
        picked up by the intake pass, and a link after the fact takes it
        (D9). No voucher is created, changed or removed. A second call for
        a link already undone is a replay: the same answer with
        `replayed: true`, nothing written."""
        source = IntakeRepository.get_source(source_id)
        if source is None:
            raise LinkNotFoundError(
                "source_not_found", "Intake source not found", f"source_id={source_id}"
            )
        voucher = VoucherRepository.get(voucher_id)
        if voucher is None:
            raise LinkNotFoundError(
                "voucher_not_found", "Voucher not found", f"voucher_id={voucher_id}"
            )

        current = IntakeRepository.get_link_by_source_id(source_id)
        if current is None or current.voucher_id != voucher_id:
            latest = IntakeRepository.latest_link(source_id, voucher_id)
            if latest is not None and not latest.is_current:
                done = IntakeUnlinkRepository.get_for_link(latest.id)
                assert done is not None  # not current means it was undone
                return self._unlink_result(done, voucher, replayed=True)
            if current is not None:
                elsewhere = VoucherRepository.get(current.voucher_id)
                raise LinkConflictError(
                    "source_linked_elsewhere",
                    "The underlag is linked to another voucher",
                    f"source_id={source_id}, voucher="
                    f"{(_number(elsewhere) if elsewhere else None) or current.voucher_id}",
                )
            raise LinkConflictError(
                "source_not_linked",
                "The underlag is not linked to the voucher",
                f"source_id={source_id}, voucher={_number(voucher) or voucher_id}",
            )

        reason = (reason or "").strip()
        if not reason or len(reason) > UNLINK_REASON_MAX:
            raise LinkRejectedError(
                "unlink_reason_required",
                f"Say why the link is undone, in at most {UNLINK_REASON_MAX} "
                "characters",
                f"length={len(reason)}",
            )

        basis_kind: UnlinkBasis
        if human:
            basis_kind = "human"
            decision_id = None
        else:
            if decision_id is None:
                raise LinkRejectedError(
                    "unlink_requires_decision",
                    "Undoing a link needs an answered decision about the "
                    "underlag, or a logged-in user",
                    f"source_id={source_id}",
                )
            self._decision(decision_id, source_id, thread_id)
            self._unlink_decision(decision_id, current)
            basis_kind = "decision"

        unlink = IntakeUnlink(
            link_id=current.id,
            intake_source_id=source_id,
            voucher_id=voucher_id,
            basis=basis_kind,
            reason=reason,
            actor=actor,
            decision_id=decision_id,
            agent_run_id=agent_run_id,
            thread_id=thread_id,
        )
        with db.transaction():
            IntakeUnlinkRepository.insert(unlink, _commit=False)
            # The source's latest attempt is what the decision queue shows
            # for a source that needs attention (`_intake_to_view`); without
            # this it would still say the underlag was linked.
            IntakeRepository.record_attempt(
                intake_source_id=source_id,
                status="failed",
                summary=(
                    f"Underlaget kopplades bort från {_number(voucher) or voucher_id}: "
                    f"{reason}"
                ),
                voucher_id=voucher_id,
                actor=actor,
                _commit=False,
            )
            IntakeRepository.update_status(
                source_id,
                IntakeStatus.NEEDS_ATTENTION.value,
                actor=actor,
                _commit=False,
            )

        result = self._unlink_result(unlink, voucher, replayed=False)
        self._after_unlink(unlink, voucher, result, thread_id=thread_id)
        return result

    @staticmethod
    def _unlink_decision(decision_id: str, link) -> None:
        """What `_decision` does not know about an unlink: the decision was
        answered after the link, is not the link's own basis, and has not
        undone another link already."""
        basis = IntakeLinkRepository.get_for_link(link.id)
        if (
            basis is not None and basis.decision_id == decision_id
        ) or IntakeUnlinkRepository.get_by_decision(decision_id) is not None:
            raise LinkConflictError(
                "decision_already_used",
                "The decision is already the basis of a link or an unlink",
                f"decision_id={decision_id}",
            )
        decision = DecisionRepository.get(decision_id)
        assert decision is not None  # `_decision` found it
        if decision.answered_at is None or decision.answered_at < link.linked_at:
            raise LinkConflictError(
                "decision_predates_link",
                "The decision was answered before the link was made",
                f"decision_id={decision_id}",
            )

    @staticmethod
    def _unlink_result(
        unlink: IntakeUnlink, voucher: Voucher, *, replayed: bool
    ) -> UnlinkResult:
        """The answer, with the references that went through the link (D2)
        and the counter read after the commit."""
        references = VoucherSourceReferenceRepository.list_through(
            unlink.intake_source_id, unlink.voucher_id
        )
        numbers = VoucherRepository.numbers_for([r.voucher_id for r in references])
        orphaned = [
            f"{numbers[r.voucher_id][0]}-{numbers[r.voucher_id][1]}"
            for r in references
            if r.voucher_id in numbers and numbers[r.voucher_id][1] is not None
        ]
        return UnlinkResult(
            source_id=unlink.intake_source_id,
            voucher_id=unlink.voucher_id,
            voucher_number=_number(voucher),
            link_id=unlink.link_id,
            basis=unlink.basis,
            decision_id=unlink.decision_id,
            reason=unlink.reason,
            replayed=replayed,
            orphaned_references=orphaned,
            missing_attachments=VoucherRepository.count_missing_attachments(),
        )

    def _after_unlink(
        self,
        unlink: IntakeUnlink,
        voucher: Voucher,
        result: UnlinkResult,
        *,
        thread_id: Optional[str],
    ) -> None:
        """In a thread: a `receipt` post, then `message.completed`; and
        `view.changed` with `kind: "source_unlinked"` on the thread and on
        `bocker.verifikationer`'s. After the commit and never fatal, as
        for a link (§9.3)."""
        try:
            post = None
            if thread_id is not None:
                post = ThreadRepository.add_post(
                    thread_id=thread_id,
                    post_type="receipt",
                    actor=self._unlink_actor(unlink),
                    body=self._unlink_body(unlink, voucher, result),
                    traces=[
                        {
                            "tool": RECEIPT_UNLINK_TOOL,
                            "label": "underlag frånkopplat",
                            "detail": _number(voucher),
                            "voucher_id": voucher.id,
                        },
                        {
                            "tool": RECEIPT_MISSING_TOOL,
                            "label": f"{result.missing_attachments} saknar underlag",
                        },
                    ],
                )
            self._publish(
                unlink.intake_source_id,
                voucher,
                post,
                thread_id,
                kind="source_unlinked",
            )
        except Exception:
            logger.exception(
                "Receipt for the unlink of source %s was not written",
                unlink.intake_source_id,
            )

    @staticmethod
    def _unlink_actor(unlink: IntakeUnlink) -> str:
        if unlink.basis == "decision" and unlink.decision_id is not None:
            decision = DecisionRepository.get(unlink.decision_id)
            if decision is not None and decision.answered_by:
                return decision.answered_by
        return unlink.actor

    @staticmethod
    def _unlink_body(
        unlink: IntakeUnlink, voucher: Voucher, result: UnlinkResult
    ) -> dict:
        """The receipt: the comparison the link was made on, when there is
        one, and the reason. A voucher that referred to the underlag through
        the link is named, since it lacks underlag again."""
        from services.interpretation import COMPARISON_DOCUMENT_LABEL, comparison_rows

        number = _number(voucher) or voucher.id
        rows: list = []
        basis = IntakeLinkRepository.get_for_link(unlink.link_id)
        interpretation = (
            InterpretationRepository.get(basis.interpretation_id)
            if basis is not None
            else InterpretationRepository.latest_for_source(unlink.intake_source_id)
        )
        if interpretation is not None:
            parts: List[Optional[Candidate]] = [
                interpretation.match,
                interpretation.expected,
                *interpretation.candidates,
            ]
            part = next(
                (p for p in parts if p is not None and p.voucher_id == voucher.id),
                None,
            )
            if part is not None:
                rows = comparison_rows(part)
        note = f"Skäl: {unlink.reason}"
        if result.orphaned_references:
            note += (
                f" {', '.join(result.orphaned_references)} bokfördes på underlaget "
                f"via {number}; ta ställning till om den ska rättas."
            )
        return {
            "title": f"Underlag frånkopplat från {number}",
            "labels": [COMPARISON_DOCUMENT_LABEL, number],
            "rows": rows,
            "voucher_id": voucher.id,
            "source_id": unlink.intake_source_id,
            "note": note,
        }

    # -- the stop in the posting (§8, D5) ----------------------------------

    @staticmethod
    def ensure_not_matching_posted(source_ids: Sequence[str]) -> None:
        """Refuse to post (or propose) a new voucher for an underlag whose
        latest interpretation is an exact match that is still open now.

        Called by `post_agent_voucher` (`posta_verifikation`,
        `POST /agent/vouchers`) and `DraftService._check_traceability`
        (`foresla_verifikation`), before anything is written; both callers
        release an idempotency key when the call raises. Not by the posting
        of a thread proposal, whose linking refuses a source that has been
        linked meanwhile (§8).

        `exact_no_date` and `amount_diff` are not stopped here -- the
        instruction and a decision stop them. Without an interpretation, or
        with a match that is no longer open, nothing is stopped: the stop
        is what the server knows, not what the agent should have done."""
        for source_id in dict.fromkeys(source_ids):
            interpretation = InterpretationRepository.latest_for_source(source_id)
            match = interpretation.match if interpretation is not None else None
            if match is None or match.kind != "exact":
                continue
            if not VoucherRepository.match_still_open(match.voucher_id, source_id):
                continue
            # Unlinked from that voucher: someone said it does not belong
            # there, so the match is no reason to stop a new voucher.
            if IntakeRepository.was_unlinked_from(source_id, match.voucher_id):
                continue
            raise SourceMatchesPostedVoucherError(
                "source_matches_posted_voucher",
                "The underlag belongs to an already posted voucher",
                f"source_id={source_id}, voucher={match.voucher_number}, "
                f"diff_ore={match.diff_ore} -- underlaget hör till en redan "
                "postad verifikation. Koppla det med koppla_underlag i stället.",
            )

    # -- the checks, in §6.3's order ---------------------------------------

    @staticmethod
    def _source(source_id: str) -> IntakeSource:
        """Checks 1 and 2."""
        source = IntakeRepository.get_source(source_id)
        if source is None:
            raise LinkNotFoundError(
                "source_not_found", "Intake source not found", f"source_id={source_id}"
            )
        if source.status == IntakeStatus.DELETED:
            raise LinkConflictError(
                "source_deleted", "Intake source is deleted", f"source_id={source_id}"
            )
        return source

    @staticmethod
    def _voucher(voucher_id: str) -> Voucher:
        """Check 6."""
        voucher = VoucherRepository.get(voucher_id)
        if voucher is None:
            raise LinkNotFoundError(
                "voucher_not_found", "Voucher not found", f"voucher_id={voucher_id}"
            )
        if voucher.status != VoucherStatus.POSTED:
            raise LinkConflictError(
                "voucher_not_posted",
                "Only posted vouchers can be linked to intake sources",
                f"voucher_id={voucher_id}, status={voucher.status.value}",
            )
        if voucher.series.value == "IB":
            raise LinkRejectedError(
                "voucher_is_opening_balance",
                "An opening balance voucher has no underlag to link",
                f"voucher_id={voucher_id}",
            )
        return voucher

    @staticmethod
    def _interpretation(source_id: str, voucher: Voucher) -> Interpretation:
        """Checks 7 and 8: the latest interpretation, and the voucher in it."""
        interpretation = InterpretationRepository.latest_for_source(source_id)
        if interpretation is None:
            raise LinkRejectedError(
                "interpretation_required",
                "tolka underlaget med tolka_underlag först",
                f"source_id={source_id}",
            )
        ids = _interpretation_voucher_ids(interpretation)
        if voucher.id not in ids:
            numbers = VoucherRepository.numbers_for(ids)
            named = ", ".join(
                f"{numbers[i][0]}-{numbers[i][1]}" for i in ids if i in numbers
            )
            raise LinkRejectedError(
                "voucher_not_in_interpretation",
                "The voucher was not set against the underlag in its "
                "latest interpretation",
                f"voucher={_number(voucher)}, interpretation={interpretation.id}, "
                f"vouchers=[{named}]",
            )
        return interpretation

    @staticmethod
    def _exact_match(
        source_id: str, voucher: Voucher, interpretation: Interpretation
    ) -> LinkBasis:
        """Check 9 without a decision (§6.4): the latest interpretation's
        match is `exact`, it is this voucher, and it is still open now.
        `exact_no_date` is not enough (`SPEC-underlagstolkning.md` §12.6 d).
        Otherwise `link_requires_decision`, with the match kind, so the
        agent knows to lay out a decision."""
        match = interpretation.match
        if IntakeRepository.was_unlinked_from(source_id, voucher.id):
            # underlag-ersatt: the link between the two was undone. An
            # exact match does not put it back; a new decision does.
            raise LinkRejectedError(
                "link_requires_decision",
                "The underlag was unlinked from this voucher; linking it "
                "again needs a decision",
                f"source_id={source_id}, voucher={_number(voucher)}, "
                "previously_unlinked=true",
            )
        if (
            match is not None
            and match.kind == "exact"
            and match.voucher_id == voucher.id
            and VoucherRepository.match_still_open(voucher.id, source_id)
        ):
            return "exact_match"
        raise LinkRejectedError(
            "link_requires_decision",
            "Only an exact, still open match links without a decision; "
            "lay out a decision about the underlag",
            f"source_id={source_id}, voucher={_number(voucher)}, "
            f"match_kind={match.kind if match is not None else 'none'}",
        )

    @staticmethod
    def _decision(decision_id: str, source_id: str, thread_id: Optional[str]) -> None:
        """Check 9 with a decision (§6.4's table, in its order). The last
        row is the only way the server can read a *no* out of the answer:
        an option with `is_exit`. Free text is let through -- every
        decision can be answered in free text (`README.md`) -- and the agent
        carries reading it right (§13.4)."""
        decision = DecisionRepository.get(decision_id)
        if decision is None:
            raise LinkNotFoundError(
                "decision_not_found",
                "Decision not found",
                f"decision_id={decision_id}",
            )
        if decision.status != "answered":
            code = (
                "decision_superseded"
                if decision.status == "superseded"
                else "decision_still_open"
            )
            raise LinkConflictError(
                code,
                "Only an answered decision is a basis for a link",
                f"decision_id={decision_id}, status={decision.status}",
            )
        if decision.source_kind != "intake_source" or decision.source_id != source_id:
            raise LinkRejectedError(
                "decision_not_for_source",
                "The decision is not about this underlag",
                f"decision_id={decision_id}, source_kind={decision.source_kind}, "
                f"source_id={decision.source_id}",
            )
        if thread_id is not None and decision.thread_id != thread_id:
            raise LinkRejectedError(
                "decision_not_in_thread",
                "The decision belongs to another thread",
                f"decision_id={decision_id}",
            )
        if decision.answer_option_id is not None:
            option = DecisionRepository.get_option(decision.answer_option_id)
            if option is not None and option.is_exit:
                raise LinkConflictError(
                    "decision_declined",
                    "The decision was answered with its way out",
                    f"decision_id={decision_id}, option={option.title}",
                )

    # -- after the commit: the receipt and view.changed (§9.3) --------------

    def _after_commit(
        self,
        basis: IntakeLinkBasis,
        voucher: Voucher,
        interpretation: Optional[Interpretation],
        *,
        was_missing: bool,
        result: LinkResult,
        thread_id: Optional[str],
    ) -> None:
        """In a thread: the `receipt` post, unless the thread has one for
        this source already, then `message.completed` and `view.changed`.
        Without a thread: only `view.changed`, and only for a new link.

        After the commit, and never fatal: the link is the books' and the
        receipt the thread's, and an error in the thread layer must not
        undo a link or change its answer (§9.3, testfall 30). A replay
        finds a missing receipt and writes it."""
        try:
            post = None
            if thread_id is not None:
                if ThreadRepository.receipt_for_source(
                    thread_id, basis.intake_source_id
                ):
                    return
                post = ThreadRepository.add_post(
                    thread_id=thread_id,
                    post_type="receipt",
                    actor=self._receipt_actor(basis),
                    body=self._receipt_body(basis, voucher, interpretation),
                    traces=self._receipt_traces(
                        voucher, was_missing, result.missing_attachments
                    ),
                )
            elif result.replayed:
                return
            self._publish(basis.intake_source_id, voucher, post, thread_id)
        except Exception:
            logger.exception(
                "Receipt for the link of source %s was not written",
                basis.intake_source_id,
            )

    @staticmethod
    def _receipt_actor(basis: IntakeLinkBasis) -> str:
        """§9.3: whose choice linked it -- the agent on an exact match,
        the human who answered the decision on a decision."""
        if basis.basis == "decision" and basis.decision_id is not None:
            decision = DecisionRepository.get(basis.decision_id)
            if decision is not None and decision.answered_by:
                return decision.answered_by
        return "agent"

    @staticmethod
    def _receipt_body(
        basis: IntakeLinkBasis,
        voucher: Voucher,
        interpretation: Optional[Interpretation],
    ) -> dict:
        """§9.3: the comparison's rows, out of the interpretation the link
        was based on -- the part about this voucher: the match, the
        expected, or the candidate. On a replay the latest interpretation
        stands in, which is the same one unless the source was interpreted
        again after the link."""
        from services.interpretation import COMPARISON_DOCUMENT_LABEL, comparison_rows

        number = _number(voucher) or voucher.id
        rows: list = []
        if interpretation is not None:
            parts: List[Optional[Candidate]] = [
                interpretation.match,
                interpretation.expected,
                *interpretation.candidates,
            ]
            part = next(
                (p for p in parts if p is not None and p.voucher_id == voucher.id),
                None,
            )
            if part is not None:
                rows = comparison_rows(part)
        return {
            "title": f"Underlag kopplat till {number}",
            "labels": [COMPARISON_DOCUMENT_LABEL, number],
            "rows": rows,
            "voucher_id": voucher.id,
            "source_id": basis.intake_source_id,
        }

    @staticmethod
    def _receipt_traces(voucher: Voucher, was_missing: bool, missing: int) -> list:
        """§9.3's chips: the link, the flag when the voucher lacked
        underlag before it, and the counter after the commit."""
        number = _number(voucher)
        traces: list = [
            {
                "tool": RECEIPT_LINK_TOOL,
                "label": "underlag kopplat",
                "detail": number,
                "voucher_id": voucher.id,
            }
        ]
        if was_missing:
            traces.append(
                {"tool": RECEIPT_FLAG_TOOL, "label": "kompletteringsflagga borttagen"}
            )
        traces.append(
            {"tool": RECEIPT_MISSING_TOOL, "label": f"{missing} saknar underlag"}
        )
        return traces

    @staticmethod
    def _publish(
        source_id: str,
        voucher: Voucher,
        post: Optional[ThreadPost],
        thread_id: Optional[str],
        *,
        kind: str = "source_linked",
    ) -> None:
        """`message.completed` for the receipt, and `view.changed` with
        `kind: "source_linked"` -- the shape `voucher_posted` has -- on the
        linking thread and on `bocker.verifikationer`'s thread for the
        voucher's fiscal year, where the `saknar` row lives. The broker is
        per thread (plan, avvikelse 5): no such thread, no open stream to
        reach, and nothing is sent."""
        from services.thread_stream import (
            EVENT_MESSAGE_COMPLETED,
            EVENT_VIEW_CHANGED,
            get_broker,
            post_event_payload,
        )

        broker = get_broker()
        targets = []
        if thread_id is not None:
            thread = ThreadRepository.get(thread_id)
            if thread is not None:
                targets.append(thread)
                if post is not None:
                    broker.publish(
                        thread.id, EVENT_MESSAGE_COMPLETED, post_event_payload(post)
                    )
        if voucher.fiscal_year_id and not any(t.view_key == VIEW_KEY for t in targets):
            view_thread = ThreadRepository.find(VIEW_KEY, voucher.fiscal_year_id)
            if view_thread is not None:
                targets.append(view_thread)
        for thread in targets:
            broker.publish(
                thread.id,
                EVENT_VIEW_CHANGED,
                {
                    "view_key": thread.view_key,
                    "changed": {
                        "voucher_id": voucher.id,
                        "source_id": source_id,
                        "kind": kind,
                    },
                },
            )

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _link_reason(basis: IntakeLinkBasis) -> str:
        """§5: `link_reason` for whoever reads `voucher_intake_sources`
        directly; the basis itself is the row in `intake_link_basis`."""
        if basis.basis == "decision":
            return (
                f"decision={basis.decision_id} "
                f"interpretation={basis.interpretation_id}"
            )
        return f"exact_match interpretation={basis.interpretation_id}"

    @staticmethod
    def _result(
        basis: IntakeLinkBasis, voucher: Voucher, *, replayed: bool
    ) -> LinkResult:
        """§6.6, with the counter read after the commit."""
        return LinkResult(
            source_id=basis.intake_source_id,
            voucher_id=basis.voucher_id,
            voucher_number=_number(voucher),
            basis=basis.basis,
            interpretation_id=basis.interpretation_id,
            decision_id=basis.decision_id,
            replayed=replayed,
            missing_attachments=VoucherRepository.count_missing_attachments(),
        )
