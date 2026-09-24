"""Tests for the `flode-verifikationer` module
(docs/redesign/SPEC-flode-verifikationer.md).

Grows across tasks F5-F12 of `tasks/flode-verifikationer/todo.md`; each task
gets its own section. Numbering (F1-F3) lives in `tests/test_numrering.py`.

Per the spec no LLM is ever called from a test.
"""

import hashlib
import json
import re
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from db.database import db
from domain.models import ThreadDraft
from domain.types import VoucherStatus
from domain.validation import ValidationError
from repositories.account_repo import AccountRepository
from repositories.intake_repo import IntakeRepository
from repositories.period_repo import PeriodRepository
from repositories.thread_draft_repo import (
    ThreadDraftRepository,
    ThreadDraftTransitionError,
)
from repositories.thread_repo import ThreadRepository
from repositories.voucher_repo import VoucherRepository
from services.agent_tools import (
    AGENT_TOOL_DEFINITIONS,
    ForeslaVerifikationArgs,
    ProposalSequence,
    _run_foresla_verifikation,
    derive_thread_posting_idempotency_key,
    derive_thread_proposal_idempotency_key,
    execute_tool,
)
from services.decision_service import DecisionService
from services.ledger import LedgerService
from services.llm import LLMCapabilities

pytestmark = pytest.mark.usefixtures("test_db")


# --- helpers ----------------------------------------------------------------


def _thread(view_key: str = "bocker.verifikationer", year: int = 2026):
    """A real thread — `thread_drafts.thread_id` is a foreign key."""
    fy = PeriodRepository.create_fiscal_year(
        start_date=date(year, 1, 1), end_date=date(year, 12, 31)
    )
    return ThreadRepository.get_or_create(
        view_key=view_key, fiscal_year_id=fy.id, model="opencode/claude-opus-5"
    )


def _post(thread_id: str, post_type: str = "draft"):
    """A real post — `thread_drafts.post_id` is a foreign key."""
    return ThreadRepository.add_post(
        thread_id=thread_id,
        post_type=post_type,
        actor="agent",
        body={"title": "Kortköp Elektronikhuset"},
    )


def _draft(thread, **kwargs) -> ThreadDraft:
    """One `pending` row. `voucher_id` is any string: there is deliberately
    no foreign key to `vouchers` (migration 028)."""
    post = _post(thread.id)
    return ThreadDraftRepository.create(
        voucher_id=kwargs.pop("voucher_id", str(uuid.uuid4())),
        thread_id=thread.id,
        post_id=post.id,
        view_key=thread.view_key,
        **kwargs,
    )


# --- F5: thread_drafts and its repository -------------------------------------


def test_create_and_get_round_trip():
    thread = _thread()
    post = _post(thread.id)
    voucher_id = str(uuid.uuid4())
    created = ThreadDraftRepository.create(
        voucher_id=voucher_id,
        thread_id=thread.id,
        post_id=post.id,
        view_key=thread.view_key,
        correction_of="orig-1",
    )
    assert created.status == "pending"

    fetched = ThreadDraftRepository.get(voucher_id)
    assert fetched is not None
    assert fetched.voucher_id == voucher_id
    assert fetched.thread_id == thread.id
    assert fetched.post_id == post.id
    assert fetched.view_key == "bocker.verifikationer"
    assert fetched.status == "pending"
    assert fetched.correction_of == "orig-1"
    assert fetched.decision_id is None
    assert fetched.correction_note_id is None
    assert fetched.replaced_by is None
    assert fetched.posted_at is None
    assert fetched.receipt_post_id is None
    assert fetched.last_error_code is None
    assert isinstance(fetched.created_at, datetime)

    assert ThreadDraftRepository.get_by_post(post.id) == fetched
    assert ThreadDraftRepository.get("nope") is None
    assert ThreadDraftRepository.get_by_post("nope") is None


def test_create_without_commit_joins_the_callers_transaction():
    thread = _thread()
    draft = _draft(thread, _commit=False)
    db.rollback()
    assert ThreadDraftRepository.get(draft.voucher_id) is None


def test_post_id_is_unique():
    thread = _thread()
    draft = _draft(thread)
    with pytest.raises(sqlite3.IntegrityError):
        ThreadDraftRepository.create(
            voucher_id=str(uuid.uuid4()),
            thread_id=thread.id,
            post_id=draft.post_id,
            view_key=thread.view_key,
        )
    db.rollback()


def test_list_filters_on_view_key_and_status_with_total():
    thread = _thread()
    other = _thread(view_key="bocker.huvudbok", year=2025)
    a = _draft(thread)
    b = _draft(thread)
    c = _draft(thread)
    _draft(other)
    ThreadDraftRepository.mark_posted(b.voucher_id, datetime.now())

    drafts, total = ThreadDraftRepository.list(view_key=thread.view_key)
    assert total == 3
    assert [d.voucher_id for d in drafts] == [a.voucher_id, b.voucher_id, c.voucher_id]

    pending, total = ThreadDraftRepository.list(
        view_key=thread.view_key, status="pending"
    )
    assert total == 2
    assert {d.voucher_id for d in pending} == {a.voucher_id, c.voucher_id}

    everything, total = ThreadDraftRepository.list(
        view_key=thread.view_key, status="all"
    )
    assert total == 3 and len(everything) == 3

    limited, total = ThreadDraftRepository.list(view_key=thread.view_key, limit=1)
    assert total == 3
    assert [d.voucher_id for d in limited] == [a.voucher_id]

    none, total = ThreadDraftRepository.list(view_key="bocker.okand")
    assert none == [] and total == 0


def test_list_rejects_an_unknown_status():
    with pytest.raises(ValueError):
        ThreadDraftRepository.list(view_key="bocker.verifikationer", status="bogus")


def test_mark_posted():
    thread = _thread()
    draft = _draft(thread)
    posted_at = datetime(2026, 6, 30, 9, 14)
    result = ThreadDraftRepository.mark_posted(draft.voucher_id, posted_at)
    assert result.status == "posted"
    assert result.posted_at == posted_at
    assert ThreadDraftRepository.get(draft.voucher_id) == result


def test_mark_superseded():
    thread = _thread()
    old = _draft(thread)
    new = _draft(thread)
    result = ThreadDraftRepository.mark_superseded(old.voucher_id, new.voucher_id)
    assert result.status == "superseded"
    assert result.replaced_by == new.voucher_id
    assert result.posted_at is None


def test_mark_posted_without_commit_rolls_back():
    thread = _thread()
    draft = _draft(thread)
    ThreadDraftRepository.mark_posted(draft.voucher_id, datetime.now(), _commit=False)
    db.rollback()
    fetched = ThreadDraftRepository.get(draft.voucher_id)
    assert fetched is not None and fetched.status == "pending"


@pytest.mark.parametrize(
    "first, second",
    [
        ("posted", "posted"),
        ("posted", "superseded"),
        ("superseded", "posted"),
        ("superseded", "superseded"),
    ],
)
def test_transition_out_of_a_final_state_is_rejected(first, second):
    """§6.2: only pending -> posted and pending -> superseded. A posted or
    superseded draft never goes anywhere, and the row is left untouched."""
    thread = _thread()
    draft = _draft(thread)
    other = _draft(thread)

    def move(target: str):
        if target == "posted":
            return ThreadDraftRepository.mark_posted(draft.voucher_id, datetime.now())
        return ThreadDraftRepository.mark_superseded(draft.voucher_id, other.voucher_id)

    before = move(first)
    with pytest.raises(ThreadDraftTransitionError) as excinfo:
        move(second)
    assert excinfo.value.voucher_id == draft.voucher_id
    assert excinfo.value.current_status == first
    assert excinfo.value.target_status == second
    assert ThreadDraftRepository.get(draft.voucher_id) == before


def test_transition_of_a_missing_draft_is_rejected():
    with pytest.raises(ThreadDraftTransitionError) as excinfo:
        ThreadDraftRepository.mark_posted("missing", datetime.now())
    assert excinfo.value.current_status is None


def test_set_error_keeps_the_draft_pending():
    """§6.2: a failed attempt changes no status."""
    thread = _thread()
    draft = _draft(thread)
    error_post = _post(thread.id, post_type="error")
    result = ThreadDraftRepository.set_error(
        draft.voucher_id, "period_locked", error_post.id
    )
    assert result.status == "pending"
    assert result.last_error_code == "period_locked"
    assert result.last_error_post_id == error_post.id


def test_set_error_on_a_posted_draft_is_rejected():
    thread = _thread()
    draft = _draft(thread)
    ThreadDraftRepository.mark_posted(draft.voucher_id, datetime.now())
    with pytest.raises(ThreadDraftTransitionError):
        ThreadDraftRepository.set_error(draft.voucher_id, "period_locked", None)


def test_set_receipt_only_once_and_only_when_posted():
    thread = _thread()
    draft = _draft(thread)
    receipt = _post(thread.id, post_type="receipt")

    with pytest.raises(ThreadDraftTransitionError):
        ThreadDraftRepository.set_receipt(draft.voucher_id, receipt.id)

    ThreadDraftRepository.mark_posted(draft.voucher_id, datetime.now())
    result = ThreadDraftRepository.set_receipt(draft.voucher_id, receipt.id)
    assert result.receipt_post_id == receipt.id

    second = _post(thread.id, post_type="receipt")
    with pytest.raises(ThreadDraftTransitionError):
        ThreadDraftRepository.set_receipt(draft.voucher_id, second.id)
    assert ThreadDraftRepository.get(draft.voucher_id).receipt_post_id == receipt.id


def test_schema_rejects_posted_without_posted_at():
    thread = _thread()
    draft = _draft(thread)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "UPDATE thread_drafts SET status = 'posted' WHERE voucher_id = ?",
            (draft.voucher_id,),
        )
    db.rollback()


def test_schema_rejects_an_unknown_status():
    thread = _thread()
    draft = _draft(thread)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "UPDATE thread_drafts SET status = 'answered' WHERE voucher_id = ?",
            (draft.voucher_id,),
        )
    db.rollback()


def test_rows_follow_the_thread_on_delete():
    thread = _thread()
    other = _thread(view_key="bocker.huvudbok", year=2025)
    draft = _draft(thread)
    kept = _draft(other)
    db.execute("DELETE FROM threads WHERE id = ?", (thread.id,))
    db.commit()
    assert ThreadDraftRepository.get(draft.voucher_id) is None
    assert ThreadDraftRepository.get(kept.voucher_id) is not None


def test_pending_for_correction_of_finds_pending_in_any_thread():
    thread = _thread()
    other = _thread(view_key="bocker.huvudbok", year=2025)
    assert ThreadDraftRepository.pending_for_correction_of("orig-1") is None

    plain = _draft(thread)  # no correction_of
    first = _draft(other, correction_of="orig-1")
    found = ThreadDraftRepository.pending_for_correction_of("orig-1")
    assert found is not None and found.voucher_id == first.voucher_id
    assert plain.correction_of is None

    replacement = _draft(thread, correction_of="orig-1")
    ThreadDraftRepository.mark_superseded(first.voucher_id, replacement.voucher_id)
    found = ThreadDraftRepository.pending_for_correction_of("orig-1")
    assert found is not None and found.voucher_id == replacement.voucher_id

    ThreadDraftRepository.mark_posted(
        replacement.voucher_id, datetime.now() + timedelta(seconds=1)
    )
    assert ThreadDraftRepository.pending_for_correction_of("orig-1") is None
    assert ThreadDraftRepository.pending_for_correction_of("orig-2") is None


# --- F6: foresla_verifikation, vanligt förslag (testfall 14-21) --------------

_FIXTURE_FILE = (
    Path(__file__).resolve().parent.parent
    / "frontend-v3"
    / "lib"
    / "chattyta"
    / "__fixtures__"
    / "inlagg.ts"
)

_ACCOUNTS = (
    ("6110", "Kontorsmateriel", "expense"),
    ("2640", "Ingående moms", "vat_in"),
    ("1930", "Företagskonto", "asset"),
)

