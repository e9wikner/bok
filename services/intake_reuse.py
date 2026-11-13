"""`foresla_delat_underlag`: one underlag, one more voucher (migration 044).

Bokföringslagen wants an underlag behind every voucher; it does not want each
underlag behind only one. A loan agreement supports every amortisation, an
annual invoice every month it is accrued over. Bok still never links an
underlag that already supports a voucher on its own -- that is how one
receipt gets booked twice -- so the agent asks with a decision card:

- **Koppla till A-14** -- this link, once;
- **Koppla, och godkänn för kommande verifikationer** -- this link, and a
  standing approval for the voucher's fiscal year: within that year the agent
  may post or link the underlag to further vouchers without asking again. An
  approval never reaches past the fiscal year; the next year is asked anew;
- **Inte nu** -- nothing.

Only a logged-in human's press answers the card (`requires_human`, the route
refuses the API key). The press links through `IntakeLinkService.link` with
the card's decision as basis, and writes the approval when that option was
chosen. A human can end an approval early (`revoke`).

Layering (AGENTS.md): no SQL here, no HTTP.
"""

import logging
from typing import Any, Dict, List, Optional

from db.database import db
from domain.intake_link import IntakeLinkProposal, ReuseApproval
from domain.models import Decision, Thread, ThreadPost, Voucher
from domain.types import IntakeStatus, VoucherStatus
from domain.validation import ValidationError
from repositories.decision_repo import DecisionRepository
from repositories.intake_repo import IntakeRepository
from repositories.intake_reuse_repo import (
    IntakeLinkProposalRepository,
    ReuseApprovalRepository,
)
from repositories.interpretation_repo import InterpretationRepository
from repositories.period_repo import PeriodRepository
from repositories.thread_repo import ThreadRepository
from repositories.voucher_repo import VoucherRepository
from services.intake import IntakeConflictError, IntakeError
from services.thread_stream import publish_posts

logger = logging.getLogger(__name__)

DECLINE_OPTION_TITLE = "Inte nu"

#: Longest reason a revocation takes; read by a human in the trace.
REVOKE_REASON_MAX = 500


def _number(voucher: Voucher) -> str:
    if voucher.number is None:
        return voucher.id
    return f"{voucher.series.value}-{voucher.number}"


