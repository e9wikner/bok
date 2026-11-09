"""Avtal och medgivanden: one underlag behind many statement transactions
(migration 048).

An autogiro mandate, a loan agreement or a subscription has no date or
amount of its own. It is the underlag of every transaction it covers in the
statements, each booked from its row -- date and amount -- with the same
kontering: the bank account against one counter account, the whole amount,
no VAT. How many transactions that is, the agent does not decide on its own:

- `foresla_avtalsbokforing` raises a card naming the transactions and the
  kontering. In the intake pass, which has no thread, it goes in the
  current fiscal year's Verifikationer thread, and the underlag is out of the
  pass's queue until it is answered (`repositories/intake_repo.py`).
- The press, by a logged-in human only (`requires_human`):
  - **Bokför** -> the set is approved; the underlag is back in the queue and
    the pass is woken. The pass posts one voucher per transaction, each with
    the underlag and its transaction (`status_line` tells it what).
  - **Bokför och godkänn för kommande** -> the same, plus a standing approval
    for the fiscal year (`intake_reuse_approvals`, migration 044, revocable
    there). A statement imported later with a transaction of the same
    account, amount and text wakes the pass, which books it the same way
    (`followups`). A matching transaction in a later fiscal year is not
    booked: the pass is asked to raise a new card for that year.
  - **Avstå** -> nothing is booked; a waiting dropzone underlag is failed.
  - free text -> nothing here; the agent's turn reads the answer.
- `guard_posting`, run by `post_agent_voucher`, holds a posting under such an
  approval to exactly one approved transaction and exactly the card's
  kontering. Only the intake pass posts under one (`check_posting_context`):
  a thread turn and the pass booking the same set at once could race.

Layering (AGENTS.md): no SQL here, no HTTP.
"""

import logging
from collections import Counter
from datetime import date
from typing import Any, Dict, List, Mapping, Optional, Sequence

from config import settings
from db.database import db
from domain.agreement_booking import (
    AgreementBooking,
    kontering,
    normalize_text,
    transaction_day,
)
from domain.models import Decision, Thread, ThreadPost
from domain.types import IntakeStatus
from domain.validation import ValidationError
from repositories.account_repo import AccountRepository
from repositories.agreement_booking_repo import AgreementBookingRepository
from repositories.bank_input_repo import BankInputRepository
from repositories.decision_repo import DecisionRepository
from repositories.intake_repo import IntakeRepository
from repositories.period_repo import PeriodRepository

logger = logging.getLogger(__name__)

EXIT_OPTION_TITLE = "Avstå"

#: The VAT accounts. An agreement booked from the statement carries no VAT:
#: a purchase with VAT needs its receipt or invoice.
_VAT_ACCOUNT_RANGE = ("2600", "2699")