_ROWS = [
    {"account": "6110", "debit": 71680},
    {"account": "2640", "debit": 17920},
    {"account": "1930", "credit": 89600},
]


def _fixture_draft_keys() -> tuple[set, set]:
    """The keys of `FIXTUR_DRAFT.body` and of its first row, read out of the
    client's own fixture -- not copied from it -- so that producer and
    consumer cannot drift apart (todo F6)."""
    source = _FIXTURE_FILE.read_text(encoding="utf-8")
    start = source.index("export const FIXTUR_DRAFT")
    block = source[start : source.index("};", start)]
    body = block[block.index("body: {") :]
    body_keys = set(re.findall(r"^    (\w+):", body, flags=re.MULTILINE))
    first_row = re.search(r"\{ (account:[^}]*)\}", body)
    assert first_row is not None
    row_keys = set(re.findall(r"(\w+):", first_row.group(1)))
    return body_keys, row_keys


def _books(month: int = 9):
    """A thread in 2026, September open, the three accounts of the design's
    example, and the human's post that triggers the turn."""
    thread = _thread()
    period = PeriodRepository.create_period(
        fiscal_year_id=thread.fiscal_year_id,
        year=2026,
        month=month,
        start_date=date(2026, month, 1),
        end_date=date(2026, month, 30),
    )
    for code, name, account_type in _ACCOUNTS:
        if AccountRepository.get(code) is None:
            AccountRepository.create(code, name, account_type)
    trigger = ThreadRepository.add_post(
        thread_id=thread.id,
        post_type="user_text",
        actor="api",
        body={"text": "Bokför kvittot från Clas Ohlson."},
    )
    return thread, period, trigger


def _args(period, **overrides) -> ForeslaVerifikationArgs:
    fields = {
        "description": "Kontorsmaterial, Clas Ohlson",
        "rows": _ROWS,
        "date": "2026-09-18",
        "period_id": period.id,
        "footnote": "Underlag: kvitto 2026-09-18 · kompletteringsflagga sätts inte",
    }
    fields.update(overrides)
    return ForeslaVerifikationArgs.model_validate(fields)


def _capabilities() -> LLMCapabilities:
    return LLMCapabilities(
        cache_breakpoint=True,
        pdf_document_blocks=True,
        refusal_stop_reason=True,
        streaming=True,
    )


def _propose(thread, args, proposals=None):
    """One `foresla_verifikation` call through its handler, the way
    `execute_tool` would make it inside a thread turn."""
    return _run_foresla_verifikation(
        args,
        actor="agent",
        capabilities=_capabilities(),
        tool_context=(
            None if thread is None else {"thread": thread, "proposals": proposals}
        ),
    )


def _count(table: str) -> int:
    return db.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]


def _draft_posts(thread):
    return [p for p in ThreadRepository.list_posts(thread.id) if p.type == "draft"]


def test_case_14_proposal_writes_draft_row_and_post():
    thread, period, trigger = _books()
    proposals = ProposalSequence(thread.id, trigger.id)

    result = _propose(thread, _args(period), proposals)

    voucher = VoucherRepository.get(result["draft_id"])
    assert voucher is not None
    assert voucher.status == VoucherStatus.DRAFT
    assert voucher.number is None
    assert voucher.series.value == "A"
    assert voucher.date == date(2026, 9, 18)
    assert [(r.account_code, r.debit, r.credit) for r in voucher.rows] == [
        ("6110", 71680, 0),
        ("2640", 17920, 0),
        ("1930", 0, 89600),
    ]

    [post] = _draft_posts(thread)
    assert post.actor == "agent"
    row = ThreadDraftRepository.get(voucher.id)
    assert row is not None
    assert row.status == "pending"
    assert row.post_id == post.id
    assert row.thread_id == thread.id
    assert row.view_key == thread.view_key
    assert row.decision_id is None
    assert row.correction_of is None
    assert result["post_id"] == post.id
    assert result["status"] == "pending"

    fixture_body_keys, fixture_row_keys = _fixture_draft_keys()
    assert set(post.body) == fixture_body_keys
    for body_row in post.body["rows"]:
        assert set(body_row) == fixture_row_keys
    assert post.body["kind"] == "voucher"
    assert post.body["draft_id"] == voucher.id
    assert post.body["decision_id"] is None
    assert post.body["rows"] == [
        {
            "account": "6110",
            "name": "Kontorsmateriel",
            "debit_ore": 71680,
            "credit_ore": None,
        },
        {
            "account": "2640",
            "name": "Ingående moms",
            "debit_ore": 17920,
            "credit_ore": None,
        },
        {
            "account": "1930",
            "name": "Företagskonto",
            "debit_ore": None,
            "credit_ore": 89600,
        },
    ]


def test_case_14_proposal_keeps_its_traceability_until_posting():
    thread, period, trigger = _books()
    source = IntakeRepository.create_source(
        source_id="kvitto-clas-ohlson",
        original_filename="kvitto-clas-ohlson.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        sha256="sha-clas-ohlson",
        stored_path="/dev/null/kvitto-clas-ohlson",
        uploaded_by="test",
    )

    result = _propose(
        thread,
        _args(period, intake_source_ids=[source.id]),
        ProposalSequence(thread.id, trigger.id),
    )

    row = ThreadDraftRepository.get(result["draft_id"])
    assert row.intake_source_ids == [source.id]
    assert row.bank_input_ids == []
    assert row.bank_transaction_ids == []
    # Not linked yet: a link marks the source processed, and only a posted
    # voucher may be linked.
    assert IntakeRepository.get_link_by_source_id(source.id) is None


def test_case_15_same_turn_run_twice_gives_the_same_draft():
    thread, period, trigger = _books()

    first = _propose(thread, _args(period), ProposalSequence(thread.id, trigger.id))
    # The turn is run again from the start (a crash after the commit): a
    # fresh sequence for the same trigger post, the same call.
    again = _propose(thread, _args(period), ProposalSequence(thread.id, trigger.id))

    assert again["draft_id"] == first["draft_id"]
    assert again["post_id"] == first["post_id"]
    assert again["idempotent_replay"] is True
    assert _count("vouchers") == 1
    assert _count("thread_drafts") == 1
    assert len(_draft_posts(thread)) == 1


def test_case_16_two_proposals_in_one_turn_give_two_drafts():
    thread, period, trigger = _books()
    proposals = ProposalSequence(thread.id, trigger.id)

    first = _propose(thread, _args(period), proposals)
    second = _propose(thread, _args(period), proposals)

    assert first["draft_id"] != second["draft_id"]
    assert _count("vouchers") == 2
    assert _count("thread_drafts") == 2
    assert len(_draft_posts(thread)) == 2
    keys = {
        derive_thread_proposal_idempotency_key(thread.id, trigger.id, n) for n in (1, 2)
    }
    assert len(keys) == 2
    # And a proposal never collides with a posting from the same post.
    assert derive_thread_posting_idempotency_key(thread.id, trigger.id) not in keys


def _open_decision(thread):
    return DecisionService().create(
        thread,
        title="Swish 4 500 kr utan referens",
        reason="Avsändaren är en privatperson.",
        consequence="Ingenting är bokfört.",
    )


def _answered_decision(thread):
    decision = _open_decision(thread)
    DecisionService().answer(decision.id, free_text="Övrig intäkt.", actor="api")
    return decision


def _failing_case(name, thread, period):
    """Arguments and expected code for each row of §5.3's table."""
    if name == "without_thread":
        return None, _args(period), "draft_requires_thread"
    if name == "unbalanced":
        rows = [{"account": "6110", "debit": 100}, {"account": "1930", "credit": 99}]
        return thread, _args(period, rows=rows), "balance_error"
    if name == "unknown_account":
        rows = [{"account": "9999", "debit": 100}, {"account": "1930", "credit": 100}]
        return thread, _args(period, rows=rows), "account_not_found"
    if name == "locked_period":
        PeriodRepository.lock_period(period.id, actor="stefan")
        return thread, _args(period), "period_locked"
    if name == "decision_not_found":
        return thread, _args(period, decision_id="nope"), "decision_not_found"
    if name == "decision_not_in_thread":
        other = ThreadRepository.get_or_create(
            view_key="bocker.huvudbok",
            fiscal_year_id=thread.fiscal_year_id,
            model="opencode/claude-opus-5",
        )
        decision = _answered_decision(other)
        return thread, _args(period, decision_id=decision.id), "decision_not_in_thread"
    if name == "decision_superseded":
        decision = _open_decision(thread)
        DecisionService().supersede(decision.id)
        return thread, _args(period, decision_id=decision.id), "decision_superseded"
    if name == "decision_still_open":
        decision = _open_decision(thread)
        return thread, _args(period, decision_id=decision.id), "decision_still_open"
    if name == "replaces_unknown":
        return thread, _args(period, replaces_draft_id="nope"), "draft_not_replaceable"
    if name == "without_date":
        return thread, _args(period, date=None), "draft_requires_date_and_period"
    if name == "correction_of":
        # F11: the correction branch runs §7.4's checks; an unknown original
        # is the first of them to fail.
        args = _args(period, correction_of="v-118", date=None, period_id=None)
        return thread, args, "voucher_not_found"
    raise AssertionError(name)


@pytest.mark.parametrize(
    "name",
    [
        "without_thread",
        "unbalanced",
        "unknown_account",
        "locked_period",
        "decision_not_found",
        "decision_not_in_thread",
        "decision_superseded",
        "decision_still_open",
        "replaces_unknown",
        "without_date",
        "correction_of",
    ],
)
def test_case_17_failed_checks_write_nothing(name):
    thread, period, trigger = _books()
    context_thread, args, code = _failing_case(name, thread, period)
    posts_before = _count("thread_posts")
    proposals = ProposalSequence(thread.id, trigger.id)

    with pytest.raises(ValidationError) as excinfo:
        _propose(context_thread, args, proposals)

    assert excinfo.value.code == code
    assert _count("vouchers") == 0
    assert _count("thread_drafts") == 0
    assert _count("thread_posts") == posts_before
    if name == "locked_period":
        assert "stefan" in (excinfo.value.details or "")
    if name != "without_thread":
        # A failed call claims no key: the same slot is free for the
        # corrected call that follows.
        assert proposals.n == 1


def test_case_17_replaces_a_draft_from_another_thread_is_refused():
    thread, period, trigger = _books()
    other = ThreadRepository.get_or_create(
        view_key="bocker.huvudbok",
        fiscal_year_id=thread.fiscal_year_id,
        model="opencode/claude-opus-5",
    )
    other_trigger = ThreadRepository.add_post(
        thread_id=other.id, post_type="user_text", actor="api", body={"text": "x"}
    )
    elsewhere = _propose(
        other, _args(period), ProposalSequence(other.id, other_trigger.id)
    )

    with pytest.raises(ValidationError) as excinfo:
        _propose(
            thread,
            _args(period, replaces_draft_id=elsewhere["draft_id"]),
            ProposalSequence(thread.id, trigger.id),
        )
    assert excinfo.value.code == "draft_not_replaceable"
    assert ThreadDraftRepository.get(elsewhere["draft_id"]).status == "pending"


def test_case_17_an_answered_decision_is_carried_on_the_draft():
    thread, period, trigger = _books()
    decision = _answered_decision(thread)

    result = _propose(
        thread,
        _args(period, decision_id=decision.id),
        ProposalSequence(thread.id, trigger.id),
    )

    assert ThreadDraftRepository.get(result["draft_id"]).decision_id == decision.id
    [post] = _draft_posts(thread)
    assert post.body["decision_id"] == decision.id