class IntakeReuseService:
    # -- the tool ----------------------------------------------------------

    def propose(
        self,
        thread: Optional[Thread],
        *,
        source_id: str,
        voucher_id: str,
        reason: str,
        actor: str,
    ) -> Dict[str, Any]:
        """Raise the card in *thread*, or raise without writing anything.

        The underlag must already support a voucher (otherwise it is an
        ordinary link: `koppla_underlag`), be interpreted (the link names an
        interpretation), and not be linked to *voucher_id* already. The
        voucher must be posted, in a fiscal year. When a standing approval
        covers the voucher's year already, no card is needed and none is
        raised (`reuse_already_approved`)."""
        if thread is None:
            raise ValidationError(
                "shared_source_requires_thread",
                "foresla_delat_underlag can only be called from a thread turn",
                "A human answers the card, so it goes in the conversation",
            )
        reason = (reason or "").strip()
        if not reason:
            raise ValidationError(
                "reason_required",
                "Say why the underlag supports this voucher too",
                f"source_id={source_id}",
            )
        source = IntakeRepository.get_source(source_id)
        if source is None or source.status == IntakeStatus.DELETED:
            raise ValidationError(
                "source_not_found", "Intake source not found", f"source_id={source_id}"
            )
        voucher = VoucherRepository.get(voucher_id)
        if voucher is None or voucher.status != VoucherStatus.POSTED:
            raise ValidationError(
                "voucher_not_posted",
                "Only a posted voucher can be given an underlag",
                f"voucher_id={voucher_id}",
            )
        if not voucher.fiscal_year_id or voucher.series.value == "IB":
            raise ValidationError(
                "voucher_not_linkable",
                "The voucher takes no underlag",
                f"voucher_id={voucher_id}",
            )
        links = IntakeRepository.list_links_for_source(source_id)
        if not links:
            raise ValidationError(
                "source_not_shared",
                "The underlag supports no voucher yet; link it with " "koppla_underlag",
                f"source_id={source_id}",
            )
        if any(link.voucher_id == voucher_id for link in links):
            raise ValidationError(
                "intake_already_linked",
                "The underlag already supports this voucher",
                f"source_id={source_id}, voucher={_number(voucher)}",
            )
        if InterpretationRepository.latest_for_source(source_id) is None:
            raise ValidationError(
                "interpretation_required",
                "tolka underlaget med tolka_underlag först",
                f"source_id={source_id}",
            )
        fiscal_year = PeriodRepository.get_fiscal_year(voucher.fiscal_year_id)
        assert fiscal_year is not None  # a posted voucher's year exists
        approval = ReuseApprovalRepository.active_for(source_id, fiscal_year.id)
        if approval is not None:
            raise ValidationError(
                "reuse_already_approved",
                "The underlag is approved for further vouchers in this fiscal "
                "year; link it with koppla_underlag",
                f"source_id={source_id}, approval_id={approval.id}",
            )

        numbers = VoucherRepository.numbers_for([link.voucher_id for link in links])
        supported = ", ".join(
            f"{numbers[lk.voucher_id][0]}-{numbers[lk.voucher_id][1]}"
            for lk in links
            if lk.voucher_id in numbers
        )
        number = _number(voucher)
        end = fiscal_year.end_date.isoformat()

        from services.decision_service import DecisionService

        decision = DecisionService().create(
            thread,
            title=f"Ska {source.original_filename} styrka {number} också?",
            reason=(
                f"Underlaget styrker redan {supported}. {reason} Samma underlag "
                "kan styrka flera verifikationer, men ett kvitto får inte "
                "bokföras två gånger -- därför frågar jag."
            ),
            consequence=(
                f"Underlaget kopplas till {number}. Inget bokförs om och inget "
                "ändras i verifikationerna."
            ),
            kind="approval",
            source={
                "kind": "intake_source",
                "id": source_id,
                "date": voucher.date,
            },
            options=[
                {
                    "title": f"Koppla till {number}",
                    "rationale": "Bara den här gången. Nästa gång frågar jag igen.",
                    "recommended": True,
                },
                {
                    "title": "Koppla, och godkänn för kommande verifikationer",
                    "rationale": (
                        f"Underlaget får styrka fler verifikationer till och med "
                        f"{end}, räkenskapsårets slut, utan att jag frågar. "
                        "Godkännandet kan återkallas."
                    ),
                },
                {
                    "title": DECLINE_OPTION_TITLE,
                    "rationale": "Underlaget kopplas inte.",
                    "is_exit": True,
                },
            ],
            actor=actor,
        )
        try:
            proposal = IntakeLinkProposalRepository.create(
                decision_id=decision.id,
                thread_id=thread.id,
                intake_source_id=source_id,
                voucher_id=voucher_id,
                fiscal_year_id=fiscal_year.id,
                once_option_id=decision.options[0].id,
                standing_option_id=decision.options[1].id,
                created_by=actor,
            )
        except Exception:
            # The card and its row are two transactions (DecisionService owns
            # its own): a card without its row would link nothing.
            DecisionService().supersede(decision.id)
            raise
        return self._result(proposal)

    # -- the press ---------------------------------------------------------

    @staticmethod
    def requires_human(decision_id: str) -> bool:
        """Whether answering *decision_id* links a shared underlag: a
        `foresla_delat_underlag` card. The route refuses the API key."""
        return IntakeLinkProposalRepository.get_by_decision(decision_id) is not None

    def on_decision_answered(
        self, decision: Decision, *, actor: str
    ) -> Optional[ThreadPost]:
        """What the answer to a shared-underlag card does; `None` for any
        other decision. Returns an error post when the link was refused."""
        proposal = IntakeLinkProposalRepository.get_by_decision(decision.id)
        if proposal is None or proposal.status != "pending":
            return None
        if decision.answer_option_id is None:
            return None  # free text: the agent's turn takes it from here
        if decision.answer_option_id not in (
            proposal.once_option_id,
            proposal.standing_option_id,
        ):
            IntakeLinkProposalRepository.resolve(proposal.id, "declined", actor=actor)
            return None

        from services.intake_link import IntakeLinkService

        try:
            IntakeLinkService().link(
                proposal.intake_source_id,
                proposal.voucher_id,
                decision_id=decision.id,
                actor=actor,
                thread_id=proposal.thread_id,
            )
        except IntakeError as exc:
            IntakeLinkProposalRepository.resolve(proposal.id, "failed", actor=actor)
            post = ThreadRepository.add_post(
                thread_id=proposal.thread_id,
                post_type="error",
                actor=actor,
                body={
                    "cause": f"Underlaget kunde inte kopplas: {exc.message}.",
                    "consequence": "Inget kopplades och inget godkändes.",
                    "retry_draft_id": None,
                },
            )
            publish_posts([post])
            return post

        with db.transaction():
            IntakeLinkProposalRepository.resolve(
                proposal.id, "linked", actor=actor, _commit=False
            )
            if decision.answer_option_id == proposal.standing_option_id:
                if (
                    ReuseApprovalRepository.active_for(
                        proposal.intake_source_id, proposal.fiscal_year_id
                    )
                    is None
                ):
                    ReuseApprovalRepository.create(
                        intake_source_id=proposal.intake_source_id,
                        fiscal_year_id=proposal.fiscal_year_id,
                        decision_id=decision.id,
                        approved_by=actor,
                        _commit=False,
                    )
        return None

    # -- the standing approval ---------------------------------------------

    @staticmethod
    def approval_for(
        source_id: str, fiscal_year_id: Optional[str]
    ) -> Optional[ReuseApproval]:
        """The source's unrevoked approval for the fiscal year, or `None`."""
        if not fiscal_year_id:
            return None
        return ReuseApprovalRepository.active_for(source_id, fiscal_year_id)

    @staticmethod
    def approvals(source_id: str) -> List[ReuseApproval]:
        return ReuseApprovalRepository.list_for_source(source_id)

    def revoke(
        self, source_id: str, approval_id: str, *, reason: str, actor: str
    ) -> ReuseApproval:
        """End *approval_id* now. Links already made stay: they are
        räkenskapsinformation, and a wrong one is undone with an unlink. A
        second revoke is a replay."""
        approval = ReuseApprovalRepository.get(approval_id)
        if approval is None or approval.intake_source_id != source_id:
            raise IntakeError(
                "approval_not_found",
                "No such approval for this underlag",
                f"source_id={source_id}, approval_id={approval_id}",
            )
        if not approval.is_active:
            return approval
        reason = (reason or "").strip()
        if not reason or len(reason) > REVOKE_REASON_MAX:
            raise IntakeConflictError(
                "revoke_reason_required",
                f"Say why the approval ends, in at most {REVOKE_REASON_MAX} "
                "characters",
                f"length={len(reason)}",
            )
        ReuseApprovalRepository.revoke(approval_id, revoked_by=actor, reason=reason)
        revoked = ReuseApprovalRepository.get(approval_id)
        assert revoked is not None
        return revoked

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _result(proposal: IntakeLinkProposal) -> Dict[str, Any]:
        decision = DecisionRepository.get(proposal.decision_id)
        return {
            "proposal_id": proposal.id,
            "decision_id": proposal.decision_id,
            "source_id": proposal.intake_source_id,
            "voucher_id": proposal.voucher_id,
            "fiscal_year_id": proposal.fiscal_year_id,
            "status": proposal.status,
            "decision_status": decision.status if decision is not None else None,
        }
