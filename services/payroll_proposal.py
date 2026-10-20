"""`foresla_lonebokforing` and `foresla_agi_bokforing`: a payslip's or an AGI
month's booking proposed as a decision card.

A salary is booked against the bank transaction that paid it, and the month's
AGI against the tax account (`PayrollService`). Neither is booked by the
agent. It proposes the booking as a decision card in the thread, with the
server's own checks already run, and a logged-in human's press books it. The
payslip and the transaction, or the month and the date, are stored with the
card (migration 043), so what is booked is exactly what the human saw.

The agent may name the transaction. Without one, the server looks for it: a
payment out equal to the net salary, near the payment date, not booked or
linked yet. Exactly one candidate is proposed. None or several is refused
with the candidates in the payload, and the agent asks the user.

A new card for the same payslip or month supersedes a pending one; the same
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
from datetime import date
from typing import Any, Dict, List, Optional

from db.database import db
from domain.models import Decision, PayrollBookingProposal, Thread, ThreadPost
from domain.payroll_models import AGI_PARTS, AgiDeclaration
from domain.validation import ValidationError
from repositories.account_repo import AccountRepository
from repositories.decision_repo import DecisionRepository
from repositories.payroll_booking_proposal_repo import (
    PayrollBookingProposalRepository,
)
from repositories.thread_repo import ThreadRepository
from repositories.voucher_repo import VoucherRepository
from services.payroll import PAYROLL_ACCOUNTS, PayrollService

logger = logging.getLogger(__name__)

BOOK_PAYSLIP_OPTION_TITLE = "Bokför lönen"
BOOK_AGI_OPTION_TITLE = "Bokför arbetsgivardeklarationen"
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

    def propose_agi(
        self,
        thread: Thread,
        *,
        year: int,
        month: int,
        voucher_date: Optional[date] = None,
        actor: str,
    ) -> Dict[str, Any]:
        """Raise the card for booking the month's AGI."""
        agi, booked_on, _period = self.payroll.check_agi_booking(
            year, month, voucher_date
        )
        for pending in PayrollBookingProposalRepository.pending_for_agi(year, month):
            if pending.voucher_date == voucher_date and _is_open(pending):
                return self._result(pending, existing_card=True)
            self._supersede(pending, actor)

        decision = self._raise_agi_card(thread, agi, booked_on, actor)
        proposal = self._store(
            decision,
            thread,
            kind="agi",
            agi_year=year,
            agi_month=month,
            voucher_date=voucher_date,
            actor=actor,
        )
        return self._result(proposal, existing_card=False)

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
        try:
            if proposal.kind == "payslip":
                voucher_ids = self._book_payslip(proposal, actor)
            else:
                voucher_ids = self._book_agi(proposal, actor)
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
        _publish(posts)
        _view_changed(proposal, voucher_ids)
        return posts[-1] if posts else None

    def _book_payslip(self, proposal: PayrollBookingProposal, actor: str) -> List[str]:
        assert proposal.payslip_id and proposal.bank_transaction_id
        payslip = self.payroll.match_bank_transaction_and_book(
            proposal.payslip_id, proposal.bank_transaction_id, actor=actor
        )
        assert payslip.voucher_id is not None
        return [payslip.voucher_id]

    def _book_agi(self, proposal: PayrollBookingProposal, actor: str) -> List[str]:
        assert proposal.agi_year is not None and proposal.agi_month is not None
        before = self.payroll.get_agi(proposal.agi_year, proposal.agi_month)
        agi = self.payroll.book_agi(
            proposal.agi_year,
            proposal.agi_month,
            voucher_date=proposal.voucher_date,
            actor=actor,
        )
        return [
            agi.voucher_ids[kind]
            for kind in AGI_PARTS
            if kind in agi.voucher_ids and kind not in before.voucher_ids
        ]

    def _failed(
        self, proposal: PayrollBookingProposal, exc: ValidationError, actor: str
    ) -> ThreadPost:
        """The books changed since the card was raised. Nothing was booked;
        the agent can propose again from the books as they are now."""
        what = (
            "Lönen kunde inte bokföras"
            if proposal.kind == "payslip"
            else "Arbetsgivardeklarationen kunde inte bokföras"
        )
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
        _publish([post])
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
        accounts = AccountRepository.get_all_as_dict()

        def line(row: Dict) -> str:
            code = row["account"]
            account = accounts.get(code)
            label = account.name if account else PAYROLL_ACCOUNTS.get(code, ("",))[0]
            name = f"{code} {label}".strip()
            side = "debet" if row["debit"] else "kredit"
            return f"{name} {side} {_kr(row['debit'] or row['credit'])}"

        rows = "; ".join(line(r) for r in checked["rows"] if r["debit"] or r["credit"])
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
                f"{_kr(payslip.employer_fee)}. Verifikationen: {rows}."
            ),
            consequence=(
                f"Bokförs som en A-verifikation daterad "
                f"{tx.transaction_date.isoformat()}, med banktransaktionen som "
                "underlag. En bokförd lön ändras inte; ett fel rättas med en "
                "B-verifikation."
            ),
            kind="approval",
            amount_ore=payslip.net_salary,
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
    def _raise_agi_card(
        thread: Thread, agi: AgiDeclaration, booked_on: date, actor: str
    ) -> Decision:
        from services.decision_service import DecisionService

        parts = [
            f"{label} {_kr(agi.amount(kind))}"
            for kind, (_account, label) in AGI_PARTS.items()
            if kind in agi.unbooked_parts
        ]
        return DecisionService().create(
            thread,
            title=f"Bokför arbetsgivardeklaration {_month(agi.year, agi.month)}",
            reason=(
                f"Lämnas och betalas senast {agi.due_date.isoformat()}. "
                f"Skatteavdrag (497) {_kr(agi.total_preliminary_tax)}, "
                f"arbetsgivaravgifter (487) {_kr(agi.total_employer_fee)}, att "
                f"betala {_kr(agi.total_to_pay)}. Uppgifterna lämnas i "
                "Skatteverkets e-tjänst."
            ),
            consequence=(
                f"Bokförs som {len(parts)} verifikation"
                f"{'er' if len(parts) != 1 else ''} daterad"
                f"{'e' if len(parts) != 1 else ''} {booked_on.isoformat()} mot "
                f"skattekontot (1630): {', '.join(parts)}."
            ),
            kind="approval",
            amount_ore=agi.total_to_pay,
            options=[
                {
                    "title": BOOK_AGI_OPTION_TITLE,
                    "rationale": "Flyttar skulderna 2710 och 2730 till skattekontot.",
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


def _publish(posts: List[ThreadPost]) -> None:
    """`message.completed` for posts written outside a turn. Never fatal."""
    from services.thread_stream import (
        EVENT_MESSAGE_COMPLETED,
        get_broker,
        post_event_payload,
    )

    for post in posts:
        try:
            get_broker().publish(
                post.thread_id, EVENT_MESSAGE_COMPLETED, post_event_payload(post)
            )
        except Exception:
            logger.exception("Post %s was not published", post.id)