def test_case_18_failure_halfway_leaves_nothing(monkeypatch):
    thread, period, trigger = _books()
    posts_before = _count("thread_posts")

    def _boom(**kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(ThreadDraftRepository, "create", staticmethod(_boom))
    proposals = ProposalSequence(thread.id, trigger.id)
    with pytest.raises(RuntimeError):
        _propose(thread, _args(period), proposals)

    assert _count("vouchers") == 0
    assert _count("voucher_rows") == 0
    assert _count("thread_drafts") == 0
    assert _count("thread_posts") == posts_before
    monkeypatch.undo()

    # The key was released, not left in flight: the retry goes through.
    result = _propose(thread, _args(period), proposals)
    assert "idempotent_replay" not in result
    assert _count("thread_drafts") == 1


def test_case_18_failure_while_replacing_keeps_the_old_draft(monkeypatch):
    thread, period, trigger = _books()
    proposals = ProposalSequence(thread.id, trigger.id)
    old = _propose(thread, _args(period), proposals)

    def _boom(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(VoucherRepository, "delete_draft", staticmethod(_boom))
    with pytest.raises(RuntimeError):
        _propose(thread, _args(period, replaces_draft_id=old["draft_id"]), proposals)

    assert _count("vouchers") == 1
    assert VoucherRepository.get(old["draft_id"]) is not None
    assert ThreadDraftRepository.get(old["draft_id"]).status == "pending"
    assert len(_draft_posts(thread)) == 1


def test_case_19_replaces_draft_id_supersedes_and_deletes_the_old_draft():
    thread, period, trigger = _books()
    proposals = ProposalSequence(thread.id, trigger.id)
    old = _propose(thread, _args(period), proposals)

    new = _propose(
        thread,
        _args(
            period,
            description="Kontorsmaterial, Clas Ohlson (rättad)",
            replaces_draft_id=old["draft_id"],
        ),
        proposals,
    )

    assert VoucherRepository.get(old["draft_id"]) is None
    old_row = ThreadDraftRepository.get(old["draft_id"])
    assert old_row.status == "superseded"
    assert old_row.replaced_by == new["draft_id"]
    assert ThreadDraftRepository.get(new["draft_id"]).status == "pending"
    assert new["replaced_draft_id"] == old["draft_id"]
    # Both cards stay in the thread: a post is never rewritten.
    assert [p.id for p in _draft_posts(thread)] == [old["post_id"], new["post_id"]]

    # No gap: drafts have no number, so the replacement is A-1 once posted.
    posted = LedgerService().post_voucher(new["draft_id"], actor="stefan")
    assert posted.number == 1


def test_case_20_description_becomes_the_voucher_and_footnote_stays_in_the_post():
    thread, period, trigger = _books()
    args = _args(period)

    result = _propose(thread, args, ProposalSequence(thread.id, trigger.id))

    voucher = VoucherRepository.get(result["draft_id"])
    assert voucher.description == "Kontorsmaterial, Clas Ohlson"
    [post] = _draft_posts(thread)
    assert post.body["title"] == "Kontorsmaterial, Clas Ohlson"
    assert post.body["footnote"] == args.footnote
    assert args.footnote not in (voucher.description or "")
    assert all(args.footnote != (row.description or "") for row in voucher.rows)


def test_case_21_meta_has_no_number_and_consequence_names_series_and_period():
    thread, period, trigger = _books()

    _propose(thread, _args(period), ProposalSequence(thread.id, trigger.id))

    [post] = _draft_posts(thread)
    assert post.body["meta"] == "Förslag · A · 2026-09-18"
    assert post.body["consequence"] == (
        "Låses vid postning · får nästa nummer i A-serien · "
        "period september 2026 öppen"
    )


def test_thread_turn_hands_the_proposal_sequence_to_the_tools(monkeypatch):
    """§5.5's `{post_id}` is the trigger post's: `run_thread_session` puts a
    fresh `ProposalSequence` for it in the opaque `tool_context`."""
    import services.thread_session as thread_session

    thread, period, trigger = _books()
    captured = {}

    def _fake_loop(client, **kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(thread_session, "run_tool_loop", _fake_loop)
    thread_session.run_thread_session(
        client=None,
        thread=thread,
        trigger_post=trigger,
        message="Bokför kvittot.",
        history=[],
        open_periods=[period],
        today=date(2026, 9, 18),
        model="opencode/claude-opus-5",
        actor="agent",
    )

    context = captured["tool_context"]
    assert context["thread"] is thread
    proposals = context["proposals"]
    assert isinstance(proposals, ProposalSequence)
    assert proposals.key() == derive_thread_proposal_idempotency_key(
        thread.id, trigger.id, 1
    )


# --- F7: verktygslistan (testfall 22) ----------------------------------------

_FIRST_TEN = [
    "las_kontoplan",
    "las_perioder",
    "las_verifikationer",
    "las_korrigeringar",
    "las_underlag",
    "hamta_underlagsfil",
    "las_bankhandelser",
    "posta_verifikation",
    "registrera_avstaende",
    "be_om_beslut",
]

# sha256 of `json.dumps(AGENT_TOOL_DEFINITIONS[:10], ensure_ascii=False)`,
# taken on `cc47e5c`, before F7 touched `_TOOL_SPECS`. No `sort_keys`: the key
# order inside each definition is part of the bytes the model is sent, and
# so of the cached prefix (SPEC-agentruntime §6.6).
_FIRST_TEN_SHA256 = "503ba62181d07802fb1a2c521e9453a4d2f213098f3e2aa73a20e67f6259f5d4"


def test_case_22_foresla_verifikation_is_last_and_the_first_ten_are_unchanged():
    """SPEC §5.7: appended last, the one change that moves none of the ten
    before it. The names catch a reorder; the hash catches an edit to a
    description or a schema that leaves the names where they were."""
    names = [tool["name"] for tool in AGENT_TOOL_DEFINITIONS]

    assert names == _FIRST_TEN + ["foresla_verifikation"]
    first_ten = json.dumps(AGENT_TOOL_DEFINITIONS[:10], ensure_ascii=False)
    assert hashlib.sha256(first_ten.encode("utf-8")).hexdigest() == _FIRST_TEN_SHA256
    assert AGENT_TOOL_DEFINITIONS[-1]["input_schema"] == (
        ForeslaVerifikationArgs.model_json_schema()
    )


def test_case_22_the_description_says_it_proposes_and_never_posts():
    [tool] = [t for t in AGENT_TOOL_DEFINITIONS if t["name"] == "foresla_verifikation"]
    description = tool["description"]

    assert "Postar aldrig" in description
    assert "numret sätts" in description
    assert "posta_verifikation" in description


def test_case_22_execute_tool_reaches_the_handler():
    """Listed is not enough: the dispatcher must route the name to F6's
    handler, with the thread from `tool_context`."""
    thread, period, trigger = _books()

    result = execute_tool(
        "foresla_verifikation",
        _args(period).model_dump(mode="json"),
        actor="agent",
        capabilities=_capabilities(),
        tool_context={
            "thread": thread,
            "proposals": ProposalSequence(thread.id, trigger.id),
        },
    )

    voucher = VoucherRepository.get(result["draft_id"])
    assert voucher is not None
    assert voucher.status == VoucherStatus.DRAFT
    assert voucher.number is None
    [post] = _draft_posts(thread)
    assert result["post_id"] == post.id


# --- F8: postningens krokar och kvittot (testfall 23-27) ----------------------


def _client():
    from fastapi.testclient import TestClient

    from api.main import app

    return TestClient(app)


def _post_route(client, voucher_id, headers, key=None):
    extra = {"Idempotency-Key": key} if key else {}
    return client.post(
        f"/api/v1/vouchers/{voucher_id}/post", headers={**headers, **extra}
    )


def _record_events(monkeypatch) -> list:
    """Every frame the broker is asked to publish, as `(thread_id, event,
    data)`. Patched on the process-wide instance, which is what
    `get_broker()` hands out."""
    from services.thread_stream import get_broker

    events: list = []
    monkeypatch.setattr(
        get_broker(),
        "publish",
        lambda thread_id, event, data: events.append((thread_id, event, data)),
    )
    return events


def _receipts(thread):
    return [p for p in ThreadRepository.list_posts(thread.id) if p.type == "receipt"]


def _proposed(thread, period, trigger, **overrides):
    result = _propose(
        thread,
        _args(period, **overrides),
        ProposalSequence(thread.id, trigger.id),
    )
    return result["draft_id"]


def _fixture_receipt_keys() -> tuple[set, set]:
    """`FIXTUR_RECEIPT`'s body keys and first row's keys, read out of the
    client's fixture like `_fixture_draft_keys`."""
    source = _FIXTURE_FILE.read_text(encoding="utf-8")
    start = source.index("export const FIXTUR_RECEIPT")
    block = source[start : source.index("};", start)]
    body = block[block.index("body: {") :]
    body_keys = set(re.findall(r"^    (\w+):", body, flags=re.MULTILINE))
    first_row = re.search(r"\{ (key:[^}]*)\}", body)
    assert first_row is not None
    row_keys = set(re.findall(r"(\w+):", first_row.group(1)))
    return body_keys, row_keys


def _intake_source(name: str = "kvitto-clas-ohlson"):
    return IntakeRepository.create_source(
        source_id=name,
        original_filename=f"{name}.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        sha256=f"sha-{name}",
        stored_path=f"/dev/null/{name}",
        uploaded_by="test",
    )


def test_case_23_posting_a_thread_draft_writes_one_receipt(monkeypatch, auth_headers):
    thread, period, trigger = _books()
    draft_id = _proposed(thread, period, trigger)
    events = _record_events(monkeypatch)

    response = _post_route(_client(), draft_id, auth_headers, key=str(uuid.uuid4()))

    assert response.status_code == 200, response.text
    assert response.json()["number"] == 1
    voucher = VoucherRepository.get(draft_id)
    assert voucher.status == VoucherStatus.POSTED
    assert voucher.number == 1

    row = ThreadDraftRepository.get(draft_id)
    assert row.status == "posted"
    assert row.posted_at is not None
    [receipt] = _receipts(thread)
    assert row.receipt_post_id == receipt.id
    assert receipt.actor == "api"  # the human who pressed Posta, not the agent

    body_keys, row_keys = _fixture_receipt_keys()
    assert set(receipt.body) == body_keys
    for body_row in receipt.body["rows"]:
        assert set(body_row) == row_keys
    assert receipt.body["title"] == "A-1 postad"
    assert receipt.body["labels"] == ["var", "blir"]
    assert receipt.body["voucher_id"] == draft_id
    assert [r["key"] for r in receipt.body["rows"]] == ["6110", "2640", "1930"]
    assert [r["text"] for r in receipt.body["rows"]] == [
        "Kontorsmateriel",
        "Ingående moms",
        "Företagskonto",
    ]

    # No attachment on the voucher: the flag is part of what happened.
    assert receipt.traces == [
        {
            "tool": "posta_utkast",
            "label": "verifikation postad",
            "detail": "A-1",
            "voucher_id": draft_id,
        },
        {"tool": "kompletteringsflagga", "label": "kompletteringsflagga satt"},
        # Last, counted after the posting (§8.2, F10): nothing else waits.
        {"tool": "vantar", "label": "0 kvar"},
    ]

    completed = [e for e in events if e[1] == "message.completed"]
    assert [(e[0], e[2]["id"], e[2]["type"]) for e in completed] == [
        (thread.id, receipt.id, "receipt")
    ]
    assert (
        thread.id,
        "view.changed",
        {
            "view_key": thread.view_key,
            "changed": {"voucher_id": draft_id, "kind": "voucher_posted"},
        },
    ) in events


def test_case_23_an_attached_voucher_gets_no_completion_flag(auth_headers):
    thread, period, trigger = _books()
    draft_id = _proposed(thread, period, trigger)
    db.execute(
        "INSERT INTO attachments "
        "(id, voucher_id, filename, sha256, mime_type, stored_path, size_bytes) "
        "VALUES (?, ?, 'kvitto.pdf', 'sha', 'application/pdf', '/dev/null', 1)",
        (str(uuid.uuid4()), draft_id),
    )
    db.commit()

    response = _post_route(_client(), draft_id, auth_headers)

    assert response.status_code == 200, response.text
    [receipt] = _receipts(thread)
    assert [t["label"] for t in receipt.traces] == ["verifikation postad", "0 kvar"]


def test_case_24_posting_twice_with_the_same_key_gives_one_receipt(
    monkeypatch, auth_headers
):
    thread, period, trigger = _books()
    draft_id = _proposed(thread, period, trigger)
    events = _record_events(monkeypatch)
    client = _client()
    key = str(uuid.uuid4())

    first = _post_route(client, draft_id, auth_headers, key=key)
    second = _post_route(client, draft_id, auth_headers, key=key)
    third = _post_route(client, draft_id, auth_headers)  # no key: 409

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.headers.get("Idempotent-Replay") == "true"
    assert second.json()["number"] == first.json()["number"] == 1
    assert third.status_code == 409
    assert third.json()["detail"]["code"] == "already_posted"

    assert _count("vouchers") == 1
    assert len(_receipts(thread)) == 1
    assert len([e for e in events if e[1] == "message.completed"]) == 1
    assert len([e for e in events if e[1] == "view.changed"]) == 1


def test_case_25_a_failed_receipt_leaves_the_posting_and_a_replay_writes_it(
    monkeypatch, auth_headers
):
    thread, period, trigger = _books()
    draft_id = _proposed(thread, period, trigger)
    client = _client()
    key = str(uuid.uuid4())

    real_add_post = ThreadRepository.add_post

    def failing_add_post(thread_id, post_type, *args, **kwargs):
        if post_type == "receipt":
            raise RuntimeError("tråden är nere")
        return real_add_post(thread_id, post_type, *args, **kwargs)

    monkeypatch.setattr(ThreadRepository, "add_post", staticmethod(failing_add_post))
    response = _post_route(client, draft_id, auth_headers, key=key)

    # The posting is committed and answered as a success.
    assert response.status_code == 200, response.text
    assert VoucherRepository.get(draft_id).number == 1
    row = ThreadDraftRepository.get(draft_id)
    assert row.status == "posted"
    assert row.receipt_post_id is None
    assert _receipts(thread) == []

    monkeypatch.setattr(ThreadRepository, "add_post", staticmethod(real_add_post))
    events = _record_events(monkeypatch)
    replay = _post_route(client, draft_id, auth_headers, key=key)

    assert replay.status_code == 200, replay.text
    assert replay.headers.get("Idempotent-Replay") == "true"
    [receipt] = _receipts(thread)
    assert ThreadDraftRepository.get(draft_id).receipt_post_id == receipt.id
    assert receipt.body["title"] == "A-1 postad"
    assert [e[1] for e in events] == ["message.completed", "view.changed"]

    # And once written, it is never written again.
    _post_route(client, draft_id, auth_headers, key=key)
    assert len(_receipts(thread)) == 1


def test_case_25_already_posted_without_a_key_resumes_the_receipt(
    monkeypatch, auth_headers
):
    thread, period, trigger = _books()
    draft_id = _proposed(thread, period, trigger)
    client = _client()

    from services.draft_service import DraftService

    def broken(self, voucher, *, actor):
        raise RuntimeError("kvittot föll")

    monkeypatch.setattr(DraftService, "_write_receipt", broken)
    assert _post_route(client, draft_id, auth_headers).status_code == 200
    assert _receipts(thread) == []

    monkeypatch.undo()
    conflict = _post_route(client, draft_id, auth_headers)

    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "already_posted"
    [receipt] = _receipts(thread)
    assert ThreadDraftRepository.get(draft_id).receipt_post_id == receipt.id


def test_case_26_receipt_rows_are_balances_before_and_after(auth_headers):
    """One row per account in the voucher's order (an account on two rows
    appears once), and both numbers agree with the general ledger."""
    thread, period, trigger = _books()
    ledger = LedgerService()

    # Earlier in the same fiscal year: counts.
    earlier = ledger.create_voucher(
        series="A",
        date=date(2026, 9, 2),
        period_id=period.id,
        description="Insättning",
        rows_data=[
            {"account": "1930", "debit": 1000000},
            {"account": "6110", "credit": 1000000},
        ],
        created_by="test",
    )
    ledger.post_voucher(earlier.id)

    # Another fiscal year: does not count.
    fy_2025 = PeriodRepository.create_fiscal_year(
        start_date=date(2025, 1, 1), end_date=date(2025, 12, 31)
    )
    period_2025 = PeriodRepository.create_period(
        fiscal_year_id=fy_2025.id,
        year=2025,
        month=9,
        start_date=date(2025, 9, 1),
        end_date=date(2025, 9, 30),
    )
    other_year = ledger.create_voucher(
        series="A",
        date=date(2025, 9, 2),
        period_id=period_2025.id,
        description="Förra året",
        rows_data=[
            {"account": "1930", "debit": 777},
            {"account": "2640", "credit": 777},
        ],
        created_by="test",
    )
    ledger.post_voucher(other_year.id)

    rows = [
        {"account": "6110", "debit": 50000},
        {"account": "2640", "debit": 17920},
        {"account": "6110", "debit": 21680},
        {"account": "1930", "credit": 89600},
    ]
    draft_id = _proposed(thread, period, trigger, rows=rows)
    client = _client()
    assert _post_route(client, draft_id, auth_headers).status_code == 200

    [receipt] = _receipts(thread)
    assert receipt.body["title"] == "A-2 postad"
    assert receipt.body["rows"] == [
        {
            "key": "6110",
            "text": "Kontorsmateriel",
            "left_ore": -1000000,
            "right_ore": -1000000 + 71680,
        },
        {"key": "2640", "text": "Ingående moms", "left_ore": 0, "right_ore": 17920},
        {
            "key": "1930",
            "text": "Företagskonto",
            "left_ore": 1000000,
            "right_ore": 1000000 - 89600,
        },
    ]

    for receipt_row in receipt.body["rows"]:
        report = client.get(
            f"/api/v1/reports/general-ledger/{receipt_row['key']}",
            params={"fiscal_year_id": thread.fiscal_year_id},
            headers=auth_headers,
        )
        assert report.status_code == 200, report.text
        report = report.json()
        own = sum(
            t["debit"] - t["credit"]
            for t in report["transactions"]
            if t["voucher_id"] == draft_id
        )
        assert report["closing_balance"] == receipt_row["right_ore"]
        assert report["closing_balance"] - own == receipt_row["left_ore"]


def test_case_27_a_draft_outside_any_thread_is_posted_as_before(
    monkeypatch, auth_headers
):
    thread, period, _trigger = _books()
    draft = LedgerService().create_voucher(
        series="A",
        date=date(2026, 9, 18),
        period_id=period.id,
        description="Utan tråd",
        rows_data=_ROWS,
        created_by="test",
    )
    events = _record_events(monkeypatch)

    response = _post_route(_client(), draft.id, auth_headers, key=str(uuid.uuid4()))

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "posted"
    assert response.json()["number"] == 1
    assert _receipts(thread) == []
    assert events == []
    assert _count("thread_drafts") == 0


def test_posting_a_thread_draft_links_its_source(auth_headers):
    thread, period, trigger = _books()
    source = _intake_source()
    draft_id = _proposed(thread, period, trigger, intake_source_ids=[source.id])

    response = _post_route(_client(), draft_id, auth_headers)

    assert response.status_code == 200, response.text
    link = IntakeRepository.get_link_by_source_id(source.id)
    assert link is not None
    assert link.voucher_id == draft_id
    assert IntakeRepository.get_source(source.id).status.value == "processed"


def test_a_source_booked_meanwhile_rolls_back_the_whole_posting(
    monkeypatch, auth_headers
):
    """F6's open risk: the intake flow posts the same source while the
    proposal waits. The press on Posta must then change nothing -- no number
    taken, the draft still a draft, the row still pending, the source still
    on the voucher that booked it -- and say which voucher that is."""
    from services.intake import IntakeService

    thread, period, trigger = _books()
    source = _intake_source()
    draft_id = _proposed(thread, period, trigger, intake_source_ids=[source.id])

    ledger = LedgerService()
    direct = ledger.create_voucher(
        series="A",
        date=date(2026, 9, 18),
        period_id=period.id,
        description="Kontorsmaterial, bokfört av intaget",
        rows_data=_ROWS,
        created_by="agent",
    )
    direct = ledger.post_voucher(direct.id)
    IntakeService().link_existing_voucher(
        source_id=source.id,
        voucher_id=direct.id,
        actor="agent",
        summary="Bokfört direkt",
    )
    events = _record_events(monkeypatch)
    client = _client()
    key = str(uuid.uuid4())

    response = _post_route(client, draft_id, auth_headers, key=key)

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "source_already_booked"
    assert detail["booked_by"] == {
        "source_kind": "intake_source",
        "source_id": source.id,
        "voucher_id": direct.id,
        "voucher_number": "A-1",
    }

    voucher = VoucherRepository.get(draft_id)
    assert voucher.status == VoucherStatus.DRAFT
    assert voucher.number is None
    row = ThreadDraftRepository.get(draft_id)
    assert row.status == "pending"
    assert row.posted_at is None
    assert IntakeRepository.get_link_by_source_id(source.id).voucher_id == direct.id
    assert _receipts(thread) == []
    # F9: the thread is told, in one `error` post, and nothing else happens.
    [error] = _errors(thread)
    assert [(e[1], e[2]["id"]) for e in events] == [("message.completed", error.id)]

    # The key was released, not stored: the same press answers the same way.
    again = _post_route(client, draft_id, auth_headers, key=key)
    assert again.status_code == 409
    assert "Idempotent-Replay" not in again.headers
    assert again.json()["detail"] == detail
    assert len(_errors(thread)) == 1

    # And no number was consumed: the next posting in the series is A-2.
    next_one = ledger.create_voucher(
        series="A",
        date=date(2026, 9, 19),
        period_id=period.id,
        description="Nästa",
        rows_data=_ROWS,
        created_by="test",
    )
    assert ledger.post_voucher(next_one.id).number == 2


# --- F9: felen i tråden (testfall 28-29) --------------------------------------


def _errors(thread):
    return [p for p in ThreadRepository.list_posts(thread.id) if p.type == "error"]


def _fixture_error_keys() -> set:
    """`FIXTUR_ERROR.body`'s keys, read out of the client's fixture like
    `_fixture_draft_keys`."""
    source = _FIXTURE_FILE.read_text(encoding="utf-8")
    start = source.index("export const FIXTUR_ERROR")
    block = source[start : source.index("};", start)]
    body = block[block.index("body: {") : block.index("},", block.index("body: {"))]
    return set(re.findall(r"^    (\w+):", body, flags=re.MULTILINE))


def _lock(period, actor="stefan", at=datetime(2026, 9, 30, 9, 14)):
    """Lock the period as `POST /periods/{id}/lock` does, at a known time so
    the post's text can be asserted on."""
    PeriodRepository.lock_period(period.id, actor=actor)
    db.execute("UPDATE periods SET locked_at = ? WHERE id = ?", (at, period.id))
    db.commit()


def _posted_count() -> int:
    return db.execute(
        "SELECT COUNT(*) AS n FROM vouchers WHERE status = 'posted'"
    ).fetchone()["n"]


def test_case_28_period_locked_between_proposal_and_press(monkeypatch, auth_headers):
    thread, period, trigger = _books()
    draft_id = _proposed(thread, period, trigger)
    _lock(period)
    events = _record_events(monkeypatch)

    response = _post_route(_client(), draft_id, auth_headers, key=str(uuid.uuid4()))

    # The HTTP answer is T7's, unchanged.
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "period_locked"
    assert detail["locked_by"] == "stefan"
    assert detail["period_id"] == period.id

    [error] = _errors(thread)
    assert set(error.body) == _fixture_error_keys()
    assert error.body == {
        "cause": (
            "Perioden september 2026 låstes 2026-09-30 09:14 av stefan "
            "medan förslaget låg."
        ),
        "consequence": (
            "Ingenting har ändrats i bokföringen. Förslaget ligger kvar men "
            "kan inte postas i september 2026."
        ),
        "retry_draft_id": None,
    }
    assert error.actor == "api"

    row = ThreadDraftRepository.get(draft_id)
    assert row.status == "pending"
    assert row.last_error_code == "period_locked"
    assert row.last_error_post_id == error.id

    assert [(e[0], e[1], e[2]["id"], e[2]["type"]) for e in events] == [
        (thread.id, "message.completed", error.id, "error")
    ]

    # Nothing booked, no number taken: the next posting in A is A-1.
    voucher = VoucherRepository.get(draft_id)
    assert voucher.status == VoucherStatus.DRAFT
    assert voucher.number is None
    assert _posted_count() == 0
    october = PeriodRepository.create_period(
        fiscal_year_id=thread.fiscal_year_id,
        year=2026,
        month=10,
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 31),
    )
    ledger = LedgerService()
    next_one = ledger.create_voucher(
        series="A",
        date=date(2026, 10, 1),
        period_id=october.id,
        description="Nästa",
        rows_data=_ROWS,
        created_by="test",
    )
    assert ledger.post_voucher(next_one.id).number == 1


def test_case_28_a_lock_with_no_recorded_actor_does_not_guess(auth_headers):
    thread, period, trigger = _books()
    draft_id = _proposed(thread, period, trigger)
    _lock(period, actor=None)

    response = _post_route(_client(), draft_id, auth_headers)

    assert response.status_code == 409
    [error] = _errors(thread)
    assert error.body["cause"] == (
        "Perioden september 2026 låstes 2026-09-30 09:14 medan förslaget låg."
    )


def test_case_29_the_same_locked_draft_posted_three_times_gives_one_post(
    monkeypatch, auth_headers
):
    thread, period, trigger = _books()
    draft_id = _proposed(thread, period, trigger)
    _lock(period)
    events = _record_events(monkeypatch)
    client = _client()

    responses = [
        _post_route(client, draft_id, auth_headers, key=str(uuid.uuid4())),
        _post_route(client, draft_id, auth_headers),
        _post_route(client, draft_id, auth_headers, key=str(uuid.uuid4())),
    ]

    assert [r.status_code for r in responses] == [409, 409, 409]
    assert len({json.dumps(r.json(), sort_keys=True) for r in responses}) == 1
    [error] = _errors(thread)
    assert ThreadDraftRepository.get(draft_id).last_error_post_id == error.id
    assert len([e for e in events if e[1] == "message.completed"]) == 1
    assert _posted_count() == 0


def test_a_validation_error_writes_a_post_and_a_new_code_writes_another(
    monkeypatch, auth_headers
):
    """The chart of accounts changes while the proposal waits: 6110 is
    deactivated. The press is refused, the thread says why -- and when the
    period is then locked too, that is a new code and a second post."""
    thread, period, trigger = _books()
    draft_id = _proposed(thread, period, trigger)
    AccountRepository.deactivate("6110")
    events = _record_events(monkeypatch)
    client = _client()

    response = _post_route(client, draft_id, auth_headers, key=str(uuid.uuid4()))

    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "inactive_account"
    [error] = _errors(thread)
    assert set(error.body) == _fixture_error_keys()
    assert error.body == {
        "cause": (
            "Konto 6110 Kontorsmateriel har inaktiverats i kontoplanen "
            "sedan förslaget lades fram."
        ),
        "consequence": (
            "Ingenting har ändrats i bokföringen. Förslaget ligger kvar men "
            "kan inte postas som det står."
        ),
        "retry_draft_id": None,
    }
    row = ThreadDraftRepository.get(draft_id)
    assert (row.last_error_code, row.last_error_post_id) == (
        "inactive_account",
        error.id,
    )
    voucher = VoucherRepository.get(draft_id)
    assert voucher.status == VoucherStatus.DRAFT
    assert voucher.number is None

    # Same code again: nothing new.
    _post_route(client, draft_id, auth_headers)
    assert len(_errors(thread)) == 1

    # A new code: a new post.
    _lock(period)
    locked = _post_route(client, draft_id, auth_headers)
    assert locked.json()["detail"]["code"] == "period_locked"
    first, second = _errors(thread)
    assert first.id == error.id
    assert second.body["cause"].startswith("Perioden september 2026 låstes")
    row = ThreadDraftRepository.get(draft_id)
    assert (row.last_error_code, row.last_error_post_id) == (
        "period_locked",
        second.id,
    )
    assert [e[2]["id"] for e in events if e[1] == "message.completed"] == [
        first.id,
        second.id,
    ]
    assert _posted_count() == 0


def test_an_account_removed_from_the_chart_writes_a_post(auth_headers):
    thread, period, trigger = _books()
    draft_id = _proposed(thread, period, trigger)
    db.execute("PRAGMA foreign_keys = OFF")
    db.execute("DELETE FROM accounts WHERE code = '6110'")
    db.commit()
    db.execute("PRAGMA foreign_keys = ON")

    response = _post_route(_client(), draft_id, auth_headers)

    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "account_not_found"
    [error] = _errors(thread)
    assert error.body["cause"] == "Konto 6110 finns inte längre i kontoplanen."


def test_source_already_booked_names_the_voucher_that_has_it(auth_headers):
    from services.intake import IntakeService

    thread, period, trigger = _books()
    source = _intake_source()
    draft_id = _proposed(thread, period, trigger, intake_source_ids=[source.id])
    ledger = LedgerService()
    direct = ledger.create_voucher(
        series="A",
        date=date(2026, 9, 18),
        period_id=period.id,
        description="Kontorsmaterial, bokfört av intaget",
        rows_data=_ROWS,
        created_by="agent",
    )
    ledger.post_voucher(direct.id)
    IntakeService().link_existing_voucher(
        source_id=source.id,
        voucher_id=direct.id,
        actor="agent",
        summary="Bokfört direkt",
    )

    response = _post_route(_client(), draft_id, auth_headers)

    assert response.status_code == 409
    [error] = _errors(thread)
    assert set(error.body) == _fixture_error_keys()
    assert error.body == {
        "cause": (
            "Underlaget kvitto-clas-ohlson.pdf bokfördes på verifikation A-1 "
            "medan förslaget låg."
        ),
        "consequence": (
            "Ingenting har ändrats i bokföringen. Samma underlag bokförs inte "
            "två gånger: A-1 står kvar och förslaget ligger kvar opostat."
        ),
        "retry_draft_id": None,
    }
    row = ThreadDraftRepository.get(draft_id)
    assert (row.last_error_code, row.last_error_post_id) == (
        "source_already_booked",
        error.id,
    )


def test_a_draft_outside_any_thread_gets_no_error_post(monkeypatch, auth_headers):
    thread, period, _trigger = _books()
    draft = LedgerService().create_voucher(
        series="A",
        date=date(2026, 9, 18),
        period_id=period.id,
        description="Utan tråd",
        rows_data=_ROWS,
        created_by="test",
    )
    _lock(period)
    events = _record_events(monkeypatch)

    response = _post_route(_client(), draft.id, auth_headers)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "period_locked"
    assert _count("thread_posts") == 1  # the trigger only
    assert events == []


def test_a_failure_writing_the_error_post_leaves_the_answer(monkeypatch, auth_headers):
    thread, period, trigger = _books()
    draft_id = _proposed(thread, period, trigger)
    outside = LedgerService().create_voucher(
        series="A",
        date=date(2026, 9, 18),
        period_id=period.id,
        description="Utan tråd",
        rows_data=_ROWS,
        created_by="test",
    )
    _lock(period)
    client = _client()
    # The answer a draft outside any thread gets: the route as before F9.
    expected = _post_route(client, outside.id, auth_headers)

    real_add_post = ThreadRepository.add_post

    def failing_add_post(thread_id, post_type, *args, **kwargs):
        if post_type == "error":
            raise RuntimeError("tråden är nere")
        return real_add_post(thread_id, post_type, *args, **kwargs)

    monkeypatch.setattr(ThreadRepository, "add_post", staticmethod(failing_add_post))
    response = _post_route(client, draft_id, auth_headers)

    assert response.status_code == 409
    assert response.json()["detail"] == expected.json()["detail"]
    row = ThreadDraftRepository.get(draft_id)
    assert row.status == "pending"
    assert row.last_error_code is None
    assert row.last_error_post_id is None


def test_a_server_error_writes_nothing_to_the_thread(monkeypatch, auth_headers):
    thread, period, trigger = _books()
    draft_id = _proposed(thread, period, trigger)
    events = _record_events(monkeypatch)

    def broken(self, *args, **kwargs):
        raise RuntimeError("disken är full")

    monkeypatch.setattr(LedgerService, "post_voucher", broken)
    response = _post_route(_client(), draft_id, auth_headers)

    assert response.status_code == 500
    assert _errors(thread) == []
    assert ThreadDraftRepository.get(draft_id).last_error_code is None
    assert events == []


# --- F10: GET /drafts, count_waiting och räknaren (testfall 30-31) ------------


def _get_drafts(client, headers, **params):
    return client.get("/api/v1/drafts", headers=headers, params=params)


def test_case_30_get_drafts_gives_status_and_voucher_only_when_posted(auth_headers):
    thread, period, trigger = _books()
    proposals = ProposalSequence(thread.id, trigger.id)
    old = _propose(thread, _args(period), proposals)
    new = _propose(thread, _args(period, replaces_draft_id=old["draft_id"]), proposals)
    waiting = _propose(thread, _args(period, description="Pennor"), proposals)
    client = _client()
    assert _post_route(client, new["draft_id"], auth_headers).status_code == 200

    response = _get_drafts(client, auth_headers, view_key=thread.view_key)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 3
    by_id = {d["draft_id"]: d for d in payload["drafts"]}
    assert [d["draft_id"] for d in payload["drafts"]] == [
        old["draft_id"],
        new["draft_id"],
        waiting["draft_id"],
    ]
    for draft in payload["drafts"]:
        assert set(draft) == {
            "draft_id",
            "post_id",
            "decision_id",
            "correction_of",
            "correction_note_id",
            "status",
            "replaced_by",
            "posted_at",
            "voucher",
            "last_error_code",
            "created_at",
        }

    superseded = by_id[old["draft_id"]]
    assert superseded["status"] == "superseded"
    assert superseded["replaced_by"] == new["draft_id"]
    assert superseded["voucher"] is None
    assert superseded["post_id"] == old["post_id"]

    posted = by_id[new["draft_id"]]
    assert posted["status"] == "posted"
    assert posted["voucher"] == {"series": "A", "number": 1}
    assert posted["posted_at"] is not None

    pending = by_id[waiting["draft_id"]]
    assert pending["status"] == "pending"
    assert pending["voucher"] is None
    assert pending["posted_at"] is None
    assert pending["last_error_code"] is None


def test_case_30_get_drafts_filters_on_status_and_limit(auth_headers):
    thread, period, trigger = _books()
    proposals = ProposalSequence(thread.id, trigger.id)
    first = _propose(thread, _args(period), proposals)
    second = _propose(thread, _args(period, description="Pennor"), proposals)
    client = _client()
    assert _post_route(client, first["draft_id"], auth_headers).status_code == 200

    pending = _get_drafts(
        client, auth_headers, view_key=thread.view_key, status="pending"
    ).json()
    assert [d["draft_id"] for d in pending["drafts"]] == [second["draft_id"]]
    assert pending["total"] == 1

    posted = _get_drafts(
        client, auth_headers, view_key=thread.view_key, status="posted"
    ).json()
    assert [d["voucher"] for d in posted["drafts"]] == [{"series": "A", "number": 1}]

    assert _get_drafts(
        client, auth_headers, view_key=thread.view_key, status="superseded"
    ).json() == {"drafts": [], "total": 0}

    limited = _get_drafts(
        client, auth_headers, view_key=thread.view_key, status="all", limit=1
    ).json()
    assert [d["draft_id"] for d in limited["drafts"]] == [first["draft_id"]]
    assert limited["total"] == 2

    # Another view sees none of this view's drafts.
    other = _get_drafts(client, auth_headers, view_key="bocker.balans").json()
    assert other == {"drafts": [], "total": 0}


def test_case_30_get_drafts_carries_the_error_code(auth_headers):
    thread, period, trigger = _books()
    draft_id = _proposed(thread, period, trigger)
    _lock(period)
    client = _client()
    assert _post_route(client, draft_id, auth_headers).status_code == 409

    [draft] = _get_drafts(client, auth_headers, view_key=thread.view_key).json()[
        "drafts"
    ]
    assert draft["status"] == "pending"
    assert draft["last_error_code"] == "period_locked"
    assert draft["voucher"] is None


def test_case_30_get_drafts_rejects_bad_input_and_requires_auth(auth_headers):
    client = _client()

    bad_status = _get_drafts(
        client, auth_headers, view_key="bocker.verifikationer", status="open"
    )
    assert bad_status.status_code == 400
    assert bad_status.json()["detail"]["code"] == "unknown_status"

    bad_view = _get_drafts(client, auth_headers, view_key="bocker.nope")
    assert bad_view.status_code == 404
    assert bad_view.json()["detail"]["code"] == "unknown_view_key"

    assert _get_drafts(client, auth_headers).status_code == 422
    assert (
        client.get(
            "/api/v1/drafts", params={"view_key": "bocker.verifikationer"}
        ).status_code
        == 401
    )


def test_case_30_voucher_numbers_are_read_in_one_query(monkeypatch, auth_headers):
    thread, period, trigger = _books()
    proposals = ProposalSequence(thread.id, trigger.id)
    client = _client()
    for description in ("Ett", "Två", "Tre"):
        draft = _propose(thread, _args(period, description=description), proposals)
        assert _post_route(client, draft["draft_id"], auth_headers).status_code == 200

    statements: list = []
    real_execute = db.execute

    def counting(sql, *args, **kwargs):
        statements.append(sql)
        return real_execute(sql, *args, **kwargs)

    monkeypatch.setattr(db, "execute", counting)
    payload = _get_drafts(client, auth_headers, view_key=thread.view_key).json()

    assert [d["voucher"]["number"] for d in payload["drafts"]] == [1, 2, 3]
    assert len([s for s in statements if "FROM vouchers" in s]) == 1


def _waiting_books():
    """Testfall 31's database: every kind of thing that can wait, and the
    kinds that must not be counted, in one view -- plus one draft in another
    view. Returns the thread and how many wait in its view."""
    thread, period, trigger = _books()
    proposals = ProposalSequence(thread.id, trigger.id)
    first = _propose(thread, _args(period), proposals)
    original = LedgerService().post_voucher(first["draft_id"], actor="stefan")
    # Straight through the ledger, so the row is marked by hand; the route's
    # hook would do the same.
    ThreadDraftRepository.mark_posted(first["draft_id"], datetime.now())
    service = DecisionService()

    # 1. An open decision with no proposal: counted, once.
    _open_decision(thread)
    # 2. An open decision with a pending proposal: counted once, via the decision.
    open_with_draft = _open_decision(thread)
    _draft(thread, decision_id=open_with_draft.id)
    # 3. An answered decision with a superseded and a pending proposal: once.
    answered = _answered_decision(thread)
    replaced = _draft(thread, decision_id=answered.id)
    successor = _draft(thread, decision_id=answered.id)
    ThreadDraftRepository.mark_superseded(replaced.voucher_id, successor.voucher_id)
    # 4. An answered decision whose proposal was posted: nothing waits.
    done = _answered_decision(thread)
    posted = _draft(thread, decision_id=done.id)
    ThreadDraftRepository.mark_posted(posted.voucher_id, datetime.now())
    # 5. A pending correction, no decision behind it: counted.
    _draft(thread, correction_of=original.id)
    # 6. A pending proposal with no decision: counted.
    _draft(thread)
    # 7. A superseded proposal with no decision: not counted.
    lone = _draft(thread)
    ThreadDraftRepository.mark_superseded(lone.voucher_id, "någon-annan")
    # 8. An open correction note (a synthetic decision) and the pending
    #    correction answering it: counted once, via the note.
    from repositories.correction_note_repo import CorrectionNoteRepository

    note = CorrectionNoteRepository.create(original.id, "Fel konto", "stefan")
    _draft(thread, correction_of=original.id, correction_note_id=note.id)
    # 9. A decision that was superseded, with a pending proposal: once.
    gone = _open_decision(thread)
    service.supersede(gone.id)
    _draft(thread, decision_id=gone.id)

    # Another view: one pending proposal, counted only without a view_key.
    other = ThreadRepository.get_or_create(
        view_key="bocker.balans",
        fiscal_year_id=thread.fiscal_year_id,
        model="opencode/claude-opus-5",
    )
    _draft(other)
    return thread, 1 + 1 + 1 + 1 + 1 + 1 + 1


def test_case_31_count_waiting_counts_each_waiting_thing_once():
    thread, in_view = _waiting_books()
    service = DecisionService()

    assert service.count_waiting(thread.view_key) == in_view
    assert service.count_waiting() == in_view + 1
    assert service.count_waiting("bocker.balans") == 1
    assert service.count_waiting("bocker.kontoplan") == 0
    # The open decisions alone (1, 2 and the note) are what count_open says.
    assert service.count_open() == 3


def test_case_31_overview_gives_the_same_number(auth_headers):
    _waiting_books()

    response = _client().get("/api/v1/overview", headers=auth_headers)

    assert response.status_code == 200, response.text
    [bocker] = [p for p in response.json()["pages"] if p["key"] == "bocker"]
    assert bocker["counters"]["open_decisions"] == DecisionService().count_waiting()
    assert bocker["counters"]["open_decisions"] == 8
    assert bocker["meta"].startswith("8 väntar på dig")


def test_the_receipt_ends_with_how_many_still_wait(auth_headers):
    thread, period, trigger = _books()
    proposals = ProposalSequence(thread.id, trigger.id)
    first = _propose(thread, _args(period), proposals)
    _propose(thread, _args(period, description="Pennor"), proposals)
    _open_decision(thread)

    response = _post_route(_client(), first["draft_id"], auth_headers)

    assert response.status_code == 200, response.text
    [receipt] = _receipts(thread)
    # Counted after the posting: the posted draft no longer waits, the other
    # proposal and the open decision do.
    assert receipt.traces[-1] == {"tool": "vantar", "label": "2 kvar"}


# --- F11: korrigeringsförslaget (testfall 32-36, 40) --------------------------

#: How A-1 should have looked: no VAT on the purchase.
_CORRECTED_ROWS = [
    {"account": "6110", "debit": 89600},
    {"account": "1930", "credit": 89600},
]


def _add_period(thread, month: int):
    return PeriodRepository.create_period(
        fiscal_year_id=thread.fiscal_year_id,
        year=2026,
        month=month,
        start_date=date(2026, month, 1),
        end_date=date(2026, month, 30),
    )


def _original(period, day: int = 18):
    """A-n in `period`, posted -- the voucher the human wants corrected."""
    ledger = LedgerService()
    draft = ledger.create_voucher(
        series="A",
        date=date(period.year, period.month, day),
        period_id=period.id,
        description="Kontorsmaterial, Clas Ohlson",
        rows_data=_ROWS,
        created_by="stefan",
    )
    return ledger.post_voucher(draft.id, actor="stefan")


def _correction_args(original, **overrides) -> ForeslaVerifikationArgs:
    fields = {
        "description": "Rättelse: kontorsmaterial utan avdragsgill moms",
        "rows": _CORRECTED_ROWS,
        "correction_of": original.id,
        "footnote": "Kvittot saknar moms",
    }
    fields.update(overrides)
    return ForeslaVerifikationArgs.model_validate(fields)


@pytest.fixture
def today(monkeypatch):
    """The server's `today` (§7.2), fixed so the date rule can be asserted:
    the thread's proposal reads it in `draft_service`, `/correct` and the
    notes' paths in `ledger` (F12)."""
    import services.draft_service as draft_service
    import services.ledger as ledger

    def set_today(value: date) -> None:
        monkeypatch.setattr(draft_service, "_today", lambda: value)
        monkeypatch.setattr(ledger, "_today", lambda: value, raising=False)

    set_today(date(2026, 9, 23))
    return set_today


def _reversal(original) -> list:
    return [
        (
            r.account_code,
            r.credit,
            r.debit,
            f"Återföring {original.series.value}{original.number}",
        )
        for r in original.rows
    ]


def test_case_32_correction_in_an_open_period(today):
    thread, september, trigger = _books()
    original = _original(september)
    posts_before = _count("thread_posts")

    result = _propose(
        thread,
        _correction_args(original),
        ProposalSequence(thread.id, trigger.id),
    )

    draft = VoucherRepository.get(result["draft_id"])
    assert draft.status == VoucherStatus.DRAFT
    assert draft.number is None
    assert draft.series.value == "B"
    assert draft.correction_of == original.id
    assert draft.period_id == september.id
    assert draft.date == date(2026, 9, 23)
    assert draft.description == "Rättelse: kontorsmaterial utan avdragsgill moms"
    # The reversal, exactly A-1's rows with debit and credit swapped, then
    # the agent's rows unchanged.
    rows = [(r.account_code, r.debit, r.credit, r.description) for r in draft.rows]
    assert rows[:3] == _reversal(original)
    assert rows[3:] == [("6110", 89600, 0, None), ("1930", 0, 89600, None)]
    assert draft.is_balanced()

    row = ThreadDraftRepository.get(draft.id)
    assert row.status == "pending"
    assert row.correction_of == original.id
    assert row.correction_note_id is None

    assert _count("thread_posts") == posts_before + 1
    [post] = _draft_posts(thread)
    assert post.body["title"] == "Rättelse: kontorsmaterial utan avdragsgill moms"
    assert post.body["meta"] == "Förslag · B · 2026-09-23"
    assert post.body["consequence"] == (
        "Låses vid postning · får nästa nummer i B-serien · "
        "period september 2026 öppen\nRättar A-1"
    )
    assert [
        (r["account"], r["debit_ore"], r["credit_ore"]) for r in post.body["rows"]
    ] == [
        ("6110", None, 71680),
        ("2640", None, 17920),
        ("1930", 89600, None),
        ("6110", 89600, None),
        ("1930", None, 89600),
    ]
    body_keys, _ = _fixture_draft_keys()
    assert set(post.body) == body_keys

    assert result["series"] == "B"
    assert result["date"] == "2026-09-23"
    assert result["period_id"] == september.id
    assert result["consequence"] == post.body["consequence"]

    # Posted, it takes the B series' number -- the original is untouched.
    posted = LedgerService().post_voucher(draft.id, actor="stefan")
    assert posted.number == 1
    assert VoucherRepository.get(original.id).rows == original.rows


def test_case_32_a_correction_can_itself_be_corrected(today):
    thread, september, trigger = _books()
    original = _original(september)
    proposals = ProposalSequence(thread.id, trigger.id)
    first = _propose(thread, _correction_args(original), proposals)
    b1 = LedgerService().post_voucher(first["draft_id"], actor="stefan")
    ThreadDraftRepository.mark_posted(b1.id, datetime.now())

    again = _propose(thread, _correction_args(b1), proposals)

    draft = VoucherRepository.get(again["draft_id"])
    assert draft.correction_of == b1.id
    rows = [(r.account_code, r.debit, r.credit, r.description) for r in draft.rows]
    assert rows[: len(b1.rows)] == _reversal(b1)


def test_case_33_original_in_a_locked_period(today):
    thread, september, trigger = _books()
    june = _add_period(thread, 6)
    original = _original(june)
    _lock(june, at=datetime(2026, 7, 5, 16, 2))

    result = _propose(
        thread,
        _correction_args(original),
        ProposalSequence(thread.id, trigger.id),
    )

    draft = VoucherRepository.get(result["draft_id"])
    assert draft.period_id == september.id
    assert draft.date == date(2026, 9, 23)
    [post] = _draft_posts(thread)
    assert post.body["consequence"] == (
        "Låses vid postning · får nästa nummer i B-serien · "
        "period september 2026 öppen\n"
        "Rättar A-1 (juni 2026, låst sedan 2026-07-05) · "
        "bokförs i september 2026, inte i juni 2026"
    )
    # Postable as it stands: the date lies in the target period.
    assert LedgerService().post_voucher(draft.id, actor="stefan").number == 1


def test_case_33_today_outside_the_target_period_gives_its_last_day(today):
    thread, september, trigger = _books()
    june = _add_period(thread, 6)
    original = _original(june)
    _lock(june, at=datetime(2026, 7, 5, 16, 2))
    today(date(2026, 10, 2))

    result = _propose(
        thread,
        _correction_args(original),
        ProposalSequence(thread.id, trigger.id),
    )

    assert result["date"] == "2026-09-30"
    assert result["period_id"] == september.id
    [post] = _draft_posts(thread)
    assert post.body["meta"] == "Förslag · B · 2026-09-30"


def test_case_33_the_latest_open_period_is_chosen(today):
    thread, september, trigger = _books()
    june = _add_period(thread, 6)
    _add_period(thread, 7)
    original = _original(june)
    _lock(june)

    result = _propose(
        thread,
        _correction_args(original),
        ProposalSequence(thread.id, trigger.id),
    )

    assert result["period_id"] == september.id


def test_case_34_no_open_period_in_the_year(today):
    thread, june, trigger = _books(month=6)
    original = _original(june)
    _lock(june)
    vouchers_before = _count("vouchers")
    posts_before = _count("thread_posts")
    proposals = ProposalSequence(thread.id, trigger.id)

    with pytest.raises(ValidationError) as excinfo:
        _propose(thread, _correction_args(original), proposals)

    assert excinfo.value.code == "no_open_period"
    assert _count("vouchers") == vouchers_before
    assert _count("thread_drafts") == 0
    assert _count("thread_posts") == posts_before
    assert proposals.n == 1


def test_case_35_a_second_correction_while_the_first_waits(today):
    thread, september, trigger = _books()
    original = _original(september)
    proposals = ProposalSequence(thread.id, trigger.id)
    first = _propose(thread, _correction_args(original), proposals)
    # Any thread: the pending correction blocks a proposal in another one.
    other = ThreadRepository.get_or_create(
        view_key="bocker.huvudbok",
        fiscal_year_id=thread.fiscal_year_id,
        model="opencode/claude-opus-5",
    )

    for where in (thread, other):
        with pytest.raises(ValidationError) as excinfo:
            _propose(where, _correction_args(original), proposals)
        assert excinfo.value.code == "correction_already_pending"
        assert first["draft_id"] in (excinfo.value.details or "")

    assert _count("thread_drafts") == 1


def test_case_35_replaces_draft_id_replaces_the_pending_correction(today):
    thread, september, trigger = _books()
    original = _original(september)
    proposals = ProposalSequence(thread.id, trigger.id)
    first = _propose(thread, _correction_args(original), proposals)

    second = _propose(
        thread,
        _correction_args(
            original,
            description="Rättelse: kontorsmaterial, moms 12 %",
            replaces_draft_id=first["draft_id"],
        ),
        proposals,
    )

    assert VoucherRepository.get(first["draft_id"]) is None
    old_row = ThreadDraftRepository.get(first["draft_id"])
    assert old_row.status == "superseded"
    assert old_row.replaced_by == second["draft_id"]
    new_row = ThreadDraftRepository.get(second["draft_id"])
    assert new_row.status == "pending"
    assert new_row.correction_of == original.id
    assert second["replaced_draft_id"] == first["draft_id"]
    assert ThreadDraftRepository.pending_for_correction_of(original.id).voucher_id == (
        second["draft_id"]
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"date": "2026-09-18"},
        {"period_id": "any"},
        {"date": "2026-09-18", "period_id": "any"},
    ],
)
def test_case_36_date_or_period_with_correction_of_is_refused(today, overrides):
    thread, september, trigger = _books()
    original = _original(september)
    if "period_id" in overrides:
        overrides["period_id"] = september.id
    vouchers_before = _count("vouchers")

    with pytest.raises(ValidationError) as excinfo:
        _propose(
            thread,
            _correction_args(original, **overrides),
            ProposalSequence(thread.id, trigger.id),
        )

    assert excinfo.value.code == "correction_period_is_derived"
    assert _count("vouchers") == vouchers_before
    assert _count("thread_drafts") == 0


