"""Domain types and enumerations."""

from enum import Enum


class VoucherStatus(str, Enum):
    """Voucher lifecycle status."""
    DRAFT = "draft"
    POSTED = "posted"


class VoucherSeries(str, Enum):
    """Voucher series (BFL §5 kap 6)."""
    A = "A"  # Normal vouchers
    B = "B"  # Correction vouchers


class AccountType(str, Enum):
    """Account classification (BAS 2026)."""
    ASSET = "asset"  # Tillgångar (1000-1999)
    LIABILITY = "liability"  # Skulder (2000-2999)
    EQUITY = "equity"  # Eget kapital (2900-2999)
    REVENUE = "revenue"  # Intäkter (3000-3999)
    EXPENSE = "expense"  # Kostnader (4000-8999)
    VAT_OUT = "vat_out"  # Utgående moms (2610-2639)
    VAT_IN = "vat_in"  # Ingående moms (2640-2659)
    CORRECTION = "correction"  # Konto för rättelser


class AuditAction(str, Enum):
    """Audit trail actions."""
    CREATED = "created"
    UPDATED = "updated"
    POSTED = "posted"
    SENT = "sent"
    BOOKED = "booked"
    LOCKED = "locked"
    DELETED = "deleted"
    CORRECTED = "corrected"


class PeriodLockStatus(str, Enum):
    """Period lock state."""
    OPEN = "open"
    LOCKED = "locked"
