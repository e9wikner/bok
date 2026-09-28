"""Tests for the `underlagstolkning` module
(docs/redesign/SPEC-underlagstolkning.md).

Grows across tasks U1-U10 of `tasks/underlagstolkning/todo.md`; each task
gets its own section. Test case numbers refer to the tables in spec §10.

Per the spec no LLM is ever called from a test.
"""

import json
import re
import sqlite3
import uuid
from datetime import date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from config import settings
from db.database import db
from domain.interpretation import Candidate, Interpretation, Match
from repositories.account_repo import AccountRepository
from repositories.intake_repo import IntakeRepository
from repositories.interpretation_repo import InterpretationRepository
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


# ---------------------------------------------------------------------------
# U2 — migration 030, domain and repository (§5, §10.4)
# ---------------------------------------------------------------------------


MIGRATION_030 = REPO_ROOT / "db" / "migrations" / "030_add_intake_interpretations.sql"
SPEC = REPO_ROOT / "docs" / "redesign" / "SPEC-underlagstolkning.md"


def _intake_source() -> str:
    """An `intake_sources` row for an interpretation to point at."""
    source_id = str(uuid.uuid4())
    IntakeRepository.create_source(
        source_id=source_id,
        original_filename="kvitto.pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        sha256=uuid.uuid4().hex,
        stored_path="/tmp/kvitto.pdf",
        uploaded_by="test",
    )
    return source_id


def _interpretation(source_id: str, **overrides) -> Interpretation:
    """Flöde 4's receipt (§6.5, §7.4): 4 600 kr against A-118's 4 480."""
    values = dict(
        intake_source_id=source_id,
        vendor="Elektronikhuset",
        document_date=date(2026, 6, 3),
        currency="SEK",
        total_ore=460000,
        vat_ore=89600,
        lines=[
            {"text": "USB-C docka", "amount_ore": 448000, "vat_rate": 25},
            {"text": "Pant", "amount_ore": 12000, "vat_rate": 0},
        ],
        checks={
            "lines_sum": "ok",
            "vat_rate": "ok",
            "vat_share": "not_applicable",
            "text_layer": "agrees",
            "date": "ok",
            "currency": "sek",
        },
        confidence="high",
        match=Match(
            kind="amount_diff",
            voucher_id="v-118",
            voucher_number="A-118",
            voucher_date="2026-06-03",
            voucher_description="Förbrukningsinventarier",
            amounts={"document_ore": 460000, "voucher_ore": 448000},
            diff_ore=12000,
            date_diff_days=0,
            vat={"document_ore": 89600, "voucher_ore": 89600, "equal": True},
            bank_transaction={
                "id": "bt-1",
                "date": "2026-06-03",
                "amount_ore": -448000,
                "counterpart_name": "ELEKTRONIKHUSET",
            },
            hypothesis={
                "text": "Skillnaden på 120,00 kr motsvarar raden ”Pant” på underlaget.",
                "basis": "line_items",
                "lines": [1],
            },
        ),
        candidates=[
            Candidate(
                voucher_id="v-118",
                voucher_number="A-118",
                voucher_date="2026-06-03",
                voucher_description="Förbrukningsinventarier",
                amounts={"document_ore": 460000, "voucher_ore": 448000},
                diff_ore=12000,
                date_diff_days=0,
                vat={"document_ore": 89600, "voucher_ore": 89600, "equal": True},
                bank_transaction=None,
            )
        ],
        actor="agent",
    )
    values.update(overrides)
    return Interpretation(**values)  # type: ignore[arg-type]


def test_30_migration_is_spec_section_5_verbatim():
    """Migration 030 carries §5's SQL block verbatim: table, index and the
    two triggers."""
    spec = SPEC.read_text(encoding="utf-8")
    section = spec.split("## 5. Datamodell — migration 030", 1)[1]
    block = section.split("```sql\n", 1)[1].split("```", 1)[0]

    assert block.strip() in MIGRATION_030.read_text(encoding="utf-8")


def test_30_migration_is_applied(test_db):
    conn = test_db.connect()
    assert (
        conn.execute("SELECT 1 FROM schema_version WHERE version = 30").fetchone()
        is not None
    )
    triggers = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' "
            "AND tbl_name = 'intake_interpretations'"
        )
    }
    assert triggers == {
        "prevent_update_intake_interpretations",
        "prevent_delete_intake_interpretations",
    }


