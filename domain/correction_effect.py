"""What a correction did to the voucher it corrects.

A B-series correction is stored as the mechanical reversal of the original
followed by the rows it should have had (§7.1). Read row by row that is
noise: changing 1650 to 2650 on a three-row voucher gives six rows, 1630
debited and credited. What a reader needs is the net per account before and
after -- the voucher as it stood and as it stands -- and whether anything is
left at all (a makulering) or the voucher was changed (an ändring).

Pure: it takes rows and returns the effect. Nothing here is stored; the
posted vouchers stay as they were posted.
"""

from dataclasses import dataclass
from typing import Dict, Iterable, List, Literal, Protocol

CorrectionKind = Literal["makulering", "andring"]


class _Row(Protocol):
    account_code: str
    debit: int
    credit: int


@dataclass(frozen=True)
class AccountChange:
    """One account's net (debit minus credit, öre) before and after."""

    account_code: str
    before: int
    after: int

    @property
    def changed(self) -> bool:
        return self.before != self.after


@dataclass(frozen=True)
class CorrectionEffect:
    kind: CorrectionKind
    # Every account the voucher had before or has after, in the order it
    # first appears: the original's rows first, then accounts the
    # correction added.
    accounts: List[AccountChange]

    @property
    def before_total(self) -> int:
        """The omslutning before: the sum of the positive nets."""
        return sum(a.before for a in self.accounts if a.before > 0)

    @property
    def after_total(self) -> int:
        return sum(a.after for a in self.accounts if a.after > 0)


def _net(rows: Iterable[_Row], into: Dict[str, int]) -> None:
    for row in rows:
        into[row.account_code] = into.get(row.account_code, 0) + (
            row.debit - row.credit
        )


def correction_effect(
    before_rows: Iterable[_Row], correction_rows: Iterable[_Row]
) -> CorrectionEffect:
    """The effect of `correction_rows` on a voucher whose rows -- the
    original's plus any earlier correction's -- are `before_rows`."""
    before: Dict[str, int] = {}
    _net(before_rows, before)
    after = dict(before)
    _net(correction_rows, after)
    accounts = [
        AccountChange(code, before.get(code, 0), after.get(code, 0))
        for code in after
        if before.get(code, 0) != 0 or after.get(code, 0) != 0
    ]
    kind: CorrectionKind = (
        "makulering" if all(a.after == 0 for a in accounts) else "andring"
    )
    return CorrectionEffect(kind=kind, accounts=accounts)
