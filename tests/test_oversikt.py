"""Tests for the `oversikt` module (SPEC-oversikt.md).

Covers the repaired attachment compliance check (O1), the derived
`missing_attachment` / `age_days` fields (O2), the voucher filter and
sorting (O3) and `GET /api/v1/overview` (O4).

Test case numbers refer to the table in SPEC-oversikt.md §7.
"""

import sqlite3
import uuid
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from config import settings
from db.database import db
from repositories.account_repo import AccountRepository
from repositories.period_repo import PeriodRepository
from services.compliance import ComplianceService


@pytest.fixture
def client(test_db):
    """Test client bound after the database swap (pattern from test_api.py)."""
    accounts = [
        ("1510", "Kundfordringar", "asset"),
        ("1910", "Kassa", "asset"),
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
def fiscal_year_id(test_db):
    """Fiscal year 2026 with one period per month, January through September."""
    fy = PeriodRepository.create_fiscal_year(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    for month in range(1, 10):
        end_day = 31 if month in (1, 3, 5, 7, 8) else 30
        if month == 2:
            end_day = 28
        PeriodRepository.create_period(
            fiscal_year_id=fy.id,
            year=2026,
            month=month,
            start_date=date(2026, month, 1),
            end_date=date(2026, month, end_day),
        )
    return fy.id


@pytest.fixture
def period_id(fiscal_year_id):
    """The March 2026 period."""
    period = PeriodRepository.get_period_by_date(fiscal_year_id, date(2026, 3, 15))
    assert period is not None
    return period.id


def _period_for(fiscal_year_id: str, when: date) -> str:
    period = PeriodRepository.get_period_by_date(fiscal_year_id, when)
    assert period is not None, f"no period covering {when}"
    return period.id


def _create_voucher(
    client,
    auth_headers,
    period_id: str,
    when: date,
    amount: int = 60000,
    description: str = "Test",
) -> str:
    """Create a draft voucher and return its id. Amount is in öre."""
    resp = client.post(
        "/api/v1/vouchers",
        headers=auth_headers,
        json={
            "series": "A",
            "date": when.isoformat(),
            "period_id": period_id,
            "description": description,
            "rows": [
                {"account": "1510", "debit": amount, "credit": 0},
                {"account": "3011", "debit": 0, "credit": amount},
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _post_voucher(client, auth_headers, voucher_id: str) -> None:
    resp = client.post(f"/api/v1/vouchers/{voucher_id}/post", headers=auth_headers)
    assert resp.status_code == 200, resp.text


def _posted_voucher(
    client,
    auth_headers,
    period_id: str,
    when: date,
    amount: int = 60000,
    description: str = "Test",
) -> str:
    voucher_id = _create_voucher(
        client, auth_headers, period_id, when, amount, description
    )
    _post_voucher(client, auth_headers, voucher_id)
    return voucher_id


def _attach(voucher_id: str, filename: str = "kvitto.pdf") -> str:
    """Insert an attachment row directly, as api/routes/attachments.py does."""
    attachment_id = str(uuid.uuid4())
    db.execute(
        """
        INSERT INTO attachments
            (id, voucher_id, filename, sha256, mime_type, stored_path, size_bytes, uploaded_at)
        VALUES (?, ?, ?, ?, 'application/pdf', ?, 1024, ?)
        """,
        (
            attachment_id,
            voucher_id,
            filename,
            uuid.uuid4().hex,
            f"/tmp/{filename}",
            datetime.now(),
        ),
    )
    db.commit()
    return attachment_id


# ---------------------------------------------------------------------------
# O1 — _check_missing_attachments
# ---------------------------------------------------------------------------


def test_posted_voucher_over_500_without_attachment_is_reported(
    client, auth_headers, period_id
):
    """Testfall 1: a posted voucher over 500 SEK without attachment gives an issue."""
    _posted_voucher(client, auth_headers, period_id, date(2026, 3, 15), amount=60000)

    issues = ComplianceService()._check_missing_attachments()

    assert len(issues) == 1
    assert issues[0].check_type == "missing_attachments"
    assert "1 verifikationer" in issues[0].title


def test_posted_voucher_with_attachment_gives_no_issue(client, auth_headers, period_id):
    """Testfall 2: the same voucher with an attachment gives no issue."""
    voucher_id = _posted_voucher(
        client, auth_headers, period_id, date(2026, 3, 15), amount=60000
    )
    _attach(voucher_id)

    assert ComplianceService()._check_missing_attachments() == []


def test_missing_attachments_schema_raises(client, auth_headers, period_id):
    """Testfall 3: a missing `attachments` schema raises, it is not swallowed."""
    _posted_voucher(client, auth_headers, period_id, date(2026, 3, 15), amount=60000)
    db.execute("DROP TABLE attachments")
    db.commit()

    with pytest.raises(sqlite3.OperationalError):
        ComplianceService()._check_missing_attachments()


def test_small_posted_voucher_without_attachment_is_not_reported(
    client, auth_headers, period_id
):
    """The 500 SEK threshold (50000 öre) is unchanged."""
    _posted_voucher(client, auth_headers, period_id, date(2026, 3, 15), amount=40000)

    assert ComplianceService()._check_missing_attachments() == []
