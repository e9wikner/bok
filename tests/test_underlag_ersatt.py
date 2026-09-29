"""`underlag-ersatt`: a wrong link can be undone, and the undoing stays.

Flöde 4's panel: "Fel verifikation vald: vägen tillbaka måste vara lika lätt
som vägen fram" and "Ersätta ett felaktigt kopplat underlag ska vara möjligt
och lämna spår" (D10 in SPEC-flode-underlag.md). Migration 034 moves the
guard against a receipt booked twice from `UNIQUE(intake_source_id)` to a
trigger over *current* links, and `voucher_intake_unlinks` records an
unlink without removing the link row.

Built on `tests/test_flode_underlag.py`'s helpers; no LLM.
"""

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from db.database import db
from repositories.intake_repo import IntakeRepository
from repositories.voucher_repo import VoucherRepository
from services.auth import AuthService
from tests import test_flode_underlag as fu
from tests.test_flode_underlag import (
    a118,
    interpret,
    make_decision,
    make_run,
    make_source,
    make_thread,
    posted_purchase,
    table_rows,
    voucher_number,
)

accounts = fu.accounts
client = fu.client
period_id = fu.period_id
auth_headers = fu.auth_headers

MIGRATIONS = Path(__file__).resolve().parent.parent / "db" / "migrations"


@pytest.fixture
def human_headers():
    return {"Authorization": f"Bearer {AuthService().create_jwt('stefan')}"}


@pytest.fixture
def events(monkeypatch):
    """Every event published on the broker, as `(thread_id, event, data)`."""
    from services.thread_stream import get_broker

    seen: list = []
    broker = get_broker()
    original = broker.publish

    def capture(thread_id, event, data):
        seen.append((thread_id, event, data))
        original(thread_id, event, data)

    monkeypatch.setattr(broker, "publish", capture)
    return seen


def _capabilities():
    from services.llm import LLMCapabilities

    return LLMCapabilities(
        cache_breakpoint=True,
        pdf_document_blocks=True,
        refusal_stop_reason=True,
        streaming=True,
    )


def _execute(name: str, arguments: dict, tool_context=None):
    from services.agent_tools import execute_tool

    return execute_tool(
        name,
        arguments,
        actor="agent",
        capabilities=_capabilities(),
        tool_context=tool_context,
    )


def _linked(period_id: str):
    """A-118 with a receipt linked on an exact match: `(voucher, source)`."""
    from services.intake_link import IntakeLinkService

    voucher_id = a118(period_id)
    source_id = make_source()
    interpret(source_id, "exact")
    IntakeLinkService().link(source_id, voucher_id, actor="agent")
    return voucher_id, source_id


def _unlink_options(other_number: str = "A-117"):
    return [
        {
            "title": f"Koppla till {other_number} i stället",
            "rationale": "Kvittot hör till det köpet.",
            "is_exit": False,
        },
        {
            "title": "Koppla bort utan ny koppling",
            "rationale": "Kvittot hör inte till något bokfört köp.",
            "is_exit": False,
        },
        {
            "title": "Låt kopplingen stå",
            "rationale": "Kopplingen var rätt.",
            "is_exit": True,
        },
    ]


def _unlink_decision(thread, source_id: str, *, answer: int = 1):
    """A decision about *source_id* with the three options the instruction
    names (docs/to_agent/03, punkt 10), answered with option *answer*."""
    from repositories.decision_repo import DecisionRepository
    from services.decision_service import DecisionService

    service = DecisionService()
    decision = service.create(
        thread,
        title="Kvittot är kopplat till fel verifikation",
        reason="Kvittot är kopplat till A-118 men gäller ett annat köp.",
        consequence="Ingenting ändras förrän du valt.",
        source={"kind": "intake_source", "id": source_id},
        options=_unlink_options(),
    )
    option = next(o for o in decision.options if o.position == answer)
    service.answer(decision.id, option_id=option.id, actor="stefan")
    answered = DecisionRepository.get(decision.id)
    assert answered is not None
    return answered


def _unlink(source_id, voucher_id, **kwargs):
    from services.intake_link import IntakeLinkService

    kwargs.setdefault("reason", "Kvittot gäller ett annat köp.")
    kwargs.setdefault("actor", "stefan")
    return IntakeLinkService().unlink(source_id, voucher_id, **kwargs)


