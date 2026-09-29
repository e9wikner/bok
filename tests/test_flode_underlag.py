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


# ---------------------------------------------------------------------------
# FU3 — `IntakeLinkService`: checks 1-8, `exact_match`, the transaction and
# the replay (§6.1-§6.6; testfall 1-3, 8, 9, 12-16, 18, 19)
# ---------------------------------------------------------------------------

#: The tables a link writes in (§6.1), and the book it never touches.
LINK_TABLES = (
    "voucher_intake_sources",
    "intake_processing_attempts",
    "intake_link_basis",
)


def link(source_id: str, voucher_id: str, **kwargs):
    from services.intake_link import IntakeLinkService

    kwargs.setdefault("actor", "agent")
    return IntakeLinkService().link(source_id, voucher_id, **kwargs)


def link_error(source_id: str, voucher_id: str, **kwargs):
    """The `IntakeLinkError` a link raises; asserts it raised one."""
    from services.intake_link import IntakeLinkError

    with pytest.raises(IntakeLinkError) as exc:
        link(source_id, voucher_id, **kwargs)
    return exc.value


def link_state() -> dict:
    """What a link writes, and the source statuses -- to assert that a
    refused link wrote nothing."""
    state = {table: table_rows(table) for table in LINK_TABLES}
    state["statuses"] = table_rows("intake_sources")
    return state


def books() -> tuple:
    """`vouchers` and `voucher_rows`, row by row (testfall 18)."""
    return table_rows("vouchers"), table_rows("voucher_rows")


def attach(voucher_id: str) -> None:
    """An `attachments` row, as `POST /vouchers/{id}/attachments` writes it."""
    from datetime import datetime

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


def source_status(source_id: str) -> str:
    source = IntakeRepository.get_source(source_id)
    assert source is not None
    return source.status.value


def test_01_exact_match_links_without_a_decision(period_id):
    """Testfall 1: exact, still open, no decision -> linked with
    `basis = exact_match`; the source is `processed` and the voucher no
    longer lacks underlag."""
    from repositories.intake_link_repo import IntakeLinkRepository
    from repositories.voucher_repo import VoucherRepository

    voucher_id = a118(period_id)
    source_id = make_source()
    interpretation = interpret(source_id, "exact")
    before = VoucherRepository.count_missing_attachments()

    result = link(source_id, voucher_id)

    assert result.to_dict() == {
        "source_id": source_id,
        "voucher_id": voucher_id,
        "voucher_number": voucher_number(voucher_id),
        "basis": "exact_match",
        "interpretation_id": interpretation["interpretation_id"],
        "decision_id": None,
        "replayed": False,
        "missing_attachments": before - 1,
    }
    assert source_status(source_id) == "processed"
    voucher = VoucherRepository.get(voucher_id)
    assert voucher is not None and voucher.missing_attachment is False
    basis = IntakeLinkRepository.get_for_source(source_id)
    assert basis is not None
    assert (basis.basis, basis.voucher_id, basis.decision_id) == (
        "exact_match",
        voucher_id,
        None,
    )
    assert basis.interpretation_id == interpretation["interpretation_id"]
    assert (basis.thread_id, basis.agent_run_id, basis.actor) == (None, None, "agent")
    vis = IntakeRepository.get_link_by_source_id(source_id)
    assert vis is not None and vis.voucher_id == voucher_id
    assert vis.link_reason == (
        f"exact_match interpretation={interpretation['interpretation_id']}"
    )
    [attempt] = IntakeRepository.list_attempts_for_source(source_id)
    assert attempt.status.value == "processed"
    assert attempt.voucher_id == voucher_id


def test_01_thread_and_run_land_on_the_basis(period_id):
    from repositories.intake_link_repo import IntakeLinkRepository

    voucher_id = a118(period_id)
    source_id = make_source()
    interpret(source_id, "exact")
    thread = make_thread(period_id)
    run_id = make_run()

    link(source_id, voucher_id, thread_id=thread.id, agent_run_id=run_id)

    basis = IntakeLinkRepository.get_for_source(source_id)
    assert basis is not None
    assert (basis.thread_id, basis.agent_run_id) == (thread.id, run_id)


