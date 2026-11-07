"""Bank reconciliation: the statement's balance against the ledger's.

For each account a statement has been imported for, the newest statement
that states a balance (`domain/statement_balance.py`) is compared with the
ledger's balance on the account at the end of the statement's day. A
difference means something on the statement is not booked, or something is
booked that the bank never saw -- `StatementMatchService.unaccounted_transactions`
lists the first kind.

Read-only. The stored file is read again on every call: the balance is not
kept in the database, so statements imported before this existed reconcile
too.
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from domain.statement_balance import statement_balance
from repositories.bank_input_repo import BankInputRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Reconciliation:
    account_code: str
    day: date
    statement_balance_ore: int
    ledger_balance_ore: int
    bank_input_id: str
    filename: str

    @property
    def difference_ore(self) -> int:
        """Statement minus ledger: positive when the bank holds more."""
        return self.statement_balance_ore - self.ledger_balance_ore

    def to_dict(self) -> dict:
        return {
            "account_code": self.account_code,
            "date": self.day.isoformat(),
            "statement_balance_ore": self.statement_balance_ore,
            "ledger_balance_ore": self.ledger_balance_ore,
            "difference_ore": self.difference_ore,
            "bank_input_id": self.bank_input_id,
            "filename": self.filename,
        }


class BankReconciliationService:
    def __init__(self) -> None:
        self.inputs = BankInputRepository()

    def latest(
        self, date_from: Optional[date] = None, date_to: Optional[date] = None
    ) -> list[Reconciliation]:
        """One per account: the newest stated balance, if its day lies
        within `date_from`..`date_to`. Sorted by account."""
        # Deferred imports (AGENTS.md: service-to-service imports wait until
        # the method runs).
        from services.bank_inputs import BankInputError, BankInputService
        from services.opening_balance import OpeningBalanceService

        files = BankInputService()
        newest: dict[str, tuple[date, int, dict]] = {}
        for row in self.inputs.list_processed_inputs_with_account():
            try:
                bank_input = files.get_bank_input(row["id"])
                content = files.resolve_input_file(bank_input).read_bytes()
                stated = statement_balance(content.decode("utf-8-sig"))
            except (BankInputError, OSError, UnicodeDecodeError, ValueError):
                logger.warning("bank reconciliation skipped input %s", row["id"])
                continue
            if stated is None:
                continue
            seen = newest.get(row["account_code"])
            # Rows come newest upload first: an older upload of the same
            # day does not replace a newer one.
            if seen is None or stated.day > seen[0]:
                newest[row["account_code"]] = (stated.day, stated.balance_ore, row)

        balances = OpeningBalanceService()
        out = []
        for account, (day, balance, row) in sorted(newest.items()):
            if (date_from and day < date_from) or (date_to and day > date_to):
                continue
            ledger = balances.position_at(day + timedelta(days=1)).get(account, 0)
            out.append(
                Reconciliation(
                    account_code=account,
                    day=day,
                    statement_balance_ore=balance,
                    ledger_balance_ore=ledger,
                    bank_input_id=row["id"],
                    filename=row["original_filename"],
                )
            )
        return out
