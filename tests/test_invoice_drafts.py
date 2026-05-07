"""Tests for agent-created invoice drafts."""

from datetime import date

from fastapi.testclient import TestClient

from api.main import app
from config import settings
from domain.types import VoucherStatus
from repositories.account_repo import AccountRepository
from repositories.invoice_repo import InvoiceRepository
from repositories.period_repo import PeriodRepository
from repositories.voucher_repo import VoucherRepository
from services.customer_article import ArticleService, CustomerService
from services.invoice_draft import InvoiceDraftService


def _headers():
    return {"Authorization": f"Bearer {settings.api_key}"}


def _ensure_invoice_accounts():
    accounts = [
        ("1510", "Kundfordringar", "asset"),
        ("3010", "Försäljning tjänster", "revenue"),
        ("2610", "Utgående moms 25%", "vat_out"),
    ]
    for code, name, account_type in accounts:
        if not AccountRepository.exists(code):
            AccountRepository.create(code, name, account_type)


def test_agent_invoice_draft_can_be_updated_sent_and_booked(test_db):
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

    updated = InvoiceDraftService().update_draft(
        draft.id,
        customer_id=customer.id,
        invoice_date=date(2026, 4, 30),
        reference="VCC SBI april korrigerad",
        rows_data=[
            {
                "article_id": article.id,
                "quantity": 12,
                "source_note": "Korrigerat efter granskning",
            }
        ],
        agent_summary="Uppdaterat efter användarkorrigering.",
        agent_confidence=0.88,
        actor="reviewer",
    )

    assert updated.amount_ex_vat == 1440000
    assert updated.vat_amount == 360000
    assert updated.amount_inc_vat == 1800000
    assert updated.reference == "VCC SBI april korrigerad"

    result = InvoiceDraftService().send(
        draft.id,
        period_id=period.id,
        actor="reviewer",
    )
    booked = result["draft"]

    assert booked.status == "sent"
    assert booked.approved_invoice_id
    assert booked.approved_voucher_id
    assert result["pdf_url"] == f"/api/v1/export/pdf/invoice/{booked.approved_invoice_id}"

    invoice = InvoiceRepository.get(booked.approved_invoice_id)
    assert invoice.voucher_id == booked.approved_voucher_id
    assert invoice.status == "sent"
    assert invoice.rows[0].revenue_account == "3010"
    assert invoice.rows[0].quantity == 12

    voucher = VoucherRepository.get(booked.approved_voucher_id)
    assert voucher.status == VoucherStatus.POSTED
    assert sum(row.debit for row in voucher.rows) == 1800000
    assert sum(row.credit for row in voucher.rows) == 1800000
    assert any(row.account_code == "1510" and row.debit == 1800000 for row in voucher.rows)
    assert any(row.account_code == "3010" and row.credit == 1440000 for row in voucher.rows)
    assert any(row.account_code == "2610" and row.credit == 360000 for row in voucher.rows)


def test_invoice_draft_send_rejects_terminal_statuses(test_db):
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
    draft = InvoiceDraftService().create_draft(
        customer_name="Testkund AB",
        invoice_date=date(2026, 4, 30),
        rows_data=[
            {
                "description": "Test",
                "quantity": 1,
                "unit_price": 100000,
                "vat_code": "MP1",
                "revenue_account": "3010",
            }
        ],
        created_by="agent",
    )

    InvoiceDraftService().reject(draft.id, actor="reviewer")
    try:
        InvoiceDraftService().send(draft.id, period_id=period.id, actor="reviewer")
    except Exception as exc:
        assert getattr(exc, "code", "") == "draft_rejected"
    else:
        raise AssertionError("Rejected draft should not be sent")


def test_invoice_draft_api_update_and_send(test_db):
    _ensure_invoice_accounts()
    fiscal_year = PeriodRepository.create_fiscal_year(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    period = PeriodRepository.create_period(
        fiscal_year_id=fiscal_year.id,
        year=2026,
        month=5,
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/invoice-drafts",
        headers=_headers(),
        json={
            "customer_name": "API Kund AB",
            "invoice_date": "2026-05-31",
            "reference": "Maj",
            "rows": [
                {
                    "description": "Konsulttjänst",
                    "quantity": 1,
                    "unit_price": 100000,
                    "vat_code": "MP1",
                    "revenue_account": "3010",
                    "source_note": "api-test.pdf",
                }
            ],
            "agent_notes": {"summary": "Skapat av agent", "confidence": 0.8},
        },
    )
    assert response.status_code == 201
    draft_id = response.json()["id"]

    response = client.put(
        f"/api/v1/invoice-drafts/{draft_id}",
        headers=_headers(),
        json={
            "customer_name": "API Kund AB",
            "invoice_date": "2026-05-31",
            "reference": "Maj korrigerad",
            "rows": [
                {
                    "description": "Konsulttjänst",
                    "quantity": 2,
                    "unit_price": 100000,
                    "vat_code": "MP1",
                    "revenue_account": "3010",
                    "source_note": "api-test.pdf",
                }
            ],
            "agent_notes": {"summary": "Korrigerad av användare", "warnings": []},
        },
    )
    assert response.status_code == 200
    assert response.json()["amount_inc_vat"] == 250000

    response = client.post(
        f"/api/v1/invoice-drafts/{draft_id}/send",
        headers=_headers(),
        json={"period_id": period.id},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["invoice_id"]
    assert result["voucher_id"]
    assert result["pdf_url"] == f"/api/v1/export/pdf/invoice/{result['invoice_id']}"

    response = client.post(
        f"/api/v1/invoice-drafts/{draft_id}/send",
        headers=_headers(),
        json={"period_id": period.id},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "draft_already_sent"
