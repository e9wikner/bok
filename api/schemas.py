"""Pydantic schemas for API requests/responses."""

from pydantic import BaseModel, Field, ConfigDict
from datetime import date as DateType, datetime as DateTimeType
from typing import Optional, List
from decimal import Decimal


# Voucher Schemas

class VoucherRowRequest(BaseModel):
    """Request model for voucher row."""
    account: str = Field(..., description="Account code (e.g., '1510')")
    debit: int = Field(0, description="Debit amount in öre (1 kr = 100)")
    credit: int = Field(0, description="Credit amount in öre (1 kr = 100)")
    description: Optional[str] = None


class VoucherRowResponse(BaseModel):
    """Response model for voucher row."""
    id: str
    voucher_id: str
    account_code: str
    debit: int
    credit: int
    description: Optional[str] = None


class CreateVoucherRequest(BaseModel):
    """Request to create new voucher."""
    series: str = Field("A", description="Voucher series (A=normal, B=correction)")
    date: DateType = Field(..., description="Voucher date")
    period_id: str = Field(..., description="Period ID")
    description: str = Field(..., description="Voucher description")
    rows: List[VoucherRowRequest] = Field(..., description="Accounting rows (min 2)")
    auto_post: bool = Field(False, description="Automatically post after creation")


class VoucherResponse(BaseModel):
    """Response model for voucher."""
    id: str
    series: str
    number: int
    date: DateType
    period_id: str
    description: str
    status: str  # draft, posted
    rows: List[VoucherRowResponse]
    correction_of: Optional[str] = None
    created_at: DateTimeType
    created_by: str
    posted_at: Optional[DateTimeType] = None


# Account Schemas

class CreateAccountRequest(BaseModel):
    """Request to create a new account."""
    code: str = Field(..., description="Account code (e.g., '1930')")
    name: str = Field(..., description="Account name")
    account_type: str = Field(..., description="Account type (asset, liability, equity, revenue, expense)")
    vat_code: Optional[str] = Field(None, description="VAT code if applicable")
    sru_code: Optional[str] = Field(None, description="SRU code for tax reporting")
    active: bool = Field(True, description="Whether account is active")


class AccountResponse(BaseModel):
    """Response model for account."""
    code: str
    name: str
    account_type: str
    vat_code: Optional[str] = None
    sru_code: Optional[str] = None
    active: bool


class AccountListResponse(BaseModel):
    """Response with list of accounts."""
    accounts: List[AccountResponse]
    total: int


# Period Schemas

class PeriodResponse(BaseModel):
    """Response model for period."""
    id: str
    fiscal_year_id: str
    year: int
    month: int
    start_date: DateType
    end_date: DateType
    locked: bool
    locked_at: Optional[DateTimeType] = None
    created_at: DateTimeType


class FiscalYearResponse(BaseModel):
    """Response model for fiscal year."""
    id: str
    start_date: DateType
    end_date: DateType
    locked: bool
    locked_at: Optional[DateTimeType] = None
    created_at: DateTimeType


# Report Schemas

class TrialBalanceRow(BaseModel):
    """Row in trial balance."""
    account_code: str
    debit: int
    credit: int
    balance: int


class TrialBalanceResponse(BaseModel):
    """Trial balance report."""
    period_id: str
    period: str
    as_of: DateType
    rows: List[TrialBalanceRow]
    total_debit: int
    total_credit: int


class AccountLedgerRow(BaseModel):
    """Row in account ledger."""
    date: DateType
    voucher_series: str
    voucher_number: str
    description: str
    debit: int
    credit: int
    balance: int


class AccountLedgerResponse(BaseModel):
    """Account ledger report."""
    account_code: str
    account_name: str
    period_id: str
    rows: List[AccountLedgerRow]
    ending_balance: int


# Audit Schemas

class AuditLogEntryResponse(BaseModel):
    """Audit log entry."""
    id: str
    entity_type: str
    entity_id: str
    action: str
    actor: str
    payload: Optional[dict] = None
    timestamp: DateTimeType


class AuditHistoryResponse(BaseModel):
    """Audit history."""
    entity_type: str
    entity_id: str
    entries: List[AuditLogEntryResponse]


# Error Schemas

class ErrorResponse(BaseModel):
    """Error response."""
    error: str
    code: str
    details: Optional[str] = None
    timestamp: DateTimeType = Field(default_factory=DateTimeType.now)