def test_30_update_and_delete_are_aborted_by_the_triggers(test_db):
    """Testfall 30: `UPDATE`/`DELETE` on `intake_interpretations` -> the
    trigger aborts, and the row is unchanged."""
    source_id = _intake_source()
    saved = InterpretationRepository.insert(_interpretation(source_id))

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute(
            "UPDATE intake_interpretations SET confidence = 'low' WHERE id = ?",
            (saved.id,),
        )
    db.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute("DELETE FROM intake_interpretations WHERE id = ?", (saved.id,))
    db.rollback()

    latest = InterpretationRepository.latest_for_source(source_id)
    assert latest is not None
    assert latest.confidence == "high"
    assert InterpretationRepository.count_for_source(source_id) == 1


def test_30_repository_has_no_update_or_delete():
    """The second of §5's three layers: nothing in the repository rewrites
    or removes a row."""
    public = {n for n in vars(InterpretationRepository) if not n.startswith("_")}
    assert public == {"insert", "latest_for_source", "count_for_source"}
    source = (REPO_ROOT / "repositories" / "interpretation_repo.py").read_text(
        encoding="utf-8"
    )
    assert "UPDATE" not in source
    assert "DELETE" not in source


@pytest.mark.parametrize(
    "overrides",
    [
        {"confidence": "certain"},
        {"total_ore": -1},
        {"vat_ore": -1},
    ],
    ids=["confidence", "total_ore", "vat_ore"],
)
def test_30_check_constraints_reject(test_db, overrides):
    """§5's CHECKs: `confidence` outside high/medium/low and negative
    amounts are refused by the schema itself."""
    source_id = _intake_source()

    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        InterpretationRepository.insert(_interpretation(source_id, **overrides))
    db.rollback()

    assert InterpretationRepository.count_for_source(source_id) == 0


def test_31_two_interpretations_latest_is_the_later(test_db):
    """Testfall 31, repository part: two interpretations of the same
    source are two rows, and `latest_for_source` is the later one -- also
    when both carry the same `created_at` (`ORDER BY created_at, rowid`)."""
    source_id = _intake_source()
    same_second = datetime(2026, 6, 3, 12, 0, 0)
    first = InterpretationRepository.insert(
        _interpretation(source_id, created_at=same_second)
    )
    second = InterpretationRepository.insert(
        _interpretation(
            source_id,
            created_at=same_second,
            total_ore=448000,
            confidence="medium",
            match=None,
            candidates=[],
        )
    )

    assert first.id != second.id
    assert InterpretationRepository.count_for_source(source_id) == 2
    latest = InterpretationRepository.latest_for_source(source_id)
    assert latest is not None
    assert latest.id == second.id
    assert latest.total_ore == 448000
    assert latest.match is None
    assert latest.candidates == []

    assert InterpretationRepository.count_for_source(_intake_source()) == 0
    assert InterpretationRepository.latest_for_source("no-such-source") is None


def test_31_interpretation_round_trips_through_the_json_columns(test_db):
    """What was inserted is what comes back: `lines`, `checks`, `match`
    and `candidates` survive their `*_json` columns unchanged."""
    source_id = _intake_source()
    written = _interpretation(source_id)
    InterpretationRepository.insert(written)

    read = InterpretationRepository.latest_for_source(source_id)
    assert read is not None
    assert read.id == written.id
    assert read.vendor == "Elektronikhuset"
    assert read.document_date == date(2026, 6, 3)
    assert read.vat_ore == 89600
    assert read.lines == written.lines
    assert read.checks == written.checks
    assert read.match == written.match
    assert read.candidates == written.candidates
    assert read.actor == "agent"
    assert read.agent_run_id is None and read.thread_id is None
    assert read.expected_voucher_id is None
    assert isinstance(read.created_at, datetime)

    row = db.execute(
        "SELECT match_json, candidates_json FROM intake_interpretations WHERE id = ?",
        (written.id,),
    ).fetchone()
    assert json.loads(row["match_json"])["diff_ore"] == 12000
    assert json.loads(row["candidates_json"])[0]["voucher_number"] == "A-118"
