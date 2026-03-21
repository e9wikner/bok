"""Invoice business rule validation (Fas 2)."""

from typing import List, Optional
from datetime import date
from domain.invoice_models import Invoice, InvoiceRow, Payment, InvoiceStatus
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
                details="add_rows_before_saving"
            )
        
        # Validate invoice date
        if invoice.invoice_date > invoice.due_date:
            raise ValidationError(
                code="invalid_due_date",
                message="Due date must be after invoice date",
                details="due_date must be >= invoice_date"
            )
        
        # Validate customer
        if not invoice.customer_name or not invoice.customer_name.strip():
            raise ValidationError(
                code="missing_customer",
                message="Customer name is required",
                details="customer_name cannot be empty"
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
                details="invoice.status must be 'draft'"
            )
        
        if not invoice.customer_email:
            raise ValidationError(
                code="missing_email",
                message="Customer email required to send invoice",
                details="add customer_email before sending"
            )
        
        if not invoice.rows:
            raise ValidationError(
                code="no_rows",
                message="Cannot send invoice with no rows",
                details="add at least 1 row"
            )
    
    @staticmethod
    def validate_can_pay(invoice: Invoice, payment_amount: int) -> None:
        """Check if payment can be registered."""
        if invoice.status == InvoiceStatus.CANCELLED:
            raise ValidationError(
                code="invoice_cancelled",
                message="Cannot pay cancelled invoice",
                details="invoice is cancelled"
            )
        
        if invoice.is_paid():
            raise ValidationError(
                code="already_paid",
                message="Invoice is already fully paid",
                details="remaining_amount is 0"
            )
        
        if payment_amount <= 0:
            raise ValidationError(
                code="invalid_amount",
                message="Payment amount must be positive",
                details="payment_amount > 0"
            )
        
        if payment_amount > invoice.remaining_amount():
            raise ValidationError(
                code="overpayment",
                message="Payment amount exceeds remaining balance",
                details=f"remaining: {invoice.remaining_amount()} öre, payment: {payment_amount} öre"
            )
    
    @staticmethod
    def validate_can_create_credit_note(invoice: Invoice, amount: int) -> None:
        """Check if credit note can be created."""
        if invoice.status == InvoiceStatus.DRAFT:
            raise ValidationError(
                code="invoice_not_sent",
                message="Cannot credit unsent invoice",
                details="send invoice first"
            )
        
        if amount <= 0:
            raise ValidationError(
                code="invalid_amount",
                message="Credit note amount must be positive",
                details="amount > 0"
            )
        
        if amount > invoice.amount_inc_vat:
            raise ValidationError(
                code="overcredit",
                message="Credit note cannot exceed original invoice amount",
                details=f"invoice_total: {invoice.amount_inc_vat}, credit: {amount}"
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
                message=f"Invoice total ex VAT mismatch",
                details=f"expected {total_ex_vat}, got {invoice.amount_ex_vat}"
            )
        
        if invoice.vat_amount != total_vat:
            raise ValidationError(
                code="invalid_vat",
                message=f"Invoice VAT mismatch",
                details=f"expected {total_vat}, got {invoice.vat_amount}"
            )
        
        if invoice.amount_inc_vat != total_inc_vat:
            raise ValidationError(
                code="invalid_total_inc_vat",
                message=f"Invoice total inc VAT mismatch",
                details=f"expected {total_inc_vat}, got {invoice.amount_inc_vat}"
            )


class VATCalculator:
    """Calculate VAT based on rates and codes."""
    
    VAT_RATES = {
        "MP1": 0.25,  # 25% standard (consulting)
        "MP2": 0.12,  # 12%
        "MP3": 0.06,  # 6%
        "MF": 0.00,   # 0% (export/exempt)
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
