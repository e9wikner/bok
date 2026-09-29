"""Ingående balans som saldo, inte verifikation (migration 033).

The first fiscal year's IB is stated; a later year's is derived from the
previous year, so it follows every change there until that year is locked.
"""

import os
import sqlite3
import tempfile
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from repositories.account_repo import AccountRepository
from repositories.audit_repo import AuditRepository
from repositories.period_repo import PeriodRepository
from services.ledger import LedgerService
from services.opening_balance import OpeningBalanceService


@pytest.fixture
def client(test_db):
    for code, name, acc_type in [
        ("1930", "Företagskonto", "asset"),
        ("2081", "Aktiekapital", "equity"),
        ("2099", "Årets resultat", "equity"),
        ("2440", "Leverantörsskulder", "liability"),
        ("3010", "Försäljning", "revenue"),
        ("5010", "Lokalhyra", "expense"),
    ]:
        _account(code, name, acc_type)

    from api.main import app

    return TestClient(app)


def _account(code: str, name: str, acc_type: str) -> None:
    if not AccountRepository.exists(code):
        AccountRepository.create(code, name, acc_type)


def _year(start_year: int):
    fy = PeriodRepository.create_fiscal_year(
        start_date=date(start_year, 1, 1), end_date=date(start_year, 12, 31)
    )
    period = PeriodRepository.create_period(
        fiscal_year_id=fy.id,
        year=start_year,
        month=1,
        start_date=date(start_year, 1, 1),
        end_date=date(start_year, 1, 31),
    )
    return fy, period


def _post(period, rows, day=date(2025, 1, 15)):
    ledger = LedgerService()
    draft = ledger.create_voucher(
        series="A",
        date=day,
        period_id=period.id,
        description="Test",
        rows_data=rows,
    )
    return ledger.post_voucher(draft.id)


def test_derived_ib_follows_the_previous_year_until_it_is_locked(client, auth_headers):
    """The problem this replaces: next year's IB had to be re-booked every
    time the previous year changed. Now it simply follows."""
    fy_2025, period_2025 = _year(2025)
    fy_2026, _ = _year(2026)
    service = OpeningBalanceService()
    service.state(fy_2025.id, {"1930": 100000, "2081": -100000}, actor="test")

    assert service.balances(fy_2026.id) == {"1930": 100000, "2081": -100000}

    # A late sale in 2025: the 2026 IB carries it, result on 2099.
    _post(
        period_2025,
        [
            {"account": "1930", "debit": 25000, "credit": 0},
            {"account": "3010", "debit": 0, "credit": 25000},
        ],
    )
    opening = service.get(fy_2026.id)
    assert opening.source == "derived"
    assert opening.balanced
    assert opening.balances == {"1930": 125000, "2081": -100000, "2099": -25000}

    # Nothing to post: the year locks with no IB draft in the way.
    resp = client.post(f"/api/v1/fiscal-years/{fy_2026.id}/lock", headers=auth_headers)
    assert resp.status_code == 200


def test_result_closed_to_2099_is_not_counted_twice(test_db):
    for code, acc_type in [
        ("1930", "asset"),
        ("2099", "equity"),
        ("3010", "revenue"),
        ("8999", "expense"),
    ]:
        _account(code, code, acc_type)
    fy_2025, period_2025 = _year(2025)
    fy_2026, _ = _year(2026)
    _post(
        period_2025,
        [
            {"account": "1930", "debit": 5000, "credit": 0},
            {"account": "3010", "debit": 0, "credit": 5000},
        ],
    )
    # Bokslut: årets resultat 8999 / 2099.
    _post(
        period_2025,
        [
            {"account": "8999", "debit": 5000, "credit": 0},
            {"account": "2099", "debit": 0, "credit": 5000},
        ],
    )
    assert OpeningBalanceService().balances(fy_2026.id) == {
        "1930": 5000,
        "2099": -5000,
    }


def test_put_states_the_first_years_ib_and_audits_it(client, auth_headers):
    fy, _ = _year(2025)
    resp = client.put(
        f"/api/v1/fiscal-years/{fy.id}/opening-balances",
        headers=auth_headers,
        json={
            "balances": [
                {"account": "1930", "amount": 50000},
                {"account": "2081", "amount": -50000},
            ]
        },
    )
    assert resp.status_code == 200
    assert resp.json()["source"] == "stated"

    history = AuditRepository.get_history("opening_balance", fy.id)
    assert [entry.action.value for entry in history] == ["created"]
    assert history[0].payload["after"] == {"1930": 50000, "2081": -50000}