def _code(excinfo) -> str:
    return excinfo.value.code


# ---------------------------------------------------------------------------
# Migration 034
# ---------------------------------------------------------------------------


def test_migration_034_is_applied_with_its_triggers(test_db):
    conn = test_db.connect()
    assert conn.execute("SELECT 1 FROM schema_version WHERE version = 34").fetchone()
    triggers = {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")
    }
    assert {
        "one_current_link_per_source",
        "unlink_matches_link",
        "prevent_update_voucher_intake_sources",
        "prevent_delete_voucher_intake_sources",
        "prevent_update_intake_link_basis",
        "prevent_delete_intake_link_basis",
        "prevent_update_voucher_intake_unlinks",
        "prevent_delete_voucher_intake_unlinks",
    } <= triggers
    table_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'voucher_intake_sources'"
    ).fetchone()["sql"]
    assert "UNIQUE" not in table_sql
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_migration_034_carries_links_and_bases_over():
    """A database at version 33 with a link and its basis: after 034 the
    link is the same row and the basis names it."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            "CREATE TABLE schema_version (version INTEGER PRIMARY KEY, "
            "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        migrations = sorted(MIGRATIONS.glob("*.sql"))
        for migration in migrations:
            if int(migration.name.split("_")[0]) < 34:
                conn.executescript(migration.read_text())
        conn.executescript("""
            INSERT INTO fiscal_years (id, start_date, end_date)
                VALUES ('fy', '2026-01-01', '2026-12-31');
            INSERT INTO periods (id, fiscal_year_id, year, month, start_date, end_date)
                VALUES ('p', 'fy', 2026, 3, '2026-03-01', '2026-03-31');
            INSERT INTO vouchers (id, series, number, date, period_id,
                                  fiscal_year_id, description, status)
                VALUES ('v', 'A', 1, '2026-03-15', 'p', 'fy', 'Inköp', 'posted');
            INSERT INTO intake_sources (id, original_filename, mime_type,
                                        size_bytes, sha256, stored_path, uploaded_by)
                VALUES ('s', 'kvitto.jpg', 'image/jpeg', 1, 'h', '/tmp/s', 'stefan');
            INSERT INTO intake_interpretations (id, intake_source_id, actor,
                                                total_ore, checks_json, confidence)
                VALUES ('i', 's', 'agent', 100, '[]', 'high');
            INSERT INTO voucher_intake_sources (id, voucher_id, intake_source_id,
                                                linked_by, link_reason)
                VALUES ('l', 'v', 's', 'agent', 'exact_match');
            INSERT INTO intake_link_basis (intake_source_id, voucher_id, basis,
                                           interpretation_id, actor)
                VALUES ('s', 'v', 'exact_match', 'i', 'agent');
            """)

        [m034] = [m for m in migrations if m.name.startswith("034_")]
        conn.executescript(m034.read_text())

        link = conn.execute("SELECT * FROM voucher_intake_sources").fetchone()
        assert (link["id"], link["voucher_id"], link["intake_source_id"]) == (
            "l",
            "v",
            "s",
        )
        basis = conn.execute("SELECT * FROM intake_link_basis").fetchone()
        assert (basis["link_id"], basis["intake_source_id"], basis["basis"]) == (
            "l",
            "s",
            "exact_match",
        )
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        with pytest.raises(sqlite3.IntegrityError, match="already linked"):
            conn.execute(
                "INSERT INTO voucher_intake_sources "
                "(id, voucher_id, intake_source_id, linked_by) "
                "VALUES ('l2', 'v', 's', 'agent')"
            )
    finally:
        conn.close()
        os.remove(path)


def test_one_current_link_per_source_is_kept_by_the_schema(period_id):
    """The old `UNIQUE(intake_source_id)`, for current links: a second link
    is refused until the first is undone."""
    voucher_id, source_id = _linked(period_id)
    other = posted_purchase(period_id, day=16)

    with pytest.raises(sqlite3.IntegrityError, match="already linked"):
        IntakeRepository.create_voucher_link(
            intake_source_id=source_id, voucher_id=other, linked_by="agent"
        )
    db.rollback()

    _unlink(source_id, voucher_id, human=True)
    IntakeRepository.create_voucher_link(
        intake_source_id=source_id, voucher_id=other, linked_by="agent"
    )
    assert IntakeRepository.get_link_by_source_id(source_id).voucher_id == other


def test_links_and_unlinks_are_append_only(period_id):
    voucher_id, source_id = _linked(period_id)
    _unlink(source_id, voucher_id, human=True)
    for table in ("voucher_intake_sources", "voucher_intake_unlinks"):
        before = table_rows(table)
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute(f"UPDATE {table} SET voucher_id = voucher_id")
        db.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute(f"DELETE FROM {table}")
        db.rollback()
        assert table_rows(table) == before


def test_an_unlink_must_name_its_link(period_id):
    voucher_id, source_id = _linked(period_id)
    link = IntakeRepository.get_link_by_source_id(source_id)
    other = posted_purchase(period_id, day=16)

    with pytest.raises(sqlite3.IntegrityError, match="does not match"):
        db.execute(
            "INSERT INTO voucher_intake_unlinks "
            "(link_id, intake_source_id, voucher_id, basis, reason, actor) "
            "VALUES (?, ?, ?, 'human', 'fel', 'stefan')",
            (link.id, source_id, other),
        )
    db.rollback()


def test_the_repositories_offer_no_update_or_delete():
    from repositories.intake_link_repo import IntakeUnlinkRepository

    public = {n for n in vars(IntakeUnlinkRepository) if not n.startswith("_")}
    assert public == {"insert", "get_for_link", "get_by_decision"}


# ---------------------------------------------------------------------------
# The unlink: what it writes and what it changes
# ---------------------------------------------------------------------------


def test_a_logged_in_human_unlinks_through_the_route(
    client, auth_headers, human_headers, period_id
):
    voucher_id, source_id = _linked(period_id)
    link = IntakeRepository.get_link_by_source_id(source_id)
    before = VoucherRepository.count_missing_attachments()

    response = client.post(
        f"/api/v1/intake/{source_id}/unlink",
        headers=human_headers,
        json={"voucher_id": voucher_id, "reason": "Kvittot gäller ett annat köp."},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["basis"], body["replayed"], body["link_id"]) == (
        "human",
        False,
        link.id,
    )
    assert body["voucher_number"] == voucher_number(voucher_id)
    assert body["missing_attachments"] == before + 1
    # The link row stays; the source has no current link and needs attention.
    assert len(table_rows("voucher_intake_sources")) == 1
    [unlink] = db.execute("SELECT * FROM voucher_intake_unlinks").fetchall()
    assert (unlink["actor"], unlink["basis"]) == ("stefan", "human")
    assert IntakeRepository.get_link_by_source_id(source_id) is None
    assert IntakeRepository.get_source(source_id).status.value == "needs_attention"
    assert VoucherRepository.get(voucher_id).missing_attachment is True
    # The decision queue shows the source with the unlink as its reason.
    [card] = [
        d
        for d in client.get("/api/v1/decisions", headers=auth_headers).json()[
            "decisions"
        ]
        if d["id"] == f"intake:{source_id}"
    ]
    assert card["reason"].startswith(
        f"Underlaget kopplades bort från {voucher_number(voucher_id)}"
    )

    context = client.get(
        f"/api/v1/vouchers/{voucher_id}/source-context", headers=auth_headers
    ).json()
    assert context["source_material"] == []
    [trace] = context["unlinked_source_material"]
    assert (trace["id"], trace["unlinked_by"], trace["unlink_reason"]) == (
        source_id,
        "stefan",
        "Kvittot gäller ett annat köp.",
    )

    detail = client.get(
        f"/api/v1/intake/workspace/voucher_source/{source_id}", headers=auth_headers
    )
    assert detail.status_code == 200, detail.text
    [history] = detail.json()["voucher_links"]
    assert (history["voucher_id"], history["unlinked_by"]) == (voucher_id, "stefan")
    assert detail.json()["linked_voucher_ids"] == []


def test_the_api_key_needs_a_decision(client, auth_headers, period_id):
    voucher_id, source_id = _linked(period_id)

    response = client.post(
        f"/api/v1/intake/{source_id}/unlink",
        headers=auth_headers,
        json={"voucher_id": voucher_id, "reason": "Fel köp."},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unlink_requires_decision"
    assert table_rows("voucher_intake_unlinks") == []


def test_the_tool_unlinks_on_a_decision_in_the_thread(period_id, events):
    from services.thread_service import ThreadService  # noqa: F401 -- labels load

    voucher_id, source_id = _linked(period_id)
    thread = make_thread(period_id)
    decision = _unlink_decision(thread, source_id, answer=2)
    run_id = make_run()

    result = _execute(
        "koppla_bort_underlag",
        {
            "source_id": source_id,
            "voucher_id": voucher_id,
            "decision_id": decision.id,
            "reason": "Kvittot gäller ett annat köp.",
        },
        tool_context={"thread": thread, "agent_run_id": run_id},
    )

    assert (result["basis"], result["decision_id"]) == ("decision", decision.id)
    unlink = db.execute("SELECT * FROM voucher_intake_unlinks").fetchone()
    assert (unlink["thread_id"], unlink["agent_run_id"]) == (thread.id, run_id)
    receipts = [
        r
        for r in db.execute(
            "SELECT * FROM thread_posts WHERE thread_id = ? AND type = 'receipt'",
            (thread.id,),
        )
    ]
    assert len(receipts) == 1
    assert "frånkopplat" in receipts[0]["body_json"]
    assert receipts[0]["actor"] == "stefan"
    changed = [d for (_, e, d) in events if e == "view.changed"]
    assert changed and changed[-1]["changed"] == {
        "voucher_id": voucher_id,
        "source_id": source_id,
        "kind": "source_unlinked",
    }


def test_the_tool_cannot_unlink_without_a_thread(period_id):
    from services.intake_link import LinkRejectedError

    voucher_id, source_id = _linked(period_id)
    decision = _unlink_decision(make_thread(period_id), source_id)

    with pytest.raises(LinkRejectedError) as excinfo:
        _execute(
            "koppla_bort_underlag",
            {
                "source_id": source_id,
                "voucher_id": voucher_id,
                "decision_id": decision.id,
                "reason": "Fel köp.",
            },
        )
    assert _code(excinfo) == "unlink_requires_decision"


def test_a_second_unlink_is_a_replay(period_id):
    voucher_id, source_id = _linked(period_id)
    first = _unlink(source_id, voucher_id, human=True)

    second = _unlink(source_id, voucher_id, human=True, reason="Igen.")

    assert second.replayed is True
    assert second.link_id == first.link_id
    assert second.reason == first.reason
    assert len(table_rows("voucher_intake_unlinks")) == 1


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------


def test_nothing_to_unlink(period_id):
    from services.intake_link import LinkConflictError, LinkNotFoundError

    voucher_id = a118(period_id)
    source_id = make_source()
    with pytest.raises(LinkConflictError) as excinfo:
        _unlink(source_id, voucher_id, human=True)
    assert _code(excinfo) == "source_not_linked"

    with pytest.raises(LinkNotFoundError) as excinfo:
        _unlink("nope", voucher_id, human=True)
    assert _code(excinfo) == "source_not_found"
    with pytest.raises(LinkNotFoundError) as excinfo:
        _unlink(source_id, "nope", human=True)
    assert _code(excinfo) == "voucher_not_found"


def test_linked_elsewhere(period_id):
    from services.intake_link import LinkConflictError

    voucher_id, source_id = _linked(period_id)
    other = posted_purchase(period_id, day=16)
    with pytest.raises(LinkConflictError) as excinfo:
        _unlink(source_id, other, human=True)
    assert _code(excinfo) == "source_linked_elsewhere"
    assert voucher_number(voucher_id) in excinfo.value.details


@pytest.mark.parametrize("reason", ["", "   ", "x" * 501])
def test_a_reason_is_required(period_id, reason):
    from services.intake_link import LinkRejectedError

    voucher_id, source_id = _linked(period_id)
    with pytest.raises(LinkRejectedError) as excinfo:
        _unlink(source_id, voucher_id, human=True, reason=reason)
    assert _code(excinfo) == "unlink_reason_required"
    assert table_rows("voucher_intake_unlinks") == []


def test_a_decision_answered_before_the_link_is_no_basis(period_id):
    from services.intake_link import IntakeLinkService, LinkConflictError

    voucher_id = a118(period_id)
    source_id = make_source()
    interpret(source_id, "exact")
    thread = make_thread(period_id)
    early = _unlink_decision(thread, source_id)
    IntakeLinkService().link(source_id, voucher_id, actor="agent")

    with pytest.raises(LinkConflictError) as excinfo:
        _unlink(source_id, voucher_id, decision_id=early.id, thread_id=thread.id)
    assert _code(excinfo) == "decision_predates_link"


def test_the_links_own_decision_is_no_basis(period_id):
    from services.intake_link import IntakeLinkService, LinkConflictError

    voucher_id = a118(period_id)
    source_id = make_source()
    interpret(source_id, "amount_diff")
    thread = make_thread(period_id)
    decision = make_decision(thread, source_id, answer=2)
    IntakeLinkService().link(
        source_id,
        voucher_id,
        decision_id=decision.id,
        actor="agent",
        thread_id=thread.id,
    )

    with pytest.raises(LinkConflictError) as excinfo:
        _unlink(source_id, voucher_id, decision_id=decision.id, thread_id=thread.id)
    assert _code(excinfo) == "decision_already_used"


def test_the_way_out_is_no_basis(period_id):
    from services.intake_link import LinkConflictError

    voucher_id, source_id = _linked(period_id)
    thread = make_thread(period_id)
    decision = _unlink_decision(thread, source_id, answer=3)

    with pytest.raises(LinkConflictError) as excinfo:
        _unlink(source_id, voucher_id, decision_id=decision.id, thread_id=thread.id)
    assert _code(excinfo) == "decision_declined"


def test_a_decision_about_another_source_is_no_basis(period_id):
    from services.intake_link import LinkRejectedError

    voucher_id, source_id = _linked(period_id)
    thread = make_thread(period_id)
    decision = _unlink_decision(thread, make_source())

    with pytest.raises(LinkRejectedError) as excinfo:
        _unlink(source_id, voucher_id, decision_id=decision.id, thread_id=thread.id)
    assert _code(excinfo) == "decision_not_for_source"


def test_a_decision_undoes_one_link(period_id):
    """Used for an unlink, the decision cannot undo the next link too."""
    from services.intake_link import IntakeLinkService, LinkConflictError

    voucher_id, source_id = _linked(period_id)
    thread = make_thread(period_id)
    decision = _unlink_decision(thread, source_id)
    _unlink(source_id, voucher_id, decision_id=decision.id, thread_id=thread.id)
    other = posted_purchase(period_id, day=16)
    interpret(source_id, "exact", expected_voucher_id=other)
    IntakeLinkService().link(
        source_id, other, decision_id=decision.id, actor="agent", thread_id=thread.id
    )

    with pytest.raises(LinkConflictError) as excinfo:
        _unlink(source_id, other, decision_id=decision.id, thread_id=thread.id)
    assert _code(excinfo) == "decision_already_used"


# ---------------------------------------------------------------------------
# The way forward again: a new link
# ---------------------------------------------------------------------------


def test_replace_moves_the_underlag_to_the_right_voucher(period_id):
    """The panel's case: one decision, unlink from A-118, link to the
    voucher the user named. Both links stand in the table; one is current."""
    from repositories.intake_link_repo import IntakeLinkRepository
    from services.intake_link import IntakeLinkService

    voucher_id, source_id = _linked(period_id)
    right = posted_purchase(period_id, day=14)
    thread = make_thread(period_id)
    decision = _unlink_decision(thread, source_id)

    _unlink(source_id, voucher_id, decision_id=decision.id, thread_id=thread.id)
    interpret(source_id, "exact", expected_voucher_id=right)
    result = IntakeLinkService().link(
        source_id, right, decision_id=decision.id, actor="agent", thread_id=thread.id
    )

    assert result.basis == "decision"
    assert IntakeRepository.get_link_by_source_id(source_id).voucher_id == right
    assert IntakeLinkRepository.get_for_source(source_id).voucher_id == right
    history = IntakeRepository.list_links_for_source(source_id, include_unlinked=True)
    assert [(link.voucher_id, link.is_current) for link in history] == [
        (voucher_id, False),
        (right, True),
    ]
    assert VoucherRepository.get(voucher_id).missing_attachment is True
    assert VoucherRepository.get(right).missing_attachment is False
    assert IntakeRepository.get_source(source_id).status.value == "processed"


def test_an_exact_match_does_not_put_an_unlinked_underlag_back(period_id):
    from services.intake_link import IntakeLinkService, LinkRejectedError

    voucher_id, source_id = _linked(period_id)
    _unlink(source_id, voucher_id, human=True)
    interpret(source_id, "exact")

    with pytest.raises(LinkRejectedError) as excinfo:
        IntakeLinkService().link(source_id, voucher_id, actor="agent")
    assert _code(excinfo) == "link_requires_decision"
    assert "previously_unlinked" in excinfo.value.details


def test_the_links_old_decision_does_not_put_it_back(period_id):
    from services.intake_link import IntakeLinkService, LinkConflictError

    voucher_id = a118(period_id)
    source_id = make_source()
    interpret(source_id, "amount_diff")
    thread = make_thread(period_id)
    decision = make_decision(thread, source_id, answer=2)
    IntakeLinkService().link(
        source_id,
        voucher_id,
        decision_id=decision.id,
        actor="agent",
        thread_id=thread.id,
    )
    _unlink(source_id, voucher_id, human=True)

    with pytest.raises(LinkConflictError) as excinfo:
        IntakeLinkService().link(
            source_id,
            voucher_id,
            decision_id=decision.id,
            actor="agent",
            thread_id=thread.id,
        )
    assert _code(excinfo) == "decision_already_used"


def test_the_posting_stop_lets_an_unlinked_underlag_through(period_id):
    """§8's stop names the matched voucher; once someone said the underlag
    does not belong there, the match is no reason to stop."""
    from services.intake_link import (
        IntakeLinkService,
        SourceMatchesPostedVoucherError,
    )

    voucher_id = a118(period_id)
    source_id = make_source()
    interpret(source_id, "exact")
    with pytest.raises(SourceMatchesPostedVoucherError):
        IntakeLinkService.ensure_not_matching_posted([source_id])

    IntakeLinkService().link(source_id, voucher_id, actor="agent")
    _unlink(source_id, voucher_id, human=True)
    interpret(source_id, "exact")

    IntakeLinkService.ensure_not_matching_posted([source_id])


def test_a_reference_through_the_link_is_named_and_stands(period_id):
    """D2: A-121 was booked on the receipt through A-118. The unlink names
    it; its reference -- and so its underlag -- stands."""
    from domain.intake_link import VoucherSourceReference
    from repositories.intake_link_repo import VoucherSourceReferenceRepository
    from services.intake_link import IntakeLinkService

    voucher_id = a118(period_id)
    source_id = make_source()
    interpret(source_id, "amount_diff")
    thread = make_thread(period_id)
    decision = make_decision(thread, source_id, answer=1)
    IntakeLinkService().link(
        source_id,
        voucher_id,
        decision_id=decision.id,
        actor="agent",
        thread_id=thread.id,
    )
    difference = posted_purchase(period_id, total=12000, vat=0, day=16)
    VoucherSourceReferenceRepository.insert(
        VoucherSourceReference(
            voucher_id=difference,
            intake_source_id=source_id,
            via_voucher_id=voucher_id,
            decision_id=decision.id,
        )
    )

    result = _unlink(source_id, voucher_id, human=True)

    assert result.orphaned_references == [voucher_number(difference)]
    assert VoucherRepository.get(difference).missing_attachment is False


def test_no_voucher_is_touched(period_id):
    voucher_id, source_id = _linked(period_id)
    vouchers = table_rows("vouchers")
    rows = table_rows("voucher_rows")

    _unlink(source_id, voucher_id, human=True)

    assert table_rows("vouchers") == vouchers
    assert table_rows("voucher_rows") == rows


def test_the_tool_is_last_and_writes_no_voucher():
    from services.agent_tools import AGENT_TOOL_DEFINITIONS, KopplaBortUnderlagArgs

    last = AGENT_TOOL_DEFINITIONS[-1]
    assert last["name"] == "koppla_bort_underlag"
    assert last["input_schema"] == KopplaBortUnderlagArgs.model_json_schema()
    assert "Skapar ingen verifikation och ändrar ingen." in last["description"]
    assert "huvudbok" not in last["description"].lower()
