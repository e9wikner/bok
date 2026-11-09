"""An agreement booked against the statement transactions it covers
(migration 048, `services/agreement_booking.py`).

An autogiro mandate, a loan agreement or a subscription has no date or
amount of its own. Each transaction it covers is booked from the statement
row -- date and amount -- with the agreement as underlag and the same
kontering: the bank account against one counter account, the whole amount,
no VAT.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class AgreementBooking:
    """One `agreement_bookings` row: the card, the pattern and the kontering.

    `amount_ore` is signed as on the statement: negative when money left the
    bank account (debit `counter_account_code`, credit `account_code`),
    positive when it came in (the other way round)."""

    id: str
    decision_id: str
    thread_id: str
    intake_source_id: str
    fiscal_year_id: str
    account_code: str
    amount_ore: int
    description: str
    counter_account_code: str
    book_option_id: str
    standing_option_id: str
    status: str
    created_by: str
    created_at: datetime
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    bank_transaction_ids: List[str] = field(default_factory=list)

    @property
    def approved(self) -> bool:
        return self.status in ("approved", "approved_standing")

    @property
    def standing(self) -> bool:
        return self.status == "approved_standing"

    def rows(self) -> List[Dict[str, Any]]:
        """The voucher rows for one transaction of the pattern's amount."""
        return kontering(self.account_code, self.counter_account_code, self.amount_ore)

    def matches(self, transaction: Dict[str, Any]) -> bool:
        """Whether a statement transaction is one more of the agreement's:
        same account, same amount, same text."""
        return (
            str(transaction.get("account_code")) == self.account_code
            and int(transaction.get("amount") or 0) == self.amount_ore
            and normalize_text(transaction.get("description")) == self.description
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "decision_id": self.decision_id,
            "thread_id": self.thread_id,
            "intake_source_id": self.intake_source_id,
            "fiscal_year_id": self.fiscal_year_id,
            "account_code": self.account_code,
            "amount_ore": self.amount_ore,
            "description": self.description,
            "counter_account_code": self.counter_account_code,
            "status": self.status,
            "bank_transaction_ids": list(self.bank_transaction_ids),
            "rows": self.rows(),
        }


def normalize_text(value: Optional[str]) -> str:
    """A statement text as the pattern compares it: trimmed, inner
    whitespace collapsed, case kept (a bank does not change case)."""
    return " ".join((value or "").split())


def kontering(account_code: str, counter_account_code: str, amount_ore: int) -> list:
    """Bank against counter account for one transaction of *amount_ore*
    (signed as on the statement)."""
    amount = abs(int(amount_ore))
    if amount_ore < 0:
        return [
            {"account": counter_account_code, "debit": amount},
            {"account": account_code, "credit": amount},
        ]
    return [
        {"account": account_code, "debit": amount},
        {"account": counter_account_code, "credit": amount},
    ]


def transaction_day(transaction: Dict[str, Any]) -> date:
    return date.fromisoformat(str(transaction["transaction_date"])[:10])
