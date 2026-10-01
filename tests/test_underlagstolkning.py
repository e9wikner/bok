"""Tests for the `underlagstolkning` module
(docs/redesign/SPEC-underlagstolkning.md).

Grows across tasks U1-U10 of `tasks/underlagstolkning/todo.md`; each task
gets its own section. Test case numbers refer to the tables in spec §10.

Per the spec no LLM is ever called from a test.
"""

import hashlib
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
from domain.interpretation import Candidate, Expected, Interpretation, Match
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
    assert public == {"insert", "get", "latest_for_source", "count_for_source"}
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
    # No new `IB`-series voucher can be created (migration 033); a legacy
    # one is made the way it was before: a draft, moved to `IB`, posted.
    draft = ledger.create_voucher(
        series="A" if series == "IB" else series,
        date=date(2026, 3, day),
        period_id=period_id,
        description=f"Inköp {uuid.uuid4().hex[:6]}",
        rows_data=rows,
        created_by=created_by,
    )
    if series == "IB":
        from db.database import db as _db

        _db.execute("UPDATE vouchers SET series = 'IB' WHERE id = ?", (draft.id,))
        _db.commit()
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
    """§7.2's amount window, as the service computes it (U5)."""
    from services.interpretation import amount_window_ore

    return amount_window_ore(total_ore)


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


# ---------------------------------------------------------------------------
# U5: ranking, unambiguity, `match`, `expected` and the hypothesis (§7.3-§7.5),
# pure logic, no database
# ---------------------------------------------------------------------------

U5_DAY = date(2026, 6, 3)


@dataclass(frozen=True)
class _MatchRead:
    """What the model claims, in §6.2's shape (the fields U5 reads)."""

    total_ore: int
    vat_ore: Optional[int] = None
    lines: Sequence[_Line] = ()
    document_date: Optional[date] = U5_DAY
    currency: str = "SEK"
    vendor: Optional[str] = None


def _read_flode4(**overrides) -> _MatchRead:
    """Flöde 4's receipt: 4 600 kr, 896 kr VAT, a 4 480 kr docka and 120 kr
    pant."""
    values: dict = dict(
        total_ore=460000,
        vat_ore=89600,
        lines=(_Line("USB-C docka", 448000, 25), _Line("Pant", 12000, 0)),
        vendor="Elektronikhuset",
    )
    values.update(overrides)
    return _MatchRead(**values)


def _row(
    number: str = "A-118",
    *,
    ore: int = 448000,
    vat: Optional[int] = 89600,
    day: date = U5_DAY,
    description: str = "Förbrukningsinventarier",
    bank_counterpart: Optional[str] = None,
    bank_description: Optional[str] = None,
    bank: bool = False,
):
    from repositories.voucher_repo import CandidateBankTransaction, MatchCandidateRow

    transaction = None
    if bank or bank_counterpart is not None or bank_description is not None:
        transaction = CandidateBankTransaction(
            id=f"bt-{number}",
            date=day,
            amount_ore=-ore,
            counterpart_name=bank_counterpart,
            description=bank_description,
        )
    return MatchCandidateRow(
        voucher_id=f"id-{number}",
        voucher_number=number,
        voucher_date=day,
        voucher_description=description,
        voucher_ore=ore,
        vat_ore=vat,
        bank_transaction=transaction,
    )


def _match(read, rows):
    from services.interpretation import match_document

    return match_document(read, rows)


def test_u5_amount_window_is_max_of_minimum_and_ten_percent():
    from services.interpretation import amount_window_ore

    assert amount_window_ore(20000) == 5000
    assert amount_window_ore(50000) == 5000
    assert amount_window_ore(60000) == 6000
    assert amount_window_ore(1_000_000) == 100000
    assert amount_window_ore(0) == 5000


def test_16_flode4_logic_amount_diff_hypothesis_on_pant_and_equal_vat():
    """Flöde 4 (logic only; the whole way is U6): 4 600 against A-118's
    4 480, same day, a 120 kr pant line."""
    row = _row(bank_counterpart="ELEKTRONIKHUSET")

    result = _match(_read_flode4(), [row])

    match = result.match
    assert match is not None
    assert match.kind == "amount_diff"
    assert match.voucher_id == "id-A-118"
    assert match.voucher_number == "A-118"
    assert match.voucher_date == "2026-06-03"
    assert match.voucher_description == "Förbrukningsinventarier"
    assert match.amounts == {"document_ore": 460000, "voucher_ore": 448000}
    assert match.diff_ore == 12000
    assert match.date_diff_days == 0
    assert match.vat == {"document_ore": 89600, "voucher_ore": 89600, "equal": True}
    assert match.bank_transaction == {
        "id": "bt-A-118",
        "date": "2026-06-03",
        "amount_ore": -448000,
        "counterpart_name": "ELEKTRONIKHUSET",
        "description": None,
    }
    assert match.hypothesis == {
        "text": "Skillnaden på 120,00 kr motsvarar raden ”Pant” på underlaget.",
        "basis": "line_items",
        "lines": [1],
    }
    assert list(match.to_dict())[0] == "kind"
    assert [c.voucher_id for c in result.candidates] == ["id-A-118"]


def test_17_exact_amount_bank_date_two_days_later_is_exact_without_hypothesis():
    row = _row(ore=460000, day=date(2026, 6, 5), bank=True)

    match = _match(_read_flode4(), [row]).match

    assert match is not None
    assert match.kind == "exact"
    assert match.diff_ore == 0
    assert match.date_diff_days == 2
    assert match.hypothesis is None


@pytest.mark.parametrize(
    "day, kind",
    [
        (date(2026, 5, 31), "exact"),  # −3: the absolute value counts
        (date(2026, 6, 6), "exact"),  # +3
        (date(2026, 6, 7), "amount_diff"),  # +4
    ],
)
def test_17_exact_needs_date_diff_at_most_three_days(day, kind):
    match = _match(_read_flode4(), [_row(ore=460000, day=day)]).match

    assert match is not None
    assert match.kind == kind


def test_18_two_equal_candidates_without_vendor_hit_give_no_match():
    rows = [_row("A-1", ore=460000), _row("A-2", ore=460000)]

    result = _match(_read_flode4(), rows)

    assert result.match is None
    assert {c.voucher_id for c in result.candidates} == {"id-A-1", "id-A-2"}


def test_18_without_vendor_there_is_no_vendor_hit():
    rows = [
        _row("A-1", ore=460000, bank_counterpart="ELEKTRONIKHUSET"),
        _row("A-2", ore=460000),
    ]

    assert _match(_read_flode4(vendor=None), rows).match is None


@pytest.mark.parametrize(
    "hit",
    [
        dict(bank_counterpart="ELEKTRONIKHUSET STOCKHOLM"),
        dict(bank_description="Kortköp elektronikhuset 0603"),
        dict(description="Docka, Elektronikhuset"),
    ],
)
def test_19_vendor_in_one_candidate_makes_it_the_match(hit):
    rows = [
        _row("A-1", ore=460000, bank_counterpart="CLAS OHLSON"),
        _row("A-2", ore=460000, **hit),
    ]

    result = _match(_read_flode4(), rows)

    assert result.match is not None
    assert result.match.voucher_id == "id-A-2"
    assert [c.voucher_id for c in result.candidates] == ["id-A-2", "id-A-1"]


def test_u5_rank_sorts_on_diff_then_date_then_vendor():
    from services.interpretation import rank

    rows = [
        _row("A-1", ore=459000, day=U5_DAY),  # diff 1 000
        _row("A-2", ore=460000, day=date(2026, 6, 8)),  # diff 0, 5 days
        _row("A-3", ore=460000, day=date(2026, 6, 1)),  # diff 0, −2 days
        _row("A-4", ore=461000, day=U5_DAY, bank_counterpart="Elektronikhuset"),
        _row("A-5", ore=460000, day=date(2026, 6, 5), bank_counterpart="x"),
        _row("A-6", ore=460000, day=date(2026, 6, 5), description="ELEKTRONIKHUSET"),
    ]

    ranked = rank(_read_flode4(), rows)

    assert [c.voucher_number for c in ranked] == [
        "A-6",  # diff 0, 2 days, vendor
        "A-3",  # diff 0, 2 days (before), no vendor: equal to A-5, input order
        "A-5",  # diff 0, 2 days
        "A-2",  # diff 0, 5 days
        "A-4",  # |diff| 1 000, vendor
        "A-1",  # |diff| 1 000
    ]
    assert ranked[4].diff_ore == -1000
    assert ranked[3].date_diff_days == 5
    assert ranked[1].date_diff_days == -2


def test_u5_first_is_the_match_when_it_differs_on_any_key():
    rows = [_row("A-1", ore=460000, day=date(2026, 6, 4)), _row("A-2", ore=460000)]

    match = _match(_read_flode4(), rows).match

    assert match is not None
    assert match.voucher_number == "A-2"


def test_u5_candidates_are_at_most_five_best_first():
    rows = [_row(f"A-{n}", ore=460000 - n * 100) for n in range(1, 9)]

    result = _match(_read_flode4(), rows)

    assert [c.voucher_number for c in result.candidates] == [
        "A-1",
        "A-2",
        "A-3",
        "A-4",
        "A-5",
    ]
    assert result.match is not None
    assert result.match.voucher_number == "A-1"


def test_u5_no_candidates_no_match():
    result = _match(_read_flode4(), [])

    assert result.match is None
    assert result.candidates == []


