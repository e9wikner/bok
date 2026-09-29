"""Invoice business rule validation (Fas 2)."""

import math
import re
from datetime import date
from decimal import Decimal
from typing import Optional, Tuple, Union

from domain.invoice_models import Invoice, InvoiceStatus
from domain.validation import ValidationError


class InvoiceValidator:
    """Validate invoice business rules."""

    @staticmethod
    def validate_new_invoice(invoice: Invoice) -> None:
        """Validate new invoice before saving."""
        if not invoice.rows:
            raise ValidationError(
                code="no_invoice_rows",
                message="Invoice must have at least 1 row",
                details="add_rows_before_saving",
            )

        # Validate invoice date
        if invoice.invoice_date > invoice.due_date:
            raise ValidationError(
                code="invalid_due_date",
                message="Due date must be after invoice date",
                details="due_date must be >= invoice_date",
            )

        # Validate customer
        if not invoice.customer_name or not invoice.customer_name.strip():
            raise ValidationError(
                code="missing_customer",
                message="Customer name is required",
                details="customer_name cannot be empty",
            )

        # Validate totals
        InvoiceValidator._validate_totals(invoice)

    @staticmethod
    def validate_can_send(invoice: Invoice) -> None:
        """Check if invoice can be sent."""
        if invoice.status != InvoiceStatus.DRAFT:
            raise ValidationError(
                code="invoice_already_sent",
                message="Cannot send non-draft invoice",
                details="invoice.status must be 'draft'",
            )

        if not invoice.rows:
            raise ValidationError(
                code="no_rows",
                message="Cannot send invoice with no rows",
                details="add at least 1 row",
            )

    @staticmethod
    def validate_can_pay(invoice: Invoice, payment_amount: int) -> None:
        """Check if payment can be registered."""
        if invoice.status == InvoiceStatus.CANCELLED:
            raise ValidationError(
                code="invoice_cancelled",
                message="Cannot pay cancelled invoice",
                details="invoice is cancelled",
            )

        if invoice.is_paid():
            raise ValidationError(
                code="already_paid",
                message="Invoice is already fully paid",
                details="remaining_amount is 0",
            )

        if payment_amount <= 0:
            raise ValidationError(
                code="invalid_amount",
                message="Payment amount must be positive",
                details="payment_amount > 0",
            )

        if payment_amount > invoice.remaining_amount():
            raise ValidationError(
                code="overpayment",
                message="Payment amount exceeds remaining balance",
                details=f"remaining: {invoice.remaining_amount()} öre, payment: {payment_amount} öre",
            )

    @staticmethod
    def validate_can_create_credit_note(invoice: Invoice, amount: int) -> None:
        """Check if credit note can be created."""
        if invoice.status == InvoiceStatus.DRAFT:
            raise ValidationError(
                code="invoice_not_sent",
                message="Cannot credit unsent invoice",
                details="send invoice first",
            )

        if amount <= 0:
            raise ValidationError(
                code="invalid_amount",
                message="Credit note amount must be positive",
                details="amount > 0",
            )

        if amount > invoice.amount_inc_vat:
            raise ValidationError(
                code="overcredit",
                message="Credit note cannot exceed original invoice amount",
                details=f"invoice_total: {invoice.amount_inc_vat}, credit: {amount}",
            )

    @staticmethod
    def _validate_totals(invoice: Invoice) -> None:
        """Validate that invoice totals match row sum."""
        total_ex_vat = sum(row.amount_ex_vat for row in invoice.rows)
        total_vat = sum(row.vat_amount for row in invoice.rows)
        total_inc_vat = sum(row.amount_inc_vat for row in invoice.rows)

        if invoice.amount_ex_vat != total_ex_vat:
            raise ValidationError(
                code="invalid_total",
                message="Invoice total ex VAT mismatch",
                details=f"expected {total_ex_vat}, got {invoice.amount_ex_vat}",
            )

        if invoice.vat_amount != total_vat:
            raise ValidationError(
                code="invalid_vat",
                message="Invoice VAT mismatch",
                details=f"expected {total_vat}, got {invoice.vat_amount}",
            )

        if invoice.amount_inc_vat != total_inc_vat:
            raise ValidationError(
                code="invalid_total_inc_vat",
                message="Invoice total inc VAT mismatch",
                details=f"expected {total_inc_vat}, got {invoice.amount_inc_vat}",
            )


class VATCalculator:
    """Calculate VAT based on rates and codes."""

    VAT_RATES = {
        "MP1": 0.25,  # 25% standard (consulting)
        "MP2": 0.12,  # 12%
        "MP3": 0.06,  # 6%
        "MF": 0.00,  # 0% (export/exempt)
    }

    @staticmethod
    def calculate_vat(amount_ex_vat: int, vat_code: str) -> int:
        """Calculate VAT for given amount and code (returns öre)."""
        rate = VATCalculator.VAT_RATES.get(vat_code, 0)
        vat = int(amount_ex_vat * rate)
        return vat

    @staticmethod
    def get_vat_rate(vat_code: str) -> float:
        """Get VAT rate for code (0.0-1.0)."""
        return VATCalculator.VAT_RATES.get(vat_code, 0.0)

    @staticmethod
    def validate_vat_code(vat_code: str) -> bool:
        """Check if VAT code is valid."""
        return vat_code in VATCalculator.VAT_RATES


