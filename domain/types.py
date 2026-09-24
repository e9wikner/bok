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
    IB = "IB"  # Opening balance vouchers (ingående balans)


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
    REGISTERED = "registered"
    LOCKED = "locked"
    DELETED = "deleted"
    CORRECTED = "corrected"
    APPROVED_AND_BOOKED = "approved_and_booked"
    REJECTED = "rejected"


class PeriodLockStatus(str, Enum):
    """Period lock state."""

    OPEN = "open"
    LOCKED = "locked"


class IntakeStatus(str, Enum):
    """Lifecycle status for uploaded voucher source material."""

    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    SKIPPED = "skipped"
    FAILED = "failed"
    NEEDS_ATTENTION = "needs_attention"
    DELETED = "deleted"


class IntakeSourceType(str, Enum):
    """Classifier for uploaded voucher source material."""

    RECEIPT = "receipt"
    SUPPLIER_INVOICE = "supplier_invoice"
    CUSTOMER_INVOICE = "customer_invoice"
    REIMBURSEMENT = "reimbursement"
    OTHER = "other"


class BankInputStatus(str, Enum):
    """Lifecycle status for uploaded bank input files."""

    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"


class ThreadViewKey(str, Enum):
    """The seven views a thread can belong to (SPEC-tradar.md §5).

    `README.md`: "Chatten hör till vyn, inte till appen. Varje vy har sin
    egen tråd." The list is **closed and validated** — an unknown key gives
    `404`, not an empty thread, because a typo in the client would otherwise
    create a thread nobody ever finds their way back to.

    No company part. Decision §12.2: single-tenant, and a `view_key` that
    carried the company would look like a separation boundary without being
    one, since the bookkeeping it refers to is not separated either. The
    company goes in the day multi-tenancy is built for real, through the
    whole stack.
    """

    BOCKER_BALANS = "bocker.balans"
    BOCKER_RESULTAT = "bocker.resultat"
    BOCKER_VERIFIKATIONER = "bocker.verifikationer"
    BETALA_FAKTURERING = "betala.fakturering"
    BETALA_LONER = "betala.loner"
    BOKSLUT_RAPPORTER = "bokslut.rapporter"
    BOKSLUT_ATGARDER = "bokslut.atgarder"