@pytest.mark.parametrize("kind", ["amount_diff", "exact_no_date"])
def test_02_03_without_exact_match_a_decision_is_required(period_id, kind):
    """Testfall 2 and 3: `link_requires_decision` with the match kind in
    `details`, and nothing written."""
    from services.intake_link import LinkRejectedError

    voucher_id = a118(period_id)
    source_id = make_source()
    interpret(source_id, kind)
    before = link_state()

    error = link_error(source_id, voucher_id)

    assert isinstance(error, LinkRejectedError)
    assert error.code == "link_requires_decision"
    assert f"match_kind={kind}" in (error.details or "")
    assert link_state() == before


def test_08_without_an_interpretation(period_id):
    """Testfall 8: `interpretation_required`, telling the agent what to do."""
    from services.intake_link import LinkRejectedError

    voucher_id = a118(period_id)
    source_id = make_source()

    error = link_error(source_id, voucher_id)

    assert isinstance(error, LinkRejectedError)
    assert error.code == "interpretation_required"
    assert "tolka_underlag" in error.message


def test_09_voucher_not_in_the_interpretation(period_id):
    """Testfall 9: a posted voucher that was never set against the receipt
    -> `voucher_not_in_interpretation`, naming the interpretation's
    vouchers."""
    from services.intake_link import LinkRejectedError

    voucher_id = a118(period_id)
    stranger = posted_purchase(period_id, total=999900, vat=0, day=2)
    source_id = make_source()
    interpret(source_id, "amount_diff")
    before = link_state()

    error = link_error(source_id, stranger)

    assert isinstance(error, LinkRejectedError)
    assert error.code == "voucher_not_in_interpretation"
    assert voucher_number(voucher_id) in (error.details or "")
    assert link_state() == before


def test_fu3_candidate_that_is_not_the_match_passes_check_8(period_id):
    """Check 8 accepts `candidates` too: a second candidate is in the
    interpretation, so the refusal is the basis (check 9), not check 8."""
    first = a118(period_id)
    second = posted_purchase(period_id, day=16)
    source_id = make_source()
    result = interpret(source_id, "amount_diff")
    ids = {c["voucher_id"] for c in result["candidates"]}
    assert {first, second} <= ids
    other = next(i for i in ids if i != (result["match"] or {}).get("voucher_id"))

    error = link_error(source_id, other)

    assert error.code == "link_requires_decision"


def test_12_deleted_source(period_id):
    """Testfall 12."""
    from services.intake_link import LinkConflictError

    voucher_id = a118(period_id)
    source_id = make_source()
    interpret(source_id, "exact")
    IntakeRepository.update_status(source_id, "deleted", actor="stefan")

    error = link_error(source_id, voucher_id)

    assert isinstance(error, LinkConflictError)
    assert error.code == "source_deleted"


def test_fu3_unknown_source_and_voucher(period_id):
    from services.intake_link import LinkNotFoundError

    voucher_id = a118(period_id)
    source_id = make_source()
    interpret(source_id, "exact")

    unknown_source = link_error("nope", voucher_id)
    unknown_voucher = link_error(source_id, "nope")

    assert isinstance(unknown_source, LinkNotFoundError)
    assert unknown_source.code == "source_not_found"
    assert isinstance(unknown_voucher, LinkNotFoundError)
    assert unknown_voucher.code == "voucher_not_found"


def test_13_same_source_same_voucher_twice_is_a_replay(period_id):
    """Testfall 13: one link, one basis, one attempt; the second answer is
    the first with `replayed: true`."""
    voucher_id = a118(period_id)
    source_id = make_source()
    interpret(source_id, "exact")

    first = link(source_id, voucher_id)
    state = link_state()
    second = link(source_id, voucher_id)

    assert second.replayed is True
    assert {**second.to_dict(), "replayed": False} == first.to_dict()
    assert link_state() == state
    assert len(state["intake_link_basis"]) == 1
    assert len(state["voucher_intake_sources"]) == 1


def test_14_same_source_another_voucher(period_id):
    """Testfall 14: `intake_already_linked` with the linked voucher's
    number."""
    from services.intake_link import LinkConflictError

    voucher_id = a118(period_id)
    other = posted_purchase(period_id, day=16)
    source_id = make_source()
    interpret(source_id, "exact")
    link(source_id, voucher_id)

    error = link_error(source_id, other)

    assert isinstance(error, LinkConflictError)
    assert error.code == "intake_already_linked"
    assert voucher_number(voucher_id) in (error.details or "")


