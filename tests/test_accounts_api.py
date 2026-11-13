"""`GET /api/v1/accounts/with-transactions`: the accounts the year's postings touch."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from repositories.account_repo import AccountRepository


@pytest.fixture
def client(test_db):
    from api.main import app

    return TestClient(app)


def _rows(account: str) -> list:
    return [
        {"account": account, "debit": 10000, "credit": 0},
        {"account": "1930", "debit": 0, "credit": 10000},
    ]


def test_lists_only_accounts_with_a_posted_voucher_row_in_the_year(
    client, auth_headers, ledger_service, test_period, fiscal_year
):
    """Not a draft's account, and not an account nothing touched."""
    for code, name in [("5010", "Lokalhyra"), ("6110", "Kontorsmateriel")]:
        if not AccountRepository.exists(code):
            AccountRepository.create(code, name, "expense")
    posted = ledger_service.create_voucher(
        series="A",
        date=date(2026, 3, 20),
        period_id=test_period.id,
        description="Hyra",
        rows_data=_rows("5010"),
        created_by="test",
    )
    ledger_service.post_voucher(posted.id, actor="test")
    ledger_service.create_voucher(
        series="A",
        date=date(2026, 3, 21),
        period_id=test_period.id,
        description="Material (utkast)",
        rows_data=_rows("6110"),
        created_by="test",
    )

    resp = client.get(
        f"/api/v1/accounts/with-transactions?fiscal_year_id={fiscal_year.id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["codes"] == ["1930", "5010"]


def test_another_year_has_none(client, auth_headers, fiscal_year):
    resp = client.get(
        "/api/v1/accounts/with-transactions?fiscal_year_id=annat-ar",
        headers=auth_headers,
    )
    assert resp.json()["codes"] == []
