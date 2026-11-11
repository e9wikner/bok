"""Kontoutdragets okopplade rader i intagspasset (migration 049).

For a movement that is only a movement on the bank or tax account, the
statement's row is the underlag (`docs/to_agent/03_bokforingsinstruktion.md`,
"Kontoutdrag som underlag"). Such a transaction never comes into the intake
queue -- nothing was dropped for it -- so the pass used to finish with it
still open, until a human pointed at it. After the queue and the agreement
follow-ups, the pass now gives each open transaction one session:

- open: not linked, not matched, not ignored (`StatementMatchService`);
- `match = "none"`: a voucher that could be it is for a human to link, and a
  purchase booked from its receipt (`covered_by_purchase`) is already booked;
- in an open period of an existing fiscal year;
- not named by an agreement card or tried by one of its follow-ups -- the
  agreement decides those;
- not tried by this pass before (`statement_followup_attempts`).

The session books the transaction with `posta_verifikation` or ends with a
sentence on why not. A transaction it leaves open gets an attempt row and is
not paid for again; it stays in the open list for a human.
"""

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from config import settings
from db.database import db
from domain.agreement_booking import normalize_text
from repositories.bank_input_repo import BankInputRepository
from repositories.statement_followup_repo import StatementFollowupRepository

logger = logging.getLogger(__name__)


def _first_input(transaction_id: str) -> List[str]:
    return BankInputRepository.list_input_ids_for_transaction(transaction_id)[:1]


def _kronor(amount_ore: int) -> str:
    sign = "-" if amount_ore < 0 else ""
    whole, ore = divmod(abs(amount_ore), 100)
    return f"{sign}{whole:,}".replace(",", " ") + f",{ore:02d} kr"


