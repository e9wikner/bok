"""Tests for agent instructions, direct posting and correction history."""

from datetime import date

from fastapi.testclient import TestClient

from api.main import app
from config import settings
from repositories.account_repo import AccountRepository
from repositories.period_repo import PeriodRepository


def _headers():
    return {"Authorization": f"Bearer {settings.api_key}"}


def _ensure_accounts():
    for code, name, account_type in [
        ("1920", "Bankkonto", "asset"),
        ("6200", "Tele och post", "expense"),
        ("6570", "Bankkostnader", "expense"),
    ]:
        if not AccountRepository.exists(code):
            AccountRepository.create(code, name, account_type)


def _period():
    fiscal_year = PeriodRepository.create_fiscal_year(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    return PeriodRepository.create_period(
        fiscal_year_id=fiscal_year.id,
        year=2026,
        month=3,
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
    )


def test_agent_instruction_versions(test_db):
    client = TestClient(app)

    response = client.get("/api/v1/agent-instructions/accounting", headers=_headers())
    assert response.status_code == 200
    assert response.json()["version"] == 1
    assert "Bokföringsinstruktioner" in response.json()["content_markdown"]

    response = client.put(
        "/api/v1/agent-instructions/accounting",
        headers=_headers(),
        json={
            "content_markdown": "# Bokföringsinstruktioner\n\n- Testregel",
            "change_summary": "Teständring",
        },
    )
    assert response.status_code == 200
    assert response.json()["version"] == 2

    response = client.get("/api/v1/agent-instructions/accounting/versions", headers=_headers())
    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert response.json()["versions"][0]["change_summary"] == "Teständring"

    response = client.get("/api/v1/agent-instructions/invoicing", headers=_headers())
    assert response.status_code == 200
    assert response.json()["version"] == 1
    assert "Faktureringsinstruktioner" in response.json()["content_markdown"]

    response = client.put(
        "/api/v1/agent-instructions/invoicing",
        headers=_headers(),
        json={
            "content_markdown": "# Faktureringsinstruktioner\n\n- Testregel",
            "change_summary": "Fakturatest",
        },
    )
    assert response.status_code == 200
    assert response.json()["scope"] == "invoicing"
    assert response.json()["version"] == 2


def test_agent_posts_directly_and_correction_is_agent_readable(test_db):
    _ensure_accounts()
    period = _period()
    client = TestClient(app)

    response = client.post(
        "/api/v1/agent/vouchers",
        headers=_headers(),
        json={
            "date": "2026-03-10",
            "period_id": period.id,
            "description": "Telefonutgift Fello",
            "reasoning_summary": "Test",
            "rows": [
                {"account": "1920", "debit": 0, "credit": 12500},
                {"account": "6200", "debit": 12500, "credit": 0},
            ],
        },
    )
    assert response.status_code == 201
    original = response.json()
    assert original["status"] == "posted"
    assert original["created_by"] == "agent"

    response = client.post(
        f"/api/v1/vouchers/{original['id']}/correct",
        headers=_headers(),
        json={
            "reason": "Bankavgift skulle användas",
            "corrected_rows": [
                {"account": "1920", "debit": 0, "credit": 12500},
                {"account": "6570", "debit": 12500, "credit": 0},
            ],
        },
    )
    assert response.status_code == 200
    correction = response.json()
    assert correction["series"] == "B"
    assert correction["status"] == "posted"
    assert correction["correction_of"] == original["id"]
    assert correction["row_count"] == 4

    response = client.get("/api/v1/accounting-corrections", headers=_headers())
    assert response.status_code == 200
    corrections = response.json()["corrections"]
    assert corrections[0]["original_voucher_id"] == original["id"]
    assert corrections[0]["corrected_voucher_id"] == correction["id"]
    assert corrections[0]["correction_reason"] == "Bankavgift skulle användas"
