"""Domain models for customers, articles and invoice drafts."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional


@dataclass
class Customer:
    id: str
    name: str
    org_number: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    payment_terms_days: int = 30
    contact_person: Optional[str] = None
    active: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class Article:
    id: str
    article_number: str
    name: str
    description: Optional[str] = None
    unit: str = "st"
    unit_price: int = 0
    vat_code: str = "MP1"
    revenue_account: str = "3010"
    active: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class InvoiceDraftRow:
    id: str
    draft_id: str
    description: str
    quantity: int  # legacy, rounded up; compute on quantity_centi (§4.2)
    unit_price: int
    vat_code: str
    revenue_account: str
    amount_ex_vat: int
    vat_amount: int
    amount_inc_vat: int
    article_id: Optional[str] = None
    source_note: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    quantity_centi: Optional[int] = None  # quantity × 100 (§4.2)
    unit: str = "st"
    delivery_from: Optional[date] = None
    delivery_to: Optional[date] = None
    delivery_month: Optional[str] = None  # YYYY-MM
    article_number: Optional[str] = None


@dataclass
class InvoiceDraft:
    id: str
    customer_name: str
    invoice_date: date
    due_date: date
    customer_id: Optional[str] = None
    customer_org_number: Optional[str] = None
    customer_email: Optional[str] = None
    reference: Optional[str] = None
    description: Optional[str] = None
    status: str = "needs_review"
    amount_ex_vat: int = 0
    vat_amount: int = 0
    amount_inc_vat: int = 0
    agent_summary: Optional[str] = None
    agent_confidence: Optional[float] = None
    agent_warnings: Optional[str] = None
    approved_invoice_id: Optional[str] = None
    approved_voucher_id: Optional[str] = None
    rows: List[InvoiceDraftRow] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    created_by: str = "system"
    updated_at: datetime = field(default_factory=datetime.now)
    invoice_number: Optional[str] = None  # proposed, not unique (§4.1)
    customer_address: Optional[str] = None
    delivery_from: Optional[date] = None  # for rows without their own
    delivery_to: Optional[date] = None
    delivery_month: Optional[str] = None
