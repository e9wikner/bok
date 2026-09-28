"""Tests for `flode-underlag` (docs/redesign/SPEC-flode-underlag.md).

This file holds the module's shared helpers (FU1) -- the other
`tests/test_flode_underlag_*.py` files import them from here, one file per
track (plan, "Testfilerna") -- and the tests for the link itself: the
schema (FU1), `IntakeLinkService`'s checks 1-8 with `exact_match` (FU3) and
the decision basis (FU4).

Test case numbers refer to the tables in the spec's §14. No real LLM:
interpretations go through `InterpretationService.interpret`, decisions
through `DecisionService`, as the tools would call them.
"""

import sqlite3
import uuid
from dataclasses import FrozenInstanceError
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

import pytest
from fastapi.testclient import TestClient

from config import settings
from db.database import db
from repositories.account_repo import AccountRepository
from repositories.intake_repo import IntakeRepository
from repositories.period_repo import PeriodRepository

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = REPO_ROOT / "docs" / "redesign" / "SPEC-flode-underlag.md"
MIGRATION_032 = REPO_ROOT / "db" / "migrations" / "032_add_intake_link_basis.sql"

#: The view whose thread flöde 4 runs in.
VIEW_KEY = "bocker.verifikationer"
MODEL = "opencode/claude-opus-5"

#: Flöde 4's A-118, moved into the fixture's March: 4 480 kr with 896 kr
#: input VAT, paid by card on the 15th.
A118_TOTAL = 448000
A118_VAT = 89600
A118_DAY = 15


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def accounts(test_db):
    """A purchase's accounts (expense, input VAT, bank) and a sale's."""
    for code, name, acc_type in [
        ("5410", "Förbrukningsinventarier", "expense"),
        ("2640", "Ingående moms", "vat_in"),
        ("1930", "Företagskonto", "asset"),
        ("1510", "Kundfordringar", "asset"),
        ("3011", "Försäljning tjänster 25%", "revenue"),
    ]:
        if not AccountRepository.exists(code):
            AccountRepository.create(code, name, acc_type)


@pytest.fixture
def period_id(test_db, accounts):
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


@pytest.fixture
def client(test_db, accounts):
    from api.main import app

    return TestClient(app)


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {settings.api_key}"}


@pytest.fixture
def intake_dir(tmp_path):
    """`settings.intake_dir` under *tmp_path*, so a source's file resolves
    inside the intake root."""
    original = settings.intake_dir
    settings.intake_dir = str(tmp_path / "intake")
    yield settings.intake_dir
    settings.intake_dir = original


# ---------------------------------------------------------------------------
# Helpers: vouchers, sources, interpretations, threads, decisions
# ---------------------------------------------------------------------------


def posted_purchase(
    period_id: str,
    *,
    total: int = A118_TOTAL,
    vat: int = A118_VAT,
    day: int = A118_DAY,
    series: str = "A",
    created_by: str = "agent",
    post: bool = True,
) -> str:
    """A purchase paid from the bank: 5410 net + 2640 VAT debit, 1930 total
    credit. Posted unless *post* is false."""
    from services.ledger import LedgerService

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


def a118(period_id: str) -> str:
    """Flöde 4's A-118, bankbokförd, without underlag."""
    return posted_purchase(period_id)


def voucher_number(voucher_id: str) -> str:
    row = db.execute(
        "SELECT series, number FROM vouchers WHERE id = ?", (voucher_id,)
    ).fetchone()
    return f"{row['series']}-{row['number']}"


def make_source(
    status: str = "pending",
    *,
    mime_type: str = "image/jpeg",
    filename: str = "kvitto.jpg",
) -> str:
    """An `intake_sources` row in *status*. An image by default, so an
    interpretation reads no text layer and needs no file on disk."""
    source_id = str(uuid.uuid4())
    IntakeRepository.create_source(
        source_id=source_id,
        original_filename=filename,
        mime_type=mime_type,
        size_bytes=1024,
        sha256=uuid.uuid4().hex,
        stored_path=f"/tmp/{source_id}.jpg",
        uploaded_by="stefan",
        status=status,
    )
    return source_id


