"""Tests for agent-created invoice drafts."""

from datetime import date

from domain.types import VoucherStatus
from repositories.account_repo import AccountRepository
from repositories.invoice_repo import InvoiceRepository
from repositories.period_repo import PeriodRepository
from repositories.voucher_repo import VoucherRepository
from services.customer_article import ArticleService, CustomerService
from services.invoice_draft import InvoiceDraftService


def _ensure_invoice_accounts():
    accounts = [
        ("1510", "Kundfordringar", "asset"),
        ("3010", "Försäljning tjänster", "revenue"),
        ("2610", "Utgående moms 25%", "vat_out"),
    ]
    for code, name, account_type in accounts:
        if not AccountRepository.exists(code):
            AccountRepository.create(code, name, account_type)


def test_agent_invoice_draft_can_be_approved_and_booked(test_db):
    _ensure_invoice_accounts()
    fiscal_year = PeriodRepository.create_fiscal_year(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    period = PeriodRepository.create_period(
        fiscal_year_id=fiscal_year.id,
        year=2026,
        month=4,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
    )

    customer = CustomerService().create_customer(
        name="Volvo Cars AB",
        org_number="556074-3089",
        email="invoice@example.com",
        payment_terms_days=20,
    )
    article = ArticleService().create_article(
        article_number="CONSULT",
        name="Konsulttjänst",
        description="Konsulttjänster april",
        unit="h",
        unit_price=120000,
        vat_code="MP1",
        revenue_account="3010",
    )

    draft = InvoiceDraftService().create_draft(
        customer_id=customer.id,
        invoice_date=date(2026, 4, 30),
        reference="VCC SBI april",
        rows_data=[
            {
                "article_id": article.id,
                "quantity": 10,
                "source_note": "VCC SBI april.pdf",
            }
        ],
        agent_summary="Skapat från underlag och tidigare fakturor.",
        agent_confidence=0.92,
        created_by="agent",
    )

    assert draft.status == "needs_review"
    assert draft.customer_name == "Volvo Cars AB"
    assert draft.due_date == date(2026, 5, 20)
    assert draft.amount_ex_vat == 1200000
    assert draft.vat_amount == 300000
    assert draft.amount_inc_vat == 1500000
    assert draft.rows[0].description == "Konsulttjänster april"
    assert draft.rows[0].revenue_account == "3010"

    booked = InvoiceDraftService().approve_and_book(
        draft.id,
        period_id=period.id,
        actor="reviewer",
    )

    assert booked.status == "booked"
    assert booked.approved_invoice_id
    assert booked.approved_voucher_id

    invoice = InvoiceRepository.get(booked.approved_invoice_id)
    assert invoice.voucher_id == booked.approved_voucher_id
    assert invoice.rows[0].revenue_account == "3010"

    voucher = VoucherRepository.get(booked.approved_voucher_id)
    assert voucher.status == VoucherStatus.POSTED
    assert sum(row.debit for row in voucher.rows) == 1500000
    assert sum(row.credit for row in voucher.rows) == 1500000
    assert any(row.account_code == "1510" and row.debit == 1500000 for row in voucher.rows)
    assert any(row.account_code == "3010" and row.credit == 1200000 for row in voucher.rows)
    assert any(row.account_code == "2610" and row.credit == 300000 for row in voucher.rows)
