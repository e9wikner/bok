"""Tests for invoice service."""

import pytest
from datetime import date
from domain.validation import ValidationError
from domain.invoice_validation import ValidationError as InvoiceValidationError
from services.invoice import InvoiceService
from repositories.account_repo import AccountRepository


@pytest.fixture
def invoice_service(test_db):
    """Create invoice service with required accounts."""
    # Create accounts needed for invoice booking
    accounts = [
        ("1010", "PlusGiro", "asset"),
        ("1510", "Kundfordringar", "asset"),
        ("3010", "Försäljning tjänster", "revenue"),
        ("3011", "Försäljning tjänster 25%", "revenue"),
        ("3020", "Försäljning tjänster 12%", "revenue"),
        ("3030", "Försäljning tjänster 6%", "revenue"),
        ("2610", "Utgående moms 25%", "vat_out"),
        ("2620", "Utgående moms 12%", "vat_out"),
        ("2630", "Utgående moms 6%", "vat_out"),
    ]
    for code, name, acc_type in accounts:
        if not AccountRepository.exists(code):
            AccountRepository.create(code, name, acc_type)
    
    return InvoiceService()


def test_create_invoice(invoice_service):
    """Test creating a basic invoice."""
    invoice = invoice_service.create_invoice(
        customer_name="Test AB",
        invoice_date=date(2026, 3, 1),
        due_date=date(2026, 3, 31),
        rows_data=[
            {"description": "Consulting", "quantity": 10, "unit_price": 100000, "vat_code": "MP1"}
        ],
        customer_email="test@example.com",
    )
    
    assert invoice.id is not None
    assert invoice.customer_name == "Test AB"
    assert invoice.amount_ex_vat == 1000000  # 10 * 100000
    assert invoice.vat_amount == 250000      # 25% of 1000000
    assert invoice.amount_inc_vat == 1250000
    assert len(invoice.rows) == 1


def test_create_invoice_multiple_vat_codes(invoice_service):
    """Test invoice with mixed VAT rates."""
    invoice = invoice_service.create_invoice(
        customer_name="Test AB",
        invoice_date=date(2026, 3, 1),
        due_date=date(2026, 3, 31),
        rows_data=[
            {"description": "Service 25%", "quantity": 1, "unit_price": 100000, "vat_code": "MP1"},
            {"description": "Service 12%", "quantity": 1, "unit_price": 100000, "vat_code": "MP2"},
            {"description": "Service 6%", "quantity": 1, "unit_price": 100000, "vat_code": "MP3"},
        ],
    )
    
    assert invoice.amount_ex_vat == 300000
    assert invoice.vat_amount == 25000 + 12000 + 6000  # 43000
    assert invoice.amount_inc_vat == 343000


def test_send_invoice(invoice_service):
    """Test sending an invoice."""
    invoice = invoice_service.create_invoice(
        customer_name="Test AB",
        invoice_date=date(2026, 3, 1),
        due_date=date(2026, 3, 31),
        rows_data=[
            {"description": "Consulting", "quantity": 1, "unit_price": 100000, "vat_code": "MP1"}
        ],
        customer_email="test@example.com",
    )
    
    sent = invoice_service.send_invoice(invoice.id)
    assert sent.status == "sent"
    assert sent.sent_at is not None


def test_send_invoice_without_email_fails(invoice_service):
    """Test that sending without email fails."""
    invoice = invoice_service.create_invoice(
        customer_name="Test AB",
        invoice_date=date(2026, 3, 1),
        due_date=date(2026, 3, 31),
        rows_data=[
            {"description": "Consulting", "quantity": 1, "unit_price": 100000, "vat_code": "MP1"}
        ],
    )
    
    with pytest.raises(ValidationError) as exc_info:
        invoice_service.send_invoice(invoice.id)
    assert exc_info.value.code == "missing_email"


