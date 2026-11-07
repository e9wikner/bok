"""Utlägg: check against the company's statements, and the card that asks.

An underlag in the dropzone's `Utlägg/` is a purchase someone paid
privately, which the company owes back: it is booked with the debt on 2820
(`domain/reimbursement.py`). If the same purchase shows up in one of the
company's statements, the company paid it and it is no utlägg -- or the file
was put in the wrong folder. The human should not have to keep track of that,
so the server does:

- `kontrollera_utlagg` lets the agent look before it books.
- `guard_posting`, run by `post_agent_voucher`, refuses to book an utlägg
  that does not credit 2820, or one whose amount matches a statement
  transaction, until a human has answered the card. The check cannot be
  skipped by not calling the tool.
- `foresla_utlaggskontroll` raises the card: "Det är ett privat utlägg",
  "Företaget betalade" (naming the transaction) or "Avstå". In the intake
  pass, which has no thread, the card goes in the current fiscal year's
  Verifikationer thread, and the underlag is out of the pass's queue until
  it is answered (`repositories/intake_repo.py`), the same as a
  fiscal-year card (`services/fiscal_year_proposal.py`).

The press (`on_decision_answered`, called by `POST /decisions/{id}/answer`):

- either answer -> the underlag is back in the queue, and the agent books it
  the way the human said (`status_line` tells the pass);
- the exit -> a waiting dropzone underlag is recorded as failed, with the
  reason;
- free text -> nothing; the agent's turn reads the answer.

Layering (AGENTS.md): no SQL here, no HTTP.
"""

import logging
from datetime import date
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from config import settings
from db.database import db
from domain.models import Decision, Thread, ThreadPost
from domain.reimbursement import (
    REIMBURSEMENT_ACCOUNT,
    ReimbursementCheck,
    StatementHit,
    amount_bounds,
    rank,
    reimbursement_credit,
    vendor_in,
    window,
)
from domain.types import IntakeSourceType, IntakeStatus
from domain.validation import ValidationError
from repositories.bank_input_repo import BankInputRepository
from repositories.decision_repo import DecisionRepository
from repositories.intake_repo import IntakeRepository
from repositories.reimbursement_check_repo import ReimbursementCheckRepository

logger = logging.getLogger(__name__)

REIMBURSEMENT_OPTION_TITLE = "Det är ett privat utlägg"
COMPANY_PAID_OPTION_TITLE = "Företaget betalade"
EXIT_OPTION_TITLE = "Avstå"


