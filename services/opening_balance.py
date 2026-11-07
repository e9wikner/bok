"""Opening balance (ingående balans, IB) of a fiscal year.

IB is not a voucher: it records no business transaction, it is the
previous fiscal year's closing position (balanskontinuitet). So:

- A fiscal year with a preceding fiscal year in the books has its IB
  *derived* on every read: the previous year's IB plus its posted
  movements on the balance accounts (class 1-2), with the year's net on the
  result accounts (class 3-8) -- the result not yet closed to equity --
  carried to 2099. It follows every change to the previous year until that
  year is locked, with nothing to update or re-post.
- The first fiscal year in the books has nothing to derive from: its IB is
  *stated* -- from an SIE4 file's `#IB 0`, or entered -- and kept in
  `opening_balances`, editable until the year is locked.

A stated IB for a year that has a predecessor (an SIE4 file imported after
its previous year) does not count; it is kept only to be reconciled
against the derived one (`stated_differences`).

Amounts are öre, debit positive (SIE4 sign convention).
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

from domain.models import FiscalYear
from domain.types import AuditAction
from domain.validation import ValidationError
from repositories.audit_repo import AuditRepository
from repositories.opening_balance_repo import OpeningBalanceRepository
from repositories.period_repo import PeriodRepository

# Årets resultat (BAS): where the previous year's unclosed result lands.
RESULT_ACCOUNT = "2099"

SOURCE_DERIVED = "derived"
SOURCE_STATED = "stated"
SOURCE_NONE = "none"


def is_balance_account(code: str) -> bool:
    return code[:1] in ("1", "2")


def is_result_account(code: str) -> bool:
    return code[:1] in ("3", "4", "5", "6", "7", "8")


def balance_differences(
    stated: Dict[str, int], derived: Dict[str, int]
) -> Dict[str, Tuple[int, int]]:
    """Accounts where two IBs disagree: `{account: (stated, derived)}`."""
    return {
        code: (stated.get(code, 0), derived.get(code, 0))
        for code in sorted(set(stated) | set(derived))
        if stated.get(code, 0) != derived.get(code, 0)
    }


def carry_forward(opening: Dict[str, int], movements: Dict[str, int]) -> Dict[str, int]:
    """The next year's IB from one year's IB and posted movements."""
    closing: Dict[str, int] = defaultdict(int)
    for code, amount in opening.items():
        if is_balance_account(code):
            closing[code] += amount
    result = 0
    for code, net in movements.items():
        if is_balance_account(code):
            closing[code] += net
        elif is_result_account(code):
            result += net
    closing[RESULT_ACCOUNT] += result
    return {code: amount for code, amount in closing.items() if amount != 0}


@dataclass
class OpeningBalance:
    fiscal_year_id: str
    source: str
    balances: Dict[str, int]
    previous_fiscal_year_id: Optional[str] = None
    stated_differences: Dict[str, Tuple[int, int]] = field(default_factory=dict)

    @property
    def balanced(self) -> bool:
        return sum(self.balances.values()) == 0


class OpeningBalanceService:
    """Reads and states the IB of a fiscal year."""

    def __init__(self):
        self.periods = PeriodRepository()
        self.repo = OpeningBalanceRepository()
        self.audit = AuditRepository()

    def balances(self, fiscal_year_id: str) -> Dict[str, int]:
        """The IB that counts for the fiscal year, per account."""
        return self.get(fiscal_year_id).balances

    def get(self, fiscal_year_id: str) -> OpeningBalance:
        years = self.periods.list_fiscal_years()
        fiscal_year = next((y for y in years if y.id == fiscal_year_id), None)
        if fiscal_year is None:
            raise ValidationError("fiscal_year_not_found", "Fiscal year not found")

        chain = [fiscal_year]
        while (previous := self._previous(chain[-1], years)) is not None:
            chain.append(previous)
        chain.reverse()  # oldest first, the requested year last

        stated_first = {
            code: amount
            for code, amount in self.repo.get_stated(chain[0].id).items()
            if is_balance_account(code)
        }
        if len(chain) == 1:
            return OpeningBalance(
                fiscal_year_id=fiscal_year_id,
                source=SOURCE_STATED if stated_first else SOURCE_NONE,
                balances=stated_first,
            )

        balances = stated_first
        for year in chain[:-1]:
            balances = carry_forward(balances, self.repo.movements(year.id))

        stated = self.repo.get_stated(fiscal_year_id)
        return OpeningBalance(
            fiscal_year_id=fiscal_year_id,
            source=SOURCE_DERIVED,
            balances=balances,
            previous_fiscal_year_id=chain[-2].id,
            stated_differences=(
                balance_differences(stated, balances) if stated else {}
            ),
        )

    def position_at(self, day: date) -> Dict[str, int]:
        """Balance accounts at the start of *day*: the IB of the fiscal year
        holding it plus that year's movements before it. After the last
        fiscal year, that year's closing position; before the first, nothing.
        """
        years = self.periods.list_fiscal_years()
        holding = next((y for y in years if y.start_date <= day <= y.end_date), None)
        if holding is not None:
            position: Dict[str, int] = defaultdict(int, self.balances(holding.id))
            for code, net in self.repo.movements(holding.id, before=day).items():
                if is_balance_account(code):
                    position[code] += net
            return {code: amount for code, amount in position.items() if amount}
        earlier = [y for y in years if y.end_date < day]
        if not earlier:
            return {}
        last = max(earlier, key=lambda y: y.end_date)
        return carry_forward(self.balances(last.id), self.repo.movements(last.id))

    def previous_fiscal_year(self, fiscal_year_id: str) -> Optional[FiscalYear]:
        years = self.periods.list_fiscal_years()
        fiscal_year = next((y for y in years if y.id == fiscal_year_id), None)
        return self._previous(fiscal_year, years) if fiscal_year else None

    def next_fiscal_year(self, fiscal_year_id: str) -> Optional[FiscalYear]:
        years = self.periods.list_fiscal_years()
        fiscal_year = next((y for y in years if y.id == fiscal_year_id), None)
        if fiscal_year is None:
            return None
        later = [y for y in years if y.start_date > fiscal_year.end_date]
        return min(later, key=lambda y: y.start_date) if later else None

    def state(
        self,
        fiscal_year_id: str,
        balances: Dict[str, int],
        actor: str,
        require_first_year: bool = True,
    ) -> OpeningBalance:
        """Replace the stated IB of a fiscal year.

        It counts only for the first fiscal year in the books; for a later
        year `require_first_year` refuses it (`opening_balance_derived`) --
        the SIE4 import passes False to keep a file's IB for reconciliation.
        A stated IB that counts must balance.
        """
        from repositories.account_repo import AccountRepository

        fiscal_year = self.periods.get_fiscal_year(fiscal_year_id)
        if fiscal_year is None:
            raise ValidationError("fiscal_year_not_found", "Fiscal year not found")
        if fiscal_year.locked:
            raise ValidationError(
                "fiscal_year_locked",
                "Fiscal year is locked",
                "the opening balance of a locked fiscal year cannot change",
            )

        balances = {code: amount for code, amount in balances.items() if amount}
        not_balance = sorted(c for c in balances if not is_balance_account(c))
        if not_balance:
            raise ValidationError(
                "opening_balance_not_balance_account",
                "Opening balances are only for balance accounts (class 1-2)",
                f"accounts={','.join(not_balance)}",
            )
        missing = sorted(c for c in balances if not AccountRepository.exists(c))
        if missing:
            raise ValidationError(
                "account_not_found",
                "Account not found",
                f"accounts={','.join(missing)}",
            )

        is_first_year = (
            self._previous(fiscal_year, self.periods.list_fiscal_years()) is None
        )
        if require_first_year and not is_first_year:
            raise ValidationError(
                "opening_balance_derived",
                "The fiscal year's opening balance is derived from the previous year",
                "only the first fiscal year in the books has a stated opening balance",
            )
        total = sum(balances.values())
        if is_first_year and total != 0:
            raise ValidationError(
                "opening_balance_unbalanced",
                "Opening balance does not balance",
                f"debit-credit={total}",
            )

        from db.database import db

        before = self.repo.get_stated(fiscal_year_id)
        with db.transaction():
            self.repo.replace_stated(fiscal_year_id, balances, actor, _commit=False)
            self.audit.log(
                entity_type="opening_balance",
                entity_id=fiscal_year_id,
                action=(
                    AuditAction.UPDATED.value if before else AuditAction.CREATED.value
                ),
                actor=actor,
                payload={
                    "fiscal_year": f"{fiscal_year.start_date} - {fiscal_year.end_date}",
                    "before": before,
                    "after": balances,
                },
                _commit=False,
            )
        return self.get(fiscal_year_id)

    @staticmethod
    def _previous(
        fiscal_year: FiscalYear, years: List[FiscalYear]
    ) -> Optional[FiscalYear]:
        earlier = [y for y in years if y.end_date < fiscal_year.start_date]
        return max(earlier, key=lambda y: y.end_date) if earlier else None