def test_u5_vat_equal_only_when_both_exist():
    from services.interpretation import rank

    [missing] = rank(_read_flode4(), [_row(vat=None)])
    [differs] = rank(_read_flode4(), [_row(vat=92000)])
    [unread] = rank(_read_flode4(vat_ore=None), [_row()])

    assert missing.vat == {"document_ore": 89600, "voucher_ore": None, "equal": None}
    assert differs.vat["equal"] is False
    assert unread.vat == {"document_ore": None, "voucher_ore": 89600, "equal": None}


def test_u5_without_document_date_date_diff_is_none_and_not_exact():
    match = _match(_read_flode4(document_date=None), [_row(ore=460000)]).match

    assert match is not None
    assert match.date_diff_days is None
    # U13 (§12.6 d): an exact amount without a date is its own kind.
    assert match.kind == "exact_no_date"


def test_u13_exact_amount_without_date_is_exact_no_date_in_match_and_expected():
    """§7.4: `diff_ore = 0` without `document_date` is `exact_no_date`, in
    `match` as in `expected`, and serialised with `kind` first."""
    from services.interpretation import expected

    read = _read_flode4(document_date=None)
    row = _row(ore=460000)
    result = _match(read, [row])

    assert result.match is not None
    assert result.match.kind == "exact_no_date"
    assert result.match.diff_ore == 0
    assert result.match.hypothesis is None
    assert list(result.match.to_dict())[0] == "kind"
    assert result.match.to_dict()["kind"] == "exact_no_date"

    exp = expected(read, row, result)
    assert exp is not None
    assert exp.kind == "exact_no_date"
    assert exp.is_best_match is True


def test_u13_amount_diff_without_date_stays_amount_diff():
    """Only `diff_ore = 0` gets the new kind: a difference without a date is
    still `amount_diff`, and a date keeps `exact`/`amount_diff` as before."""
    from services.interpretation import expected

    read = _read_flode4(document_date=None)
    row = _row()  # 4 480 kr against 4 600 kr
    exp = expected(read, row, _match(read, [row]))

    assert exp is not None
    assert exp.diff_ore == 12000
    assert exp.kind == "amount_diff"

    dated = _match(_read_flode4(), [_row(ore=460000)]).match
    assert dated is not None
    assert dated.kind == "exact"


def test_u13_tool_without_date_answers_and_saves_exact_no_date(
    period_id, purchase_accounts, intake_dir
):
    """Testfall 24 the whole way: no `document_date`, a posted voucher on the
    exact amount -> `match.kind = "exact_no_date"`, answered and saved."""
    voucher_id = _purchase(period_id, total=460000, vat=89600, day=15)
    source = _upload(_text_pdf(U6_TEXT_LINES))

    result = _tolka(source.id, document_date=None)

    match = result["match"]
    assert match["kind"] == "exact_no_date"
    assert match["voucher_id"] == voucher_id
    assert match["diff_ore"] == 0
    assert match["date_diff_days"] is None
    saved = InterpretationRepository.latest_for_source(source.id)
    assert saved is not None
    assert saved.match is not None and saved.match.to_dict() == match


def test_25_currency_not_sek_gives_no_match_and_no_candidates():
    result = _match(_read_flode4(currency="EUR"), [_row(ore=460000)])

    assert result.match is None
    assert result.candidates == []


def test_26_expected_a_worse_candidate_is_not_the_best_match():
    from services.interpretation import expected

    best = _row("A-109", ore=460000)
    worse = _row("A-118")
    read = _read_flode4()
    result = _match(read, [worse, best])

    exp = expected(read, worse, result)

    assert result.match is not None
    assert result.match.voucher_number == "A-109"
    assert exp is not None
    assert exp.voucher_number == "A-118"
    assert exp.is_best_match is False
    assert exp.kind == "amount_diff"
    assert exp.diff_ore == 12000
    assert exp.vat["equal"] is True
    assert exp.hypothesis is not None
    assert exp.hypothesis["lines"] == [1]
    assert exp.to_dict()["is_best_match"] is False


def test_26_expected_the_match_is_the_best_match():
    from services.interpretation import expected

    row = _row(ore=460000)
    read = _read_flode4()

    exp = expected(read, row, _match(read, [row]))

    assert exp is not None
    assert exp.is_best_match is True
    assert exp.kind == "exact"


def test_26_expected_outside_the_windows_is_computed_in_full():
    """§7.3: even outside the windows, `expected` has diff, VAT, hypothesis."""
    from services.interpretation import expected

    far = _row("A-7", ore=300000, vat=None, day=date(2026, 5, 1))
    read = _read_flode4()

    exp = expected(read, far, _match(read, []))

    assert exp is not None
    assert exp.is_best_match is False
    assert exp.diff_ore == 160000
    assert exp.date_diff_days == -33
    assert exp.vat["equal"] is None
    assert exp.hypothesis is None


def test_26_expected_with_ambiguous_ranking_is_not_the_best_match():
    from services.interpretation import expected

    rows = [_row("A-1", ore=460000), _row("A-2", ore=460000)]
    read = _read_flode4()

    exp = expected(read, rows[0], _match(read, rows))

    assert exp is not None
    assert exp.is_best_match is False


def test_25_expected_in_another_currency_is_none():
    from services.interpretation import expected

    read = _read_flode4(currency="EUR")
    row = _row(ore=460000)

    assert expected(read, row, _match(read, [row])) is None


def _hypothesis(lines, diff_ore):
    from services.interpretation import hypothesis

    return hypothesis(lines, diff_ore)


def test_27_difference_explained_by_two_lines_together():
    lines = [
        _Line("Docka", 448000, 25),
        _Line("Pant", 8000, 0),
        _Line("Frakt", 4000, 25),
    ]

    hyp = _hypothesis(lines, 12000)

    assert hyp == {
        "text": (
            "Skillnaden på 120,00 kr motsvarar raderna ”Pant” och ”Frakt” "
            "på underlaget."
        ),
        "basis": "line_items",
        "lines": [1, 2],
    }


def test_27_three_lines_when_no_smaller_set_explains_it():
    lines = [
        _Line("A", 100000),
        _Line("B", 2000),
        _Line("C", 3000),
        _Line("D", 7000),
    ]

    hyp = _hypothesis(lines, 12000)

    assert hyp is not None
    assert hyp["lines"] == [1, 2, 3]
    assert hyp["text"] == (
        "Skillnaden på 120,00 kr motsvarar raderna ”B”, ”C” och ”D” på underlaget."
    )


def test_27_smallest_set_wins_over_a_larger_one():
    """A single line explains it: the pair that also does is not asked."""
    lines = [_Line("Pant", 12000), _Line("X", 5000), _Line("Y", 7000)]

    hyp = _hypothesis(lines, 12000)

    assert hyp is not None
    assert hyp["lines"] == [0]


def test_28_two_different_single_lines_give_no_hypothesis():
    lines = [_Line("Docka", 448000), _Line("Pant", 12000), _Line("Frakt", 12000)]

    assert _hypothesis(lines, 12000) is None


def test_28_two_different_pairs_give_no_hypothesis():
    lines = [
        _Line("A", 5000),
        _Line("B", 7000),
        _Line("C", 4000),
        _Line("D", 8000),
    ]

    assert _hypothesis(lines, 12000) is None


def test_u5_hypothesis_tolerance_is_one_ore_per_line():
    assert _hypothesis([_Line("Pant", 12001)], 12000) is not None
    assert _hypothesis([_Line("Pant", 12002)], 12000) is None
    pair = [_Line("A", 5001), _Line("B", 7001)]
    assert _hypothesis(pair, 12000) is not None
    assert _hypothesis([_Line("A", 5002), _Line("B", 7001)], 12000) is None


def test_u5_no_hypothesis_without_difference_lines_or_explaining_line():
    assert _hypothesis([_Line("Pant", 12000)], 0) is None
    assert _hypothesis([], 12000) is None
    assert _hypothesis([_Line("Docka", 448000)], 12000) is None
    assert _hypothesis([_Line("A", 1), _Line("B", 2), _Line("C", 3)], 20) is None


def test_u5_negative_difference_is_explained_by_a_discount_line():
    hyp = _hypothesis([_Line("Docka", 460000), _Line("Rabatt", -12000)], -12000)

    assert hyp is not None
    assert hyp["lines"] == [1]
    assert hyp["text"] == (
        "Skillnaden på -120,00 kr motsvarar raden ”Rabatt” på underlaget."
    )


def test_u5_hypothesis_amount_is_swedish_formatted():
    hyp = _hypothesis([_Line("Stor rad", 123456789)], 123456789)

    assert hyp is not None
    assert hyp["text"].startswith("Skillnaden på 1 234 567,89 kr ")


def test_u5_hypothesis_over_a_hundred_lines_is_fast():
    """§7.5: at most three of at most a hundred lines. The worst case is no
    hit at all: every size is searched to the end."""
    import time

    lines = [_Line(f"Rad {n}", 1000 * (n + 1)) for n in range(100)]

    started = time.perf_counter()
    hyp = _hypothesis(lines, 5)
    elapsed = time.perf_counter() - started

    assert hyp is None
    assert elapsed < 2.0


def test_u5_match_document_takes_the_section_6_2_pydantic_model_as_is():
    """The same covariance as U3: U6's Pydantic args go in without copying."""
    from typing import Literal as L

    from pydantic import BaseModel, Field

    class Line(BaseModel):
        text: str = Field(..., min_length=1, max_length=200)
        amount_ore: int
        vat_rate: Optional[L[25, 12, 6, 0]] = None

    class Args(BaseModel):
        source_id: str
        vendor: Optional[str] = None
        document_date: Optional[date] = None
        currency: str = "SEK"
        total_ore: int
        vat_ore: Optional[int] = None
        lines: List[Line] = Field(default_factory=list)
        expected_voucher_id: Optional[str] = None

    args = Args(
        source_id="s",
        vendor="Elektronikhuset",
        document_date=U5_DAY,
        total_ore=460000,
        vat_ore=89600,
        lines=[
            Line(text="Docka", amount_ore=448000),
            Line(text="Pant", amount_ore=12000),
        ],
    )

    match = _match(args, [_row()]).match

    assert match is not None
    assert match.hypothesis is not None
    assert match.hypothesis["lines"] == [1]


