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
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import List, Literal, Optional, Sequence

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


# ---------------------------------------------------------------------------
# U4 — the candidate query (§7.1-§7.2, §10.3 testfall 20-24, 29; 5b)
# ---------------------------------------------------------------------------


@pytest.fixture
def purchase_accounts(test_db):
    """A purchase's accounts: expense, input VAT (`vat_in`), bank."""
    for code, name, acc_type in [
        ("5410", "Förbrukningsinventarier", "expense"),
        ("2640", "Ingående moms", "vat_in"),
        ("1930", "Företagskonto", "asset"),
    ]:
        if not AccountRepository.exists(code):
            AccountRepository.create(code, name, acc_type)


def _purchase(
    period_id: str,
    *,
    total: int,
    vat: int = 0,
    day: int = 15,
    series: str = "A",
    created_by: str = "agent",
    post: bool = True,
) -> str:
    """A purchase paid from the bank: 5410 net + 2640 VAT on the debit
    side, 1930 total on the credit side. Posted unless *post* is false."""
    rows = [{"account": "5410", "debit": total - vat, "credit": 0}]
    if vat:
        rows.append({"account": "2640", "debit": vat, "credit": 0})
    rows.append({"account": "1930", "debit": 0, "credit": total})
    ledger = LedgerService()
    draft = ledger.create_voucher(
        series=series,
        date=date(2026, 3, day),
        period_id=period_id,
        description=f"Inköp {uuid.uuid4().hex[:6]}",
        rows_data=rows,
        created_by=created_by,
    )
    if not post:
        return draft.id
    return ledger.post_voucher(draft.id, actor=created_by).id


