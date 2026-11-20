"""A review from start to finish with the review key (docs/granskning.md
§2): entrypoint, instruction, the books, the upload, the list. The ledger
is the same afterwards."""

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from api.main import app
from config import settings
from db.database import db
from repositories.account_repo import AccountRepository

REVIEW_KEY = "test-review-key-0123456789"
#: Every table that is not one of the review's own.
LEDGER_TABLES_EXCLUDED = {
    "review_reports",
    "review_findings",
    "review_finding_vouchers",
    "review_examined_vouchers",
}


def _row_counts() -> dict:
    tables = [
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        if row[0] not in LEDGER_TABLES_EXCLUDED
    ]
    return {
        table: db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        for table in tables
    }


@pytest.fixture
def posted_voucher(ledger_service, fiscal_year, test_period):
    for code, kind in [("1930", "asset"), ("5010", "expense")]:
        if not AccountRepository.exists(code):
            AccountRepository.create(code, code, kind)
    voucher = ledger_service.create_voucher(
        series="A",
        date=date(2026, 3, 1),
        period_id=test_period.id,
        description="Hyra mars",
        rows_data=[
            {"account": "5010", "debit": 500000, "credit": 0},
            {"account": "1930", "debit": 0, "credit": 500000},
        ],
    )
    ledger_service.post_voucher(voucher.id)
    return voucher.id


def test_a_review_with_the_review_key(monkeypatch, posted_voucher, fiscal_year):
    monkeypatch.setattr(settings, "review_api_key", REVIEW_KEY)
    public = TestClient(app)
    reviewer = TestClient(app, headers={"Authorization": f"Bearer {REVIEW_KEY}"})
    before = _row_counts()

    entrypoint = public.get("/api/v1/review/entrypoint").json()
    step = entrypoint["startup_sequence"][0]
    path = step["path"].replace("{id}", fiscal_year.id)
    check = entrypoint["auth"]["check"]
    assert reviewer.request(check["method"], check["path"]).status_code == 200

    instructions = reviewer.get(path)
    assert instructions.status_code == 200
    data = instructions.json()
    assert data["fiscal_year"]["id"] == fiscal_year.id
    endpoints = data["read_endpoints"]

    sie4 = reviewer.get(endpoints["sie4"])
    assert sie4.status_code == 200
    assert "#VER" in sie4.content.decode("cp437")

    page = reviewer.get(endpoints["vouchers"]).json()
    assert page["total"] == 1
    voucher_id = page["vouchers"][0]["id"]
    assert voucher_id == posted_voucher
    voucher = reviewer.get(endpoints["voucher"].replace("{voucher_id}", voucher_id))
    assert voucher.status_code == 200
    context = reviewer.get(
        endpoints["source_context"].replace("{voucher_id}", voucher_id)
    )
    assert context.status_code == 200
    balance = reviewer.get(endpoints["balance_sheet"])
    assert balance.status_code == 200

    report_id = str(uuid.uuid4())
    upload = entrypoint["startup_sequence"][2]
    response = reviewer.request(
        upload["method"],
        upload["path"],
        json={
            "id": report_id,
            "fiscal_year_id": fiscal_year.id,
            "reviewer": {"agent": "Claude Code", "model": "claude-opus-5-5"},
            "instruction_sha256": data["instruction_sha256"],
            "summary_markdown": "Hela året prövades. Inga lager, inga externa bekräftelser.",
            "examined_voucher_ids": [voucher_id],
            "findings": [
                {
                    "severity": "should_fix",
                    "area": "underlag",
                    "title": "Kvitto saknas",
                    "description": "Hyran har inget underlag i source-context.",
                    "voucher_ids": [voucher_id],
                    "amount_ore": 500000,
                }
            ],
        },
    )
    assert response.status_code == 201, response.text

    listed = reviewer.get(f"/api/v1/review/reports?fiscal_year_id={fiscal_year.id}")
    reports = listed.json()["reports"]
    assert [r["id"] for r in reports] == [report_id]
    assert reports[0]["uploaded_by"] == "review_key"
    assert reports[0]["instruction_outdated"] is False
    assert reports[0]["counts"]["should_fix"] == 1

    assert _row_counts() == before