def test_case_36_the_original_must_be_posted(today):
    thread, september, trigger = _books()
    draft = LedgerService().create_voucher(
        series="A",
        date=date(2026, 9, 18),
        period_id=september.id,
        description="Utkast",
        rows_data=_ROWS,
    )

    with pytest.raises(ValidationError) as excinfo:
        _propose(
            thread,
            _correction_args(draft),
            ProposalSequence(thread.id, trigger.id),
        )

    assert excinfo.value.code == "not_posted"
    assert _count("thread_drafts") == 0


def test_an_unbalanced_correction_writes_nothing(today):
    thread, september, trigger = _books()
    original = _original(september)
    vouchers_before = _count("vouchers")
    posts_before = _count("thread_posts")
    rows = [{"account": "6110", "debit": 100}, {"account": "1930", "credit": 99}]

    with pytest.raises(ValidationError) as excinfo:
        _propose(
            thread,
            _correction_args(original, rows=rows),
            ProposalSequence(thread.id, trigger.id),
        )

    assert excinfo.value.code == "balance_error"
    assert _count("vouchers") == vouchers_before
    assert _count("voucher_rows") == len(original.rows)
    assert _count("thread_drafts") == 0
    assert _count("thread_posts") == posts_before


def test_a_correction_run_twice_in_the_same_turn_gives_the_same_draft(today):
    thread, september, trigger = _books()
    original = _original(september)

    first = _propose(
        thread, _correction_args(original), ProposalSequence(thread.id, trigger.id)
    )
    again = _propose(
        thread, _correction_args(original), ProposalSequence(thread.id, trigger.id)
    )

    assert again["draft_id"] == first["draft_id"]
    assert again["idempotent_replay"] is True
    assert _count("thread_drafts") == 1


