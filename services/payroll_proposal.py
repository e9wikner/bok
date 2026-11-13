"""`foresla_lonebokforing`: a payslip's booking proposed as a decision card.

A salary is booked against the bank transaction that paid it
(`PayrollService`), not by the agent. It proposes the booking as a decision
card in the thread, with the server's own checks already run, and a
logged-in human's press books it. The payslip and the transaction are stored
with the card (migration 043), so what is booked is exactly what the human
saw.

A month's AGI has no card: the agent books it from its kvittens
(`bokfor_agi`). Migration 043's `agi` kind is no longer raised.

The agent may name the transaction. Without one, the server looks for it: a
payment out equal to the net salary, near the payment date, not booked or
linked yet. Exactly one candidate is proposed. None or several is refused
with the candidates in the payload, and the agent asks the user.

A new card for the same payslip supersedes a pending one; the same
card asked for again is joined.

The press (`on_decision_answered`, called by `POST /decisions/{id}/answer`
after the answer has committed; the route refuses the API key first, see
`requires_human`):

- the book option -> the voucher(s) are posted and a receipt is written in
  the thread; when the books changed under the card (the transaction was
  booked, the period locked) an error post says so and nothing is booked;
- any other option -> declined, nothing booked;
- free text -> nothing yet. The agent's turn reads the answer and, on a yes,
  proposes again, which supersedes this card with a new one.

Layering (AGENTS.md): no SQL here, no HTTP.
"""

import logging
from typing import Any, Dict, List, Optional

from db.database import db
from domain.models import Decision, PayrollBookingProposal, Thread, ThreadPost
from domain.validation import ValidationError
from repositories.account_repo import AccountRepository
from repositories.decision_repo import DecisionRepository
from repositories.payroll_booking_proposal_repo import (
    PayrollBookingProposalRepository,
)
from repositories.thread_repo import ThreadRepository
from repositories.voucher_repo import VoucherRepository
from services.payroll import PAYROLL_ACCOUNTS, PayrollService
from services.thread_stream import publish_posts

logger = logging.getLogger(__name__)

BOOK_PAYSLIP_OPTION_TITLE = "Bokför lönen"
DECLINE_OPTION_TITLE = "Inte nu"

_MANAD = [
    "januari", "februari", "mars", "april", "maj", "juni",
    "juli", "augusti", "september", "oktober", "november", "december",
]  # fmt: skip


def _kr(ore: int) -> str:
    """`42 300 kr`, or `42 300,50 kr` when there are öre."""
    sign = "−" if ore < 0 else ""
    kr, rest = divmod(abs(ore), 100)
    text = f"{kr:,}".replace(",", " ")
    if rest:
        text += f",{rest:02d}"
    return f"{sign}{text} kr"


def _month(year: int, month: int) -> str:
    return f"{_MANAD[month - 1]} {year}"


