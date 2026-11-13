"""The decision cards whose answer does something before the agent's turn.

Each card service keeps its proposal in its own table, keyed by the
decision id, and recognises its own card by looking it up there: a
decision belongs to at most one of them. `POST /decisions/{id}/answer`
asks this module twice -- before the answer is written, whether the API
key may answer at all (`human_only_reason`), and after it has committed,
what the press does (`on_decision_answered`) -- instead of asking every
service in turn.

Adding a card that acts on its answer means adding it to `_CARDS`; one
whose press books, links or approves something also names why only a
logged-in human may press it.
"""

from typing import Any, Callable, NamedTuple, Optional

from domain.models import Decision


class _Card(NamedTuple):
    #: The service class, imported late (service-to-service imports are
    #: deferred to avoid cycles; see AGENTS.md).
    service: Callable[[], Any]
    #: Why the API key may not answer this card, or None if it may.
    human_only: Optional[str] = None


def _fiscal_year():
    from services.fiscal_year_proposal import FiscalYearProposalService

    return FiscalYearProposalService


def _company_info():
    from services.company_info_proposal import CompanyInfoProposalService

    return CompanyInfoProposalService


def _payroll():
    from services.payroll_proposal import PayrollProposalService

    return PayrollProposalService


def _intake_reuse():
    from services.intake_reuse import IntakeReuseService

    return IntakeReuseService


def _reimbursement():
    from services.reimbursement_check import ReimbursementCheckService

    return ReimbursementCheckService


def _agreement():
    from services.agreement_booking import AgreementBookingService

    return AgreementBookingService


_CARDS = (
    # `foresla_rakenskapsar`: the create option creates the year, so the
    # agent's turn already sees its open periods.
    _Card(_fiscal_year),
    # `foresla_bolagsinformation`: a fill or overwrite option writes the details.
    _Card(_company_info),
    # `foresla_lonebokforing`: the book option books the payslip.
    _Card(_payroll, "a payroll booking is pressed by a logged-in user"),
    # `foresla_delat_underlag`: a yes links the underlag; the standing yes
    # also approves it for the fiscal year.
    _Card(_intake_reuse, "a shared underlag is approved by a logged-in user"),
    # `foresla_utlaggskontroll`: either answer puts the underlag back in the
    # pass's queue; the exit records it as failed.
    _Card(_reimbursement),
    # `foresla_avtalsbokforing`: a yes puts the underlag back in the queue,
    # the standing yes also approves it for the fiscal year.
    _Card(_agreement, "an agreement booking is approved by a logged-in user"),
)


def human_only_reason(decision_id: str) -> Optional[str]:
    """Why only a logged-in human may answer *decision_id*, or None.

    Every card that may be answered with the API key returns None, as does
    any decision that is not one of these cards.
    """
    for card in _CARDS:
        if card.human_only and card.service().requires_human(decision_id):
            return card.human_only
    return None


def on_decision_answered(decision: Decision, *, actor: str) -> None:
    """Run what the press on *decision* does. Each service ignores a
    decision that is not its own card, so at most one of them acts."""
    for card in _CARDS:
        card.service()().on_decision_answered(decision, actor=actor)