def _note(voucher, status: str = "pending"):
    from repositories.correction_note_repo import CorrectionNoteRepository

    note = CorrectionNoteRepository.create(voucher.id, "Fel moms", "stefan")
    if status != "pending":
        db.execute(
            "UPDATE correction_notes SET status = ? WHERE id = ?", (status, note.id)
        )
        db.commit()
    return note


@pytest.mark.parametrize("status", ["pending", "suggested"])
def test_case_40_a_note_for_the_original_is_kept_on_the_row(today, status):
    thread, september, trigger = _books()
    original = _original(september)
    note = _note(original, status)

    result = _propose(
        thread,
        _correction_args(original, correction_note_id=note.id),
        ProposalSequence(thread.id, trigger.id),
    )

    row = ThreadDraftRepository.get(result["draft_id"])
    assert row.correction_of == original.id
    assert row.correction_note_id == note.id


def _mismatched_note(case, original, other):
    if case == "other_voucher":
        return _note(other).id, original
    if case == "applied":
        return _note(original, "applied").id, original
    if case == "dismissed":
        return _note(original, "dismissed").id, original
    if case == "unknown":
        return "nope", original
    raise AssertionError(case)


@pytest.mark.parametrize("case", ["other_voucher", "applied", "dismissed", "unknown"])
def test_case_40_a_note_that_does_not_match_is_refused(today, case):
    thread, september, trigger = _books()
    original = _original(september)
    other = _original(september, day=19)
    note_id, corrected = _mismatched_note(case, original, other)
    vouchers_before = _count("vouchers")

    with pytest.raises(ValidationError) as excinfo:
        _propose(
            thread,
            _correction_args(corrected, correction_note_id=note_id),
            ProposalSequence(thread.id, trigger.id),
        )

    assert excinfo.value.code == "correction_note_mismatch"
    assert _count("vouchers") == vouchers_before
    assert _count("thread_drafts") == 0