class PayrollProposalService:
    def __init__(self) -> None:
        self.payroll = PayrollService()

    # -- the tools ---------------------------------------------------------

    def propose_payslip(
        self,
        thread: Thread,
        *,
        payslip_id: str,
        bank_transaction_id: Optional[str] = None,
        actor: str,
    ) -> Dict[str, Any]:
        """Raise the card for booking one payslip against its payment."""
        if bank_transaction_id is None:
            bank_transaction_id = self._only_candidate(payslip_id)
        checked = self.payroll.check_payslip_booking(payslip_id, bank_transaction_id)
        payslip, tx = checked["payslip"], checked["transaction"]

        for pending in PayrollBookingProposalRepository.pending_for_payslip(
            payslip_id
        ) + PayrollBookingProposalRepository.pending_for_bank_transaction(tx.id):
            if (
                pending.payslip_id == payslip_id
                and pending.bank_transaction_id == tx.id
                and _is_open(pending)
            ):
                return self._result(pending, existing_card=True)
            self._supersede(pending, actor)

        decision = self._raise_payslip_card(thread, checked, actor)
        proposal = self._store(
            decision,
            thread,
            kind="payslip",
            payslip_id=payslip.id,
            bank_transaction_id=tx.id,
            actor=actor,
        )
        return self._result(proposal, existing_card=False)

    # -- what the view reads -----------------------------------------------

    @staticmethod
    def open_card_for_payslip(payslip_id: str) -> Optional[str]:
        """The decision id of the payslip's open card, if it has one. The
        `/v4` row opens that card, so a row that waits always leads somewhere."""
        for pending in PayrollBookingProposalRepository.pending_for_payslip(payslip_id):
            if _is_open(pending):
                return pending.decision_id
        return None

    # -- the press ---------------------------------------------------------

    @staticmethod
    def requires_human(decision_id: str) -> bool:
        """Whether answering *decision_id* can book: a payroll card. The
        route refuses the API key for it before the answer is written."""
        return PayrollBookingProposalRepository.get_by_decision(decision_id) is not None

    def on_decision_answered(
        self, decision: Decision, *, actor: str
    ) -> Optional[ThreadPost]:
        """What the answer to a payroll card does; `None` for any other
        decision. Returns the post it wrote, already published."""
        proposal = PayrollBookingProposalRepository.get_by_decision(decision.id)
        if proposal is None or proposal.status != "pending":
            return None
        if decision.answer_option_id is None:
            return None  # free text: the agent's turn takes it from here
        if decision.answer_option_id != proposal.book_option_id:
            PayrollBookingProposalRepository.resolve(
                proposal.id, "declined", actor=actor
            )
            return None
        if proposal.kind != "payslip":
            return None  # an AGI card from before `bokfor_agi`: books nothing
        try:
            voucher_ids = self._book_payslip(proposal, actor)
        except ValidationError as exc:
            return self._failed(proposal, exc, actor)

        posts = []
        with db.transaction():
            PayrollBookingProposalRepository.resolve(
                proposal.id, "booked", actor=actor, _commit=False
            )
            for voucher_id in voucher_ids:
                posts.append(
                    ThreadRepository.add_post(
                        thread_id=proposal.thread_id,
                        post_type="receipt",
                        actor=actor,
                        body=_receipt_body(voucher_id),
                        _commit=False,
                    )
                )
        publish_posts(posts)
        _view_changed(proposal, voucher_ids)
        return posts[-1] if posts else None

    def _book_payslip(self, proposal: PayrollBookingProposal, actor: str) -> List[str]:
        assert proposal.payslip_id and proposal.bank_transaction_id
        payslip = self.payroll.match_bank_transaction_and_book(
            proposal.payslip_id, proposal.bank_transaction_id, actor=actor
        )
        assert payslip.voucher_id is not None
        return [payslip.voucher_id]

    def _failed(
        self, proposal: PayrollBookingProposal, exc: ValidationError, actor: str
    ) -> ThreadPost:
        """The books changed since the card was raised. Nothing was booked;
        the agent can propose again from the books as they are now."""
        what = "Lönen kunde inte bokföras"
        with db.transaction():
            PayrollBookingProposalRepository.resolve(
                proposal.id, "failed", actor=actor, _commit=False
            )
            post = ThreadRepository.add_post(
                thread_id=proposal.thread_id,
                post_type="error",
                actor=actor,
                body={
                    "cause": f"{what}: {exc.message}.",
                    "consequence": "Inget bokfördes. Be agenten lägga fram kortet igen.",
                    "retry_draft_id": None,
                },
                _commit=False,
            )
        publish_posts([post])
        return post

    # -- helpers -----------------------------------------------------------

    def _only_candidate(self, payslip_id: str) -> str:
        candidates = self.payroll.payment_candidates(payslip_id)
        if len(candidates) == 1:
            return candidates[0].id
        payslip = self.payroll.payslips.get(payslip_id)
        assert payslip is not None  # payment_candidates raised otherwise
        payload = {
            "candidates": [
                {
                    "bank_transaction_id": tx.id,
                    "date": tx.transaction_date.isoformat(),
                    "amount": tx.amount,
                    "description": tx.description,
                    "counterpart_name": tx.counterpart_name,
                }
                for tx in candidates
            ]
        }
        if not candidates:
            raise ValidationError(
                "payroll_payment_not_found",
                f"Ingen obokad utbetalning på {_kr(payslip.net_salary)} nära "
                f"{payslip.payment_date.isoformat()}",
                f"payslip_id={payslip_id}",
                payload=payload,
            )
        raise ValidationError(
            "payroll_payment_ambiguous",
            f"{len(candidates)} utbetalningar på {_kr(payslip.net_salary)} kan "
            "vara lönen; ange bank_transaction_id",
            f"payslip_id={payslip_id}",
            payload=payload,
        )

    @staticmethod
    def _supersede(proposal: PayrollBookingProposal, actor: str) -> None:
        from services.decision_service import DecisionService

        PayrollBookingProposalRepository.resolve(proposal.id, "superseded", actor=actor)
        decision = DecisionRepository.get(proposal.decision_id)
        if decision is not None and decision.status == "open":
            DecisionService().supersede(proposal.decision_id)

    @staticmethod
    def _store(
        decision: Decision, thread: Thread, *, kind: str, actor: str, **target: Any
    ) -> PayrollBookingProposal:
        try:
            return PayrollBookingProposalRepository.create(
                decision_id=decision.id,
                thread_id=thread.id,
                kind=kind,
                book_option_id=decision.options[0].id,
                created_by=actor,
                **target,
            )
        except Exception:
            # A card without its row could be pressed to no effect.
            from services.decision_service import DecisionService

            DecisionService().supersede(decision.id)
            raise

    @staticmethod
    def _raise_payslip_card(thread: Thread, checked: Dict, actor: str) -> Decision:
        from services.decision_service import DecisionService

        payslip, tx = checked["payslip"], checked["transaction"]
        name = payslip.employee.name if payslip.employee else payslip.employee_id
        text = " · ".join(t for t in (tx.description, tx.counterpart_name) if t)
        return DecisionService().create(
            thread,
            title=f"Bokför lön {_month(payslip.period_year, payslip.period_month)} · {name}",
            reason=(
                f"Nettolönen {_kr(payslip.net_salary)} betalades ut "
                f"{tx.transaction_date.isoformat()}"
                + (f" ({text})" if text else "")
                + f". Bruttolön {_kr(payslip.gross_salary)}, skatteavdrag "
                f"{_kr(payslip.preliminary_tax)}, arbetsgivaravgift "
                f"{_kr(payslip.employer_fee)}."
            ),
            consequence=(
                f"Bokförs som en A-verifikation daterad "
                f"{tx.transaction_date.isoformat()}, med banktransaktionen som "
                "underlag. En bokförd lön ändras inte; ett fel rättas med en "
                "B-verifikation."
            ),
            kind="approval",
            amount_ore=payslip.net_salary,
            rows=_card_rows(checked["rows"]),
            options=[
                {
                    "title": BOOK_PAYSLIP_OPTION_TITLE,
                    "rationale": "Bokför lönen mot utbetalningen.",
                    "recommended": True,
                },
                {
                    "title": DECLINE_OPTION_TITLE,
                    "rationale": "Ingenting bokförs.",
                    "is_exit": True,
                },
            ],
            actor=actor,
        )

    @staticmethod
    def _result(proposal: PayrollBookingProposal, *, existing_card: bool) -> dict:
        return {
            "status": "pending",
            "proposal_id": proposal.id,
            "decision_id": proposal.decision_id,
            "kind": proposal.kind,
            "payslip_id": proposal.payslip_id,
            "bank_transaction_id": proposal.bank_transaction_id,
            "year": proposal.agi_year,
            "month": proposal.agi_month,
            "existing_card": existing_card,
        }