@pytest.mark.parametrize("ore", [0, 5, 12000, -12000, 100000, 123456789, -1234567])
def test_u5_amount_format_is_the_same_as_pdf_exports(ore):
    from services.interpretation import _format_kr
    from services.pdf_export import format_sek

    assert _format_kr(ore) == format_sek(ore)


# ---------------------------------------------------------------------------
# U6 — `tolka_underlag`: arguments, handler and orchestration (§6, §7;
# testfall 15, 16, 25, 33, 35, 36), against the test database
# ---------------------------------------------------------------------------

U6_DAY = date(2026, 3, 15)

#: Flöde 4's receipt as the model sends it (§6.5), dated inside the
#: `period_id` fixture's March.
U6_ARGS: dict = {
    "vendor": "Elektronikhuset",
    "document_date": "2026-03-15",
    "currency": "SEK",
    "total_ore": 460000,
    "vat_ore": 89600,
    "lines": [
        {"text": "USB-C docka", "amount_ore": 448000, "vat_rate": 25},
        {"text": "Pant", "amount_ore": 12000, "vat_rate": 0},
    ],
}

#: The receipt's text layer: 3 704 + 896 = 4 600, the pant carries no VAT.
U6_TEXT_LINES = [
    "Elektronikhuset AB",
    "Kvitto 2026-03-15",
    "USB-C docka 4 480,00 kr",
    "Pant 120,00 kr",
    "Netto 3 704,00 kr",
    "Moms 896,00 kr",
    "Att betala 4 600,00 kr",
]