def test_case_40_a_note_without_correction_of_is_refused(today):
    thread, september, trigger = _books()
    original = _original(september)
    note = _note(original)

    with pytest.raises(ValidationError) as excinfo:
        _propose(
            thread,
            _args(september, correction_note_id=note.id),
            ProposalSequence(thread.id, trigger.id),
        )

    assert excinfo.value.code == "correction_note_mismatch"
    assert _count("thread_drafts") == 0


# --- F12: rättelsens postning och noteringarna (testfall 37-39, 41, 43) -------


def _history(original_id: str) -> list:
    from repositories.accounting_correction_repo import AccountingCorrectionRepository

    return AccountingCorrectionRepository.list(voucher_id=original_id)


def _proposed_correction(thread, trigger, original, **overrides) -> str:
    result = _propose(
        thread,
        _correction_args(original, **overrides),
        ProposalSequence(thread.id, trigger.id),
    )
    return result["draft_id"]


def _note_status(note_id: str):
    from repositories.correction_note_repo import CorrectionNoteRepository

    return CorrectionNoteRepository.get(note_id)


def test_case_37_posting_a_correction(today, auth_headers):
    thread, september, trigger = _books()
    original = _original(september)
    draft_id = _proposed_correction(thread, trigger, original)

    response = _post_route(_client(), draft_id, auth_headers, key=str(uuid.uuid4()))

    assert response.status_code == 200, response.text
    posted = VoucherRepository.get(draft_id)
    assert posted.status == VoucherStatus.POSTED
    assert (posted.series.value, posted.number) == ("B", 1)
    assert ThreadDraftRepository.get(draft_id).status == "posted"

    [entry] = _history(original.id)
    assert entry.corrected_voucher_id == draft_id
    assert entry.change_type == "multiple"
    assert entry.corrected_by == "api"
    assert entry.was_successful is None or entry.was_successful
    assert entry.original_data["id"] == original.id
    assert [r["account_code"] for r in entry.original_data["rows"]] == [
        "6110",
        "2640",
        "1930",
    ]
    # The corrected rows are the agent's -- never the reversal.
    assert [
        (r["account_code"], r["debit"], r["credit"])
        for r in entry.corrected_data["rows"]
    ] == [("6110", 89600, 0), ("1930", 0, 89600)]
    # "How the voucher should have looked": the original, corrected.
    assert entry.corrected_data["description"] == original.description
    assert entry.corrected_data["correction_voucher_id"] == draft_id
    assert entry.correction_reason == (
        "Rättelse: kontorsmaterial utan avdragsgill moms"
    )

    [receipt] = _receipts(thread)
    assert receipt.body["title"] == "B-1 postad · rättar A-1"
    # Every account the reversal or the corrected rows touch, once each.
    assert [r["key"] for r in receipt.body["rows"]] == ["6110", "2640", "1930"]
    assert receipt.traces[:2] == [
        {
            "tool": "posta_utkast",
            "label": "verifikation postad",
            "detail": "B-1",
            "voucher_id": draft_id,
        },
        {
            "tool": "rattar",
            "label": "rättar A-1",
            "detail": "A-1",
            "voucher_id": original.id,
        },
    ]
    assert receipt.traces[-1] == {"tool": "vantar", "label": "0 kvar"}


