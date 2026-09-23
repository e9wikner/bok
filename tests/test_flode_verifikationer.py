"""Tests for the `flode-verifikationer` module
(docs/redesign/SPEC-flode-verifikationer.md).

Grows across tasks F5-F12 of `tasks/flode-verifikationer/todo.md`; each task
gets its own section. Numbering (F1-F3) lives in `tests/test_numrering.py`.

Per the spec no LLM is ever called from a test.
"""

import sqlite3
import uuid
from datetime import date, datetime, timedelta

import pytest

from db.database import db
from domain.models import ThreadDraft
from repositories.period_repo import PeriodRepository
from repositories.thread_draft_repo import (
    ThreadDraftRepository,
    ThreadDraftTransitionError,
)
from repositories.thread_repo import ThreadRepository

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