@pytest.mark.parametrize(
    "rows, code",
    [
        (
            [{"account": "1930", "amount": 50000}],
            "opening_balance_unbalanced",
        ),
        (
            [
                {"account": "3010", "amount": -50000},
                {"account": "1930", "amount": 50000},
            ],
            "opening_balance_not_balance_account",
        ),
    ],
)
def test_put_refuses_an_invalid_ib(client, auth_headers, rows, code):
    fy, _ = _year(2025)
    resp = client.put(
        f"/api/v1/fiscal-years/{fy.id}/opening-balances",
        headers=auth_headers,
        json={"balances": rows},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == code


def test_put_refuses_a_derived_year_and_a_locked_year(client, auth_headers):
    fy_2025, _ = _year(2025)
    fy_2026, _ = _year(2026)
    body = {
        "balances": [
            {"account": "1930", "amount": 50000},
            {"account": "2081", "amount": -50000},
        ]
    }

    resp = client.put(
        f"/api/v1/fiscal-years/{fy_2026.id}/opening-balances",
        headers=auth_headers,
        json=body,
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "opening_balance_derived"

    client.post(f"/api/v1/fiscal-years/{fy_2025.id}/lock", headers=auth_headers)
    resp = client.put(
        f"/api/v1/fiscal-years/{fy_2025.id}/opening-balances",
        headers=auth_headers,
        json=body,
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "fiscal_year_locked"


def test_locked_years_stated_ib_is_fixed_in_the_database(test_db):
    """Defence in depth: the trigger holds even past the service."""
    _account("1930", "Företagskonto", "asset")
    fy, _ = _year(2025)
    OpeningBalanceService().state(fy.id, {"1930": 0}, actor="test")
    PeriodRepository.lock_fiscal_year(fy.id)
    with pytest.raises(sqlite3.IntegrityError, match="locked"):
        test_db.execute(
            "INSERT INTO opening_balances "
            "(fiscal_year_id, account_code, amount, updated_by) "
            "VALUES (?, '1930', 1, 'test')",
            (fy.id,),
        )


def test_no_new_ib_series_voucher(client):
    _, period = _year(2025)
    from domain.validation import ValidationError

    with pytest.raises(ValidationError) as exc:
        LedgerService().create_voucher(
            series="IB",
            date=date(2025, 1, 1),
            period_id=period.id,
            description="Ingående balans",
            rows_data=[
                {"account": "1930", "debit": 100, "credit": 0},
                {"account": "2081", "debit": 0, "credit": 100},
            ],
        )
    assert exc.value.code == "opening_balance_not_a_voucher"


def test_reports_start_from_the_ib(client):
    fy, period = _year(2025)
    OpeningBalanceService().state(
        fy.id, {"1930": 100000, "2081": -100000}, actor="test"
    )
    _post(
        period,
        [
            {"account": "5010", "debit": 30000, "credit": 0},
            {"account": "1930", "debit": 0, "credit": 30000},
        ],
    )

    trial = LedgerService().get_trial_balance(period.id)
    assert trial["1930"] == {"debit": 100000, "credit": 30000}

    ledger_rows = LedgerService().get_account_ledger("1930", period.id)
    assert ledger_rows[0]["description"] == "Ingående balans"
    assert ledger_rows[-1]["balance"] == 70000

    sheet = client.get(
        "/api/v1/reports/balance-sheet", params={"fiscal_year_id": fy.id}
    ).json()
    assert sheet["opening_balance_source"] == "stated"
    assert sheet["opening_bank_and_cash"] == 100000
    assert sheet["closing_bank_and_cash"] == 70000


def test_migration_033_moves_ib_drafts_out_of_the_voucher_table():
    """The SIE4 import used to leave the IB as a draft voucher, which blocked
    locking the year. 033 moves it to `opening_balances` and deletes the
    draft; a posted IB voucher is kept and copied."""
    migrations = sorted((Path(__file__).parent.parent / "db/migrations").glob("*.sql"))
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute(
            "CREATE TABLE schema_version (version INTEGER PRIMARY KEY, "
            "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        for migration in migrations:
            if int(migration.name.split("_")[0]) < 33:
                conn.executescript(migration.read_text())

        conn.executescript("""
            INSERT OR IGNORE INTO accounts (code, name, account_type) VALUES
                ('1930', 'Bank', 'asset'), ('2081', 'AK', 'equity');
            INSERT INTO fiscal_years (id, start_date, end_date) VALUES
                ('fy1', '2011-01-01', '2011-12-31'),
                ('fy2', '2012-01-01', '2012-12-31');
            INSERT INTO periods (id, fiscal_year_id, year, month, start_date, end_date)
            VALUES ('p1', 'fy1', 2011, 1, '2011-01-01', '2011-01-31'),
                   ('p2', 'fy2', 2012, 1, '2012-01-01', '2012-01-31');
            INSERT INTO vouchers (id, series, number, date, period_id,
                                  fiscal_year_id, description, status)
            VALUES ('posted-ib', 'IB', NULL, '2011-01-01', 'p1', 'fy1', 'IB 2011', 'draft'),
                   ('draft-ib', 'IB', NULL, '2012-01-01', 'p2', 'fy2', 'IB 2012', 'draft');
            INSERT INTO voucher_rows (id, voucher_id, account_code, debit, credit) VALUES
                ('r1', 'posted-ib', '1930', 500, 0), ('r2', 'posted-ib', '2081', 0, 500),
                ('r3', 'draft-ib', '1930', 700, 0), ('r4', 'draft-ib', '2081', 0, 700);
            UPDATE vouchers SET status = 'posted', number = 1 WHERE id = 'posted-ib';
            """)

        [m033] = [m for m in migrations if m.name.startswith("033_")]
        conn.executescript(m033.read_text())

        stated = {
            (row["fiscal_year_id"], row["account_code"]): row["amount"]
            for row in conn.execute("SELECT * FROM opening_balances")
        }
        assert stated == {
            ("fy1", "1930"): 500,
            ("fy1", "2081"): -500,
            ("fy2", "1930"): 700,
            ("fy2", "2081"): -700,
        }
        remaining = [row["id"] for row in conn.execute("SELECT id FROM vouchers")]
        assert remaining == ["posted-ib"]
        audit = conn.execute(
            "SELECT entity_id, actor FROM audit_log WHERE action = 'deleted'"
        ).fetchall()
        assert [(row["entity_id"], row["actor"]) for row in audit] == [
            ("draft-ib", "migration_033")
        ]
    finally:
        conn.close()
        os.remove(path)