def test_case_37_a_plain_draft_gets_no_correction_chip(auth_headers):
    thread, period, trigger = _books()
    draft_id = _proposed(thread, period, trigger)

    assert _post_route(_client(), draft_id, auth_headers).status_code == 200

    [receipt] = _receipts(thread)
    assert receipt.body["title"] == "A-1 postad"
    assert "rattar" not in [t["tool"] for t in receipt.traces]
    assert _count("correction_history") == 0


def test_case_37_a_correction_note_gives_the_reason(today, auth_headers):
    thread, september, trigger = _books()
    original = _original(september)
    note = _note(original)
    draft_id = _proposed_correction(
        thread, trigger, original, correction_note_id=note.id
    )

    assert _post_route(_client(), draft_id, auth_headers).status_code == 200

    [entry] = _history(original.id)
    assert entry.correction_reason == (
        "Rättelse: kontorsmaterial utan avdragsgill moms · notering: Fel moms"
    )


def test_case_38_a_failed_history_rolls_back_the_whole_posting(
    today, monkeypatch, auth_headers
):
    from repositories.accounting_correction_repo import AccountingCorrectionRepository

    thread, september, trigger = _books()
    original = _original(september)
    note = _note(original)
    draft_id = _proposed_correction(
        thread, trigger, original, correction_note_id=note.id
    )
    key = str(uuid.uuid4())

    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(AccountingCorrectionRepository, "create", broken)
    response = _post_route(_client(), draft_id, auth_headers, key=key)

    assert response.status_code == 500
    draft = VoucherRepository.get(draft_id)
    assert draft.status == VoucherStatus.DRAFT
    assert draft.number is None
    assert ThreadDraftRepository.get(draft_id).status == "pending"
    assert _note_status(note.id).status == "pending"
    assert _count("correction_history") == 0
    assert _receipts(thread) == []

    # Nothing was used up: the next try takes B-1, with its history.
    monkeypatch.undo()
    retry = _post_route(_client(), draft_id, auth_headers, key=key)
    assert retry.status_code == 200, retry.text
    assert retry.json()["number"] == 1
    assert len(_history(original.id)) == 1


