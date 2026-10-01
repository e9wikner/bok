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


# ---------------------------------------------------------------------------
# O2 — missing_attachment and age_days on the voucher
# ---------------------------------------------------------------------------


def _list_vouchers(client, auth_headers, **params) -> dict:
    resp = client.get("/api/v1/vouchers", headers=auth_headers, params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_missing_attachment_is_derived_per_voucher(client, auth_headers, period_id):
    """Testfall 4: true on a posted voucher without attachment, false with one."""
    without = _posted_voucher(client, auth_headers, period_id, date(2026, 3, 10))
    with_file = _posted_voucher(client, auth_headers, period_id, date(2026, 3, 11))
    _attach(with_file)

    by_id = {v["id"]: v for v in _list_vouchers(client, auth_headers)["vouchers"]}

    assert by_id[without]["missing_attachment"] is True
    assert by_id[with_file]["missing_attachment"] is False

    # Same on the single-voucher read.
    resp = client.get(f"/api/v1/vouchers/{without}", headers=auth_headers)
    assert resp.json()["missing_attachment"] is True


def test_age_days_counts_from_the_voucher_date(client, auth_headers, period_id):
    """Testfall 5: age is the age of the business event, not of the posting."""
    when = date(2026, 3, 15)
    voucher_id = _posted_voucher(client, auth_headers, period_id, when)

    resp = client.get(f"/api/v1/vouchers/{voucher_id}", headers=auth_headers)
    assert resp.status_code == 200

    expected = (date.today() - when).days
    assert resp.json()["age_days"] == expected


def _count_execute(monkeypatch, work) -> int:
    """Count db.execute calls made while *work* runs."""
    original = db.execute
    calls = []

    def counting(sql, params=()):
        calls.append(sql)
        return original(sql, params)

    monkeypatch.setattr(db, "execute", counting)
    try:
        work()
    finally:
        monkeypatch.undo()
    return len(calls)


def test_listing_does_not_add_sql_calls_per_voucher(
    client, auth_headers, fiscal_year_id, monkeypatch
):
    """Testfall 15: the per-voucher SQL cost of a listing is unchanged.

    Measured before O2: 3 db.execute calls per listed voucher (the row itself,
    its rows, and the account lookup in _voucher_to_response).
    """
    per_voucher_before_o2 = 3

    march = _period_for(fiscal_year_id, date(2026, 3, 1))
    _posted_voucher(client, auth_headers, march, date(2026, 3, 1))
    one = _count_execute(monkeypatch, lambda: _list_vouchers(client, auth_headers))

    for day in (2, 3, 4):
        _posted_voucher(client, auth_headers, march, date(2026, 3, day))
    four = _count_execute(monkeypatch, lambda: _list_vouchers(client, auth_headers))

    marginal = (four - one) / 3
    assert (
        marginal <= per_voucher_before_o2
    ), f"{marginal} SQL calls per listed voucher, was {per_voucher_before_o2}"


# ---------------------------------------------------------------------------
# O3 — ?missing_attachment=true&sort_by=age
# ---------------------------------------------------------------------------


def test_missing_attachment_filter_selects_both_ways(client, auth_headers, period_id):
    """Testfall 6: true gives only those without, false only those with."""
    without = _posted_voucher(client, auth_headers, period_id, date(2026, 3, 10))
    with_file = _posted_voucher(client, auth_headers, period_id, date(2026, 3, 11))
    _attach(with_file)

    missing = _list_vouchers(client, auth_headers, missing_attachment="true")
    assert [v["id"] for v in missing["vouchers"]] == [without]
    assert missing["total"] == 1

    complete = _list_vouchers(client, auth_headers, missing_attachment="false")
    assert [v["id"] for v in complete["vouchers"]] == [with_file]
    assert complete["total"] == 1

    unfiltered = _list_vouchers(client, auth_headers)
    assert unfiltered["total"] == 2


def test_sort_by_age_gives_oldest_first(client, auth_headers, fiscal_year_id):
    """Testfall 7: ?sort_by=age is oldest first."""
    days = [date(2026, 1, 20), date(2026, 3, 15), date(2026, 9, 2)]
    ids = [
        _posted_voucher(client, auth_headers, _period_for(fiscal_year_id, d), d)
        for d in days
    ]

    listed = _list_vouchers(client, auth_headers, sort_by="age")
    assert [v["id"] for v in listed["vouchers"]] == ids

    ages = [v["age_days"] for v in listed["vouchers"]]
    assert ages == sorted(ages, reverse=True)


def test_missing_attachment_filter_honoured_with_period_id(
    client, auth_headers, fiscal_year_id
):
    """Testfall 8: the filter behaves the same in the period_id branch."""
    march = _period_for(fiscal_year_id, date(2026, 3, 1))
    without = _posted_voucher(client, auth_headers, march, date(2026, 3, 10))
    with_file = _posted_voucher(client, auth_headers, march, date(2026, 3, 11))
    _attach(with_file)

    scoped = _list_vouchers(
        client, auth_headers, period_id=march, missing_attachment="true"
    )
    assert [v["id"] for v in scoped["vouchers"]] == [without]
    assert scoped["total"] == 1

    scoped_complete = _list_vouchers(
        client, auth_headers, period_id=march, missing_attachment="false"
    )
    assert [v["id"] for v in scoped_complete["vouchers"]] == [with_file]


def test_draft_without_attachment_is_never_missing_attachment(
    client, auth_headers, period_id
):
    """Testfall 9: a draft without attachment is a draft, not a complement."""
    posted = _posted_voucher(client, auth_headers, period_id, date(2026, 3, 10))
    draft = _create_voucher(client, auth_headers, period_id, date(2026, 3, 11))

    missing = _list_vouchers(client, auth_headers, missing_attachment="true")
    assert [v["id"] for v in missing["vouchers"]] == [posted]

    # Nor on the other side of the filter: the flag is about posted vouchers.
    complete = _list_vouchers(client, auth_headers, missing_attachment="false")
    assert draft not in [v["id"] for v in complete["vouchers"]]

    scoped = _list_vouchers(
        client, auth_headers, period_id=period_id, missing_attachment="true"
    )
    assert [v["id"] for v in scoped["vouchers"]] == [posted]


# ---------------------------------------------------------------------------
# O4 — GET /api/v1/overview
# ---------------------------------------------------------------------------


def _overview(client, auth_headers) -> dict:
    resp = client.get("/api/v1/overview", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _row_census() -> dict:
    """Row count per table, to prove a read wrote nothing."""
    tables = [
        row["name"]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]
    return {
        table: db.execute(f"SELECT COUNT(*) AS cnt FROM {table}").fetchone()["cnt"]
        for table in tables
    }


def _overdue_invoice(client, auth_headers) -> None:
    """An invoice whose due date has passed."""
    from services.invoice import InvoiceService

    InvoiceService().create_invoice(
        customer_name="Kund AB",
        invoice_date=date(2026, 1, 10),
        due_date=date(2026, 2, 10),
        rows_data=[
            {
                "description": "Konsultarvode",
                "quantity": 1,
                "unit_price": 100000,
                "vat_code": "MP1",
            }
        ],
    )


def test_overview_has_three_pages_in_order(client, auth_headers, period_id):
    """Testfall 10: three pages, in the order bocker, betala, bokslut."""
    data = _overview(client, auth_headers)

    assert [page["key"] for page in data["pages"]] == ["bocker", "betala", "bokslut"]
    assert data["fiscal_year"]["label"] == "2026"
    assert data["fiscal_year"]["start"] == "2026-01-01"
    assert data["period_state"]["locked"] is False

    for page in data["pages"]:
        assert set(page["counters"]) == {
            "open_decisions",
            "overdue_invoices",
            "payroll_waiting",
            "missing_attachments",
        }
        assert page["title"]
        assert page["meta"]


def test_waiting_is_true_exactly_when_a_counter_is_nonzero(
    client, auth_headers, period_id
):
    """Testfall 11: the server decides waiting, the client counts nothing."""
    quiet = _overview(client, auth_headers)
    assert [page["waiting"] for page in quiet["pages"]] == [False, False, False]

    _posted_voucher(client, auth_headers, period_id, date(2026, 3, 10))

    data = _overview(client, auth_headers)
    for page in data["pages"]:
        assert page["waiting"] is any(
            count != 0 for count in page["counters"].values()
        ), page["key"]

    bocker = data["pages"][0]
    assert bocker["counters"]["missing_attachments"] == 1
    assert bocker["waiting"] is True


def test_overdue_invoices_matches_the_invoice_summary(client, auth_headers, period_id):
    """Testfall 12: the same predicate as GET /invoices, not a second one."""
    _overdue_invoice(client, auth_headers)

    listed = client.get("/api/v1/invoices", headers=auth_headers)
    assert listed.status_code == 200
    expected = listed.json()["summary"]["overdue_count"]
    assert expected == 1

    betala = _overview(client, auth_headers)["pages"][1]
    assert betala["key"] == "betala"
    assert betala["counters"]["overdue_invoices"] == expected
    assert betala["waiting"] is True


def test_overview_requires_bearer(client):
    """Testfall 13: no bearer, no overview."""
    assert client.get("/api/v1/overview").status_code == 401


def test_overview_writes_nothing(client, auth_headers, period_id):
    """Testfall 14: twice over gives the same answer and no new rows."""
    _posted_voucher(client, auth_headers, period_id, date(2026, 3, 10))
    _overdue_invoice(client, auth_headers)

    before = _row_census()
    first = _overview(client, auth_headers)
    second = _overview(client, auth_headers)

    assert first == second
    assert _row_census() == before
