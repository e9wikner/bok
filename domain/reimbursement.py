"""Utlägg: a purchase someone paid privately, which the company owes back.

An underlag in the dropzone's `Utlägg/` (`source_type = reimbursement`) is
booked with the debt to the person who paid on 2820. A purchase the company
paid itself, which shows up in one of its statements, is not an utlägg: the
check below finds such a transaction, and a human decides before anything is
booked against 2820 (services/reimbursement_check.py, migration 045).

Pure domain: no SQL, no HTTP.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Iterable, Mapping, Optional, Tuple

#: The debt to the person who paid (BAS: kortfristiga skulder till anställda).
REIMBURSEMENT_ACCOUNT = "2820"

#: A card charge is often settled days after the purchase.
WINDOW_BEFORE_DAYS = 3
WINDOW_AFTER_DAYS = 10

#: A purchase in a foreign currency is converted at Riksbank's rate; the
#: bank converts at its own, so the statement's amount differs a little.
FOREIGN_TOLERANCE = Decimal("0.05")


def window(purchase_date: date) -> Tuple[date, date]:
    return (
        purchase_date - timedelta(days=WINDOW_BEFORE_DAYS),
        purchase_date + timedelta(days=WINDOW_AFTER_DAYS),
    )


def amount_bounds(sek_ore: int, *, foreign: bool) -> Tuple[int, int]:
    """The statement amounts (positive öre) that count as the same purchase:
    exactly the amount in kronor, ±5 % for a converted one."""
    if not foreign:
        return sek_ore, sek_ore
    slack = int((Decimal(sek_ore) * FOREIGN_TOLERANCE).to_integral_value())
    return max(sek_ore - slack, 1), sek_ore + slack


def reimbursement_credit(rows: Iterable[Mapping[str, object]]) -> int:
    """What the voucher credits 2820, in öre: the amount owed back."""
    return sum(
        int(row.get("credit") or 0)  # type: ignore[call-overload]
        for row in rows
        if str(row.get("account", "")) == REIMBURSEMENT_ACCOUNT
    )


@dataclass(frozen=True)
class StatementHit:
    """A transaction in one of the company's statements that looks like the
    purchase on the underlag."""

    bank_transaction_id: str
    date: date
    amount_ore: int
    account_code: Optional[str]
    counterpart_name: Optional[str]
    description: Optional[str]
    linked_voucher_id: Optional[str]
    vendor_hit: bool

    def label(self) -> str:
        from domain.exchange_rate import format_amount

        text = self.counterpart_name or self.description or "utan text"
        account = f" på {self.account_code}" if self.account_code else ""
        return (
            f"{self.date.isoformat()} · {format_amount(Decimal(self.amount_ore) / 100)}"
            f" kr · {text}{account}"
        )

    def as_dict(self) -> dict:
        return {
            "bank_transaction_id": self.bank_transaction_id,
            "date": self.date.isoformat(),
            "amount_ore": self.amount_ore,
            "account_code": self.account_code,
            "counterpart_name": self.counterpart_name,
            "description": self.description,
            "linked_voucher_id": self.linked_voucher_id,
            "vendor_hit": self.vendor_hit,
        }


def vendor_in(vendor: Optional[str], *texts: Optional[str]) -> bool:
    if not vendor or not vendor.strip():
        return False
    needle = vendor.strip().casefold()
    return any(needle in text.casefold() for text in texts if text)


def rank(hits: Iterable[StatementHit], sek_ore: int, purchase_date: date) -> list:
    """The vendor's name first, then the closest amount, then the closest
    date."""
    return sorted(
        hits,
        key=lambda h: (
            not h.vendor_hit,
            abs(h.amount_ore - sek_ore),
            abs((h.date - purchase_date).days),
        ),
    )


@dataclass
class ReimbursementCheck:
    """A decision card asking whether an underlag in Utlägg/ is an utlägg
    or a purchase the company paid (the statement transaction it matched).
    `status` moves only out of `pending`: `reimbursement` or `company_paid`
    on the two answers, `declined` on the exit, `superseded` when a new card
    replaces one answered in free text."""

    id: str
    intake_source_id: str
    bank_transaction_id: str
    decision_id: str
    reimbursement_option_id: str
    company_paid_option_id: str
    thread_id: str
    status: str
    created_by: str
    created_at: datetime
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