def _bank_transaction(
    voucher_id: str,
    *,
    day: int,
    amount: int,
    counterpart: str = "ELEKTRONIKHUSET",
    description: str = "Kortköp",
) -> str:
    """A bank transaction linked to *voucher_id* through
    `voucher_bank_transactions`, as the agent's posting links it."""
    from repositories.bank_input_repo import BankInputRepository

    connection_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO bank_connections (id, provider, bank_name, status) "
        "VALUES (?, 'manual', 'Testbanken', 'active')",
        (connection_id,),
    )
    transaction_id = str(uuid.uuid4())
    db.execute(
        """
        INSERT INTO bank_transactions
            (id, bank_connection_id, external_id, transaction_date, amount,
             description, counterpart_name)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            transaction_id,
            connection_id,
            uuid.uuid4().hex,
            date(2026, 3, day).isoformat(),
            amount,
            description,
            counterpart,
        ),
    )
    db.commit()
    BankInputRepository.create_voucher_bank_transaction_link(
        voucher_id=voucher_id, bank_transaction_id=transaction_id, linked_by="agent"
    )
    return transaction_id


def _amount_window(total_ore: int) -> int:
    """§7.2's amount window, from the constants in services/interpretation."""
    from services.interpretation import AMOUNT_WINDOW_MIN_ORE, AMOUNT_WINDOW_PERCENT

    return max(AMOUNT_WINDOW_MIN_ORE, total_ore * AMOUNT_WINDOW_PERCENT // 100)


def _candidates(document_date, total_ore: int):
    """`match_candidates` with §7.2's windows, as the service will call it."""
    from repositories.voucher_repo import VoucherRepository
    from services.interpretation import (
        DATE_WINDOW_DAYS_AFTER,
        DATE_WINDOW_DAYS_BEFORE,
    )

    return VoucherRepository.match_candidates(
        document_date,
        total_ore,
        date_window=(DATE_WINDOW_DAYS_BEFORE, DATE_WINDOW_DAYS_AFTER),
        amount_window_ore=_amount_window(total_ore),
    )


def _ids(candidates) -> set:
    return {c.voucher_id for c in candidates}


def test_u4_windows_are_constants_in_the_service_not_defaults_in_the_repo():
    """§7.2: the windows are defined in services/interpretation.py and passed
    in; `match_candidates` has no defaults of its own for them."""
    import inspect

    from repositories.voucher_repo import VoucherRepository
    from services import interpretation

    assert interpretation.DATE_WINDOW_DAYS_BEFORE == 3
    assert interpretation.DATE_WINDOW_DAYS_AFTER == 7
    assert interpretation.AMOUNT_WINDOW_MIN_ORE == 5000
    assert interpretation.AMOUNT_WINDOW_PERCENT == 10

    params = inspect.signature(VoucherRepository.match_candidates).parameters
    for name in ("date_window", "amount_window_ore"):
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY
        assert params[name].default is inspect.Parameter.empty


def test_u4_candidate_carries_debit_sum_vat_in_and_bank_transaction(
    period_id, purchase_accounts
):
    """§7.1: `voucher_ore` is the sum of the debit rows (gross), `vat_ore`
    the rows on `vat_in` accounts, and the linked bank transaction rides
    along. Flöde 4's A-118: 4 480 kr of which 896 kr VAT."""
    voucher_id = _purchase(period_id, total=448000, vat=89600, day=3)
    transaction_id = _bank_transaction(
        voucher_id, day=3, amount=-448000, description="Kortköp 0603"
    )

    [candidate] = _candidates(date(2026, 3, 3), 460000)

    assert candidate.voucher_id == voucher_id
    assert candidate.voucher_number == "A-1"
    assert candidate.voucher_date == date(2026, 3, 3)
    assert candidate.voucher_description.startswith("Inköp ")
    assert candidate.voucher_ore == 448000
    assert candidate.vat_ore == 89600
    bank = candidate.bank_transaction
    assert bank is not None
    assert bank.id == transaction_id
    assert bank.date == date(2026, 3, 3)
    assert bank.amount_ore == -448000
    assert bank.counterpart_name == "ELEKTRONIKHUSET"
    assert bank.description == "Kortköp 0603"


def test_u4_candidate_without_vat_or_bank_transaction_has_none(
    period_id, purchase_accounts
):
    """No `vat_in` row → `vat_ore = None` (not 0: §7.1 compares only when
    both exist). No link in `voucher_bank_transactions` → `None`."""
    _purchase(period_id, total=20000)

    [candidate] = _candidates(date(2026, 3, 15), 20000)

    assert candidate.voucher_ore == 20000
    assert candidate.vat_ore is None
    assert candidate.bank_transaction is None


def test_u4_several_bank_transactions_give_one_row_the_earliest(
    period_id, purchase_accounts
):
    """A voucher linked to two bank transactions is one candidate, not two;
    the bank transaction shown is the earliest."""
    voucher_id = _purchase(period_id, total=30000)
    _bank_transaction(voucher_id, day=17, amount=-10000, counterpart="SENARE")
    earliest = _bank_transaction(
        voucher_id, day=16, amount=-20000, counterpart="TIDIGARE"
    )

    candidates = _candidates(date(2026, 3, 15), 30000)

    assert len(candidates) == 1
    assert candidates[0].voucher_id == voucher_id
    assert candidates[0].voucher_ore == 30000
    assert candidates[0].bank_transaction.id == earliest
    assert candidates[0].bank_transaction.counterpart_name == "TIDIGARE"


def test_20_voucher_with_underlag_is_no_candidate(period_id, purchase_accounts):
    """Testfall 20: a voucher whose source is in `voucher_intake_sources`
    has underlag and is no candidate; nor is one with an `attachments` row.
    The one without either is."""
    via_intake = _purchase(period_id, total=20000)
    _link_intake_source(via_intake)
    via_attachment = _purchase(period_id, total=20000)
    _attach(via_attachment)
    open_one = _purchase(period_id, total=20000)

    assert _ids(_candidates(date(2026, 3, 15), 20000)) == {open_one}


def test_05b_sie4_imported_voucher_is_no_candidate(period_id, purchase_accounts):
    """Testfall 5b's exception holds for the candidates too (§7.1): an
    SIE4-imported voucher never gets its underlag in Bok."""
    _purchase(period_id, total=20000, created_by="sie4_import")
    by_agent = _purchase(period_id, total=20000, created_by="agent")

    assert _ids(_candidates(date(2026, 3, 15), 20000)) == {by_agent}


def test_21_ib_series_is_no_candidate(period_id, purchase_accounts):
    """Testfall 21: an opening balance voucher is never a candidate."""
    _purchase(period_id, total=20000, series="IB")
    a_series = _purchase(period_id, total=20000, series="A")

    assert _ids(_candidates(date(2026, 3, 15), 20000)) == {a_series}


def test_u4_draft_is_no_candidate(period_id, purchase_accounts):
    """§7.1: only posted vouchers can get the underlag linked."""
    _purchase(period_id, total=20000, post=False)

    assert _candidates(date(2026, 3, 15), 20000) == []


def test_22_outside_the_date_window_is_no_candidate(period_id, purchase_accounts):
    """Testfall 22: the window is [document_date − 3, document_date + 7],
    both ends included. Document dated 15 March: 12-22 March."""
    by_day = {
        day: _purchase(period_id, total=20000, day=day) for day in (11, 12, 22, 23)
    }

    assert _ids(_candidates(date(2026, 3, 15), 20000)) == {by_day[12], by_day[22]}


def test_23_outside_the_amount_window_is_no_candidate(period_id, purchase_accounts):
    """Testfall 23: on 20 000 öre the window is max(5 000, 2 000) = 5 000.
    A diff of 6 000 is out, 5 000 (either side) is in."""
    _purchase(period_id, total=26000)
    _purchase(period_id, total=14000)
    over = _purchase(period_id, total=25000)
    under = _purchase(period_id, total=15000)

    assert _ids(_candidates(date(2026, 3, 15), 20000)) == {over, under}


def test_23_amount_window_is_ten_percent_on_a_large_total(period_id, purchase_accounts):
    """On 460 000 öre the window is 10 % = 46 000: flöde 4's 12 000 is in,
    46 001 is out."""
    inside = _purchase(period_id, total=448000)
    _purchase(period_id, total=460000 - 46001)

    assert _ids(_candidates(date(2026, 3, 15), 460000)) == {inside}


def test_24_without_document_date_only_the_exact_amount(period_id, purchase_accounts):
    """Testfall 24: no `document_date` → no date window, and only the exact
    amount matches (the amount window is not applied)."""
    exact_early = _purchase(period_id, total=20000, day=1)
    exact_late = _purchase(period_id, total=20000, day=31)
    _purchase(period_id, total=20001, day=15)

    assert _ids(_candidates(None, 20000)) == {exact_early, exact_late}


def test_29_candidate_query_is_one_sql_call(monkeypatch, period_id, purchase_accounts):
    """Testfall 29: one `db.execute` whatever the number of candidates --
    the amounts, the VAT and the bank transaction are joined in."""
    first = _purchase(period_id, total=20000, vat=4000)
    _bank_transaction(first, day=15, amount=-20000)

    def count(document_date, total):
        calls = []
        original = db.execute

        def counting(sql, params=()):
            calls.append(sql)
            return original(sql, params)

        monkeypatch.setattr(db, "execute", counting)
        try:
            found = _candidates(document_date, total)
        finally:
            monkeypatch.undo()
        return len(found), len(calls)

    assert count(date(2026, 3, 15), 20000) == (1, 1)

    for _ in range(3):
        voucher_id = _purchase(period_id, total=20000, vat=4000)
        _bank_transaction(voucher_id, day=16, amount=-20000)

    assert count(date(2026, 3, 15), 20000) == (4, 1)
    assert count(None, 20000) == (4, 1)


# ---------------------------------------------------------------------------
# U3: the checks and the confidence (§6.3-§6.4), pure logic, no database
# ---------------------------------------------------------------------------

U3_TODAY = date(2026, 6, 10)

# Text layers in the shape `reconciliation_result` recognises: one labelled
# amount per line (netto / moms / att betala), Swedish number format.
TEXT_LAYER_4600 = (
    "Elektronikhuset AB\n"
    "Kvitto 2026-06-03\n"
    "Netto 3 680,00 kr\n"
    "Moms 920,00 kr\n"
    "Att betala 4 600,00 kr\n"
)
TEXT_LAYER_4060 = (
    "Elektronikhuset AB\n"
    "Kvitto 2026-06-03\n"
    "Netto 3 248,00 kr\n"
    "Moms 812,00 kr\n"
    "Att betala 4 060,00 kr\n"
)


@dataclass(frozen=True)
class _Line:
    text: str
    amount_ore: int
    vat_rate: Optional[int] = None


@dataclass(frozen=True)
class _Read:
    """What the model claims, in §6.2's shape (only the fields U3 reads)."""

    total_ore: int
    vat_ore: Optional[int] = None
    lines: Sequence[_Line] = ()
    document_date: Optional[date] = date(2026, 6, 3)
    currency: str = "SEK"


def _checks(read, text_layer_text=None):
    from services.interpretation import run_checks

    return run_checks(read, text_layer_text=text_layer_text, today=U3_TODAY)


def _read_4600(**overrides) -> _Read:
    """4 600 kr incl. 920 kr VAT at 25 %, no lines."""
    values: dict = dict(total_ore=460000, vat_ore=92000)
    values.update(overrides)
    return _Read(**values)


def test_06_lines_sum_to_the_total_is_ok():
    read = _read_4600(
        lines=[_Line("Docka", 400000, 25), _Line("Kabel", 60000, 25)],
    )
    assert _checks(read).lines_sum == "ok"


def test_06_without_lines_lines_sum_is_not_applicable():
    assert _checks(_read_4600()).lines_sum == "not_applicable"


def test_07_two_ore_off_over_three_lines_is_ok():
    read = _read_4600(
        lines=[_Line("A", 100000), _Line("B", 200000), _Line("C", 160002)],
    )
    assert _checks(read).lines_sum == "ok"


def test_07_four_ore_off_over_three_lines_is_a_mismatch():
    read = _read_4600(
        lines=[_Line("A", 100000), _Line("B", 200000), _Line("C", 160004)],
    )
    assert _checks(read).lines_sum == "mismatch"


def test_08_hundred_ore_off_is_a_mismatch_and_low():
    from services.interpretation import confidence

    read = _read_4600(
        lines=[_Line("A", 100000), _Line("B", 200000), _Line("C", 160100)],
    )
    checks = _checks(read)
    assert checks.lines_sum == "mismatch"
    assert confidence(checks) == "low"


def test_09_a_25_percent_line_with_matching_vat_is_ok():
    """Flöde 4's receipt: 4 480 kr at 25 % carries 896 kr VAT, the deposit
    none."""
    read = _Read(
        total_ore=460000,
        vat_ore=89600,
        lines=[_Line("USB-C docka", 448000, 25), _Line("Pant", 12000, 0)],
    )
    checks = _checks(read)
    assert checks.vat_rate == "ok"
    assert checks.lines_sum == "ok"
    assert checks.vat_share == "not_applicable"


def test_09_vat_rate_tolerates_one_ore_per_line_and_no_more():
    # 3 x 100,00 kr at 12 %: 10,714… kr each, 32,142… kr in all.
    lines = [_Line("A", 10000, 12), _Line("B", 10000, 12), _Line("C", 10000, 12)]
    assert _checks(_Read(30000, 3214 + 3, lines)).vat_rate == "ok"
    assert _checks(_Read(30000, 3214 - 2, lines)).vat_rate == "ok"
    assert _checks(_Read(30000, 3214 + 5, lines)).vat_rate == "mismatch"


def test_09_vat_rate_mismatch_lowers_confidence():
    from services.interpretation import confidence

    read = _Read(total_ore=12500, vat_ore=1250, lines=[_Line("A", 12500, 25)])
    checks = _checks(read)
    assert checks.vat_rate == "mismatch"
    assert confidence(checks) == "low"


def test_09_vat_rate_not_applicable_without_rates_or_vat():
    assert _checks(_read_4600()).vat_rate == "not_applicable"
    assert _checks(_read_4600(lines=[_Line("A", 460000)])).vat_rate == "not_applicable"
    assert (
        _checks(_read_4600(vat_ore=None, lines=[_Line("A", 460000, 25)])).vat_rate
        == "not_applicable"
    )


def test_10_without_lines_vat_twenty_percent_of_net_is_implausible_and_low():
    from services.interpretation import confidence

    checks = _checks(_Read(total_ore=12000, vat_ore=2000))
    assert checks.vat_share == "implausible"
    assert confidence(checks) == "low"


@pytest.mark.parametrize(
    "total, vat",
    [
        (12500, 2500),  # 25 %
        (11200, 1200),  # 12 %
        (10600, 600),  # 6 %
        (10000, 0),  # no VAT
        (12540, 2540),  # 25,4 % of net
        (11150, 1150),  # 11,5 % of net: the edge
    ],
)
def test_10_vat_share_near_a_swedish_rate_is_ok(total, vat):
    assert _checks(_Read(total_ore=total, vat_ore=vat)).vat_share == "ok"


@pytest.mark.parametrize(
    "total, vat",
    [
        (12560, 2560),  # 25,6 % of net
        (11140, 1140),  # 11,4 % of net
        (100, 100),  # all VAT, no net
    ],
)
def test_10_vat_share_outside_half_a_point_is_implausible(total, vat):
    assert _checks(_Read(total_ore=total, vat_ore=vat)).vat_share == "implausible"


def test_10_vat_share_not_applicable_with_lines_or_without_vat():
    assert _checks(_read_4600(vat_ore=None)).vat_share == "not_applicable"
    read = _read_4600(lines=[_Line("A", 460000, 25)])
    assert _checks(read).vat_share == "not_applicable"


def test_11_text_layer_with_same_total_and_vat_agrees_and_high():
    from services.agent_documents import ReconciliationState, reconciliation_result
    from services.interpretation import confidence

    # The fixture is a text `reconciliation_result` recognises and reconciles.
    assert reconciliation_result(TEXT_LAYER_4600).state is (
        ReconciliationState.RECONCILES
    )
    checks = _checks(_read_4600(), TEXT_LAYER_4600)
    assert checks.text_layer == "agrees"
    assert confidence(checks) == "high"


def test_12_model_read_4600_where_the_text_says_4060_disagrees_and_low():
    from services.agent_documents import ReconciliationState, reconciliation_result
    from services.interpretation import confidence

    assert reconciliation_result(TEXT_LAYER_4060).state is (
        ReconciliationState.RECONCILES
    )
    checks = _checks(_read_4600(), TEXT_LAYER_4060)
    assert checks.text_layer == "disagrees"
    assert confidence(checks) == "low"


def test_12_text_layer_vat_the_model_did_not_read_disagrees():
    """The text has a VAT amount; a read without `vat_ore` does not agree
    with it (§6.3: both `total_ore` and `vat_ore` are compared)."""
    checks = _checks(_read_4600(vat_ore=None), TEXT_LAYER_4600)
    assert checks.text_layer == "disagrees"


def test_13_image_has_no_text_layer_and_is_at_best_medium():
    from services.interpretation import confidence

    checks = _checks(_read_4600(), None)
    assert checks.text_layer == "not_available"
    assert confidence(checks) == "medium"


@pytest.mark.parametrize(
    "text",
    [
        "",  # scanned PDF: `extract_pdf_text` gives ""
        "Elektronikhuset AB\nTack för ditt köp!\n",  # no triple
        # A triple that does not add up: the text itself is scrambled and
        # is no source to compare the model with.
        "Netto 3 680,00 kr\nMoms 920,00 kr\nAtt betala 4 700,00 kr\n",
    ],
)
def test_13_text_without_a_reconciling_triple_is_not_available(text):
    from services.interpretation import confidence

    checks = _checks(_read_4600(), text)
    assert checks.text_layer == "not_available"
    assert confidence(checks) == "medium"


def test_14_date_tomorrow_is_future_and_low():
    from services.interpretation import confidence

    tomorrow = date(2026, 6, 11)
    checks = _checks(_read_4600(document_date=tomorrow), TEXT_LAYER_4600)
    assert checks.date == "future"
    assert confidence(checks) == "low"


def test_14_date_today_is_ok_and_missing_date_does_not_lower():
    from services.interpretation import confidence

    assert _checks(_read_4600(document_date=U3_TODAY)).date == "ok"
    checks = _checks(_read_4600(document_date=None), TEXT_LAYER_4600)
    assert checks.date == "missing"
    assert confidence(checks) == "high"


def test_u3_currency_not_sek_does_not_lower_confidence():
    from services.interpretation import confidence

    assert _checks(_read_4600()).currency == "sek"
    checks = _checks(_read_4600(currency="EUR"), TEXT_LAYER_4600)
    assert checks.currency == "not_sek"
    assert confidence(checks) == "high"
    checks = _checks(_read_4600(currency="EUR"))
    assert confidence(checks) == "medium"


def test_u3_checks_serialise_in_section_6_3_order():
    checks = _checks(_read_4600(), TEXT_LAYER_4600)
    assert checks.to_dict() == {
        "lines_sum": "not_applicable",
        "vat_rate": "not_applicable",
        "vat_share": "ok",
        "text_layer": "agrees",
        "date": "ok",
        "currency": "sek",
    }
    assert list(checks.to_dict()) == [
        "lines_sum",
        "vat_rate",
        "vat_share",
        "text_layer",
        "date",
        "currency",
    ]


def test_u3_run_checks_takes_the_section_6_2_pydantic_model_as_is():
    """U6's `TolkaUnderlagArgs` goes into `run_checks` without conversion.
    The models are §6.2's, copied here only as the contract."""
    from pydantic import BaseModel, Field

    class TolkaUnderlagLine(BaseModel):
        text: str = Field(..., min_length=1, max_length=200)
        amount_ore: int
        vat_rate: Optional[Literal[25, 12, 6, 0]] = None

    class TolkaUnderlagArgs(BaseModel):
        source_id: str
        vendor: Optional[str] = Field(None, max_length=200)
        document_date: Optional[date] = None
        currency: str = Field("SEK", pattern="^[A-Z]{3}$")
        total_ore: int = Field(..., ge=0)
        vat_ore: Optional[int] = Field(None, ge=0)
        lines: List[TolkaUnderlagLine] = Field(default_factory=list, max_length=100)
        expected_voucher_id: Optional[str] = None

    args = TolkaUnderlagArgs(
        source_id="s-1",
        document_date=date(2026, 6, 3),
        total_ore=460000,
        vat_ore=89600,
        lines=[
            TolkaUnderlagLine(text="USB-C docka", amount_ore=448000, vat_rate=25),
            TolkaUnderlagLine(text="Pant", amount_ore=12000, vat_rate=0),
        ],
    )
    checks = _checks(args)
    assert (checks.lines_sum, checks.vat_rate, checks.date) == ("ok", "ok", "ok")


def test_u3_run_checks_arguments_are_keyword_only():
    import inspect

    from services.interpretation import run_checks

    params = inspect.signature(run_checks).parameters
    for name in ("text_layer_text", "today"):
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY
        assert params[name].default is inspect.Parameter.empty


def test_u3_service_has_no_sql_and_reads_no_file():
    source = (REPO_ROOT / "services" / "interpretation.py").read_text()
    for forbidden in ("db.execute", "sqlite3", "SELECT ", "open(", "extract_pdf_text("):
        assert forbidden not in source