def test_register_payment(invoice_service):
    """Test registering a payment."""
    invoice = invoice_service.create_invoice(
        customer_name="Test AB",
        invoice_date=date(2026, 3, 1),
        due_date=date(2026, 3, 31),
        rows_data=[
            {"description": "Consulting", "quantity": 1, "unit_price": 100000, "vat_code": "MP1"}
        ],
        customer_email="test@example.com",
    )
    invoice_service.send_invoice(invoice.id)
    
    payment = invoice_service.register_payment(
        invoice_id=invoice.id,
        amount=125000,  # Full amount inc VAT
        payment_date=date(2026, 3, 15),
        payment_method="bank_transfer",
    )
    
    assert payment.amount == 125000
    
    # Check invoice is now paid
    updated = invoice_service.invoices.get(invoice.id)
    assert updated.status == "paid"


def test_partial_payment(invoice_service):
    """Test partial payment."""
    invoice = invoice_service.create_invoice(
        customer_name="Test AB",
        invoice_date=date(2026, 3, 1),
        due_date=date(2026, 3, 31),
        rows_data=[
            {"description": "Consulting", "quantity": 1, "unit_price": 100000, "vat_code": "MP1"}
        ],
        customer_email="test@example.com",
    )
    invoice_service.send_invoice(invoice.id)
    
    # Pay half
    invoice_service.register_payment(
        invoice_id=invoice.id,
        amount=60000,
        payment_date=date(2026, 3, 10),
        payment_method="bank_transfer",
    )
    
    updated = invoice_service.invoices.get(invoice.id)
    assert updated.status == "partially_paid"
    assert updated.remaining_amount() == 65000


def test_overpayment_rejected(invoice_service):
    """Test that overpayment is rejected."""
    invoice = invoice_service.create_invoice(
        customer_name="Test AB",
        invoice_date=date(2026, 3, 1),
        due_date=date(2026, 3, 31),
        rows_data=[
            {"description": "Consulting", "quantity": 1, "unit_price": 100000, "vat_code": "MP1"}
        ],
        customer_email="test@example.com",
    )
    invoice_service.send_invoice(invoice.id)
    
    with pytest.raises(ValidationError) as exc_info:
        invoice_service.register_payment(
            invoice_id=invoice.id,
            amount=200000,  # More than invoice total
            payment_date=date(2026, 3, 15),
            payment_method="bank_transfer",
        )
    assert exc_info.value.code == "overpayment"


def test_invalid_vat_code_rejected(invoice_service):
    """Test that invalid VAT code is rejected."""
    with pytest.raises(ValidationError) as exc_info:
        invoice_service.create_invoice(
            customer_name="Test AB",
            invoice_date=date(2026, 3, 1),
            due_date=date(2026, 3, 31),
            rows_data=[
                {"description": "Bad", "quantity": 1, "unit_price": 100000, "vat_code": "INVALID"}
            ],
        )
    assert exc_info.value.code == "invalid_vat_code"


@pytest.fixture
def invoice_period(test_db):
    """Create fiscal year and period for invoice booking tests."""
    from repositories.period_repo import PeriodRepository
    fy = PeriodRepository.create_fiscal_year(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    period = PeriodRepository.create_period(
        fiscal_year_id=fy.id,
        year=2026,
        month=3,
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
    )
    return period


def test_book_invoice(invoice_service, invoice_period):
    """Test auto-booking invoice to accounting."""
    invoice = invoice_service.create_invoice(
        customer_name="Test AB",
        invoice_date=date(2026, 3, 1),
        due_date=date(2026, 3, 31),
        rows_data=[
            {"description": "Consulting", "quantity": 10, "unit_price": 100000, "vat_code": "MP1"}
        ],
    )
    
    voucher_id = invoice_service.create_booking_for_invoice(
        invoice_id=invoice.id,
        period_id=invoice_period.id,
    )
    
    assert voucher_id is not None
    
    # Verify invoice is linked to voucher
    updated = invoice_service.invoices.get(invoice.id)
    assert updated.voucher_id == voucher_id
