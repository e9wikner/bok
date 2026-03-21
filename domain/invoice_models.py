"""Invoice and payment domain models (Fas 2)."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, List
from enum import Enum


class InvoiceStatus(str, Enum):
    """Invoice lifecycle status."""
    DRAFT = "draft"
    SENT = "sent"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


@dataclass
class InvoiceRow:
    """Row in an invoice."""
    id: str
    invoice_id: str
    description: str
    quantity: int
    unit_price: int  # In öre
    vat_code: str  # MP1 (25%), MP2 (12%), MP3 (6%), MF (0%)
    amount_ex_vat: int  # quantity * unit_price in öre
    vat_amount: int  # Calculated VAT in öre
    amount_inc_vat: int  # amount_ex_vat + vat_amount
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Invoice:
    """Faktura (customer invoice)."""
    id: str
    invoice_number: str  # e.g., "2026001"
    customer_name: str
    customer_org_number: Optional[str]  # Swedish org number
    customer_email: Optional[str]
    invoice_date: date
    due_date: date
    description: Optional[str]
    rows: List[InvoiceRow] = field(default_factory=list)
    amount_ex_vat: int = 0  # In öre
    vat_amount: int = 0  # In öre
    amount_inc_vat: int = 0  # In öre
    status: str = InvoiceStatus.DRAFT
    paid_amount: int = 0  # In öre (cumulative)
    voucher_id: Optional[str] = None  # Linked to accounting voucher
    created_at: datetime = field(default_factory=datetime.now)
    created_by: str = "system"
    sent_at: Optional[datetime] = None
    
    def is_draft(self) -> bool:
        """Check if invoice is still draft."""
        return self.status == InvoiceStatus.DRAFT
    
    def is_sent(self) -> bool:
        """Check if invoice has been sent."""
        return self.status in [InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.PAID, InvoiceStatus.OVERDUE]
    
    def is_paid(self) -> bool:
        """Check if invoice is fully paid."""
        return self.status == InvoiceStatus.PAID
    
    def remaining_amount(self) -> int:
        """Get remaining amount to pay (in öre)."""
        return self.amount_inc_vat - self.paid_amount
    
    def is_overdue(self, as_of_date: Optional[date] = None) -> bool:
        """Check if invoice is overdue."""
        check_date = as_of_date or date.today()
        return (self.due_date < check_date and 
                self.status != InvoiceStatus.PAID and 
                self.status != InvoiceStatus.CANCELLED)


@dataclass
class Payment:
    """Payment for an invoice."""
    id: str
    invoice_id: str
    amount: int  # In öre
    payment_date: date
    payment_method: str  # bank_transfer, card, cash, etc
    reference: Optional[str] = None  # Invoice number, reference code, etc
    voucher_id: Optional[str] = None  # Linked to accounting voucher
    notes: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    created_by: str = "system"


@dataclass
class CreditNote:
    """Kreditfaktura (credit note / refund)."""
    id: str
    credit_note_number: str
    invoice_id: str  # Reference to original invoice
    reason: str  # Reason for credit (e.g., "Return", "Discount", "Correction")
    amount_ex_vat: int  # In öre
    vat_amount: int  # In öre
    amount_inc_vat: int  # In öre
    credit_date: date
    voucher_id: Optional[str] = None  # Linked to accounting voucher
    created_at: datetime = field(default_factory=datetime.now)
    created_by: str = "system"