class StatementFollowupService:
    def followups(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """The open transactions the pass is to take up, oldest first. Each
        is the transaction (as `get_transaction_with_account` gives it) plus
        the `period_id` it is booked in, the statement it came with
        (`bank_input_ids`) and, for a transfer, its other side
        (`counterpart`, see `_counterpart`)."""
        # Deferred imports (AGENTS.md: service-to-service imports wait until
        # the method runs).
        from services.statement_match import StatementMatchService

        matcher = StatementMatchService()
        skip = self._skip_ids()
        items: List[Dict[str, Any]] = []
        for match in matcher.open_transactions():
            item = self._item(matcher, match, skip)
            if item is None:
                continue
            items.append(item)
            if limit is not None and len(items) >= limit:
                break
        return items

    def refreshed(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        """*transaction_id* as `followups` would give it now, or `None` when
        it is no longer one to take up.

        The pass reads its list once; a session before this one may have
        booked this very transaction -- the other side of the transfer it
        booked -- and a second session would book the transfer twice."""
        from services.statement_match import StatementMatchService

        transaction = BankInputRepository.get_transaction_with_account(transaction_id)
        if transaction is None or transaction["linked_voucher_id"] is not None:
            return None
        if transaction["matched_voucher_id"] is not None:
            return None
        if transaction.get("status") == "ignored":
            return None
        matcher = StatementMatchService()
        match = matcher.match_transaction(transaction)
        return self._item(matcher, match, self._skip_ids())

    @staticmethod
    def _skip_ids() -> set:
        return (
            StatementFollowupRepository.attempted_transaction_ids()
            | StatementFollowupRepository.agreement_transaction_ids()
        )

    def _item(self, matcher, match, skip: set) -> Optional[Dict[str, Any]]:
        from services.agreement_booking import _open_period

        if match.bank_transaction_id in skip or match.kind != "none":
            return None
        if matcher.purchases_covering(match):
            return None
        transaction = BankInputRepository.get_transaction_with_account(
            match.bank_transaction_id
        )
        if transaction is None:
            return None
        period = _open_period(transaction)
        if period is None:
            return None
        return {
            **transaction,
            "period_id": period.id,
            # The statement the transaction came in with: the posting's
            # traceability when no underlag stands behind it
            # (`voucher_posting._ensure_agent_voucher_has_...`).
            "bank_input_ids": _first_input(transaction["id"]),
            # An agreement card decides its own transactions; one this pass
            # tried alone may still be the other side of a transfer.
            "counterpart": self._counterpart(
                transaction, StatementFollowupRepository.agreement_transaction_ids()
            ),
        }

    @staticmethod
    def _counterpart(
        transaction: Dict[str, Any], excluded: set
    ) -> Optional[Dict[str, Any]]:
        """The other side of a transfer between own accounts, when there is
        exactly one: an open transaction of the opposite amount on another
        statement account, dated within the candidate window. The session
        books both on one voucher, so that it has both statements as
        underlag from the start and neither side is booked a second time."""
        from domain.statement_coverage import is_statement_account
        from services.agreement_booking import _open_period
        from services.statement_match import CANDIDATE_WINDOW_DAYS

        day = date.fromisoformat(str(transaction["transaction_date"])[:10])
        window = timedelta(days=CANDIDATE_WINDOW_DAYS)
        others = [
            tx
            for tx in BankInputRepository.list_open_transactions_for_amount(
                amount_ore=-int(transaction["amount"]),
                date_from=(day - window).isoformat(),
                date_to=(day + window).isoformat(),
            )
            if tx["account_code"] != transaction["account_code"]
            and is_statement_account(tx["account_code"] or "")
            and tx["id"] not in excluded
        ]
        if len(others) != 1:
            return None
        other = others[0]
        # The voucher is dated on the side the money left; its period may
        # be another month than this row's (2026-08-29 -> 2026-09-01).
        outgoing = transaction if int(transaction["amount"]) < 0 else other
        period = _open_period(outgoing)
        if period is None:
            return None
        return {
            **other,
            "bank_input_ids": _first_input(other["id"]),
            "voucher_date": str(outgoing["transaction_date"])[:10],
            "voucher_period_id": period.id,
        }

    def has_followups(self) -> bool:
        return bool(self.followups(limit=1))

    def wake_if_followups(self) -> None:
        """After a statement import: wake the pass when a transaction is
        left for it. Never raises -- the import already succeeded."""
        try:
            if not settings.agent_runtime_enabled or not self.has_followups():
                return
            from services.agreement_booking import AgreementBookingService

            AgreementBookingService.wake_pass()
        except Exception:
            logger.exception("Could not look for statement follow-ups")

    @staticmethod
    def followup_turn(transaction: Dict[str, Any]) -> str:
        """The user turn of a session about one statement transaction."""
        counterpart = normalize_text(transaction.get("counterpart_name"))
        lines = [
            "Kontoutdragets rad nedan har ingen verifikation och inget "
            'underlag i kön. Läs "Kontoutdrag som underlag" i '
            "bokföringsinstruktionen.",
            f"- bank_transaction_id: {transaction['id']}",
            f"- datum: {str(transaction['transaction_date'])[:10]}",
            f"- konto: {transaction['account_code']}",
            f"- belopp: {_kronor(int(transaction['amount']))}",
            f"- text: \"{normalize_text(transaction.get('description'))}\"",
        ]
        if counterpart:
            lines.append(f'- motpart: "{counterpart}"')
        lines += [
            f"- period_id: {transaction['period_id']}",
            f"- bank_input_ids: {list(transaction['bank_input_ids'])}",
        ]
        other = transaction.get("counterpart")
        if other:
            lines += [
                "",
                "Ett annat kontoutdrag har en okopplad rad med motsatt belopp "
                "några dagar ifrån:",
                f"- bank_transaction_id: {other['id']}",
                f"- datum: {str(other['transaction_date'])[:10]}",
                f"- konto: {other['account_code']}",
                f"- belopp: {_kronor(int(other['amount']))}",
                f"- text: \"{normalize_text(other.get('description'))}\"",
                f"- bank_input_ids: {list(other['bank_input_ids'])}",
                "Är de två raderna samma överföring mellan egna konton, bokför "
                "den som en verifikation: date = "
                f"{other['voucher_date']} (dagen pengarna lämnade kontot), "
                f"period_id = {other['voucher_period_id']}, båda raderna i "
                "bank_transaction_ids och båda radernas bank_input_ids. Bokför "
                "aldrig överföringen en gång per rad.",
            ]
        lines += [
            "",
            "Är raden en händelse där kontoutdraget är underlaget -- en "
            "överföring mellan egna konton, en skattekontohändelse, en "
            "bankavgift, en kundinbetalning eller betalningen av en "
            "leverantörsfaktura som redan är bokförd (sök den med "
            "sok_verifikationer) -- bokför den med posta_verifikation: date = "
            "radens datum, period_id och bank_input_ids enligt ovan, "
            "bank_transaction_ids = [radens id], utan intake_source_ids. Skriv i description var "
            "raden finns i kontoutdraget.",
            "Är det ett köp, en lön, en deklaration eller något annat som "
            "behöver sitt eget underlag, eller går konteringen inte att avgöra "
            "från raden, bokför inte. Avsluta då med en mening om varför. "
            "Raden står kvar för användaren. Anropa inte registrera_avstaende "
            "eller be_om_beslut: det finns inget underlag och ingen tråd.",
        ]
        return "\n".join(lines)

    @staticmethod
    def record_outcome(
        transaction_id: str, *, agent_run_id: Optional[str], reason: str
    ) -> None:
        """After a session: a transaction still open gets an attempt row, so
        the pass does not pay for it again."""
        transaction = BankInputRepository.get_transaction_with_account(transaction_id)
        if transaction is None or transaction["linked_voucher_id"] is not None:
            return
        with db.transaction():
            StatementFollowupRepository.record_attempt(
                bank_transaction_id=transaction_id,
                agent_run_id=agent_run_id,
                reason=(reason or "agent_no_outcome")[:500],
                _commit=False,
            )