def _card_rows(rows: List[Dict]) -> List[Dict]:
    """The rows the press books, as the card shows them. A payroll account
    not yet in the chart is named as booking will create it."""
    from services.draft_service import card_rows

    names = {code: name for code, (name, _type) in PAYROLL_ACCOUNTS.items()}
    return card_rows(rows, AccountRepository.get_all_as_dict(), names)


def _is_open(proposal: PayrollBookingProposal) -> bool:
    decision = DecisionRepository.get(proposal.decision_id)
    return decision is not None and decision.status == "open"


def _receipt_body(voucher_id: str) -> dict:
    from services.draft_service import receipt_body

    voucher = VoucherRepository.get(voucher_id)
    assert voucher is not None  # just posted
    body = receipt_body(voucher, AccountRepository.get_all_as_dict())
    body["title"] = f"{body['title']} · {voucher.description}"
    return body


def _view_changed(proposal: PayrollBookingProposal, voucher_ids: List[str]) -> None:
    """`view.changed` in the card's thread, so the view reads the runs and
    the decisions again. Never fatal."""
    from services.thread_stream import EVENT_VIEW_CHANGED, get_broker

    thread = ThreadRepository.get(proposal.thread_id)
    if thread is None:
        return
    try:
        get_broker().publish(
            thread.id,
            EVENT_VIEW_CHANGED,
            {
                "view_key": thread.view_key,
                "changed": {"kind": "payroll_booked", "voucher_ids": voucher_ids},
            },
        )
    except Exception:
        logger.exception("view.changed for thread %s failed", thread.id)
