"""Tests for the `underlagstolkning` module
(docs/redesign/SPEC-underlagstolkning.md).

Grows across tasks U1-U10 of `tasks/underlagstolkning/todo.md`; each task
gets its own section. Test case numbers refer to the tables in spec §10.

Per the spec no LLM is ever called from a test.
"""

import re
import uuid
from datetime import date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from config import settings
from db.database import db
from repositories.account_repo import AccountRepository
from repositories.intake_repo import IntakeRepository
from repositories.period_repo import PeriodRepository
from services.compliance import ComplianceService
from services.ledger import LedgerService

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def client(test_db):
    """Test client bound after the database swap (pattern from test_oversikt)."""
    for code, name, acc_type in [
        ("1510", "Kundfordringar", "asset"),
        ("3011", "Försäljning tjänster 25%", "revenue"),
    ]:
        if not AccountRepository.exists(code):
            AccountRepository.create(code, name, acc_type)

    from api.main import app

    return TestClient(app)


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {settings.api_key}"}


@pytest.fixture
def period_id(test_db):
    """March 2026 in fiscal year 2026."""
    fy = PeriodRepository.create_fiscal_year(
        start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)
    )
    period = PeriodRepository.create_period(
        fiscal_year_id=fy.id,
        year=2026,
        month=3,
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
    )
    return period.id


def _posted(
    period_id: str,
    *,
    amount: int = 60000,
    created_by: str = "agent",
    day: int = 10,
) -> str:
    """A posted A-series voucher over 500 kr, created the way its
    `created_by` says (the SIE4 importer uses `create_voucher` +
    `post_voucher` with `sie4_import` too, services/sie4_import.py)."""
    ledger = LedgerService()
    draft = ledger.create_voucher(
        series="A",
        date=date(2026, 3, day),
        period_id=period_id,
        description=f"Köp {uuid.uuid4().hex[:6]}",
        rows_data=[
            {"account": "1510", "debit": amount, "credit": 0},
            {"account": "3011", "debit": 0, "credit": amount},
        ],
        created_by=created_by,
    )
    return ledger.post_voucher(draft.id, actor=created_by).id


def _attach(voucher_id: str) -> None:
    """An `attachments` row, as `POST /vouchers/{id}/attachments` writes it."""
    db.execute(
        """
        INSERT INTO attachments
            (id, voucher_id, filename, sha256, mime_type, stored_path,
             size_bytes, uploaded_at)
        VALUES (?, ?, 'kvitto.pdf', ?, 'application/pdf', '/tmp/kvitto.pdf',
                1024, ?)
        """,
        (str(uuid.uuid4()), voucher_id, uuid.uuid4().hex, datetime.now()),
    )
    db.commit()


def _link_intake_source(voucher_id: str) -> None:
    """A `voucher_intake_sources` row, as the agent's posting writes it
    (services/voucher_posting.py) -- and no row in `attachments`."""
    source_id = str(uuid.uuid4())
    IntakeRepository.create_source(
        source_id=source_id,
        original_filename="kvitto.pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        sha256=uuid.uuid4().hex,
        stored_path="/tmp/kvitto.pdf",
        uploaded_by="test",
        status="processed",
    )
    IntakeRepository.create_voucher_link(
        intake_source_id=source_id, voucher_id=voucher_id, linked_by="agent"
    )


def _missing_flag(client, auth_headers, voucher_id: str) -> bool:
    resp = client.get(f"/api/v1/vouchers/{voucher_id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["missing_attachment"]


# ---------------------------------------------------------------------------
# U1 — the predicate "saknar underlag" (§2.1, §10.1)
# ---------------------------------------------------------------------------


def test_01_posted_with_attachment_is_not_missing(client, auth_headers, period_id):
    """Testfall 1: posted, a row in `attachments` -> false."""
    voucher_id = _posted(period_id)
    _attach(voucher_id)

    assert _missing_flag(client, auth_headers, voucher_id) is False


def test_02_posted_with_intake_source_is_not_missing(client, auth_headers, period_id):
    """Testfall 2: posted, a row in `voucher_intake_sources` and none in
    `attachments` -> false (was true before U1)."""
    voucher_id = _posted(period_id)
    _link_intake_source(voucher_id)

    assert _missing_flag(client, auth_headers, voucher_id) is False
    complete = client.get(
        "/api/v1/vouchers",
        headers=auth_headers,
        params={"missing_attachment": "false"},
    ).json()
    assert [v["id"] for v in complete["vouchers"]] == [voucher_id]


def test_03_posted_with_neither_is_missing(client, auth_headers, period_id):
    """Testfall 3: posted, neither -> true. Created by the agent or by
    hand, the SIE4 exception does not reach it."""
    by_agent = _posted(period_id, created_by="agent")
    by_hand = _posted(period_id, created_by="system")

    assert _missing_flag(client, auth_headers, by_agent) is True
    assert _missing_flag(client, auth_headers, by_hand) is True


def test_04_overview_filter_and_compliance_agree(client, auth_headers, period_id):
    """Testfall 4: `GET /overview`, `GET /vouchers?missing_attachment=true`
    and `compliance` give the same number on the same data."""
    _attach(_posted(period_id, day=2))
    _link_intake_source(_posted(period_id, day=3))
    _posted(period_id, day=4, created_by="sie4_import")
    missing = {_posted(period_id, day=5), _posted(period_id, day=6)}

    overview = client.get("/api/v1/overview", headers=auth_headers)
    assert overview.status_code == 200, overview.text
    counters = overview.json()["pages"][0]["counters"]

    listed = client.get(
        "/api/v1/vouchers",
        headers=auth_headers,
        params={"missing_attachment": "true"},
    ).json()

    issues = ComplianceService()._check_missing_attachments()
    assert len(issues) == 1
    match = re.search(r"(\d+) verifikationer", issues[0].title)
    assert match is not None

    assert {v["id"] for v in listed["vouchers"]} == missing
    assert counters["missing_attachments"] == listed["total"] == 2
    assert int(match.group(1)) == 2


def test_05_compliance_has_no_sql_of_its_own_for_the_predicate():
    """Testfall 5: `services/compliance.py` uses the shared predicate
    through `VoucherRepository`, it does not carry a copy (grep test)."""
    source = (REPO_ROOT / "services" / "compliance.py").read_text(encoding="utf-8")

    assert "FROM attachments" not in source
    assert "voucher_intake_sources" not in source
    assert "sie4_import" not in source
    assert "MISSING_ATTACHMENT_SQL" not in source
    assert "count_missing_attachments" in source


def test_05b_sie4_imported_voucher_is_not_missing(client, auth_headers, period_id):
    """Testfall 5b: posted, `created_by = 'sie4_import'`, neither
    `attachments` nor `voucher_intake_sources` -> false (§12.5)."""
    imported = _posted(period_id, created_by="sie4_import")

    assert _missing_flag(client, auth_headers, imported) is False
    assert ComplianceService()._check_missing_attachments() == []
    missing = client.get(
        "/api/v1/vouchers",
        headers=auth_headers,
        params={"missing_attachment": "true"},
    ).json()
    assert missing["total"] == 0