class AgreementBookingService:
    # -- the tool ----------------------------------------------------------

    def propose(
        self,
        thread: Optional[Thread],
        *,
        source_id: str,
        bank_transaction_ids: Sequence[str],
        counter_account: str,
        reason: str,
        actor: str,
    ) -> Dict[str, Any]:
        """Raise the card. `thread` is the turn's; `None` is the intake pass,
        and the card goes in the Verifikationer thread. A pending card for
        the same underlag is superseded by this one."""
        source = IntakeRepository.get_source(source_id)
        if source is None or source.status == IntakeStatus.DELETED:
            raise ValidationError(
                "intake_source_not_found",
                f"No underlag {source_id}",
                f"source_id={source_id}",
            )
        reason = (reason or "").strip()
        if not reason:
            raise ValidationError(
                "reason_required",
                "Say in one sentence why the underlag covers these transactions",
            )
        ids = list(dict.fromkeys(bank_transaction_ids))
        if not ids:
            raise ValidationError(
                "bank_transactions_required",
                "Name the statement transactions the agreement covers",
            )
        transactions = [self._open_transaction(tx_id) for tx_id in ids]
        transactions.sort(key=lambda tx: (str(tx["transaction_date"]), tx["id"]))
        first = transactions[0]
        account_code = str(first["account_code"])
        amount_ore = int(first["amount"])
        description = normalize_text(first["description"])
        for transaction in transactions[1:]:
            if (
                str(transaction["account_code"]) != account_code
                or int(transaction["amount"]) != amount_ore
                or normalize_text(transaction["description"]) != description
            ):
                raise ValidationError(
                    "agreement_transactions_differ",
                    "The transactions must share account, amount and text",
                    f"{first['id']} and {transaction['id']} differ; propose "
                    "one card per pattern",
                )
        if not description:
            raise ValidationError(
                "agreement_transaction_without_text",
                "A transaction without a text cannot be recognised again",
                f"bank_transaction_id={first['id']}",
            )
        fiscal_year = self._fiscal_year_of(transactions)
        counter = self._counter_account(counter_account, account_code)

        from repositories.thread_repo import ThreadRepository
        from services.fiscal_year_proposal import (
            FiscalYearProposalService,
            _publish,
        )

        pending = AgreementBookingRepository.pending_for_source(source.id)
        if pending is not None:
            from services.decision_service import DecisionService

            AgreementBookingRepository.resolve(pending.id, "superseded", actor=actor)
            decision = DecisionRepository.get(pending.decision_id)
            if decision is not None and decision.status == "open":
                DecisionService().supersede(pending.decision_id)

        target = thread or FiscalYearProposalService._vouchers_thread()
        seq_before = ThreadRepository.last_seq(target.id)
        decision = self._raise_card(
            target,
            source=source,
            transactions=transactions,
            fiscal_year=fiscal_year,
            account_code=account_code,
            counter=counter,
            amount_ore=amount_ore,
            reason=reason,
            actor=actor,
        )
        try:
            with db.transaction():
                booking = AgreementBookingRepository.create(
                    decision_id=decision.id,
                    thread_id=target.id,
                    intake_source_id=source.id,
                    fiscal_year_id=fiscal_year.id,
                    account_code=account_code,
                    amount_ore=amount_ore,
                    description=description,
                    counter_account_code=counter,
                    book_option_id=decision.options[0].id,
                    standing_option_id=decision.options[1].id,
                    bank_transaction_ids=[tx["id"] for tx in transactions],
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
            _publish(ThreadRepository.list_posts(target.id, since=seq_before))
        return {
            "booking_id": booking.id,
            "decision_id": booking.decision_id,
            "thread_id": booking.thread_id,
            "source_id": booking.intake_source_id,
            "bank_transaction_ids": booking.bank_transaction_ids,
            "rows": booking.rows(),
            "status": booking.status,
            "waiting": True,
        }

    def _raise_card(
        self,
        thread: Thread,
        *,
        source: Any,
        transactions: List[Dict[str, Any]],
        fiscal_year: Any,
        account_code: str,
        counter: str,
        amount_ore: int,
        reason: str,
        actor: str,
    ) -> Decision:
        from services.decision_service import DecisionService
        from services.draft_service import card_rows

        count = len(transactions)
        noun = "transaktion" if count == 1 else "transaktioner"
        year = _year_label(fiscal_year)
        listed = ", ".join(str(tx["transaction_date"])[:10] for tx in transactions)
        rows = kontering(account_code, counter, amount_ore)
        return DecisionService().create(
            thread,
            title=(
                f"{source.original_filename} gäller {count} {noun} i "
                f"kontoutdraget {account_code}"
            ),
            reason=(f"{reason} Transaktionerna, {_kronor(amount_ore)} var: {listed}."),
            consequence=(
                f"Varje transaktion bokförs som en egen verifikation på sitt "
                f"datum, debet/kredit som nedan, med underlaget och raden i "
                f"kontoutdraget. Godkänner du för kommande bokförs också nya "
                f"transaktioner med samma text och belopp på {account_code} "
                f"under {year}, när kontoutdragen läses in."
            ),
            kind="approval",
            amount_ore=abs(amount_ore) * count,
            source={
                "kind": "intake_source",
                "id": source.id,
                "date": transaction_day(transactions[-1]),
            },
            options=[
                {
                    "title": f"Bokför {count} {noun}",
                    "rationale": "Bara de här. Kommande frågas om igen.",
                },
                {
                    "title": f"Bokför och godkänn för kommande under {year}",
                    "rationale": (
                        "Nya transaktioner med samma text och belopp bokförs "
                        "likadant när kontoutdragen läses in. Godkännandet "
                        "kan återkallas på underlaget."
                    ),
                    "recommended": True,
                },
                {
                    "title": EXIT_OPTION_TITLE,
                    "rationale": "Inget bokförs.",
                    "is_exit": True,
                },
            ],
            rows=card_rows(rows, AccountRepository.get_all_as_dict()),
            actor=actor,
        )

    # -- the press ---------------------------------------------------------

    @staticmethod
    def requires_human(decision_id: str) -> bool:
        """Whether answering *decision_id* approves bookings: an agreement
        card. The route refuses the API key."""
        return AgreementBookingRepository.get_by_decision(decision_id) is not None

    def on_decision_answered(
        self, decision: Decision, *, actor: str
    ) -> Optional[ThreadPost]:
        booking = AgreementBookingRepository.get_by_decision(decision.id)
        if booking is None or booking.status != "pending":
            return None
        if decision.answer_option_id is None:
            return None  # free text: the agent's turn takes it from here
        if decision.answer_option_id == booking.book_option_id:
            AgreementBookingRepository.resolve(booking.id, "approved", actor=actor)
            self._back_in_queue(booking, actor)
            self.wake_pass()
            return None
        if decision.answer_option_id == booking.standing_option_id:
            from repositories.intake_reuse_repo import ReuseApprovalRepository

            with db.transaction():
                AgreementBookingRepository.resolve(
                    booking.id, "approved_standing", actor=actor, _commit=False
                )
                if (
                    ReuseApprovalRepository.active_for(
                        booking.intake_source_id, booking.fiscal_year_id
                    )
                    is None
                ):
                    ReuseApprovalRepository.create(
                        intake_source_id=booking.intake_source_id,
                        fiscal_year_id=booking.fiscal_year_id,
                        decision_id=decision.id,
                        approved_by=actor,
                        _commit=False,
                    )
            self._back_in_queue(booking, actor)
            self.wake_pass()
            return None
        AgreementBookingRepository.resolve(booking.id, "declined", actor=actor)
        self._decline(booking, actor)
        return None

    @staticmethod
    def _back_in_queue(booking: AgreementBooking, actor: str) -> None:
        """An underlag the agent abstained on earlier (the card raised from a
        thread, or after a retry) is put back in the pass's queue, so that
        the pass can book it. One already booked stays as it is: the pass
        books what is left as a follow-up."""
        from services.intake import RETRYABLE_STATUSES, IntakeService

        source = IntakeRepository.get_source(booking.intake_source_id)
        if (
            source is None
            or source.status not in RETRYABLE_STATUSES
            or IntakeRepository.is_in_a_thread(source.id)
            or IntakeService().supported_vouchers(source.id)
        ):
            return
        IntakeService().retry(source.id, actor=actor)

    @staticmethod
    def _decline(booking: AgreementBooking, actor: str) -> None:
        with db.transaction():
            for transaction_id in booking.bank_transaction_ids:
                AgreementBookingRepository.record_attempt(
                    booking_id=booking.id,
                    bank_transaction_id=transaction_id,
                    agent_run_id=None,
                    reason="Användaren avstod på kortet",
                    _commit=False,
                )
        from services.intake import IntakeService

        source = IntakeRepository.get_source(booking.intake_source_id)
        if source is None or source.status != IntakeStatus.PENDING:
            return
        if IntakeRepository.is_in_a_thread(source.id):
            return  # the thread's turn answers for its own files
        IntakeService().record_failed(
            source.id,
            summary="Avtalet bokförs inte mot kontoutdraget",
            error_detail=(
                "Underlaget är ett avtal eller medgivande. Användaren valde att "
                "avstå från att bokföra transaktionerna det gäller."
            ),
            actor=actor,
        )

    @staticmethod
    def wake_pass() -> None:
        if not settings.agent_runtime_enabled:
            return
        try:
            from services.agent_runtime import get_runner

            runner = get_runner()
            if runner.running:
                runner.trigger_pass_now()
        except Exception:
            logger.exception("Could not wake the intake pass")

    # -- posting -----------------------------------------------------------

    def posting_basis(
        self, source_id: str, bank_transaction_ids: Sequence[str]
    ) -> Optional[AgreementBooking]:
        """The approved card a posting of *source_id* against
        *bank_transaction_ids* rests on, or `None`: one whose set names every
        transaction, or a standing one whose pattern each matches, in a
        fiscal year the underlag is approved for."""
        ids = list(dict.fromkeys(bank_transaction_ids))
        if not ids:
            return None
        bookings = AgreementBookingRepository.approved_for_source(source_id)
        if not bookings:
            return None
        for booking in bookings:
            if all(tx_id in booking.bank_transaction_ids for tx_id in ids):
                return booking
        transactions = [
            BankInputRepository.get_transaction_with_account(i) for i in ids
        ]
        if any(tx is None for tx in transactions):
            return None
        for booking in bookings:
            if not booking.standing:
                continue
            if all(
                booking.matches(tx) and self._approved_year(source_id, tx)
                for tx in transactions
                if tx is not None
            ):
                return booking
        return None

    def guard_posting(
        self,
        intake_source_ids: Sequence[str],
        bank_transaction_ids: Sequence[str],
        rows: Sequence[Mapping[str, Any]],
    ) -> None:
        """A posting under an agreement approval books exactly one approved
        transaction with exactly the card's kontering."""
        for source_id in dict.fromkeys(intake_source_ids):
            booking = self.posting_basis(source_id, bank_transaction_ids)
            if booking is None:
                continue
            if len(set(bank_transaction_ids)) != 1:
                raise ValidationError(
                    "agreement_one_transaction_per_voucher",
                    "Book one statement transaction per voucher under an " "agreement",
                    f"bank_transaction_ids={list(bank_transaction_ids)}",
                )
            if _row_key(rows) != _row_key(booking.rows()):
                raise ValidationError(
                    "agreement_rows_differ",
                    "The rows must be the kontering the human approved",
                    f"expected {booking.rows()}",
                )

    @staticmethod
    def check_posting_context(
        intake_source_ids: Sequence[str],
        bank_transaction_ids: Sequence[str],
        *,
        in_thread: bool,
    ) -> Optional[AgreementBooking]:
        """The booking a tool posting rests on, refused in a thread: the pass
        books an approved agreement, a thread turn does not."""
        service = AgreementBookingService()
        for source_id in dict.fromkeys(intake_source_ids):
            booking = service.posting_basis(source_id, bank_transaction_ids)
            if booking is None:
                continue
            if in_thread:
                raise ValidationError(
                    "agreement_booked_by_pass",
                    "The intake pass books an approved agreement, not a thread",
                    "Say in the thread that the transactions are booked by the "
                    "intake pass; post nothing.",
                )
            return booking
        return None

    # -- what is left to book ----------------------------------------------

    def remaining(self, source_id: str) -> List[Dict[str, Any]]:
        """Transactions the underlag is approved for and that are still open:
        the approved sets, and under a standing approval the matching
        transactions in the approved years. Open periods only, never one a
        pass has given up on. Oldest first."""
        return self._work(source_id)["book"]

    def followups(self) -> List[Dict[str, Any]]:
        """For each underlag with an approved card that is not in the
        pass's queue itself (booked already, or a thread's file, which the
        queue never holds): what is left to book, and the matching
        transactions in a later fiscal year that need a new card."""
        work = []
        for source_id in AgreementBookingRepository.sources_with_approved():
            source = IntakeRepository.get_source(source_id)
            if source is None or source.status == IntakeStatus.DELETED:
                continue
            if source.status == IntakeStatus.PENDING and not (
                IntakeRepository.is_in_a_thread(source_id)
            ):
                continue  # in the pass's queue: the item books it
            item = self._work(source_id)
            if item["book"] or item["ask"]:
                work.append({"source": source, **item})
        return work

    def has_followups(self) -> bool:
        return bool(self.followups())

    def wake_if_followups(self) -> None:
        """After a statement import: wake the pass when it has something to
        book. Never raises -- the import already succeeded."""
        try:
            if self.has_followups():
                self.wake_pass()
        except Exception:
            logger.exception("Could not look for agreement follow-ups")

    def _work(self, source_id: str) -> Dict[str, Any]:
        bookings = AgreementBookingRepository.approved_for_source(source_id)
        attempted = AgreementBookingRepository.attempted_transaction_ids()
        book: Dict[str, Dict[str, Any]] = {}
        ask: Dict[str, Dict[str, Any]] = {}
        booking_for: Dict[str, AgreementBooking] = {}
        for booking in bookings:
            for tx_id in booking.bank_transaction_ids:
                if tx_id in attempted or tx_id in book:
                    continue
                transaction = self._bookable(tx_id)
                if transaction is not None:
                    book[tx_id] = transaction
                    booking_for[tx_id] = booking
        standing = next((b for b in bookings if b.standing), None)
        if (
            standing is not None
            and AgreementBookingRepository.pending_for_source(source_id) is None
        ):
            from services.statement_match import StatementMatchService

            matcher = StatementMatchService()
            for (
                transaction
            ) in BankInputRepository.list_unlinked_transactions_with_account():
                tx_id = transaction["id"]
                if tx_id in attempted or tx_id in book or tx_id in ask:
                    continue
                if not standing.matches(transaction):
                    continue
                if matcher.match_transaction(transaction).kind != "none":
                    continue  # a voucher may already be it: not ours to book
                period = _open_period(transaction)
                if period is None:
                    continue
                enriched = {**transaction, "period_id": period.id}
                if self._approved_year(source_id, transaction):
                    book[tx_id] = enriched
                    booking_for[tx_id] = standing
                elif period.fiscal_year_id != standing.fiscal_year_id and (
                    transaction_day(transaction) > _year_end(standing.fiscal_year_id)
                ):
                    ask[tx_id] = enriched
        ordered = sorted(
            book.values(), key=lambda tx: (str(tx["transaction_date"]), tx["id"])
        )
        return {
            "booking": standing or (bookings[0] if bookings else None),
            "book": ordered,
            "bookings": {tx["id"]: booking_for[tx["id"]] for tx in ordered},
            "ask": sorted(
                ask.values(), key=lambda tx: (str(tx["transaction_date"]), tx["id"])
            ),
        }

    def _bookable(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        transaction = BankInputRepository.get_transaction_with_account(transaction_id)
        if transaction is None or not self._is_open(transaction_id, transaction):
            return None
        period = _open_period(transaction)
        if period is None:
            return None
        return {**transaction, "period_id": period.id}

    @staticmethod
    def _is_open(
        transaction_id: str, transaction: Optional[Dict[str, Any]] = None
    ) -> bool:
        transaction = transaction or BankInputRepository.get_transaction_with_account(
            transaction_id
        )
        return (
            transaction is not None
            and transaction["linked_voucher_id"] is None
            and transaction["matched_voucher_id"] is None
            and transaction["status"] != "ignored"
        )

    @staticmethod
    def _approved_year(source_id: str, transaction: Mapping[str, Any]) -> bool:
        from services.fiscal_years import FiscalYearService
        from services.intake_reuse import IntakeReuseService

        fiscal_year = FiscalYearService.containing(transaction_day(dict(transaction)))
        return (
            fiscal_year is not None
            and IntakeReuseService.approval_for(source_id, fiscal_year.id) is not None
        )

    # -- the pass ----------------------------------------------------------

    def status_line(self, source_id: str) -> Optional[str]:
        """What the human approved for this underlag, for the pass's user
        turn; `None` when nothing approved is left to book."""
        work = self._work(source_id)
        if not work["book"]:
            return None
        return (
            "användaren har godkänt att underlaget bokförs mot transaktioner i "
            "kontoutdraget. " + self._instructions(source_id, work)
        )

    def followup_turn(self, item: Mapping[str, Any]) -> str:
        """The user turn's extra lines for a follow-up: an underlag already
        booked, with transactions that came with a later statement."""
        source = item["source"]
        parts = [
            "Avtalsbokföring: användaren har godkänt underlaget nedan för "
            "transaktioner i kontoutdragen, och det finns transaktioner kvar "
            "att bokföra."
        ]
        if item["book"]:
            parts.append(self._instructions(source.id, item))
        if item["ask"]:
            listed = "; ".join(
                f"{tx['id']} ({str(tx['transaction_date'])[:10]}, "
                f"{_kronor(int(tx['amount']))})"
                for tx in item["ask"]
            )
            parts.append(
                "Följande transaktioner liknar avtalets men ligger i ett "
                "räkenskapsår som underlaget inte är godkänt för: "
                f"{listed}. Bokför dem inte. Lägg fram dem med "
                "foresla_avtalsbokforing (samma motkonto) och avsluta."
            )
        parts.append(
            "Anropa inte registrera_avstaende: underlaget är godkänt. "
            "Kan en transaktion inte bokföras, avsluta med en mening om varför."
        )
        return "\n".join(parts)

    @staticmethod
    def _instructions(source_id: str, work: Mapping[str, Any]) -> str:
        lines = [
            "Bokför var och en av transaktionerna nedan med posta_verifikation, "
            "en verifikation per transaktion: date = transaktionens datum, "
            "period_id enligt nedan, rows exakt som angivet, "
            f'intake_source_ids = ["{source_id}"] och bank_transaction_ids = '
            "[transaktionens id]. Skriv i description vad det är och var raden "
            "finns i kontoutdraget. Passet fortsätter efter varje postning tills "
            "alla är bokförda."
        ]
        for transaction in work["book"]:
            booking: AgreementBooking = work["bookings"][transaction["id"]]
            rows = ", ".join(
                f"{r['account']} {'debet' if r.get('debit') else 'kredit'} "
                f"{r.get('debit') or r.get('credit')} öre"
                for r in booking.rows()
            )
            lines.append(
                f"- {transaction['id']}: {str(transaction['transaction_date'])[:10]}, "
                f"konto {transaction['account_code']}, "
                f"{_kronor(int(transaction['amount']))}, "
                f"\"{normalize_text(transaction['description'])}\", "
                f"period_id {transaction['period_id']}; rows: {rows}"
            )
        return "\n".join(lines)

    def record_followup_outcome(
        self,
        source_id: str,
        transaction_ids: Sequence[str],
        *,
        agent_run_id: Optional[str],
        reason: str,
    ) -> None:
        """After a follow-up session: every transaction it was to book that
        is still open gets an attempt row, so the pass does not pay for it
        again. It stays open for a human."""
        work = self._work(source_id)
        open_ids = {tx["id"] for tx in work["book"]} | {tx["id"] for tx in work["ask"]}
        booking = work["booking"]
        if booking is None:
            return
        with db.transaction():
            for transaction_id in transaction_ids:
                if transaction_id not in open_ids:
                    continue
                if AgreementBookingRepository.pending_for_source(source_id):
                    continue  # the session raised a card: the card decides
                AgreementBookingRepository.record_attempt(
                    booking_id=work["bookings"].get(transaction_id, booking).id,
                    bank_transaction_id=transaction_id,
                    agent_run_id=agent_run_id,
                    reason=reason[:500] or "agent_no_outcome",
                    _commit=False,
                )

    # -- checks ------------------------------------------------------------

    @staticmethod
    def _open_transaction(transaction_id: str) -> Dict[str, Any]:
        transaction = BankInputRepository.get_transaction_with_account(transaction_id)
        if transaction is None:
            raise ValidationError(
                "bank_transaction_not_found",
                f"No statement transaction {transaction_id}",
                f"bank_transaction_id={transaction_id}",
            )
        if not AgreementBookingService._is_open(transaction_id, transaction):
            raise ValidationError(
                "bank_transaction_accounted",
                "The transaction already has a voucher",
                f"bank_transaction_id={transaction_id}",
            )
        return transaction

    @staticmethod
    def _fiscal_year_of(transactions: List[Dict[str, Any]]) -> Any:
        from services.fiscal_years import FiscalYearService

        years = {
            getattr(FiscalYearService.containing(transaction_day(tx)), "id", None)
            for tx in transactions
        }
        if None in years:
            raise ValidationError(
                "underlag_outside_fiscal_years",
                "A transaction is dated outside every fiscal year",
                "Propose the fiscal year first (foresla_rakenskapsar)",
            )
        if len(years) != 1:
            raise ValidationError(
                "agreement_spans_fiscal_years",
                "An agreement card covers one fiscal year",
                "Propose one card per fiscal year",
            )
        year_id = years.pop()
        assert year_id is not None
        fiscal_year = PeriodRepository.get_fiscal_year(year_id)
        assert fiscal_year is not None
        return fiscal_year

    @staticmethod
    def _counter_account(code: str, account_code: str) -> str:
        code = (code or "").strip()
        if _VAT_ACCOUNT_RANGE[0] <= code <= _VAT_ACCOUNT_RANGE[1]:
            raise ValidationError(
                "agreement_with_vat",
                "An agreement booked from the statement carries no VAT",
                "A purchase with VAT is booked from its receipt or invoice",
            )
        account = AccountRepository.get(code)
        if account is None or not account.active:
            raise ValidationError(
                "account_not_found",
                f"No active account {code!r} in the chart",
                f"counter_account={code}",
            )
        if code == account_code:
            raise ValidationError(
                "agreement_counter_is_bank",
                "The counter account cannot be the statement's own account",
                f"counter_account={code}",
            )
        return code


# -- helpers -----------------------------------------------------------------


def _open_period(transaction: Mapping[str, Any]) -> Optional[Any]:
    from services.fiscal_years import FiscalYearService

    day = transaction_day(dict(transaction))
    fiscal_year = FiscalYearService.containing(day)
    if fiscal_year is None or fiscal_year.locked:
        return None
    period = PeriodRepository.get_period_by_date(fiscal_year.id, day)
    if period is None or period.locked:
        return None
    return period


def _year_end(fiscal_year_id: str) -> date:
    fiscal_year = PeriodRepository.get_fiscal_year(fiscal_year_id)
    assert fiscal_year is not None
    return fiscal_year.end_date


def _year_label(fiscal_year: Any) -> str:
    start, end = fiscal_year.start_date, fiscal_year.end_date
    if start.month == 1 and start.day == 1 and end.year == start.year:
        return str(start.year)
    return f"räkenskapsåret {start.isoformat()}–{end.isoformat()}"


def _kronor(amount_ore: int) -> str:
    kronor = abs(amount_ore) / 100
    text = f"{kronor:,.2f}".replace(",", " ").replace(".", ",")
    if text.endswith(",00"):
        text = text[:-3]
    return f"{text} kr"


def _row_key(rows: Sequence[Mapping[str, Any]]) -> Counter:
    return Counter(
        (str(r["account"]), int(r.get("debit") or 0), int(r.get("credit") or 0))
        for r in rows
        if (r.get("debit") or r.get("credit"))
    )