@pytest.mark.parametrize("status", ["pending", "suggested"])
def test_case_39_the_note_is_applied_with_the_posting(today, auth_headers, status):
    thread, september, trigger = _books()
    original = _original(september)
    note = _note(original, status)
    draft_id = _proposed_correction(
        thread, trigger, original, correction_note_id=note.id
    )
    client = _client()
    decision_id = f"correction:{note.id}"

    def open_ids():
        response = client.get("/api/v1/decisions", headers=auth_headers)
        assert response.status_code == 200, response.text
        return [d["id"] for d in response.json()["decisions"]]

    # The proposal leaves the note as it was: only the posting moves it,
    # so the old page's approve cannot post the thread's draft past the hooks.
    assert _note_status(note.id).status == status
    assert decision_id in open_ids()
    waiting_before = DecisionService().count_waiting(thread.view_key)

    assert _post_route(client, draft_id, auth_headers).status_code == 200

    applied = _note_status(note.id)
    assert applied.status == "applied"
    assert applied.resolved_at is not None
    if status == "pending":
        assert applied.suggested_voucher_id == draft_id
    assert decision_id not in open_ids()
    # The note and its proposal were one thing waiting; now none.
    assert waiting_before == 1
    assert DecisionService().count_waiting(thread.view_key) == 0
    [receipt] = _receipts(thread)
    assert receipt.traces[-1] == {"tool": "vantar", "label": "0 kvar"}


def test_case_39_a_note_closed_meanwhile_refuses_the_posting(today, auth_headers):
    thread, september, trigger = _books()
    original = _original(september)
    note = _note(original)
    draft_id = _proposed_correction(
        thread, trigger, original, correction_note_id=note.id
    )
    db.execute(
        "UPDATE correction_notes SET status = 'dismissed' WHERE id = ?", (note.id,)
    )
    db.commit()

    response = _post_route(_client(), draft_id, auth_headers)

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "correction_note_mismatch"
    assert VoucherRepository.get(draft_id).number is None
    assert _count("correction_history") == 0
    assert ThreadDraftRepository.get(draft_id).last_error_code == (
        "correction_note_mismatch"
    )


def test_case_41_answering_a_correction_decision_points_at_the_chat(auth_headers):
    thread, september, trigger = _books()
    original = _original(september)
    note = _note(original)

    response = _client().post(
        f"/api/v1/decisions/correction:{note.id}/answer",
        json={"free_text": "Rätta den."},
        headers=auth_headers,
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "decision_not_answerable"
    assert "Verifikationers chatt" in detail["details"]
    assert "bocker.verifikationer" in detail["details"]
    assert f"correction_of={original.id}" in detail["details"]
    assert f"correction_note_id={note.id}" in detail["details"]
    assert "/suggest" not in detail["details"]


def test_case_43_posta_verifikation_has_no_correction_of():
    from services.agent_tools import PostaVerifikationArgs

    assert "correction_of" not in PostaVerifikationArgs.model_fields
    assert "correction_note_id" not in PostaVerifikationArgs.model_fields
    [tool] = [t for t in AGENT_TOOL_DEFINITIONS if t["name"] == "posta_verifikation"]
    assert "correction_of" not in json.dumps(tool["input_schema"])


def test_las_korrigeringar_gives_a_vouchers_open_notes(today):
    from services.agent_tools import LasKorrigeringarArgs, _run_las_korrigeringar

    thread, september, trigger = _books()
    original = _original(september)
    other = _original(september, day=19)
    # One active note per voucher (migration 022): the closed ones first.
    _note(original, "dismissed")
    _note(original, "applied")
    pending = _note(original)
    _note(other)

    result = _run_las_korrigeringar(
        LasKorrigeringarArgs(voucher_id=original.id),
        actor="agent",
        capabilities=_capabilities(),
    )

    assert result["voucher_id"] == original.id
    assert result["history"] == []
    assert [(n["id"], n["status"], n["text"]) for n in result["open_notes"]] == [
        (pending.id, "pending", "Fel moms")
    ]
    # Without voucher_id the answer is the history list, as before.
    assert (
        _run_las_korrigeringar(
            LasKorrigeringarArgs(), actor="agent", capabilities=_capabilities()
        )
        == []
    )


def test_las_korrigeringar_lists_a_suggested_note_too(today):
    from services.agent_tools import LasKorrigeringarArgs, _run_las_korrigeringar

    thread, september, trigger = _books()
    original = _original(september)
    note = _note(original, "suggested")

    result = _run_las_korrigeringar(
        LasKorrigeringarArgs(voucher_id=original.id),
        actor="agent",
        capabilities=_capabilities(),
    )

    assert [(n["id"], n["status"]) for n in result["open_notes"]] == [
        (note.id, "suggested")
    ]


# The date bug F11 found: `/correct`, the old page's `suggest` and
# `create_draft` dated the B voucher with the original's date, so a
# correction of a voucher in a locked period landed in a later period with a
# date outside it.


def _june_locked_september_open():
    thread, september, trigger = _books()
    june = _add_period(thread, 6)
    original = _original(june)
    _lock(june)
    return september, original


def test_correct_route_books_a_locked_original_in_the_open_period(today, auth_headers):
    september, original = _june_locked_september_open()

    response = _client().post(
        f"/api/v1/vouchers/{original.id}/correct",
        json={"corrected_rows": _CORRECTED_ROWS, "reason": "Fel moms"},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    correction = VoucherRepository.get(response.json()["id"])
    assert correction.status == VoucherStatus.POSTED
    assert correction.period_id == september.id
    assert correction.date == date(2026, 9, 23)
    assert _history(original.id)[0].correction_reason == "Fel moms"


def test_correct_route_takes_the_periods_last_day_when_today_is_outside(
    today, auth_headers
):
    september, original = _june_locked_september_open()
    today(date(2026, 10, 2))

    response = _client().post(
        f"/api/v1/vouchers/{original.id}/correct",
        json={"corrected_rows": _CORRECTED_ROWS, "reason": "Fel moms"},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["date"] == "2026-09-30"


def test_note_suggest_and_create_draft_book_a_locked_original_in_the_open_period(
    today,
):
    from services.correction_notes import CorrectionNoteService

    september, original = _june_locked_september_open()
    note = _note(original)
    rows = LedgerService.reversal_rows(original) + _CORRECTED_ROWS
    service = CorrectionNoteService()

    suggested, draft = service.suggest(original.id, note.id, rows)
    assert (draft.period_id, draft.date) == (september.id, date(2026, 9, 23))
    posted = service.approve(original.id, note.id)
    assert posted.status == VoucherStatus.POSTED

    other = service.create_draft(original.id, rows)
    assert (other.period_id, other.date) == (september.id, date(2026, 9, 23))


def test_correct_route_rolls_back_when_the_history_fails(
    today, monkeypatch, auth_headers
):
    """`/correct`'s choice (F12): a correction without its history is not
    posted. The history used to be swallowed; now the whole correction,
    number included, rolls back and the answer is `500`."""
    from repositories.accounting_correction_repo import AccountingCorrectionRepository

    thread, september, trigger = _books()
    original = _original(september)

    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(AccountingCorrectionRepository, "create", broken)
    response = _client().post(
        f"/api/v1/vouchers/{original.id}/correct",
        json={"corrected_rows": _CORRECTED_ROWS, "reason": "Fel moms"},
        headers=auth_headers,
    )

    assert response.status_code == 500
    assert _count("vouchers") == 1
    assert _count("correction_history") == 0


# --- F14: vyns meta (testfall 42) ---------------------------------------------


def _list_vouchers(client, headers, **params):
    response = client.get("/api/v1/vouchers", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return {v["id"]: v for v in response.json()["vouchers"]}


def test_case_42_corrected_by_and_corrects_in_the_list(today, auth_headers):
    thread, september, trigger = _books()
    original = _original(september)
    untouched = _original(september, day=19)
    draft_id = _proposed_correction(thread, trigger, original)
    client = _client()
    assert _post_route(client, draft_id, auth_headers).status_code == 200

    listed = _list_vouchers(client, auth_headers, status="posted")

    assert listed[original.id]["corrected_by"] == {
        "id": draft_id,
        "series": "B",
        "number": 1,
    }
    assert listed[original.id]["corrects"] is None
    assert listed[draft_id]["corrects"] == {
        "id": original.id,
        "series": "A",
        "number": 1,
    }
    assert listed[draft_id]["corrected_by"] is None
    assert listed[untouched.id]["corrected_by"] is None
    assert listed[untouched.id]["corrects"] is None
    # The single read carries the same fields.
    single = client.get(f"/api/v1/vouchers/{original.id}", headers=auth_headers)
    assert single.json()["corrected_by"]["number"] == 1


def test_case_42_a_waiting_correction_is_not_corrected_by(today, auth_headers):
    thread, september, trigger = _books()
    original = _original(september)
    draft_id = _proposed_correction(thread, trigger, original)

    listed = _list_vouchers(_client(), auth_headers)

    assert listed[original.id]["corrected_by"] is None
    # The draft already says what it corrects; it just has no number yet.
    assert listed[draft_id]["corrects"] == {
        "id": original.id,
        "series": "A",
        "number": 1,
    }
    assert listed[draft_id]["number"] is None


def test_case_42_the_list_does_not_query_per_row(today, monkeypatch, auth_headers):
    """No N+1 (SPEC-oversikt §3): the number of statements a page costs does
    not grow with the number of vouchers on it."""
    thread, september, trigger = _books()
    original = _original(september)
    draft_id = _proposed_correction(thread, trigger, original)
    client = _client()
    assert _post_route(client, draft_id, auth_headers).status_code == 200

    real_execute = db.execute

    def statements_for_one_page() -> list:
        statements: list = []

        def counting(sql, *args, **kwargs):
            statements.append(sql)
            return real_execute(sql, *args, **kwargs)

        monkeypatch.setattr(db, "execute", counting)
        try:
            _list_vouchers(client, auth_headers, status="posted")
        finally:
            monkeypatch.setattr(db, "execute", real_execute)
        return statements

    few = statements_for_one_page()
    for day in (19, 20, 21, 22):
        _original(september, day=day)
    many = statements_for_one_page()

    assert len(many) == len(few)
    assert len([s for s in many if "FROM vouchers" in s]) <= 2


def test_get_drafts_names_the_note_a_correction_answers(today, auth_headers):
    """F14: the view folds a waiting correction into the `correction:{note}`
    decision it answers, as `count_waiting` does (§11.1, §11.3)."""
    thread, september, trigger = _books()
    original = _original(september)
    note = _note(original)
    draft_id = _proposed_correction(
        thread, trigger, original, correction_note_id=note.id
    )

    [draft] = _get_drafts(_client(), auth_headers, view_key=thread.view_key).json()[
        "drafts"
    ]

    assert draft["draft_id"] == draft_id
    assert draft["correction_note_id"] == note.id