def test_fu3_source_linked_by_a_posting_is_already_linked(period_id):
    """A link made by a posting has no basis (§5), so there is nothing to
    replay: linking the same source to the same voucher again is
    `intake_already_linked`, with that voucher's number."""
    voucher_id = a118(period_id)
    source_id = make_source()
    interpret(source_id, "exact")
    IntakeRepository.create_voucher_link(
        intake_source_id=source_id, voucher_id=voucher_id, linked_by="agent"
    )

    error = link_error(source_id, voucher_id)

    assert error.code == "intake_already_linked"
    assert voucher_number(voucher_id) in (error.details or "")


def test_15_opening_balance_and_draft(period_id):
    """Testfall 15: a voucher in `IB` / a draft."""
    from services.intake_link import LinkConflictError, LinkRejectedError

    source_id = make_source()
    interpret(source_id, "exact")
    opening = posted_purchase(period_id, series="IB", created_by="system")
    draft = posted_purchase(period_id, post=False)

    ib_error = link_error(source_id, opening)
    draft_error = link_error(source_id, draft)

    assert isinstance(ib_error, LinkRejectedError)
    assert ib_error.code == "voucher_is_opening_balance"
    assert isinstance(draft_error, LinkConflictError)
    assert draft_error.code == "voucher_not_posted"


@pytest.mark.parametrize(
    "status", ["pending", "processing", "failed", "needs_attention"]
)
def test_fu3_linkable_statuses(period_id, status):
    """Check 5 (D9): `failed` and `needs_attention` link too."""
    voucher_id = a118(period_id)
    source_id = make_source(status)
    interpret(source_id, "exact")

    result = link(source_id, voucher_id)

    assert result.basis == "exact_match"
    assert source_status(source_id) == "processed"


@pytest.mark.parametrize("status", ["processed", "skipped"])
def test_fu3_unlinkable_statuses(period_id, status):
    """Check 5: `processed` without a link, and `skipped`, do not link
    (§15: "Fråga först")."""
    from services.intake_link import LinkConflictError

    voucher_id = a118(period_id)
    source_id = make_source()
    interpret(source_id, "exact")
    IntakeRepository.update_status(source_id, status, actor="stefan")

    error = link_error(source_id, voucher_id)

    assert isinstance(error, LinkConflictError)
    assert error.code == "intake_not_linkable"
    assert f"status={status}" in (error.details or "")


def test_16_failure_half_way_leaves_nothing(period_id, monkeypatch):
    """Testfall 16: the basis insert fails -> no link, no attempt, no
    status change, no basis."""
    from repositories.intake_link_repo import IntakeLinkRepository

    voucher_id = a118(period_id)
    source_id = make_source()
    interpret(source_id, "exact")
    before = link_state()

    def boom(*args, **kwargs):
        raise RuntimeError("basis insert failed")

    monkeypatch.setattr(IntakeLinkRepository, "insert", staticmethod(boom))
    with pytest.raises(RuntimeError, match="basis insert failed"):
        link(source_id, voucher_id)

    assert link_state() == before
    assert source_status(source_id) == "pending"


def test_18_a_link_never_touches_the_books(period_id):
    """Testfall 18: `vouchers` and `voucher_rows` are the same, row by row,
    before and after a link."""
    voucher_id = a118(period_id)
    source_id = make_source()
    interpret(source_id, "exact")
    before = books()

    link(source_id, voucher_id)

    assert books() == before


def test_19_exact_but_the_voucher_got_underlag_in_between(period_id):
    """Testfall 19: `still_open` is counted now; a voucher that got an
    attachment since the interpretation needs a decision."""
    voucher_id = a118(period_id)
    source_id = make_source()
    interpret(source_id, "exact")
    attach(voucher_id)

    error = link_error(source_id, voucher_id)

    assert error.code == "link_requires_decision"
    assert "match_kind=exact" in (error.details or "")


def test_fu3_posting_still_refuses_a_failed_source(period_id):
    """§3.3: the posting's own check is untouched -- `posta_verifikation`
    still refuses a `failed` source with `intake_not_processable`."""
    from services.idempotency import IdempotencyService
    from services.intake import IntakeError
    from services.voucher_posting import VoucherPostingRequest, post_agent_voucher

    source_id = make_source("failed")
    request = VoucherPostingRequest(
        date=date(2026, 3, 15),
        period_id=period_id,
        description="Kortköp",
        rows=[
            {"account": "5410", "debit": 358400, "credit": 0},
            {"account": "2640", "debit": 89600, "credit": 0},
            {"account": "1930", "debit": 0, "credit": 448000},
        ],
        intake_source_ids=[source_id],
    )

    with pytest.raises(IntakeError) as exc:
        post_agent_voucher(request, "agent", IdempotencyService(), None, "test")

    assert exc.value.code == "intake_not_processable"