#: What the model reads from flöde 4's receipt, per match kind against
#: A-118 (`SPEC-underlagstolkning.md` §7.4).
_READS: Dict[str, Dict[str, Any]] = {
    "exact": {
        "vendor": "Elektronikhuset",
        "document_date": "2026-03-15",
        "total_ore": A118_TOTAL,
        "vat_ore": A118_VAT,
        "lines": [
            {"text": "USB-C docka", "amount_ore": A118_TOTAL, "vat_rate": 25},
        ],
    },
    "amount_diff": {
        "vendor": "Elektronikhuset",
        "document_date": "2026-03-15",
        "total_ore": 460000,
        "vat_ore": A118_VAT,
        "lines": [
            {"text": "USB-C docka", "amount_ore": A118_TOTAL, "vat_rate": 25},
            {"text": "Pant", "amount_ore": 12000, "vat_rate": 0},
        ],
    },
    "exact_no_date": {
        "vendor": "Elektronikhuset",
        "document_date": None,
        "total_ore": A118_TOTAL,
        "vat_ore": A118_VAT,
        "lines": [
            {"text": "USB-C docka", "amount_ore": A118_TOTAL, "vat_rate": 25},
        ],
    },
}


def interpret(
    source_id: str,
    kind: str = "exact",
    *,
    thread=None,
    agent_run_id: Optional[str] = None,
    expected_voucher_id: Optional[str] = None,
    **overrides,
) -> Dict[str, Any]:
    """Interpret *source_id* through `InterpretationService.interpret`, the
    way `tolka_underlag` does, with the read that gives *kind* against
    A-118. Returns the tool's answer (§6.5)."""
    from services.agent_tools import TolkaUnderlagArgs
    from services.interpretation_service import InterpretationService

    arguments = {
        **_READS[kind],
        "source_id": source_id,
        "expected_voucher_id": expected_voucher_id,
        **overrides,
    }
    return InterpretationService().interpret(
        TolkaUnderlagArgs.model_validate(arguments),
        actor="agent",
        thread_id=thread.id if thread is not None else None,
        agent_run_id=agent_run_id,
    )


def make_thread(period_id: str, view_key: str = VIEW_KEY):
    from repositories.thread_repo import ThreadRepository

    period = PeriodRepository.get_period(period_id)
    assert period is not None
    return ThreadRepository.get_or_create(
        view_key=view_key, fiscal_year_id=period.fiscal_year_id, model=MODEL
    )


def make_run(trigger: str = "thread") -> str:
    from repositories.agent_run_repo import AgentRunRepository

    return AgentRunRepository.create(
        trigger=trigger, model=MODEL, protocol="messages"
    ).id


#: Flöde 4 steg 3's three options (§9.2), in the panel's order.
def link_options(amount_ore: int = 12000):
    return [
        {
            "title": "Koppla och bokför skillnaden",
            "account": "5410",
            "amount_ore": amount_ore,
            "rationale": "Pantavgiften bokförs som egen verifikation.",
            "recommended": True,
            "is_exit": False,
        },
        {
            "title": "Koppla utan att ändra",
            "rationale": "Skillnaden lämnas som en anteckning.",
            "is_exit": False,
        },
        {
            "title": "Det är ett annat köp",
            "rationale": "Kvittot hör inte till A-118.",
            "is_exit": True,
        },
    ]


def make_decision(
    thread,
    source_id: str,
    *,
    answer: Optional[Any] = 1,
    source_kind: str = "intake_source",
    actor: str = "stefan",
):
    """A decision about *source_id* in *thread* with §9.2's three options,
    answered with option *answer* (1-based position), with free text when
    *answer* is a string, or left open when it is `None`."""
    from repositories.decision_repo import DecisionRepository
    from services.decision_service import DecisionService

    service = DecisionService()
    decision = service.create(
        thread,
        title="Kvitto Elektronikhuset mot A-118",
        reason="Kvittot är 4 600 kr, A-118 är 4 480 kr.",
        consequence="Ingenting kopplas förrän du valt.",
        source={"kind": source_kind, "id": source_id},
        options=link_options(),
    )
    if answer is None:
        return decision
    if isinstance(answer, str):
        service.answer(decision.id, free_text=answer, actor=actor)
    else:
        option = next(o for o in decision.options if o.position == answer)
        service.answer(decision.id, option_id=option.id, actor=actor)
    answered = DecisionRepository.get(decision.id)
    assert answered is not None
    return answered


def table_rows(table: str) -> list:
    return [tuple(r) for r in db.execute(f"SELECT * FROM {table} ORDER BY rowid")]


# ---------------------------------------------------------------------------
# FU1 — migration 032, domain and repositories (§5; testfall 17, 42c)
# ---------------------------------------------------------------------------


def _section_5_blocks() -> list:
    spec = SPEC.read_text(encoding="utf-8")
    section = spec.split("## 5. Datamodell — migration 032", 1)[1]
    section = section.split("\n## 6.", 1)[0]
    return [part.split("```", 1)[0].strip() for part in section.split("```sql\n")[1:]]