def _text_pdf(lines: Sequence[str]) -> bytes:
    """A one-page PDF with *lines* as a real text layer (Helvetica, BT/Tj),
    the same construction as `test_agent_runtime._build_text_pdf_bytes`."""
    import io

    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    font = DictionaryObject()
    font[NameObject("/Type")] = NameObject("/Font")
    font[NameObject("/Subtype")] = NameObject("/Type1")
    font[NameObject("/BaseFont")] = NameObject("/Helvetica")
    font[NameObject("/Encoding")] = NameObject("/WinAnsiEncoding")
    fonts = DictionaryObject()
    fonts[NameObject("/F1")] = writer._add_object(font)
    resources = DictionaryObject()
    resources[NameObject("/Font")] = fonts
    page[NameObject("/Resources")] = resources
    content = ["BT", "/F1 12 Tf", "50 800 Td", "14 TL"]
    for i, line in enumerate(lines):
        if i:
            content.append("T*")
        content.append(f"({line}) Tj")
    content.append("ET")
    stream = DecodedStreamObject()
    stream.set_data("\n".join(content).encode("latin-1"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@pytest.fixture
def intake_dir(tmp_path):
    """`settings.intake_dir` under *tmp_path* for the test, so a source's
    file resolves inside the intake root."""
    original = settings.intake_dir
    settings.intake_dir = str(tmp_path / "intake")
    yield settings.intake_dir
    settings.intake_dir = original


def _upload(content: bytes, *, name: str = "kvitto.pdf", mime="application/pdf"):
    from services.intake import IntakeService

    return IntakeService().create_source_from_upload_content(
        filename=name,
        content_type=mime,
        content=content,
        explanation="Kvitto Elektronikhuset",
        source_type="receipt",
        actor="api",
    )


def _u6_capabilities():
    from services.llm import LLMCapabilities

    return LLMCapabilities(
        cache_breakpoint=True,
        pdf_document_blocks=True,
        refusal_stop_reason=True,
        streaming=True,
    )


def _tolka(source_id: str, tool_context=None, **overrides) -> dict:
    """One `tolka_underlag` call through its handler, with the arguments
    validated by the tool's own model as `execute_tool` would."""
    from services.agent_tools import TolkaUnderlagArgs, _run_tolka_underlag

    arguments = {**U6_ARGS, "source_id": source_id, **overrides}
    return _run_tolka_underlag(
        TolkaUnderlagArgs.model_validate(arguments),
        actor="agent",
        capabilities=_u6_capabilities(),
        tool_context=tool_context,
    )


def _a118(period_id: str) -> str:
    """Flöde 4's A-118: 4 480 kr with 896 kr input VAT, paid by card the
    same day -- posted by the bank path, without underlag."""
    voucher_id = _purchase(period_id, total=448000, vat=89600, day=15)
    _bank_transaction(voucher_id, day=15, amount=-448000)
    return voucher_id


def _voucher_number(voucher_id: str) -> str:
    row = db.execute(
        "SELECT series, number FROM vouchers WHERE id = ?", (voucher_id,)
    ).fetchone()
    return f"{row['series']}-{row['number']}"


def test_15_confidence_or_hypothesis_in_the_arguments_is_invalid():
    """Testfall 15: the fields do not exist, and `extra="forbid"` makes
    sending them `invalid_tool_arguments` instead of silently dropping
    them. Routed through `execute_tool` and the real tool list (U7)."""
    from domain.validation import ValidationError
    from services import agent_tools

    for extra in ({"confidence": "high"}, {"hypothesis": {"text": "Pant"}}):
        with pytest.raises(ValidationError) as exc:
            agent_tools.execute_tool(
                "tolka_underlag",
                {**U6_ARGS, "source_id": "s-1", **extra},
                actor="agent",
                capabilities=_u6_capabilities(),
            )
        assert exc.value.code == "invalid_tool_arguments"
        assert next(iter(extra)) in str(exc.value.details)

    # A line may not carry one either.
    line = {"text": "Pant", "amount_ore": 12000, "confidence": "high"}
    with pytest.raises(ValidationError) as exc:
        agent_tools.execute_tool(
            "tolka_underlag",
            {**U6_ARGS, "source_id": "s-1", "lines": [line]},
            actor="agent",
            capabilities=_u6_capabilities(),
        )
    assert exc.value.code == "invalid_tool_arguments"


def test_u6_args_are_section_6_2():
    from pydantic import ValidationError as PydanticError

    from services.agent_tools import TolkaUnderlagArgs, TolkaUnderlagLine

    assert list(TolkaUnderlagArgs.model_fields) == [
        "source_id",
        "vendor",
        "document_date",
        "currency",
        "total_ore",
        "vat_ore",
        "lines",
        "expected_voucher_id",
    ]
    assert list(TolkaUnderlagLine.model_fields) == ["text", "amount_ore", "vat_rate"]
    minimal = TolkaUnderlagArgs.model_validate({"source_id": "s", "total_ore": 0})
    assert (minimal.currency, minimal.lines, minimal.vat_ore) == ("SEK", [], None)
    for bad in (
        {"total_ore": -1},
        {"vat_ore": -1},
        {"currency": "sek"},
        {"lines": [{"text": "", "amount_ore": 1}]},
        {"lines": [{"text": "A", "amount_ore": 1, "vat_rate": 20}]},
        {"lines": [{"text": "A", "amount_ore": 1}] * 101},
    ):
        with pytest.raises(PydanticError):
            TolkaUnderlagArgs.model_validate({"source_id": "s", "total_ore": 1, **bad})


def test_u6_only_tolka_underlag_forbids_extra_fields():
    """`extra="forbid"` puts `additionalProperties: false` in a schema, and
    the schemas are the cached prefix: no other tool's model may get it."""
    from services.agent_tools import (
        AGENT_TOOL_DEFINITIONS,
        TolkaUnderlagArgs,
        TolkaUnderlagLine,
    )

    assert TolkaUnderlagArgs.model_config.get("extra") == "forbid"
    assert TolkaUnderlagLine.model_config.get("extra") == "forbid"
    for tool in AGENT_TOOL_DEFINITIONS:
        if tool["name"] == "tolka_underlag":
            assert "additionalProperties" in json.dumps(tool["input_schema"])
            continue
        assert "additionalProperties" not in json.dumps(tool["input_schema"]), tool[
            "name"
        ]


def test_16_flode4_the_whole_way_against_the_database(
    period_id, purchase_accounts, intake_dir
):
    """Testfall 16 the whole way: a PDF receipt of 4 600 kr against A-118's
    4 480 kr the same day -> `amount_diff`, `diff_ore = 12000`, the
    hypothesis on the pant line, equal VAT; the text layer agrees."""
    voucher_id = _a118(period_id)
    number = _voucher_number(voucher_id)
    source = _upload(_text_pdf(U6_TEXT_LINES))

    result = _tolka(source.id)

    assert list(result) == [
        "interpretation_id",
        "source_id",
        "read",
        "checks",
        "confidence",
        "match",
        "candidates",
        "expected",
        "placement",
    ]
    assert result["source_id"] == source.id
    assert result["checks"] == {
        "lines_sum": "ok",
        "vat_rate": "ok",
        "vat_share": "not_applicable",
        "text_layer": "agrees",
        "date": "ok",
        "currency": "sek",
    }
    assert result["confidence"] == "high"
    match = result["match"]
    assert match["kind"] == "amount_diff"
    assert match["voucher_id"] == voucher_id
    assert match["voucher_number"] == number
    assert match["voucher_date"] == "2026-03-15"
    assert match["amounts"] == {"document_ore": 460000, "voucher_ore": 448000}
    assert match["diff_ore"] == 12000
    assert match["date_diff_days"] == 0
    assert match["vat"] == {"document_ore": 89600, "voucher_ore": 89600, "equal": True}
    assert match["bank_transaction"]["amount_ore"] == -448000
    assert match["bank_transaction"]["counterpart_name"] == "ELEKTRONIKHUSET"
    assert match["hypothesis"] == {
        "text": "Skillnaden på 120,00 kr motsvarar raden ”Pant” på underlaget.",
        "basis": "line_items",
        "lines": [1],
    }
    assert [c["voucher_id"] for c in result["candidates"]] == [voucher_id]
    assert result["expected"] is None

    # The row is what was answered: the same read, checks and match.
    saved = InterpretationRepository.latest_for_source(source.id)
    assert saved is not None
    assert saved.id == result["interpretation_id"]
    assert saved.actor == "agent"
    assert saved.confidence == "high"
    assert saved.checks == result["checks"]
    assert saved.match is not None and saved.match.to_dict() == match
    assert [c.to_dict() for c in saved.candidates] == result["candidates"]
    assert saved.lines == U6_ARGS["lines"]
    assert (saved.vendor, saved.document_date) == ("Elektronikhuset", U6_DAY)
    assert (saved.total_ore, saved.vat_ore) == (460000, 89600)
    assert saved.expected_voucher_id is None
    assert json.loads(json.dumps(result)) == result  # JSON-serialisable


def test_u6_read_is_what_the_model_sent_unchanged(
    period_id, purchase_accounts, intake_dir
):
    """§6.5: `read` is the model's claims as sent -- no `source_id`, no
    `expected_voucher_id`, nothing added or normalised."""
    source = _upload(_text_pdf(U6_TEXT_LINES))
    lines = [{"text": "Docka", "amount_ore": 460000, "vat_rate": None}]

    result = _tolka(source.id, vendor=None, lines=lines)

    assert result["read"] == {**U6_ARGS, "vendor": None, "lines": lines}
    assert list(result["read"]) == [
        "vendor",
        "document_date",
        "currency",
        "total_ore",
        "vat_ore",
        "lines",
    ]


def test_u6_image_source_has_no_text_layer_and_is_medium(
    period_id, purchase_accounts, intake_dir
):
    """An image is not read for a text layer (§6.3): `not_available`,
    and at best `medium`."""
    _a118(period_id)
    source = _upload(b"\x89PNG\r\n\x1a\n fake", name="kvitto.png", mime="image/png")

    result = _tolka(source.id)

    assert result["checks"]["text_layer"] == "not_available"
    assert result["confidence"] == "medium"
    assert result["match"]["diff_ore"] == 12000


def test_u6_text_layer_disagreeing_is_low(period_id, purchase_accounts, intake_dir):
    source = _upload(_text_pdf(U6_TEXT_LINES))

    result = _tolka(source.id, total_ore=406000, lines=[])

    assert result["checks"]["text_layer"] == "disagrees"
    assert result["confidence"] == "low"


def test_u6_ambiguous_candidates_give_no_match(
    period_id, purchase_accounts, intake_dir
):
    """§7.3 against the database: two equal candidates, no vendor hit ->
    `match = null`, both in `candidates`."""
    first = _purchase(period_id, total=460000, vat=92000, day=15)
    second = _purchase(period_id, total=460000, vat=92000, day=15)
    source = _upload(_text_pdf(U6_TEXT_LINES))

    result = _tolka(source.id, vendor=None)

    assert result["match"] is None
    assert {c["voucher_id"] for c in result["candidates"]} == {first, second}
    saved = InterpretationRepository.latest_for_source(source.id)
    assert saved is not None and saved.match is None
    assert len(saved.candidates) == 2


def test_u6_expected_is_computed_against_that_voucher_even_outside_the_windows(
    period_id, purchase_accounts, intake_dir
):
    """§7.3: `expected_voucher_id` does not change the ranking; `expected`
    is counted in full against that voucher, even three weeks off and far
    outside the amount window, with `is_best_match = false`."""
    a118 = _a118(period_id)
    elsewhere = _purchase(period_id, total=99000, vat=19800, day=1)
    source = _upload(_text_pdf(U6_TEXT_LINES))

    result = _tolka(source.id, expected_voucher_id=elsewhere)

    assert result["match"]["voucher_id"] == a118
    expected = result["expected"]
    assert expected["voucher_id"] == elsewhere
    assert expected["voucher_number"] == _voucher_number(elsewhere)
    assert expected["diff_ore"] == 460000 - 99000
    assert expected["date_diff_days"] == -14
    assert expected["vat"] == {
        "document_ore": 89600,
        "voucher_ore": 19800,
        "equal": False,
    }
    assert expected["kind"] == "amount_diff"
    assert expected["is_best_match"] is False
    assert expected["bank_transaction"] is None
    saved = InterpretationRepository.latest_for_source(source.id)
    assert saved is not None and saved.expected_voucher_id == elsewhere

    again = _tolka(source.id, expected_voucher_id=a118)
    assert again["expected"]["is_best_match"] is True
    assert again["expected"]["hypothesis"] == again["match"]["hypothesis"]
    assert again["expected"]["bank_transaction"] == again["match"]["bank_transaction"]


def test_u6_expected_voucher_that_is_not_posted_is_refused(
    period_id, purchase_accounts, intake_dir
):
    """An `expected_voucher_id` with no posted voucher behind it is a hard
    error, and nothing is saved -- there is nothing to compare with, and
    the column is a foreign key."""
    from domain.validation import ValidationError

    draft = _purchase(period_id, total=448000, vat=89600, day=15, post=False)
    source = _upload(_text_pdf(U6_TEXT_LINES))

    for voucher_id in ("no-such-voucher", draft):
        with pytest.raises(ValidationError) as exc:
            _tolka(source.id, expected_voucher_id=voucher_id)
        assert exc.value.code == "expected_voucher_not_found"
    assert InterpretationRepository.count_for_source(source.id) == 0


def test_25_currency_eur_the_whole_way(period_id, purchase_accounts, intake_dir):
    """Testfall 25 against the database: an exact SEK candidate exists,
    but a EUR document is not matched -- and `expected` is null too (§7.1:
    no matching in another currency)."""
    a118 = _purchase(period_id, total=460000, vat=89600, day=15)
    source = _upload(_text_pdf(U6_TEXT_LINES))

    result = _tolka(source.id, currency="EUR", expected_voucher_id=a118)

    assert result["checks"]["currency"] == "not_sek"
    assert result["match"] is None
    assert result["candidates"] == []
    assert result["expected"] is None
    assert result["read"]["currency"] == "EUR"
    saved = InterpretationRepository.latest_for_source(source.id)
    assert saved is not None
    assert (saved.currency, saved.match, saved.candidates) == ("EUR", None, [])
    assert saved.expected_voucher_id == a118


def _books_snapshot() -> dict:
    """The full content of what `tolka_underlag` must not touch (§14):
    every column of `vouchers`, `voucher_rows`, `voucher_intake_sources`
    and `attachments`, and every source's status."""
    queries = {
        "vouchers": "SELECT * FROM vouchers ORDER BY id",
        "voucher_rows": "SELECT * FROM voucher_rows ORDER BY id",
        "voucher_intake_sources": "SELECT * FROM voucher_intake_sources "
        "ORDER BY voucher_id, intake_source_id",
        "attachments": "SELECT * FROM attachments ORDER BY id",
        "intake_sources.status": "SELECT id, status FROM intake_sources ORDER BY id",
    }
    return {
        name: [tuple(row) for row in db.execute(sql).fetchall()]
        for name, sql in queries.items()
    }


def test_33_tolka_underlag_changes_nothing_in_the_books(
    period_id, purchase_accounts, intake_dir
):
    """Testfall 33: before and after, the content -- not only the row
    count -- of `vouchers`, `voucher_intake_sources`, `attachments` and
    `intake_sources.status` is the same. The only new row is the
    interpretation."""
    a118 = _a118(period_id)
    with_attachment = _purchase(period_id, total=460000, vat=92000, day=16)
    _attach(with_attachment)
    linked = _purchase(period_id, total=455000, vat=91000, day=14)
    _link_intake_source(linked)
    source = _upload(_text_pdf(U6_TEXT_LINES))
    before = _books_snapshot()
    assert all(before[name] for name in before), "every table has content"

    result = _tolka(source.id, expected_voucher_id=a118)

    assert result["match"]["voucher_id"] == a118
    assert _books_snapshot() == before
    assert InterpretationRepository.count_for_source(source.id) == 1
    source_after = IntakeRepository.get_source(source.id)
    assert source_after is not None and source_after.status.value == "pending"


def test_35_from_the_thread_turn_thread_id_and_agent_run_id_are_set(
    period_id, purchase_accounts, intake_dir
):
    """Testfall 35: `tool_context` carries the thread (as the thread turn
    puts it there) and the turn's `agent_run_id`; both land on the row."""
    from repositories.agent_run_repo import AgentRunRepository
    from repositories.thread_repo import ThreadRepository

    fiscal_year_id = PeriodRepository.get_period(period_id).fiscal_year_id
    thread = ThreadRepository.get_or_create(
        view_key="bocker.verifikationer",
        fiscal_year_id=fiscal_year_id,
        model="opencode/claude-opus-5",
    )
    run = AgentRunRepository.create(
        trigger="thread", model="opencode/claude-opus-5", protocol="messages"
    )
    source = _upload(_text_pdf(U6_TEXT_LINES))

    result = _tolka(source.id, tool_context={"thread": thread, "agent_run_id": run.id})

    saved = InterpretationRepository.latest_for_source(source.id)
    assert saved is not None and saved.id == result["interpretation_id"]
    assert saved.thread_id == thread.id
    assert saved.agent_run_id == run.id


def test_35_without_tool_context_both_are_null(
    period_id, purchase_accounts, intake_dir
):
    """The intake pass or a bare call (§6.6): the tool works without
    either, and the row says so."""
    source = _upload(_text_pdf(U6_TEXT_LINES))

    _tolka(source.id)
    _tolka(source.id, tool_context={"proposals": object()})

    saved = InterpretationRepository.latest_for_source(source.id)
    assert saved is not None
    assert (saved.thread_id, saved.agent_run_id) == (None, None)
    assert InterpretationRepository.count_for_source(source.id) == 2


def test_36_unknown_and_deleted_source(period_id, purchase_accounts, intake_dir):
    """Testfall 36: `source_not_found` / `source_deleted`, and nothing
    saved."""
    from services.intake import IntakeError, IntakeService

    with pytest.raises(IntakeError) as exc:
        _tolka("no-such-source")
    assert exc.value.code == "source_not_found"

    source = _upload(_text_pdf(U6_TEXT_LINES))
    IntakeService().soft_delete(source.id, actor="api")
    with pytest.raises(IntakeError) as exc:
        _tolka(source.id)
    assert exc.value.code == "source_deleted"

    assert (
        db.execute("SELECT COUNT(*) AS n FROM intake_interpretations").fetchone()["n"]
        == 0
    )


def test_u6_service_has_no_sql_and_no_http():
    """§4: the orchestration holds no SQL and no HTTP concepts either."""
    source = (REPO_ROOT / "services" / "interpretation_service.py").read_text()
    for forbidden in ("db.execute", "sqlite3", "SELECT ", "fastapi", "HTTPException"):
        assert forbidden not in source


def test_u6_voucher_candidate_row_is_one_posted_voucher_any_window(
    period_id, purchase_accounts
):
    """`VoucherRepository.candidate_row`: the same fields as
    `match_candidates`, for one posted voucher, whatever its date or
    amount; `None` for a draft or an unknown id."""
    from repositories.voucher_repo import VoucherRepository

    a118 = _a118(period_id)
    [in_window] = _candidates(U6_DAY, 448000)

    assert VoucherRepository.candidate_row(a118) == in_window
    draft = _purchase(period_id, total=1000, day=2, post=False)
    assert VoucherRepository.candidate_row(draft) is None
    assert VoucherRepository.candidate_row("no-such-voucher") is None


# ---------------------------------------------------------------------------
# U7 — the tool list: `tolka_underlag` twelfth (§6.2, §6.6; testfall 34).
# It was last until `flode-underlag` appended `koppla_underlag` after it
# (SPEC-flode-underlag.md §6.7); what comes after it is that module's
# testfall 36.
# ---------------------------------------------------------------------------

# sha256 of `json.dumps(AGENT_TOOL_DEFINITIONS[:11])`, taken on `9523c81`,
# before U7 touched `_TOOL_SPECS`. No `sort_keys`: the key order inside each
# definition is part of the bytes the model is sent, and so of the cached
# prefix (SPEC-agentruntime §6.6). Re-taken for SPEC-lasbarhet L6, which
# deliberately rewords `be_om_beslut` and `foresla_verifikation`. Re-taken
# again for the period lock, which rewords `las_perioder`.
_FIRST_ELEVEN_SHA256 = (
    "a820eb76949af28c78d96f8eef29ba4a459edfe3bdcd74db93751b8072b1c6be"
)


#: `tolka_underlag`'s description as the spec (§6.2) set it. The tool list is
#: part of the cached prefix, so a change here is deliberate.
_TOLKA_UNDERLAG_DESCRIPTION = (
    "Lämna det du läst ur ett underlag (leverantör, datum, belopp, moms, "
    "rader) för kontroll och matchning mot postade verifikationer. "
    "Servern stämmer av momsen och textlagret, letar efter en postad "
    "verifikation som saknar underlag och räknar differensen. Sparar "
    "tolkningen men kopplar ingenting och ändrar ingenting i "
    "bokföringen. Anropa efter hamta_underlagsfil och före "
    "posta_verifikation eller foresla_verifikation för samma underlag."
)


def test_34_tolka_underlag_is_twelfth_and_the_first_eleven_are_unchanged():
    """Testfall 34: appended after the eleven, the twelfth tool; the names
    catch a reorder, the hash an edit to a description or schema before
    it."""
    from services.agent_tools import AGENT_TOOL_DEFINITIONS, TolkaUnderlagArgs

    assert len(AGENT_TOOL_DEFINITIONS) == 27
    assert [t["name"] for t in AGENT_TOOL_DEFINITIONS][10:12] == [
        "foresla_verifikation",
        "tolka_underlag",
    ]
    first_eleven = json.dumps(AGENT_TOOL_DEFINITIONS[:11])
    assert hashlib.sha256(first_eleven.encode()).hexdigest() == _FIRST_ELEVEN_SHA256
    assert AGENT_TOOL_DEFINITIONS[11]["input_schema"] == (
        TolkaUnderlagArgs.model_json_schema()
    )


def test_34_the_description_is_section_6_2_verbatim():
    from services.agent_tools import AGENT_TOOL_DEFINITIONS

    assert AGENT_TOOL_DEFINITIONS[11]["description"] == _TOLKA_UNDERLAG_DESCRIPTION


def test_u7_the_docstrings_say_twelve_tools():
    from services import agent_tools

    assert "twelfth" in (agent_tools.__doc__ or "")
    assert "tolka_underlag" in (agent_tools.__doc__ or "")
    # Twenty-seven since fakturering F1, the payroll tools and
    # foresla_rakenskapsar were appended after the statement tools.
    assert "twenty-seven" in (agent_tools.execute_tool.__doc__ or "")


# ---------------------------------------------------------------------------
# U8 — `GET /api/v1/intake/{id}/interpretation` (§8; testfall 31, 32, 37)
# ---------------------------------------------------------------------------


def _interpretation_url(source_id: str) -> str:
    return f"/api/v1/intake/{source_id}/interpretation"


def _get_interpretation(client, auth_headers, source_id: str):
    return client.get(_interpretation_url(source_id), headers=auth_headers)


def test_31_get_gives_the_later_with_superseded_count_one(
    client, auth_headers, period_id, purchase_accounts, intake_dir
):
    """Testfall 31 over HTTP: two interpretations, the GET gives the later
    one, in §6.5's form plus §8's fields, with `superseded_count = 1`."""
    a118 = _a118(period_id)
    source = _upload(_text_pdf(U6_TEXT_LINES))
    _tolka(source.id, vendor="Elektronikhuset AB")
    later = _tolka(source.id)

    response = _get_interpretation(client, auth_headers, source.id)

    assert response.status_code == 200
    body = response.json()
    assert list(body) == [
        "interpretation_id",
        "source_id",
        "read",
        "checks",
        "confidence",
        "match",
        "candidates",
        "expected",
        "placement",
        "expected_voucher_id",
        "created_at",
        "actor",
        "thread_id",
        "superseded_count",
        "source_status",
    ]
    assert body["interpretation_id"] == later["interpretation_id"]
    assert body["superseded_count"] == 1
    assert body["read"] == later["read"]
    assert body["read"]["vendor"] == "Elektronikhuset"
    assert body["checks"] == later["checks"]
    assert body["confidence"] == later["confidence"]
    assert body["candidates"] == later["candidates"]
    assert body["match"] == {**later["match"], "still_open": True}
    assert body["match"]["voucher_id"] == a118
    assert (body["actor"], body["thread_id"]) == ("agent", None)
    saved = InterpretationRepository.latest_for_source(source.id)
    assert saved is not None
    assert body["created_at"] == saved.created_at.isoformat()


def test_32_linking_the_source_leaves_the_snapshot_and_closes_the_match(
    client, auth_headers, period_id, purchase_accounts, intake_dir
):
    """Testfall 32: interpretation, then the source is linked through the
    existing path. The GET gives the same snapshot; only `still_open`
    turns false. Nothing about the row changed."""
    from services.intake import IntakeService

    a118 = _a118(period_id)
    source = _upload(_text_pdf(U6_TEXT_LINES))
    _tolka(source.id)
    before = _get_interpretation(client, auth_headers, source.id).json()
    row_before = db.execute(
        "SELECT * FROM intake_interpretations WHERE intake_source_id = ?",
        (source.id,),
    ).fetchall()
    assert before["match"]["still_open"] is True

    IntakeService().link_existing_voucher(
        source_id=source.id,
        voucher_id=a118,
        actor="api",
        summary="Kvittot hör till A-118",
    )
    after = _get_interpretation(client, auth_headers, source.id).json()

    assert after["match"]["still_open"] is False
    # The link marks the source processed (U14's `source_status`); the
    # snapshot itself is the same.
    assert (before["source_status"], after["source_status"]) == (
        "pending",
        "processed",
    )
    assert {**after, "match": None, "source_status": None} == {
        **before,
        "match": None,
        "source_status": None,
    }
    assert {**after["match"], "still_open": True} == before["match"]
    assert [
        tuple(r)
        for r in db.execute(
            "SELECT * FROM intake_interpretations WHERE intake_source_id = ?",
            (source.id,),
        ).fetchall()
    ] == [tuple(r) for r in row_before]


def test_u8_still_open_needs_both_the_predicate_and_an_unlinked_source(
    client, auth_headers, period_id, purchase_accounts, intake_dir
):
    """§8: `still_open` is false as soon as either side is closed -- the
    voucher got underlag some other way (an attachment), or the source was
    linked to some other voucher."""
    from services.intake import IntakeService

    a118 = _a118(period_id)
    other = _purchase(period_id, total=10000, vat=2000, day=2)

    attached = _upload(_text_pdf(U6_TEXT_LINES))
    _tolka(attached.id)
    _attach(a118)
    body = _get_interpretation(client, auth_headers, attached.id).json()
    assert body["match"]["voucher_id"] == a118
    assert body["match"]["still_open"] is False

    linked_elsewhere = _upload(_text_pdf([*U6_TEXT_LINES, "Kopia"]))
    a119 = _a118(period_id)
    _tolka(linked_elsewhere.id)
    assert (
        _get_interpretation(client, auth_headers, linked_elsewhere.id).json()["match"][
            "still_open"
        ]
        is True
    )
    IntakeService().link_existing_voucher(
        source_id=linked_elsewhere.id,
        voucher_id=other,
        actor="api",
        summary="Hör till en annan verifikation",
    )
    body = _get_interpretation(client, auth_headers, linked_elsewhere.id).json()
    assert body["match"]["voucher_id"] == a119
    assert body["match"]["still_open"] is False


def test_u8_expected_is_not_recomputed_and_names_its_voucher(
    client, auth_headers, period_id, purchase_accounts, intake_dir
):
    """The GET does not recompute `expected` against today's ledger: it
    gives the comparison stored with the row (migration 031, U14) -- even
    after the expected voucher got a bank transaction a recomputation would
    show -- and `expected_voucher_id` says which voucher the agent named."""
    a118 = _a118(period_id)
    far = _purchase(period_id, total=99900, day=1)
    source = _upload(_text_pdf(U6_TEXT_LINES))
    answered = _tolka(source.id, expected_voucher_id=far)
    assert answered["expected"] is not None
    assert answered["expected"]["bank_transaction"] is None
    _bank_transaction(far, day=1, amount=-99900)

    body = _get_interpretation(client, auth_headers, source.id).json()

    assert body["expected"] == answered["expected"]
    assert body["expected_voucher_id"] == far
    assert body["match"]["voucher_id"] == a118
    plain = _upload(_text_pdf([*U6_TEXT_LINES, "Kopia"]))
    _tolka(plain.id)
    body = _get_interpretation(client, auth_headers, plain.id).json()
    assert (body["expected"], body["expected_voucher_id"]) == (None, None)


def test_u8_no_match_is_null_and_carries_no_still_open(
    client, auth_headers, period_id, purchase_accounts, intake_dir
):
    source = _upload(_text_pdf(U6_TEXT_LINES))
    _tolka(source.id)

    body = _get_interpretation(client, auth_headers, source.id).json()

    assert body["match"] is None
    assert body["candidates"] == []
    assert body["superseded_count"] == 0


def test_37_get_without_interpretation_is_404(
    client, auth_headers, period_id, purchase_accounts, intake_dir
):
    """Testfall 37, and §8's other 404: an unknown source."""
    source = _upload(_text_pdf(U6_TEXT_LINES))

    response = _get_interpretation(client, auth_headers, source.id)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "interpretation_not_found"

    response = _get_interpretation(client, auth_headers, "no-such-source")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "source_not_found"


def test_u8_requires_bearer_and_no_method_changes_an_interpretation(
    client, auth_headers, period_id, purchase_accounts, intake_dir
):
    """GET and POST (U15, which only adds a row) need the bearer; no method
    changes or removes an interpretation -- PUT, PATCH and DELETE are 405."""
    source = _upload(_text_pdf(U6_TEXT_LINES))
    _tolka(source.id)
    url = _interpretation_url(source.id)

    assert client.get(url).status_code == 401
    assert client.post(url, json=U6_ARGS).status_code == 401
    for method in ("put", "patch", "delete"):
        response = getattr(client, method)(url, headers=auth_headers)
        assert response.status_code == 405, method


def test_u8_get_writes_nothing(
    client, auth_headers, period_id, purchase_accounts, intake_dir
):
    """`still_open` is derived at read time: the GET changes neither the
    books nor the interpretations."""
    _a118(period_id)
    source = _upload(_text_pdf(U6_TEXT_LINES))
    _tolka(source.id)
    before = (
        _books_snapshot(),
        [tuple(r) for r in db.execute("SELECT * FROM intake_interpretations")],
    )

    assert _get_interpretation(client, auth_headers, source.id).status_code == 200

    after = (
        _books_snapshot(),
        [tuple(r) for r in db.execute("SELECT * FROM intake_interpretations")],
    )
    assert after == before


def test_u8_deleted_source_keeps_its_interpretation_readable(
    client, auth_headers, period_id, purchase_accounts, intake_dir
):
    """§8 names two 404s and no `source_deleted`: a source soft-deleted
    after it was interpreted still has its (append-only) interpretation."""
    from services.intake import IntakeService

    source = _upload(_text_pdf(U6_TEXT_LINES))
    result = _tolka(source.id)
    IntakeService().soft_delete(source.id, actor="api")

    response = _get_interpretation(client, auth_headers, source.id)

    assert response.status_code == 200
    assert response.json()["interpretation_id"] == result["interpretation_id"]


# ---------------------------------------------------------------------------
# U14 — `expected_json` and `source_status` (§12.6 e, h)
# ---------------------------------------------------------------------------

MIGRATION_031 = REPO_ROOT / "db" / "migrations" / "031_add_interpretation_expected.sql"


def _expected_a118(**overrides) -> Expected:
    values = dict(
        kind="amount_diff",
        voucher_id="v-118",
        voucher_number="A-118",
        voucher_date="2026-06-03",
        voucher_description="Förbrukningsinventarier",
        amounts={"document_ore": 460000, "voucher_ore": 448000},
        diff_ore=12000,
        date_diff_days=0,
        vat={"document_ore": 89600, "voucher_ore": 89600, "equal": True},
        bank_transaction=None,
        hypothesis={
            "text": "Skillnaden på 120,00 kr motsvarar raden ”Pant” på underlaget.",
            "basis": "line_items",
            "lines": [1],
        },
        is_best_match=True,
    )
    values.update(overrides)
    return Expected(**values)  # type: ignore[arg-type]


def test_u14_migration_031_adds_a_nullable_expected_json(test_db):
    conn = test_db.connect()
    assert (
        conn.execute("SELECT 1 FROM schema_version WHERE version = 31").fetchone()
        is not None
    )
    columns = {
        r["name"]: r for r in conn.execute("PRAGMA table_info(intake_interpretations)")
    }
    assert "expected_json" in columns
    assert columns["expected_json"]["type"] == "TEXT"
    assert columns["expected_json"]["notnull"] == 0
    assert "ADD COLUMN expected_json TEXT" in MIGRATION_031.read_text(encoding="utf-8")


def test_u14_triggers_abort_an_update_of_expected_json(test_db):
    """030's triggers cover the added column unchanged: `expected_json`
    cannot be rewritten or cleared after the fact."""
    source_id = _intake_source()
    saved = InterpretationRepository.insert(
        _interpretation(source_id, expected=_expected_a118())
    )

    for value in ("{}", None):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute(
                "UPDATE intake_interpretations SET expected_json = ? WHERE id = ?",
                (value, saved.id),
            )
        db.rollback()

    latest = InterpretationRepository.latest_for_source(source_id)
    assert latest is not None and latest.expected == _expected_a118()


def test_u14_expected_round_trips_through_expected_json(test_db):
    source_id = _intake_source()
    written = _interpretation(source_id, expected=_expected_a118())
    InterpretationRepository.insert(written)

    read = InterpretationRepository.latest_for_source(source_id)
    assert read is not None
    assert read.expected == written.expected
    row = db.execute(
        "SELECT expected_json FROM intake_interpretations WHERE id = ?",
        (written.id,),
    ).fetchone()
    stored = json.loads(row["expected_json"])
    assert stored["kind"] == "amount_diff"
    assert stored["is_best_match"] is True

    plain = _interpretation(_intake_source())
    InterpretationRepository.insert(plain)
    assert plain.json_columns()["expected_json"] is None
    read_plain = InterpretationRepository.latest_for_source(plain.intake_source_id)
    assert read_plain is not None and read_plain.expected is None


def test_u14_tool_saves_the_expected_it_answered(
    period_id, purchase_accounts, intake_dir
):
    a118 = _a118(period_id)
    source = _upload(_text_pdf(U6_TEXT_LINES))

    answered = _tolka(source.id, expected_voucher_id=a118)

    saved = InterpretationRepository.latest_for_source(source.id)
    assert saved is not None and saved.expected is not None
    assert saved.expected.to_dict() == answered["expected"]
    assert answered["expected"]["is_best_match"] is True


def test_u14_get_shows_the_stored_expected_even_after_the_voucher_got_underlag(
    client, auth_headers, period_id, purchase_accounts, intake_dir
):
    """§12.6 (e): the read path gives the `expected` the tool answered, as
    stored -- also after the source is linked to that voucher, when a
    recomputation would find nothing. `expected` carries no `still_open`
    (§8 adds it to `match` only)."""
    from services.intake import IntakeService

    a118 = _a118(period_id)
    source = _upload(_text_pdf(U6_TEXT_LINES))
    answered = _tolka(source.id, expected_voucher_id=a118)
    before = _get_interpretation(client, auth_headers, source.id).json()
    assert before["expected"] == answered["expected"]
    assert before["expected_voucher_id"] == a118

    IntakeService().link_existing_voucher(
        source_id=source.id,
        voucher_id=a118,
        actor="api",
        summary="Kvittot hör till A-118",
    )
    after = _get_interpretation(client, auth_headers, source.id).json()

    assert after["expected"] == answered["expected"]
    assert "still_open" not in after["expected"]
    assert after["match"]["still_open"] is False
    assert after["expected_voucher_id"] == a118


def test_u14_without_expected_voucher_id_expected_is_null(
    client, auth_headers, period_id, purchase_accounts, intake_dir
):
    _a118(period_id)
    source = _upload(_text_pdf(U6_TEXT_LINES))
    _tolka(source.id)

    body = _get_interpretation(client, auth_headers, source.id).json()

    assert (body["expected"], body["expected_voucher_id"]) == (None, None)
    row = db.execute(
        "SELECT expected_json FROM intake_interpretations WHERE intake_source_id = ?",
        (source.id,),
    ).fetchone()
    assert row["expected_json"] is None


def test_u14_source_status_and_a_deleted_source_is_still_200(
    client, auth_headers, period_id, purchase_accounts, intake_dir
):
    """§12.6 (h): the answer carries the source's status, so a client sees
    that the source is deleted; the interpretation is part of the trail and
    is still read."""
    from services.intake import IntakeService

    source = _upload(_text_pdf(U6_TEXT_LINES))
    result = _tolka(source.id)
    body = _get_interpretation(client, auth_headers, source.id).json()
    assert body["source_status"] == IntakeRepository.get_source(source.id).status.value
    assert body["source_status"] != "deleted"

    IntakeService().soft_delete(source.id, actor="api")
    response = _get_interpretation(client, auth_headers, source.id)

    assert response.status_code == 200
    assert response.json()["source_status"] == "deleted"
    assert response.json()["interpretation_id"] == result["interpretation_id"]


# ---------------------------------------------------------------------------
# U10 — the scripted intake pass (§10.5 testfall 39)
# ---------------------------------------------------------------------------

#: A receipt for exactly A-118's 4 480 kr, VAT 896 kr, the same day.
U10_TEXT_LINES = [
    "Elektronikhuset AB",
    "Kvitto 2026-03-15",
    "USB-C docka 4 480,00 kr",
    "Netto 3 584,00 kr",
    "Moms 896,00 kr",
    "Att betala 4 480,00 kr",
]


def test_39_scripted_pass_abstains_instead_of_double_posting(
    period_id, purchase_accounts, intake_dir
):
    """Testfall 39: an intake pass (`AgentWorker.run_pass_once`) with
    `agentruntime`'s scripted client, over a receipt that matches a posted
    A-voucher exactly. The model does what §9 says: `hamta_underlagsfil`
    -> `tolka_underlag` -> `registrera_avstaende` with the voucher number
    in the motivation. No new voucher, nothing in `voucher_intake_sources`.

    Scripted: it proves the path works when the model follows the
    instruction, not that a real model does (§11 kriterium 6)."""
    from services.agent_runtime import AgentWorker
    from services.llm import LLMTurn, ToolCall, Usage
    from tests.test_agent_runtime import FakeLLMClient

    voucher_id = _a118(period_id)
    number = _voucher_number(voucher_id)
    assert number.startswith("A-")
    source = _upload(_text_pdf(U10_TEXT_LINES))
    before = _books_snapshot()

    def _turn(call_id: str, name: str, arguments: dict) -> LLMTurn:
        return LLMTurn(
            text="",
            tool_calls=[ToolCall(id=call_id, name=name, arguments=arguments)],
            stop="tool_calls",
            usage=Usage(10, 10, 0),
        )

    motivation = (
        f"Underlaget hör till redan postade {number}: 4 480,00 kr på båda, "
        "differens 0 kr. Kopplas i flode-underlag."
    )
    client = FakeLLMClient(
        [
            _turn("call-1", "hamta_underlagsfil", {"source_id": source.id}),
            _turn(
                "call-2",
                "tolka_underlag",
                {
                    "source_id": source.id,
                    "vendor": "Elektronikhuset",
                    "document_date": "2026-03-15",
                    "currency": "SEK",
                    "total_ore": 448000,
                    "vat_ore": 89600,
                    "lines": [
                        {"text": "USB-C docka", "amount_ore": 448000, "vat_rate": 25}
                    ],
                },
            ),
            _turn(
                "call-3",
                "registrera_avstaende",
                {
                    "source_id": source.id,
                    "summary": f"Underlaget matchar {number} exakt",
                    "error_detail": motivation,
                },
            ),
        ],
        _u6_capabilities(),
    )

    run = AgentWorker().run_pass_once(client_factory=lambda model: client)

    # The pass ran the three calls, in order, and abstained.
    assert run is not None and run.status == "completed"
    assert run.items_posted == 0
    assert len(client.calls) == 3
    assert "tolka_underlag" in [t["name"] for t in client.calls[0]["tools"]]

    # What the model saw before it abstained: the file's text, then an
    # exact match on the voucher it names. (The fake keeps the loop's one
    # message list by reference, so results are found by their call id.)
    results = {
        block["tool_use_id"]: block
        for message in client.calls[-1]["messages"]
        if message["role"] == "user" and isinstance(message["content"], list)
        for block in message["content"]
        if block.get("type") == "tool_result"
    }
    assert list(results) == ["call-1", "call-2"]
    assert not any(block.get("is_error") for block in results.values())
    file_text = json.dumps(results["call-1"]["content"], ensure_ascii=False)
    assert "Att betala 4 480,00 kr" in file_text
    tolka_block = results["call-2"]
    tolka = json.loads(tolka_block["content"][0]["text"])
    assert tolka["confidence"] == "high"
    assert tolka["checks"]["text_layer"] == "agrees"
    assert tolka["match"]["kind"] == "exact"
    assert tolka["match"]["voucher_id"] == voucher_id
    assert tolka["match"]["voucher_number"] == number
    assert tolka["match"]["diff_ore"] == 0
    assert tolka["match"]["hypothesis"] is None

    # The interpretation is saved; the intake pass carries no thread.
    saved = InterpretationRepository.latest_for_source(source.id)
    assert saved is not None and saved.id == tolka["interpretation_id"]
    assert saved.match is not None and saved.match.kind == "exact"
    assert saved.thread_id is None
    # ... but it does carry the pass's own run (§12.6 a, U11).
    assert saved.agent_run_id == run.id

    # The abstention names the voucher; the source is failed, not linked.
    refreshed = IntakeRepository.get_source(source.id)
    assert refreshed is not None and refreshed.status.value == "failed"
    after = _books_snapshot()
    assert after["vouchers"] == before["vouchers"]
    assert after["voucher_rows"] == before["voucher_rows"]
    assert after["attachments"] == before["attachments"]
    assert after["voucher_intake_sources"] == before["voucher_intake_sources"] == []
    attempt = db.execute(
        "SELECT error_detail FROM intake_processing_attempts "
        "WHERE intake_source_id = ? AND error_detail IS NOT NULL",
        (source.id,),
    ).fetchall()
    assert [row["error_detail"] for row in attempt] == [motivation]
    assert number in motivation


# ---------------------------------------------------------------------------
# U11 — `agent_run_id` in `tool_context` (§12.6 a)
# ---------------------------------------------------------------------------


def _u11_turn(call_id: str, name: str, arguments: dict):
    from services.llm import LLMTurn, ToolCall, Usage

    return LLMTurn(
        text="",
        tool_calls=[ToolCall(id=call_id, name=name, arguments=arguments)],
        stop="tool_calls",
        usage=Usage(10, 10, 0),
    )


def _u11_tolka_arguments(source_id: str) -> dict:
    return {**U6_ARGS, "source_id": source_id}


def test_u11_thread_turn_saves_its_run_id(period_id, purchase_accounts, intake_dir):
    """A `tolka_underlag` call in a real thread turn (`ThreadTurnRunner.run`
    -> `run_thread_session` -> `run_tool_loop` -> `execute_tool`) saves the
    turn's own `agent_runs` row as `agent_run_id`, next to the thread."""
    from repositories.agent_run_repo import AgentRunRepository
    from repositories.thread_repo import ThreadRepository
    from services.llm import LLMTurn, Usage
    from services.thread_stream import ThreadTurnRunner
    from tests.test_agent_runtime import FakeLLMClient

    fiscal_year_id = PeriodRepository.get_period(period_id).fiscal_year_id
    thread = ThreadRepository.get_or_create(
        view_key="bocker.verifikationer",
        fiscal_year_id=fiscal_year_id,
        model="opencode/claude-opus-5",
    )
    trigger = ThreadRepository.add_post(
        thread_id=thread.id,
        post_type="user_text",
        actor="stefan",
        body={"text": "Vad står det på kvittot?"},
    )
    source = _upload(_text_pdf(U6_TEXT_LINES))
    client = FakeLLMClient(
        [
            _u11_turn("call-1", "tolka_underlag", _u11_tolka_arguments(source.id)),
            LLMTurn(
                text="Kvittot är tolkat.",
                tool_calls=[],
                stop="end",
                usage=Usage(10, 10, 0),
            ),
        ],
        _u6_capabilities(),
    )

    outcome = ThreadTurnRunner().run(
        thread, trigger, "Vad står det på kvittot?", client_factory=lambda m: client
    )

    assert outcome is not None and outcome.kind == "answered"
    saved = InterpretationRepository.latest_for_source(source.id)
    assert saved is not None
    assert saved.thread_id == thread.id
    assert saved.agent_run_id is not None
    run = AgentRunRepository.get(saved.agent_run_id)
    assert run is not None and run.trigger == "thread"


def test_u11_intake_pass_saves_its_run_id(period_id, purchase_accounts, intake_dir):
    """A `tolka_underlag` call in an intake pass (`AgentWorker.run_pass_once`
    -> `run_session`) saves the pass's `agent_runs` row, without a thread."""
    from services.agent_runtime import AgentWorker
    from tests.test_agent_runtime import FakeLLMClient

    source = _upload(_text_pdf(U6_TEXT_LINES))
    client = FakeLLMClient(
        [
            _u11_turn("call-1", "tolka_underlag", _u11_tolka_arguments(source.id)),
            _u11_turn(
                "call-2",
                "registrera_avstaende",
                {
                    "source_id": source.id,
                    "summary": "Tolkat, inte bokfört",
                    "error_detail": "U11-test",
                },
            ),
        ],
        _u6_capabilities(),
    )

    run = AgentWorker().run_pass_once(client_factory=lambda model: client)

    assert run is not None
    saved = InterpretationRepository.latest_for_source(source.id)
    assert saved is not None
    assert saved.thread_id is None
    assert saved.agent_run_id == run.id


# ---------------------------------------------------------------------------
# U15 — `POST /api/v1/intake/{id}/interpretation` (§8, §12.6 f)
# ---------------------------------------------------------------------------

#: sha256 of `tolka_underlag`'s `input_schema`, taken on `e2ad486` (U14),
#: before the route: the request body reuses the tool's fields without
#: changing the tool's schema -- the schemas are the cached prefix.
_TOLKA_UNDERLAG_SCHEMA_SHA256 = (
    "66d6422366b21fcd9024306cf9b0b8b2e3a4efad0d6ba06d965ab9759492ccfd"
)


def _post_interpretation(client, headers, source_id: str, body: dict):
    return client.post(_interpretation_url(source_id), headers=headers, json=body)


def _interpretation_rows() -> list:
    return [tuple(r) for r in db.execute("SELECT * FROM intake_interpretations")]


def test_u15_post_is_testfall_16_over_http(
    client, auth_headers, period_id, purchase_accounts, intake_dir
):
    """Testfall 16 through the POST: 4 600 kr against A-118's 4 480 kr ->
    `amount_diff`, `diff_ore = 12000`, the hypothesis on the pant line. The
    answer is the tool's (§6.5); the row has the route's actor and neither
    a thread nor a run."""
    voucher_id = _a118(period_id)
    source = _upload(_text_pdf(U6_TEXT_LINES))

    response = _post_interpretation(client, auth_headers, source.id, U6_ARGS)

    assert response.status_code == 201
    result = response.json()
    assert list(result) == [
        "interpretation_id",
        "source_id",
        "read",
        "checks",
        "confidence",
        "match",
        "candidates",
        "expected",
        "placement",
    ]
    assert result["source_id"] == source.id
    assert result["read"] == U6_ARGS
    assert result["confidence"] == "high"
    assert result["checks"]["text_layer"] == "agrees"
    match = result["match"]
    assert match["kind"] == "amount_diff"
    assert match["voucher_id"] == voucher_id
    assert match["voucher_number"] == _voucher_number(voucher_id)
    assert match["amounts"] == {"document_ore": 460000, "voucher_ore": 448000}
    assert match["diff_ore"] == 12000
    assert match["vat"] == {"document_ore": 89600, "voucher_ore": 89600, "equal": True}
    assert match["hypothesis"] == {
        "text": "Skillnaden på 120,00 kr motsvarar raden ”Pant” på underlaget.",
        "basis": "line_items",
        "lines": [1],
    }
    assert result["expected"] is None

    saved = InterpretationRepository.latest_for_source(source.id)
    assert saved is not None and saved.id == result["interpretation_id"]
    assert (saved.actor, saved.thread_id, saved.agent_run_id) == ("api", None, None)


def test_u15_post_requires_bearer(
    client, auth_headers, period_id, purchase_accounts, intake_dir
):
    source = _upload(_text_pdf(U6_TEXT_LINES))
    url = _interpretation_url(source.id)

    assert client.post(url, json=U6_ARGS).status_code == 401
    wrong = {"Authorization": "Bearer not-the-key"}
    assert client.post(url, headers=wrong, json=U6_ARGS).status_code == 401
    assert _interpretation_rows() == []


def test_u15_confidence_or_hypothesis_in_the_body_is_refused(
    client, auth_headers, period_id, purchase_accounts, intake_dir
):
    """Criterion 5 over HTTP: the body is the tool's model, `extra="forbid"`
    -- a `confidence` or `hypothesis` is refused, not dropped, also on a
    line. Nothing is saved."""
    source = _upload(_text_pdf(U6_TEXT_LINES))
    line = {"text": "Pant", "amount_ore": 12000, "confidence": "high"}

    for body in (
        {**U6_ARGS, "confidence": "high"},
        {**U6_ARGS, "hypothesis": {"text": "Pant"}},
        {**U6_ARGS, "lines": [line]},
    ):
        response = _post_interpretation(client, auth_headers, source.id, body)
        assert response.status_code == 422, body
    assert _interpretation_rows() == []


def test_u15_source_id_in_the_body_is_refused(
    client, auth_headers, period_id, purchase_accounts, intake_dir
):
    """The id is the path's; a `source_id` in the body -- the same or
    another -- is an unknown field."""
    source = _upload(_text_pdf(U6_TEXT_LINES))
    other = _upload(_text_pdf([*U6_TEXT_LINES, "Kopia"]))

    for source_id in (source.id, other.id):
        response = _post_interpretation(
            client, auth_headers, source.id, {**U6_ARGS, "source_id": source_id}
        )
        assert response.status_code == 422
        assert "source_id" in json.dumps(response.json()["detail"])
    assert _interpretation_rows() == []


def test_u15_request_body_reuses_the_tool_fields_and_leaves_its_schema(client):
    """The body is `TolkaUnderlagArgs` without `source_id`, and the tool's
    `input_schema` is byte for byte what it was before the route."""
    from services.agent_tools import AGENT_TOOL_DEFINITIONS

    tool = AGENT_TOOL_DEFINITIONS[11]
    assert tool["name"] == "tolka_underlag"
    schema = json.dumps(tool["input_schema"])
    assert hashlib.sha256(schema.encode()).hexdigest() == _TOLKA_UNDERLAG_SCHEMA_SHA256

    openapi = client.get("/openapi.json").json()
    operation = openapi["paths"]["/api/v1/intake/{source_id}/interpretation"]["post"]
    ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    body = openapi["components"]["schemas"][ref.rsplit("/", 1)[-1]]
    assert list(body["properties"]) == [
        name for name in tool["input_schema"]["properties"] if name != "source_id"
    ]
    assert body["additionalProperties"] is False
    assert body["required"] == ["total_ore"]


def test_u15_unknown_and_deleted_source(
    client, auth_headers, period_id, purchase_accounts, intake_dir
):
    """Testfall 36 over HTTP: an unknown source is 404 `source_not_found`
    (as the GET's), a soft-deleted one 409 `source_deleted` (the intake
    routes' state conflict). Nothing is saved."""
    from services.intake import IntakeService

    response = _post_interpretation(client, auth_headers, "no-such-source", U6_ARGS)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "source_not_found"

    source = _upload(_text_pdf(U6_TEXT_LINES))
    IntakeService().soft_delete(source.id, actor="api")
    response = _post_interpretation(client, auth_headers, source.id, U6_ARGS)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "source_deleted"
    assert _interpretation_rows() == []


def test_u15_expected_voucher_not_found(
    client, auth_headers, period_id, purchase_accounts, intake_dir
):
    """A domain `ValidationError` is 400 with its code, as in the other
    routes (`drafts`, `decisions`, `agent`); nothing is saved."""
    source = _upload(_text_pdf(U6_TEXT_LINES))

    response = _post_interpretation(
        client,
        auth_headers,
        source.id,
        {**U6_ARGS, "expected_voucher_id": "no-such-voucher"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "expected_voucher_not_found"
    assert _interpretation_rows() == []


def test_u15_post_changes_nothing_in_the_books(
    client, auth_headers, period_id, purchase_accounts, intake_dir
):
    """Testfall 33 over HTTP: the same snapshot before and after; the only
    new row is the interpretation, and a second POST adds a second one."""
    a118 = _a118(period_id)
    with_attachment = _purchase(period_id, total=460000, vat=92000, day=16)
    _attach(with_attachment)
    linked = _purchase(period_id, total=455000, vat=91000, day=14)
    _link_intake_source(linked)
    source = _upload(_text_pdf(U6_TEXT_LINES))
    before = _books_snapshot()
    assert all(before[name] for name in before), "every table has content"

    body = {**U6_ARGS, "expected_voucher_id": a118}
    response = _post_interpretation(client, auth_headers, source.id, body)
    assert response.status_code == 201
    assert response.json()["match"]["voucher_id"] == a118
    assert _books_snapshot() == before
    assert InterpretationRepository.count_for_source(source.id) == 1
    first = _interpretation_rows()

    assert (
        _post_interpretation(client, auth_headers, source.id, body).status_code == 201
    )
    assert _books_snapshot() == before
    assert InterpretationRepository.count_for_source(source.id) == 2
    assert set(first) < set(_interpretation_rows())


def test_u15_get_after_post_gives_the_same_interpretation(
    client, auth_headers, period_id, purchase_accounts, intake_dir
):
    a118 = _a118(period_id)
    source = _upload(_text_pdf(U6_TEXT_LINES))
    posted = _post_interpretation(
        client, auth_headers, source.id, {**U6_ARGS, "expected_voucher_id": a118}
    ).json()

    body = _get_interpretation(client, auth_headers, source.id).json()

    for key in posted:
        if key == "match":
            continue
        assert body[key] == posted[key], key
    assert body["match"] == {**posted["match"], "still_open": True}
    assert body["expected_voucher_id"] == a118
    assert (body["actor"], body["thread_id"]) == ("api", None)
    assert body["superseded_count"] == 0
