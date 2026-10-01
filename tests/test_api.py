"""Tests for API endpoints."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from config import settings
from repositories.account_repo import AccountRepository
from repositories.period_repo import PeriodRepository


@pytest.fixture
def client(test_db):
    """Create test client with initialized database."""
    # Create required accounts
    accounts = [
        ("1510", "Kundfordringar", "asset"),
        ("3011", "Försäljning tjänster 25%", "revenue"),
        ("2610", "Utgående moms 25%", "vat_out"),
    ]
    for code, name, acc_type in accounts:
        if not AccountRepository.exists(code):
            AccountRepository.create(code, name, acc_type)

    from api.main import app

    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Authorization headers."""
    return {"Authorization": f"Bearer {settings.api_key}"}


@pytest.fixture
def period_id(test_db):
    """Create fiscal year and period, return period ID."""
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
    return period.id


def test_health_check(client):
    """Test health endpoint."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_root(client):
    """Test root endpoint."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "title" in resp.json()


def test_list_accounts(client, auth_headers):
    """Test listing accounts."""
    resp = client.get("/api/v1/accounts", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 3


def test_get_account(client, auth_headers):
    """Test getting single account."""
    resp = client.get("/api/v1/accounts/1510", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["code"] == "1510"


def test_get_account_not_found(client, auth_headers):
    """Test 404 for missing account."""
    resp = client.get("/api/v1/accounts/9999", headers=auth_headers)
    assert resp.status_code == 404


def test_company_info_can_be_updated(client, auth_headers):
    """Test editable company metadata."""
    payload = {
        "name": "Demo AB",
        "org_number": "559123-4567",
        "contact_name": "Demo Kontakt",
        "address": "Testgatan 1",
        "postnr": "11122",
        "postort": "Stockholm",
        "email": "demo@example.com",
        "phone": "08-123456",
    }

    resp = client.put("/api/v1/company-info", headers=auth_headers, json=payload)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Demo AB"
    assert resp.json()["org_number"] == "559123-4567"

    resp = client.get("/api/v1/company-info", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["contact_name"] == "Demo Kontakt"
    assert resp.json()["postort"] == "Stockholm"


def test_company_info_invoice_fields_survive_an_older_client(client, auth_headers):
    """seat, vat_number, bankgiro and f_skatt can be set, and a PUT that
    does not send them (the older settings page) leaves them as they are."""
    from services.pdf_export import CompanyInfo

    full = {
        "name": "Demo AB",
        "org_number": "559123-4567",
        "address": "Testgatan 1",
        "seat": "Stockholm",
        "vat_number": "SE559123456701",
        "bankgiro": "123-4567",
        "f_skatt": True,
    }
    resp = client.put("/api/v1/company-info", headers=auth_headers, json=full)
    assert resp.status_code == 200
    assert resp.json()["seat"] == "Stockholm"
    assert resp.json()["f_skatt"] is True

    older = {"name": "Demo AB", "org_number": "559123-4567", "phone": "08-1"}
    resp = client.put("/api/v1/company-info", headers=auth_headers, json=older)
    assert resp.status_code == 200
    assert resp.json()["seat"] == "Stockholm"
    assert resp.json()["vat_number"] == "SE559123456701"
    assert resp.json()["f_skatt"] is True

    company = CompanyInfo.load()
    assert company.f_skatt is True
    company.check_complete_for_invoice()


def test_sru_mappings_use_account_codes(client, auth_headers, test_db):
    """Test SRU mappings are saved and returned by account code."""
    fy = PeriodRepository.create_fiscal_year(
        start_date=date(2027, 1, 1),
        end_date=date(2027, 12, 31),
    )

    resp = client.post(
        f"/api/v1/fiscal-years/{fy.id}/sru-mappings/bulk",
        headers=auth_headers,
        json=[
            {"account_id": "1510", "sru_field": "7261"},
            {"account_id": "3011", "sru_field": "7410"},
        ],
    )
    assert resp.status_code == 201

    resp = client.get(
        f"/api/v1/fiscal-years/{fy.id}/sru-mappings",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    mappings = {row["account_code"]: row["sru_field"] for row in resp.json()}
    assert mappings == {"1510": "7261", "3011": "7410"}


def test_sru_bulk_update_removes_deleted_mappings(client, auth_headers, test_db):
    """Test omitted mappings are removed during bulk save."""
    fy = PeriodRepository.create_fiscal_year(
        start_date=date(2028, 1, 1),
        end_date=date(2028, 12, 31),
    )

    client.post(
        f"/api/v1/fiscal-years/{fy.id}/sru-mappings/bulk",
        headers=auth_headers,
        json=[
            {"account_id": "1510", "sru_field": "7261"},
            {"account_id": "3011", "sru_field": "7410"},
        ],
    )
    resp = client.post(
        f"/api/v1/fiscal-years/{fy.id}/sru-mappings/bulk",
        headers=auth_headers,
        json=[
            {"account_id": "1510", "sru_field": "7261"},
        ],
    )
    assert resp.status_code == 201

    resp = client.get(
        f"/api/v1/fiscal-years/{fy.id}/sru-mappings",
        headers=auth_headers,
    )
    mappings = {row["account_code"]: row["sru_field"] for row in resp.json()}
    assert mappings == {"1510": "7261"}


def test_create_voucher(client, auth_headers, period_id):
    """Test creating a voucher via API."""
    resp = client.post(
        "/api/v1/vouchers",
        headers=auth_headers,
        json={
            "series": "A",
            "date": "2026-03-20",
            "period_id": period_id,
            "description": "Test voucher",
            "rows": [
                {"account": "1510", "debit": 10000, "credit": 0},
                {"account": "3011", "debit": 0, "credit": 10000},
            ],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "draft"
    assert len(data["rows"]) == 2


def test_create_voucher_unbalanced(client, auth_headers, period_id):
    """Test that unbalanced voucher returns 400."""
    resp = client.post(
        "/api/v1/vouchers",
        headers=auth_headers,
        json={
            "series": "A",
            "date": "2026-03-20",
            "period_id": period_id,
            "description": "Unbalanced",
            "rows": [
                {"account": "1510", "debit": 10000, "credit": 0},
                {"account": "3011", "debit": 0, "credit": 5000},
            ],
        },
    )
    assert resp.status_code == 400


def test_unauthorized_request(client):
    """Test that missing auth returns 401."""
    resp = client.get("/api/v1/accounts")
    assert resp.status_code == 401
    resp = client.post("/api/v1/vouchers", json={})
    assert resp.status_code == 401


#: The only routes a request without a bearer gets past (api/main.py).
PUBLIC_ROUTES = {
    ("GET", "/"),
    ("GET", "/health"),
    ("GET", "/api/v1/health"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/logout"),
    ("GET", "/api/v1/agent-instructions/entrypoint"),
}


def test_every_route_but_the_public_ones_needs_the_bearer(client):
    """Reads too: salaries, personal numbers and invoices are behind the
    bearer. A new router that forgets it fails here."""
    let_through = set()
    for path, operations in client.app.openapi()["paths"].items():
        url = path.replace("{", "").replace("}", "")
        for method in operations:
            response = client.request(method.upper(), url)
            if response.status_code != 401:
                let_through.add((method.upper(), path))
    assert let_through == PUBLIC_ROUTES


def test_post_voucher(client, auth_headers, period_id):
    """Test posting (finalizing) a voucher."""
    # Create
    resp = client.post(
        "/api/v1/vouchers",
        headers=auth_headers,
        json={
            "series": "A",
            "date": "2026-03-20",
            "period_id": period_id,
            "description": "To post",
            "rows": [
                {"account": "1510", "debit": 10000, "credit": 0},
                {"account": "3011", "debit": 0, "credit": 10000},
            ],
        },
    )
    voucher_id = resp.json()["id"]

    # Post
    resp = client.post(f"/api/v1/vouchers/{voucher_id}/post", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "posted"