def test_fu1_migration_carries_section_5_verbatim():
    """Both of §5's `sql` blocks stand in the migration as written."""
    blocks = _section_5_blocks()
    migration = MIGRATION_032.read_text(encoding="utf-8")

    assert len(blocks) == 2
    for block in blocks:
        assert block in migration


def test_fu1_migration_is_applied_with_four_triggers(test_db):
    conn = test_db.connect()
    assert (
        conn.execute("SELECT 1 FROM schema_version WHERE version = 32").fetchone()
        is not None
    )
    # test_numrering checks that 27 is applied; 32 does not unapply it.
    assert (
        conn.execute("SELECT 1 FROM schema_version WHERE version = 27").fetchone()
        is not None
    )
    triggers = {
        (r["tbl_name"], r["name"])
        for r in conn.execute(
            "SELECT tbl_name, name FROM sqlite_master WHERE type = 'trigger' "
            "AND tbl_name IN ('intake_link_basis', 'voucher_source_references')"
        )
    }
    assert triggers == {
        ("intake_link_basis", "prevent_update_intake_link_basis"),
        ("intake_link_basis", "prevent_delete_intake_link_basis"),
        ("voucher_source_references", "prevent_update_voucher_source_references"),
        ("voucher_source_references", "prevent_delete_voucher_source_references"),
    }


def _basis_rows(period_id: str, *, basis: str = "decision"):
    """A real row for each foreign key: voucher, source, interpretation,
    thread, run and decision."""
    from domain.intake_link import IntakeLinkBasis

    voucher_id = a118(period_id)
    source_id = make_source()
    interpretation = interpret(source_id, "amount_diff")
    thread = make_thread(period_id)
    run_id = make_run()
    decision = make_decision(thread, source_id)
    return (
        IntakeLinkBasis(
            intake_source_id=source_id,
            voucher_id=voucher_id,
            basis=basis,  # type: ignore[arg-type]
            interpretation_id=interpretation["interpretation_id"],
            decision_id=decision.id if basis == "decision" else None,
            actor="stefan",
            agent_run_id=run_id,
            thread_id=thread.id,
        ),
        decision,
    )


def test_fu1_link_basis_round_trips(period_id):
    from repositories.intake_link_repo import IntakeLinkRepository

    basis, decision = _basis_rows(period_id)

    IntakeLinkRepository.insert(basis)

    assert IntakeLinkRepository.get_for_source(basis.intake_source_id) == basis
    assert IntakeLinkRepository.get_by_decision(decision.id) == basis
    assert IntakeLinkRepository.get_for_source("nope") is None
    assert IntakeLinkRepository.get_by_decision("nope") is None


def test_17_update_and_delete_on_link_basis_are_aborted(period_id):
    """Testfall 17: the trigger aborts, and the row is unchanged."""
    from repositories.intake_link_repo import IntakeLinkRepository

    basis, _ = _basis_rows(period_id)
    IntakeLinkRepository.insert(basis)
    before = table_rows("intake_link_basis")

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute(
            "UPDATE intake_link_basis SET actor = 'agent' WHERE intake_source_id = ?",
            (basis.intake_source_id,),
        )
    db.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute(
            "DELETE FROM intake_link_basis WHERE intake_source_id = ?",
            (basis.intake_source_id,),
        )
    db.rollback()

    assert table_rows("intake_link_basis") == before


@pytest.mark.parametrize(
    "basis, with_decision",
    [("decision", False), ("exact_match", True), ("guess", False)],
    ids=["decision-without-id", "exact-with-id", "unknown-basis"],
)
def test_fu1_link_basis_checks_reject(period_id, basis, with_decision):
    """`CHECK ((basis = 'decision') = (decision_id IS NOT NULL))` and the
    basis values."""
    from dataclasses import replace

    from repositories.intake_link_repo import IntakeLinkRepository

    row, decision = _basis_rows(period_id)
    row = replace(
        row,
        basis=basis,  # type: ignore[arg-type]
        decision_id=decision.id if with_decision else None,
    )

    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        IntakeLinkRepository.insert(row)
    db.rollback()
    assert table_rows("intake_link_basis") == []


def _reference(period_id: str, *, same_voucher: bool = False):
    from domain.intake_link import VoucherSourceReference

    basis, decision = _basis_rows(period_id)
    correction = (
        basis.voucher_id
        if same_voucher
        else posted_purchase(period_id, total=12000, vat=0)
    )
    return VoucherSourceReference(
        voucher_id=correction,
        intake_source_id=basis.intake_source_id,
        via_voucher_id=basis.voucher_id,
        decision_id=decision.id,
    )


