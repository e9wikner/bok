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
        return thread, _args(period, correction_of="v-118"), "not_implemented"
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