def test_fu3_service_has_no_sql():
    import re

    source = (REPO_ROOT / "services" / "intake_link.py").read_text(encoding="utf-8")
    assert "db.execute" not in source
    assert not re.search(r"\b(SELECT|INSERT|UPDATE|DELETE)\b", source)


# ---------------------------------------------------------------------------
# FU4 — the decision basis (check 9, D1, §6.4; testfall 4-7, 10, 11)
# ---------------------------------------------------------------------------


def _diff_case(period_id: str, *, status: str = "pending"):
    """A-118, a source in *status* interpreted as `amount_diff` against it,
    and the thread the decision will be in."""
    voucher_id = a118(period_id)
    source_id = make_source(status)
    interpret(source_id, "amount_diff")
    return voucher_id, source_id, make_thread(period_id)


def test_04_amount_diff_with_option_1_links_on_the_decision(period_id):
    """Testfall 4: `basis = decision`, the decision in the basis and in
    `link_reason`."""
    from repositories.intake_link_repo import IntakeLinkRepository

    voucher_id, source_id, thread = _diff_case(period_id)
    decision = make_decision(thread, source_id, answer=1)

    result = link(source_id, voucher_id, decision_id=decision.id, thread_id=thread.id)

    assert (result.basis, result.decision_id, result.replayed) == (
        "decision",
        decision.id,
        False,
    )
    basis = IntakeLinkRepository.get_for_source(source_id)
    assert basis is not None
    assert (basis.basis, basis.decision_id, basis.thread_id) == (
        "decision",
        decision.id,
        thread.id,
    )
    vis = IntakeRepository.get_link_by_source_id(source_id)
    assert vis is not None
    assert vis.link_reason == (
        f"decision={decision.id} interpretation={result.interpretation_id}"
    )
    assert source_status(source_id) == "processed"


def test_05_exit_option_is_declined(period_id):
    """Testfall 5: the answer is the exit ("Det är ett annat köp")."""
    from services.intake_link import LinkConflictError

    voucher_id, source_id, thread = _diff_case(period_id)
    decision = make_decision(thread, source_id, answer=3)
    before = link_state()

    error = link_error(
        source_id, voucher_id, decision_id=decision.id, thread_id=thread.id
    )

    assert isinstance(error, LinkConflictError)
    assert error.code == "decision_declined"
    assert link_state() == before


def test_06_free_text_links(period_id):
    """Testfall 6: free text is let through (§6.4, §13.4)."""
    voucher_id, source_id, thread = _diff_case(period_id)
    decision = make_decision(thread, source_id, answer="Ja, koppla det")

    result = link(source_id, voucher_id, decision_id=decision.id, thread_id=thread.id)

    assert result.basis == "decision"


def test_07_open_superseded_other_source_other_thread(period_id):
    """Testfall 7: the four refusals, in §6.4's order, nothing written."""
    from services.decision_service import DecisionService
    from services.intake_link import (
        LinkConflictError,
        LinkNotFoundError,
        LinkRejectedError,
    )

    voucher_id, source_id, thread = _diff_case(period_id)
    other_thread = make_thread(period_id, view_key="bocker.balans")
    open_decision = make_decision(thread, source_id, answer=None)
    superseded = make_decision(thread, source_id, answer=None)
    DecisionService().supersede(superseded.id)
    about_another = make_decision(thread, make_source(), answer=1)
    elsewhere = make_decision(other_thread, source_id, answer=1)
    before = link_state()

    cases = [
        ("nope", LinkNotFoundError, "decision_not_found"),
        (open_decision.id, LinkConflictError, "decision_still_open"),
        (superseded.id, LinkConflictError, "decision_superseded"),
        (about_another.id, LinkRejectedError, "decision_not_for_source"),
        (elsewhere.id, LinkRejectedError, "decision_not_in_thread"),
    ]
    for decision_id, error_type, code in cases:
        error = link_error(
            source_id, voucher_id, decision_id=decision_id, thread_id=thread.id
        )
        assert isinstance(error, error_type), code
        assert error.code == code
    assert link_state() == before


