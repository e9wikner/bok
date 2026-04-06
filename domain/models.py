"""Domain models for the accounting system."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, List
from domain.types import VoucherStatus, VoucherSeries, AccountType, AuditAction


@dataclass
class FiscalYear:
    """Räkenskapsår (accounting year)."""
    id: str
    start_date: date
    end_date: date
    locked: bool = False
    locked_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)

    def is_open(self) -> bool:
        """Check if fiscal year is open for posting."""
        return not self.locked


@dataclass
class Period:
    """Redovisningsperiod (accounting period - typically monthly)."""
    id: str
    fiscal_year_id: str
    year: int
    month: int
    start_date: date
    end_date: date
    locked: bool = False
    locked_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)

    def is_open(self) -> bool:
        """Check if period is open for posting (BFL varaktighet requirement)."""
        return not self.locked


@dataclass
class Account:
    """Konto (chart of accounts - BAS 2026)."""
    code: str  # e.g., "1510"
    name: str
    account_type: AccountType
    vat_code: Optional[str] = None  # e.g., "MP1" for 25% VAT
    sru_code: Optional[str] = None  # Skatteverkets rapporteringskoder
    active: bool = True
    created_at: datetime = field(default_factory=datetime.now)

    def is_debit_account(self) -> bool:
        """Check if account normally has debit balance (assets, expenses)."""
        return self.account_type in [AccountType.ASSET, AccountType.EXPENSE, AccountType.VAT_IN]

    def is_credit_account(self) -> bool:
        """Check if account normally has credit balance (liabilities, equity, revenue)."""
        return self.account_type in [AccountType.LIABILITY, AccountType.EQUITY, AccountType.REVENUE, AccountType.VAT_OUT]


@dataclass
class VoucherRow:
    """Konteringsrad (accounting row in a voucher)."""
    id: str
    voucher_id: str
    account_code: str
    debit: int = 0  # In öre (1 kr = 100)
    credit: int = 0  # In öre
    description: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    def is_debit(self) -> bool:
        """Check if this row is a debit entry."""
        return self.debit > 0

    def is_credit(self) -> bool:
        """Check if this row is a credit entry."""
        return self.credit > 0

    def get_amount(self) -> int:
        """Get the amount (debit or credit) in öre."""
        return self.debit if self.is_debit() else self.credit


@dataclass
class Voucher:
    """Verifikation (accounting voucher - BFL §5 kap 6)."""
    id: str
    series: VoucherSeries  # A or B (B for corrections)
    number: int
    date: date
    period_id: str
    description: str
    status: VoucherStatus = VoucherStatus.DRAFT
    fiscal_year_id: Optional[str] = None
    rows: List[VoucherRow] = field(default_factory=list)
    correction_of: Optional[str] = None  # Reference to original voucher if this is a correction
    created_at: datetime = field(default_factory=datetime.now)
    created_by: str = "system"
    posted_at: Optional[datetime] = None

    def is_posted(self) -> bool:
        """Check if voucher is posted (varaktighet - immutable)."""
        return self.status == VoucherStatus.POSTED

    def is_draft(self) -> bool:
        """Check if voucher is still in draft status."""
        return self.status == VoucherStatus.DRAFT

    def is_balanced(self) -> bool:
        """Validate that debit = credit (BFL balansräkning requirement)."""
        total_debit = sum(row.debit for row in self.rows)
        total_credit = sum(row.credit for row in self.rows)
        return total_debit == total_credit

    def get_total_debit(self) -> int:
        """Get total debit amount in öre."""
        return sum(row.debit for row in self.rows)

    def get_total_credit(self) -> int:
        """Get total credit amount in öre."""
        return sum(row.credit for row in self.rows)

    def is_correction(self) -> bool:
        """Check if this is a correction voucher (B-series)."""
        return self.series == VoucherSeries.B or self.correction_of is not None


@dataclass
class AuditLogEntry:
    """Behandlingshistorik (audit log entry)."""
    id: str
    entity_type: str  # voucher, period, account, etc
    entity_id: str
    action: AuditAction
    actor: str  # User ID or "system"
    payload: Optional[dict] = None  # JSON with before/after values
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class VoucherAttachment:
    """Verifikationsbilag (voucher attachment)."""
    id: str
    voucher_id: str
    filename: str
    sha256: str
    mime_type: str
    stored_path: str
    size_bytes: int
    uploaded_at: datetime = field(default_factory=datetime.now)


@dataclass
class LearningRule:
    """Inlärd regel från användarkorrigeringar (ML-lite)."""
    id: str
    pattern_type: str  # 'keyword', 'regex', 'counterparty', 'amount_range', 'composite'
    pattern_value: str
    corrected_account: str
    original_account: Optional[str] = None
    company_id: Optional[str] = None
    description: Optional[str] = None
    confidence: float = 0.5
    usage_count: int = 1
    success_count: int = 1
    source_voucher_id: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    last_used: Optional[datetime] = None
    last_confirmed: Optional[datetime] = None
    is_active: bool = True
    is_golden: bool = False

    def is_reliable(self, threshold: float = 0.8) -> bool:
        """Check if rule has high enough confidence to be used."""
        return self.confidence >= threshold and self.is_active

    def success_rate(self) -> float:
        """Calculate success rate from usage."""
        if self.usage_count == 0:
            return 0.0
        return self.success_count / self.usage_count


@dataclass
class CorrectionHistory:
    """Historik över korrigeringar (audit trail för ML)."""
    id: str
    original_voucher_id: str
    learning_rule_id: Optional[str] = None
    corrected_voucher_id: Optional[str] = None
    original_data: Optional[dict] = None
    corrected_data: Optional[dict] = None
    change_type: Optional[str] = None  # 'account', 'amount', 'description', 'vat_code', 'multiple'
    was_successful: Optional[bool] = None
    corrected_by: Optional[str] = None
    correction_reason: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