def test_fu1_reference_round_trips(period_id):
    from repositories.intake_link_repo import VoucherSourceReferenceRepository

    ref = _reference(period_id)

    VoucherSourceReferenceRepository.insert(ref)

    assert VoucherSourceReferenceRepository.get_for_voucher(ref.voucher_id) == ref
    assert VoucherSourceReferenceRepository.get_for_voucher(ref.via_voucher_id) is None


def test_42c_update_and_delete_on_references_are_aborted(period_id):
    """Testfall 42c."""
    from repositories.intake_link_repo import VoucherSourceReferenceRepository

    ref = _reference(period_id)
    VoucherSourceReferenceRepository.insert(ref)
    before = table_rows("voucher_source_references")

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute(
            "UPDATE voucher_source_references SET via_voucher_id = voucher_id "
            "WHERE voucher_id = ?",
            (ref.voucher_id,),
        )
    db.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute(
            "DELETE FROM voucher_source_references WHERE voucher_id = ?",
            (ref.voucher_id,),
        )
    db.rollback()

    assert table_rows("voucher_source_references") == before


def test_fu1_reference_to_itself_is_rejected(period_id):
    """`CHECK (voucher_id != via_voucher_id)`."""
    from repositories.intake_link_repo import VoucherSourceReferenceRepository

    ref = _reference(period_id, same_voucher=True)

    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        VoucherSourceReferenceRepository.insert(ref)
    db.rollback()
    assert table_rows("voucher_source_references") == []


def test_fu1_repositories_have_no_update_or_delete():
    """The second of the three layers: nothing in the repositories rewrites
    or removes a row."""
    from repositories.intake_link_repo import (
        IntakeLinkRepository,
        VoucherSourceReferenceRepository,
    )

    def public(cls):
        return {n for n in vars(cls) if not n.startswith("_")}

    assert public(IntakeLinkRepository) == {
        "insert",
        "get_for_source",
        "get_by_decision",
    }
    assert public(VoucherSourceReferenceRepository) == {"insert", "get_for_voucher"}
    source = (REPO_ROOT / "repositories" / "intake_link_repo.py").read_text(
        encoding="utf-8"
    )
    assert "UPDATE" not in source
    assert "DELETE" not in source


def test_fu1_domain_types_are_frozen_and_result_is_section_6_6():
    from domain.intake_link import (
        IntakeLinkBasis,
        LinkResult,
        VoucherSourceReference,
    )

    basis = IntakeLinkBasis(
        intake_source_id="s",
        voucher_id="v",
        basis="exact_match",
        interpretation_id="i",
        actor="agent",
    )
    ref = VoucherSourceReference(
        voucher_id="a121", intake_source_id="s", via_voucher_id="a118", decision_id="d"
    )
    for frozen in (basis, ref):
        with pytest.raises(FrozenInstanceError):
            frozen.voucher_id = "other"  # type: ignore[misc]

    result = LinkResult(
        source_id="s",
        voucher_id="v",
        voucher_number="A-118",
        basis="decision",
        interpretation_id="i",
        decision_id="d",
        replayed=False,
        missing_attachments=3,
    )
    assert result.to_dict() == {
        "source_id": "s",
        "voucher_id": "v",
        "voucher_number": "A-118",
        "basis": "decision",
        "interpretation_id": "i",
        "decision_id": "d",
        "replayed": False,
        "missing_attachments": 3,
    }


def test_fu1_helpers_give_each_kind(period_id):
    """The helpers the other files build on: the three kinds against A-118,
    and a decision answered by option, by exit, by free text or open."""
    voucher_id = a118(period_id)
    for kind in ("exact", "amount_diff", "exact_no_date"):
        result = interpret(make_source(), kind)
        assert result["match"]["kind"] == kind
        assert result["match"]["voucher_id"] == voucher_id

    thread = make_thread(period_id)
    source_id = make_source()
    assert make_decision(thread, source_id, answer=None).status == "open"
    option_2 = make_decision(thread, source_id, answer=2)
    assert option_2.status == "answered"
    assert option_2.answer_option_id == option_2.options[1].id
    free = make_decision(thread, source_id, answer="Ja, samma köp")
    assert free.answer_text == "Ja, samma köp"
    assert free.source_kind == "intake_source" and free.source_id == source_id