def _as_date(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


class ReimbursementCheckService:
    # -- the check ---------------------------------------------------------

    def statement_hits(
        self,
        sek_ore: int,
        purchase_date: date,
        *,
        foreign: bool,
        vendor: Optional[str] = None,
    ) -> List[StatementHit]:
        """Transactions in the company's statements that look like this
        purchase, the likeliest first."""
        if sek_ore <= 0:
            return []
        low, high = amount_bounds(sek_ore, foreign=foreign)
        start, end = window(purchase_date)
        rows = BankInputRepository.find_outgoing_near(
            low, high, start.isoformat(), end.isoformat()
        )
        hits = [
            StatementHit(
                bank_transaction_id=row["id"],
                date=_as_date(row["transaction_date"]),
                amount_ore=-int(row["amount"]),
                account_code=row["account_code"],
                counterpart_name=row["counterpart_name"],
                description=row["description"],
                linked_voucher_id=row["linked_voucher_id"],
                vendor_hit=vendor_in(
                    vendor, row["counterpart_name"], row["description"]
                ),
            )
            for row in rows
        ]
        return rank(hits, sek_ore, purchase_date)

    def check_source(
        self,
        source_id: str,
        *,
        sek_ore: int,
        purchase_date: date,
        foreign: bool,
    ) -> Dict[str, Any]:
        """`kontrollera_utlagg`: the hits, and what the agent does next."""
        source = self._source(source_id)
        hits = self.statement_hits(
            sek_ore,
            purchase_date,
            foreign=foreign,
            vendor=self._vendor(source_id),
        )
        check = ReimbursementCheckRepository.latest_for_source(source_id)
        start, end = window(purchase_date)
        return {
            "source_id": source.id,
            "is_reimbursement": source.source_type == IntakeSourceType.REIMBURSEMENT,
            "sek_ore": sek_ore,
            "window": {"from": start.isoformat(), "to": end.isoformat()},
            "tolerance": "±5 %" if foreign else "exakt belopp",
            "hits": [hit.as_dict() for hit in hits],
            "answered": (
                {"status": check.status, "decision_id": check.decision_id}
                if check is not None and check.status != "declined"
                else None
            ),
            "next": self._next_step(hits, check),
        }

    @staticmethod
    def _next_step(
        hits: Sequence[StatementHit], check: Optional[ReimbursementCheck]
    ) -> str:
        if check is not None and check.status == "reimbursement":
            return "Användaren har sagt att det är ett utlägg: bokför mot 2820."
        if check is not None and check.status == "company_paid":
            return (
                "Användaren har sagt att företaget betalade: bokför mot "
                f"banktransaktionen {check.bank_transaction_id}, inte mot 2820."
            )
        if check is not None and check.status == "pending":
            return "Ett kort väntar redan på svar. Bokför inte."
        if hits:
            return (
                "Ett köp i företagets kontoutdrag liknar utlägget. Bokför inte: "
                "kör foresla_utlaggskontroll med den första träffen."
            )
        return "Inget i kontoutdragen liknar utlägget: bokför mot 2820."

    def guard_posting(
        self,
        source_ids: Iterable[str],
        rows: Sequence[Mapping[str, Any]],
        voucher_date: date,
        *,
        foreign: bool,
    ) -> None:
        """Before an agent posting: an utlägg credits 2820, and is not booked
        against 2820 while a statement transaction looks like the same
        purchase and no human has said which it is."""
        owed = reimbursement_credit(rows)
        for source_id in dict.fromkeys(source_ids):
            source = IntakeRepository.get_source(source_id)
            if source is None or source.source_type != IntakeSourceType.REIMBURSEMENT:
                continue
            check = ReimbursementCheckRepository.latest_for_source(source_id)
            status = check.status if check is not None else None
            if status == "pending":
                raise ValidationError(
                    "reimbursement_check_pending",
                    "A card asks the user whether the company paid this "
                    "purchase; nothing is booked until it is answered",
                    f"decision_id={check.decision_id}",  # type: ignore[union-attr]
                )
            if status == "company_paid":
                if owed:
                    raise ValidationError(
                        "reimbursement_company_paid",
                        "The user answered that the company paid this purchase: "
                        "it is not booked against 2820",
                        "book it against the statement transaction "
                        f"{check.bank_transaction_id} "  # type: ignore[union-attr]
                        "(bank_transaction_ids) and its account",
                    )
                continue
            if not owed:
                raise ValidationError(
                    "reimbursement_requires_2820",
                    "An underlag in Utlägg/ is a private outlay: the amount "
                    "owed to the person who paid is credited 2820",
                    "credit 2820 with the whole amount; the company has paid "
                    "nothing yet",
                )
            if status == "reimbursement":
                continue
            hits = self.statement_hits(
                owed, voucher_date, foreign=foreign, vendor=self._vendor(source_id)
            )
            if hits:
                raise ValidationError(
                    "reimbursement_matches_statement",
                    (
                        "A transaction in the company's statements looks like "
                        f"the same purchase: {hits[0].label()}. A purchase the "
                        "company paid is not an utlägg"
                    ),
                    "do not post; run foresla_utlaggskontroll with "
                    f"source_id={source_id} and "
                    f"bank_transaction_id={hits[0].bank_transaction_id}",
                    payload={"hits": [hit.as_dict() for hit in hits]},
                )

    # -- the card ----------------------------------------------------------

    def propose(
        self,
        thread: Optional[Thread],
        *,
        source_id: str,
        bank_transaction_id: str,
        actor: str,
    ) -> Dict[str, Any]:
        """Raise the card, or return the one already waiting for this
        underlag. `thread` is the turn's; `None` is the intake pass, and the
        card goes in the Verifikationer thread."""
        source = self._source(source_id)
        if source.source_type != IntakeSourceType.REIMBURSEMENT:
            raise ValidationError(
                "not_a_reimbursement",
                "Only an underlag in Utlägg/ is checked as an utlägg",
                f"source_id={source_id}, source_type={source.source_type}",
            )
        transaction = BankInputRepository.get_transaction_with_account(
            bank_transaction_id
        )
        if transaction is None:
            raise ValidationError(
                "bank_transaction_not_found",
                f"No statement transaction {bank_transaction_id}",
                f"bank_transaction_id={bank_transaction_id}",
            )
        hit = StatementHit(
            bank_transaction_id=transaction["id"],
            date=_as_date(transaction["transaction_date"]),
            amount_ore=abs(int(transaction["amount"])),
            account_code=transaction["account_code"],
            counterpart_name=transaction["counterpart_name"],
            description=transaction["description"],
            linked_voucher_id=transaction["linked_voucher_id"],
            vendor_hit=vendor_in(
                self._vendor(source_id),
                transaction["counterpart_name"],
                transaction["description"],
            ),
        )

        existing = ReimbursementCheckRepository.latest_for_source(source_id)
        if existing is not None and existing.status == "pending":
            decision = DecisionRepository.get(existing.decision_id)
            if decision is not None and decision.status == "open":
                return self._result(existing, hit, existing_card=True)
            ReimbursementCheckRepository.resolve(existing.id, "superseded", actor=actor)

        from repositories.thread_repo import ThreadRepository
        from services.fiscal_year_proposal import FiscalYearProposalService

        target = thread or FiscalYearProposalService._vouchers_thread()
        seq_before = ThreadRepository.last_seq(target.id)
        decision = self._raise_card(target, source, hit, actor)
        try:
            with db.transaction():
                check = ReimbursementCheckRepository.create(
                    intake_source_id=source.id,
                    bank_transaction_id=hit.bank_transaction_id,
                    decision_id=decision.id,
                    reimbursement_option_id=decision.options[0].id,
                    company_paid_option_id=decision.options[1].id,
                    thread_id=target.id,
                    created_by=actor,
                    _commit=False,
                )
        except Exception:
            # The card and its row are two transactions (DecisionService owns
            # its own): a card without its row could be pressed to no effect.
            from services.decision_service import DecisionService

            DecisionService().supersede(decision.id)
            raise

        if thread is None:
            from services.fiscal_year_proposal import _publish

            _publish(ThreadRepository.list_posts(target.id, since=seq_before))
        return self._result(check, hit, existing_card=False)

    @staticmethod
    def _raise_card(
        thread: Thread, source: Any, hit: StatementHit, actor: str
    ) -> Decision:
        from services.decision_service import DecisionService

        booked = (
            " Transaktionen är redan kopplad till en verifikation."
            if hit.linked_voucher_id
            else ""
        )
        return DecisionService().create(
            thread,
            title=f"Är {source.original_filename} ett utlägg?",
            reason=(
                "Underlaget ligger i Utlägg/, men en transaktion i företagets "
                f"kontoutdrag ser ut att vara samma köp: {hit.label()}.{booked} "
                "Ett köp som företaget betalade är inget utlägg."
            ),
            consequence=(
                f"Ett utlägg bokförs som skuld på {REIMBURSEMENT_ACCOUNT} till den "
                "som betalade. Betalade företaget bokförs köpet mot "
                "transaktionen i kontoutdraget."
            ),
            kind="approval",
            amount_ore=hit.amount_ore,
            source={"kind": "intake_source", "id": source.id, "date": hit.date},
            options=[
                {
                    "title": REIMBURSEMENT_OPTION_TITLE,
                    "rationale": (
                        f"Bokförs mot {REIMBURSEMENT_ACCOUNT} och ersätts den som "
                        "betalade. Transaktionen i kontoutdraget är något annat."
                    ),
                },
                {
                    "title": COMPANY_PAID_OPTION_TITLE,
                    "rationale": (
                        f"Bokförs mot transaktionen {hit.label()}, inte som " "utlägg."
                    ),
                    "recommended": hit.vendor_hit,
                },
                {
                    "title": EXIT_OPTION_TITLE,
                    "rationale": "Inget bokförs.",
                    "is_exit": True,
                },
            ],
            actor=actor,
        )

    # -- the press ---------------------------------------------------------

    def on_decision_answered(
        self, decision: Decision, *, actor: str
    ) -> Optional[ThreadPost]:
        check = ReimbursementCheckRepository.get_by_decision(decision.id)
        if check is None or check.status != "pending":
            return None
        if decision.answer_option_id is None:
            return None  # free text: the agent's turn takes it from here
        if decision.answer_option_id == check.reimbursement_option_id:
            ReimbursementCheckRepository.resolve(check.id, "reimbursement", actor=actor)
            self._wake_pass()
            return None
        if decision.answer_option_id == check.company_paid_option_id:
            ReimbursementCheckRepository.resolve(check.id, "company_paid", actor=actor)
            self._wake_pass()
            return None
        ReimbursementCheckRepository.resolve(check.id, "declined", actor=actor)
        self._decline(check, actor)
        return None

    @staticmethod
    def _decline(check: ReimbursementCheck, actor: str) -> None:
        from services.intake import IntakeService

        source = IntakeRepository.get_source(check.intake_source_id)
        if source is None or source.status != IntakeStatus.PENDING:
            return
        if IntakeRepository.is_in_a_thread(source.id):
            return  # the thread's turn answers for its own files
        IntakeService().record_failed(
            source.id,
            summary="Utlägg eller företagets köp?",
            error_detail=(
                "Underlaget ligger i Utlägg/, men en transaktion i företagets "
                "kontoutdrag liknar köpet. Användaren valde att avstå, så "
                "inget bokfördes."
            ),
            actor=actor,
        )

    @staticmethod
    def _wake_pass() -> None:
        if not settings.agent_runtime_enabled:
            return
        try:
            from services.agent_runtime import get_runner

            runner = get_runner()
            if runner.running:
                runner.trigger_pass_now()
        except Exception:
            logger.exception("Could not wake the intake pass")

    # -- reading -----------------------------------------------------------

    def status_line(self, source_id: str) -> Optional[str]:
        """What the human has answered about this utlägg, for the pass's user
        turn; `None` when nothing has been asked."""
        check = ReimbursementCheckRepository.latest_for_source(source_id)
        if check is None or check.status in ("pending", "declined"):
            return None
        transaction = BankInputRepository.get_transaction_with_account(
            check.bank_transaction_id
        )
        label = (
            f"{transaction['transaction_date']}, {abs(int(transaction['amount']))} öre"
            if transaction
            else check.bank_transaction_id
        )
        if check.status == "reimbursement":
            return (
                "användaren har svarat att det är ett privat utlägg; "
                f"transaktionen {label} i kontoutdraget är något annat. Bokför "
                f"mot {REIMBURSEMENT_ACCOUNT}."
            )
        return (
            "användaren har svarat att företaget betalade köpet. Bokför mot "
            f"banktransaktionen {check.bank_transaction_id} ({label}) och dess "
            f"konto, inte mot {REIMBURSEMENT_ACCOUNT}."
        )

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _source(source_id: str) -> Any:
        source = IntakeRepository.get_source(source_id)
        if source is None or source.status == IntakeStatus.DELETED:
            raise ValidationError(
                "source_not_found",
                f"No intake source {source_id}",
                f"source_id={source_id}",
            )
        return source

    @staticmethod
    def _vendor(source_id: str) -> Optional[str]:
        from repositories.interpretation_repo import InterpretationRepository

        interpretation = InterpretationRepository.latest_for_source(source_id)
        return interpretation.vendor if interpretation is not None else None

    @staticmethod
    def _result(
        check: ReimbursementCheck, hit: StatementHit, *, existing_card: bool
    ) -> Dict[str, Any]:
        return {
            "check_id": check.id,
            "decision_id": check.decision_id,
            "status": check.status,
            "source_id": check.intake_source_id,
            "bank_transaction": hit.as_dict(),
            "existing_card": existing_card,
            "next": (
                "Kortet väntar på användarens svar. Bokför inte och avstå inte: "
                "avsluta. Underlaget väntar utanför kön tills kortet är besvarat."
            ),
        }