def test_07_decision_about_a_voucher_is_not_for_the_source(period_id):
    """`source.kind` must be `intake_source`, not only the id."""
    voucher_id, source_id, thread = _diff_case(period_id)
    decision = make_decision(thread, source_id, answer=1, source_kind="voucher")

    error = link_error(
        source_id, voucher_id, decision_id=decision.id, thread_id=thread.id
    )

    assert error.code == "decision_not_for_source"


def test_fu4_without_a_thread_the_decision_is_not_bound_to_one(period_id):
    """`decision_not_in_thread` only when `thread_id` is set: the route
    (§7) links with a decision answered in any thread."""
    voucher_id, source_id, thread = _diff_case(period_id)
    decision = make_decision(thread, source_id, answer=2)

    result = link(source_id, voucher_id, decision_id=decision.id)

    assert result.basis == "decision"


def test_fu4_the_pass_links_on_exact_match_only(period_id):
    """§6.7: from the intake pass (the tool without a thread) only
    `exact_match` applies; a decision id gives `link_requires_decision`."""
    voucher_id, source_id, thread = _diff_case(period_id)
    decision = make_decision(thread, source_id, answer=2)

    error = link_error(
        source_id, voucher_id, decision_id=decision.id, decisions_allowed=False
    )

    assert error.code == "link_requires_decision"


def test_fu4_a_decision_also_links_an_exact_match(period_id):
    """With a decision the basis is the decision, whatever the match."""
    voucher_id = a118(period_id)
    source_id = make_source()
    interpret(source_id, "exact_no_date")
    thread = make_thread(period_id)
    decision = make_decision(thread, source_id, answer=2)

    result = link(source_id, voucher_id, decision_id=decision.id, thread_id=thread.id)

    assert result.basis == "decision"


def test_fu4_replay_with_another_decision_writes_nothing(period_id):
    """§6.5: same voucher, another decision -- a replay; the basis is not
    rewritten."""
    voucher_id, source_id, thread = _diff_case(period_id)
    first = make_decision(thread, source_id, answer=1)
    second = make_decision(thread, source_id, answer=2)
    link(source_id, voucher_id, decision_id=first.id, thread_id=thread.id)
    state = link_state()

    replay = link(source_id, voucher_id, decision_id=second.id, thread_id=thread.id)

    assert replay.replayed is True
    assert replay.decision_id == first.id
    assert link_state() == state


def test_10_expected_only_sie4_voucher_links_with_a_decision(period_id):
    """Testfall 10: a SIE4-imported voucher is never a candidate; after an
    interpretation with `expected_voucher_id` it stands as `expected`, and
    an answered decision links it."""
    imported = posted_purchase(period_id, created_by="sie4_import")
    source_id = make_source()
    result = interpret(source_id, "amount_diff", expected_voucher_id=imported)
    assert imported not in {c["voucher_id"] for c in result["candidates"]}
    assert result["expected"]["voucher_id"] == imported
    thread = make_thread(period_id)
    decision = make_decision(thread, source_id, answer=2)

    linked = link(source_id, imported, decision_id=decision.id, thread_id=thread.id)

    assert (linked.voucher_id, linked.basis) == (imported, "decision")


def test_11_failed_after_the_pass_abstained_links_and_leaves_decisions(
    period_id, client, auth_headers
):
    """Testfall 11: the pass abstained (`failed`), the thread decides, the
    link goes through -- and the synthetic `intake:` decision is gone from
    `GET /decisions`."""
    from services.intake import IntakeService

    voucher_id, source_id, thread = _diff_case(period_id)
    IntakeService().record_failed(
        source_id,
        summary="Matchar A-118 med differens",
        error_detail="A-118: 4 600 kr mot 4 480 kr",
        actor="agent",
    )

    def open_ids():
        resp = client.get("/api/v1/decisions", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        return {d["id"] for d in resp.json()["decisions"]}

    assert f"intake:{source_id}" in open_ids()
    decision = make_decision(thread, source_id, answer=2)

    result = link(source_id, voucher_id, decision_id=decision.id, thread_id=thread.id)

    assert result.basis == "decision"
    assert source_status(source_id) == "processed"
    assert f"intake:{source_id}" not in open_ids()