# --- SPEC-fakturering.md §4.1–4.2: nummer, antal och leverans ---------------

_QUANTITY_RE = re.compile(r"^\d+(?:[.,]\d{1,2})?$")
_INVOICE_NUMBER_RE = re.compile(r"^[A-Za-z0-9-]{1,32}$")
_DATE_NUMBER_RE = re.compile(r"^(?:\d{8}|\d{4}-\d{2}-\d{2})$")
_MONTH_RE = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")


def parse_quantity_centi(value: Union[int, float, str, Decimal, None]) -> int:
    """The quantity times 100 (7,5 → 750), from a number or a string with
    point or comma. At most two decimals and greater than zero, else
    `invalid_quantity`. A float goes through its shortest repr, so 0.29 is
    29 and not 28."""
    text: Optional[str] = None
    if isinstance(value, bool) or value is None:
        text = None
    elif isinstance(value, int):
        text = str(value)
    elif isinstance(value, float):
        text = repr(value) if math.isfinite(value) else None
    elif isinstance(value, Decimal):
        text = format(value, "f") if value.is_finite() else None
    elif isinstance(value, str):
        text = value.strip()
    if text is None or not _QUANTITY_RE.match(text):
        raise ValidationError(
            code="invalid_quantity",
            message=("Quantity must be a positive number with at most two decimals"),
            details=f"got {value!r}",
        )
    centi = int(Decimal(text.replace(",", ".")) * 100)
    if centi <= 0:
        raise ValidationError(
            code="invalid_quantity",
            message="Quantity must be greater than zero",
            details=f"got {value!r}",
        )
    return centi


def quantity_from_centi(quantity_centi: int) -> Union[int, float]:
    """The quantity for a JSON reader: 750 → 7.5, 2800 → 28."""
    whole, rest = divmod(quantity_centi, 100)
    return whole if rest == 0 else quantity_centi / 100


def legacy_quantity(quantity_centi: int) -> int:
    """The old integer `quantity` column, kept for old readers and never
    computed on (§4.2). Rounded up so it satisfies its CHECK(quantity > 0)
    for 0,5 and never shows less than was delivered."""
    return max(1, -(-quantity_centi // 100))


def amount_ex_vat_from_centi(quantity_centi: int, unit_price: int) -> int:
    """round_half_even(quantity_centi * unit_price / 100), in öre (§4.2).
    Integer arithmetic, so no float ever rounds the wrong way."""
    quotient, remainder = divmod(quantity_centi * unit_price, 100)
    if remainder > 50 or (remainder == 50 and quotient % 2 == 1):
        quotient += 1
    return quotient


def normalize_invoice_number(number: Optional[str]) -> Optional[str]:
    """A proposed invoice number, or None. `^[A-Za-z0-9-]{1,32}$`, and not a
    bare date (§4.1)."""
    if number is None:
        return None
    number = str(number).strip()
    if not number:
        return None
    if _DATE_NUMBER_RE.match(number):
        raise ValidationError(
            code="number_is_date",
            message="An invoice number may not be just a date",
            details=f"got {number!r}",
        )
    if not _INVOICE_NUMBER_RE.match(number):
        raise ValidationError(
            code="invalid_invoice_number",
            message=(
                "Invoice number may only contain letters, digits and '-', "
                "at most 32 characters"
            ),
            details=f"got {number!r}",
        )
    return number


def _as_date(value, field: str) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ValidationError(
            code="invalid_delivery_date",
            message=f"{field} must be a date (YYYY-MM-DD)",
            details=f"got {value!r}",
        )


def normalize_delivery(
    delivery_from=None, delivery_to=None, delivery_month=None
) -> Tuple[Optional[date], Optional[date], Optional[str]]:
    """Delivery as a day, a period or a month (§4.2). A lone from or to
    date is a single day. Dates and a month together are ambiguous."""
    start = _as_date(delivery_from, "delivery_from")
    end = _as_date(delivery_to, "delivery_to")
    month = str(delivery_month).strip() if delivery_month else None
    start, end = start or end, end or start
    if start and end and end < start:
        raise ValidationError(
            code="invalid_delivery_date",
            message="delivery_to must be on or after delivery_from",
            details=f"{start} > {end}",
        )
    if month and not _MONTH_RE.match(month):
        raise ValidationError(
            code="invalid_delivery_date",
            message="delivery_month must be YYYY-MM",
            details=f"got {delivery_month!r}",
        )
    if month and start:
        raise ValidationError(
            code="invalid_delivery_date",
            message="Give delivery as dates or as a month, not both",
        )
    return start, end, month
