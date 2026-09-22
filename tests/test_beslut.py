"""Tests for the `beslut` module (docs/redesign/SPEC-beslut.md).

Grows across tasks B1-B12 of `tasks/beslut/todo.md`; each task gets its own
section so the file stays navigable. Test case numbers refer to the table in
SPEC-beslut.md §9.

Per SPEC §9 no LLM is ever called from a test.
"""

import sqlite3
import uuid
from datetime import date, datetime

import pytest

from db.database import db
from repositories.period_repo import PeriodRepository
from repositories.thread_repo import ThreadRepository

pytestmark = pytest.mark.usefixtures("test_db")


# --- helpers ----------------------------------------------------------------


def _fiscal_year(start: date = date(2026, 1, 1), end: date = date(2026, 12, 31)):
    """A fiscal year to hang a thread off — `threads.fiscal_year_id` is a
    real foreign key, so no test may invent an id."""
    return PeriodRepository.create_fiscal_year(start_date=start, end_date=end)


def _thread_and_post(view_key: str = "bocker.verifikationer"):
    """A thread with one `decision` post in it — `decisions.thread_id` and
    `decisions.post_id` are real foreign keys, so no test may invent them."""
    fy = _fiscal_year()
    thread = ThreadRepository.get_or_create(
        view_key=view_key,
        fiscal_year_id=fy.id,
        model="opencode/claude-opus-5",
    )
    post = ThreadRepository.add_post(
        thread_id=thread.id,
        post_type="decision",
        actor="agent",
        body={"title": "Kortköp Elektronikhuset"},
    )
    return thread, post


def _decision_row(thread_id: str, post_id: str, view_key: str, **overrides) -> dict:
    """A valid `decisions` row as a column->value mapping, so a test can
    override exactly the column it means to break."""
    row = {
        "id": str(uuid.uuid4()),
        "thread_id": thread_id,
        "post_id": post_id,
        "view_key": view_key,
        "kind": "abstention",
        "status": "open",
        "title": "Kortköp Elektronikhuset",
        "amount_ore": 448000,
        "reason": "Kvittot saknas och beloppet ligger nära gränsen.",
        "consequence": "Ingenting är bokfört.",
        "created_at": datetime.now(),
    }
    row.update(overrides)
    return row


def _insert_decision(**columns) -> None:
    names = ", ".join(columns.keys())
    placeholders = ", ".join("?" for _ in columns)
    db.execute(
        f"INSERT INTO decisions ({names}) VALUES ({placeholders})",
        tuple(columns.values()),
    )
    db.commit()


def _option_row(decision_id: str, position: int, **overrides) -> dict:
    """A valid `decision_options` row as a column->value mapping."""
    row = {
        "id": str(uuid.uuid4()),
        "decision_id": decision_id,
        "position": position,
        "title": "Förbrukningsinventarier",
        "account": "5410",
        "amount_ore": 358400,
        "rationale": "Kostnadsförs direkt i juni.",
        "recommended": 0,
        "is_exit": 0,
    }
    row.update(overrides)
    return row


def _insert_option(**columns) -> None:
    names = ", ".join(columns.keys())
    placeholders = ", ".join("?" for _ in columns)
    db.execute(
        f"INSERT INTO decision_options ({names}) VALUES ({placeholders})",
        tuple(columns.values()),
    )
    db.commit()


# --- B1: migration 026 (SPEC §4, testfall 1-4) -------------------------------


class TestMigration026:
    def test_decisions_and_decision_options_exist(self):
        tables = {
            row["name"]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert "decisions" in tables
        assert "decision_options" in tables

    def test_a_valid_decision_with_valid_options_is_accepted(self):
        """Proves the rows below aren't rejected by something other than
        the constraint each test means to exercise."""
        thread, post = _thread_and_post()
        row = _decision_row(thread.id, post.id, thread.view_key)
        _insert_decision(**row)

        _insert_option(**_option_row(row["id"], 1, is_exit=0))
        _insert_option(**_option_row(row["id"], 2, title="Annat konto", is_exit=1))

        stored = db.execute(
            "SELECT * FROM decisions WHERE id = ?", (row["id"],)
        ).fetchone()
        assert stored["status"] == "open"
        options = db.execute(
            "SELECT * FROM decision_options WHERE decision_id = ? ORDER BY position",
            (row["id"],),
        ).fetchall()
        assert len(options) == 2

    def test_case_1_two_decisions_on_the_same_post_are_rejected(self):
        """SPEC §4: `UNIQUE (post_id)` — one `decision` post carries exactly
        one decision row."""
        thread, post = _thread_and_post()
        _insert_decision(**_decision_row(thread.id, post.id, thread.view_key))

        with pytest.raises(sqlite3.IntegrityError):
            _insert_decision(**_decision_row(thread.id, post.id, thread.view_key))
        db.rollback()

    def test_case_2_answered_without_answered_at_is_rejected(self):
        """SPEC §4: `CHECK (status != 'answered' OR answered_at IS NOT NULL)`."""
        thread, post = _thread_and_post()

        with pytest.raises(sqlite3.IntegrityError):
            _insert_decision(
                **_decision_row(
                    thread.id,
                    post.id,
                    thread.view_key,
                    status="answered",
                    answered_at=None,
                    answer_text="Ja, det är rätt konto.",
                )
            )
        db.rollback()

    def test_case_3_answered_without_an_option_or_free_text_is_rejected(self):
        """SPEC §4: `CHECK (status != 'answered' OR answer_option_id IS NOT
        NULL OR answer_text IS NOT NULL)` — an `answered_at` alone is not an
        answer."""
        thread, post = _thread_and_post()

        with pytest.raises(sqlite3.IntegrityError):
            _insert_decision(
                **_decision_row(
                    thread.id,
                    post.id,
                    thread.view_key,
                    status="answered",
                    answered_at=datetime.now(),
                    answer_option_id=None,
                    answer_text=None,
                )
            )
        db.rollback()

    def test_case_4_a_fourth_kind_is_rejected(self):
        thread, post = _thread_and_post()

        with pytest.raises(sqlite3.IntegrityError):
            _insert_decision(
                **_decision_row(thread.id, post.id, thread.view_key, kind="urgent")
            )
        db.rollback()

    def test_case_4_a_fourth_status_is_rejected(self):
        thread, post = _thread_and_post()

        with pytest.raises(sqlite3.IntegrityError):
            _insert_decision(
                **_decision_row(thread.id, post.id, thread.view_key, status="archived")
            )
        db.rollback()

    def test_duplicate_position_on_the_same_decision_is_rejected(self):
        """SPEC §4: `UNIQUE (decision_id, position)` — the order options were
        laid out in is part of the contract (last option is always a way
        out)."""
        thread, post = _thread_and_post()
        row = _decision_row(thread.id, post.id, thread.view_key)
        _insert_decision(**row)
        _insert_option(**_option_row(row["id"], 1))

        with pytest.raises(sqlite3.IntegrityError):
            _insert_option(**_option_row(row["id"], 1, title="Annat konto"))
        db.rollback()

    def test_recommended_outside_zero_or_one_is_rejected(self):
        thread, post = _thread_and_post()
        row = _decision_row(thread.id, post.id, thread.view_key)
        _insert_decision(**row)

        with pytest.raises(sqlite3.IntegrityError):
            _insert_option(**_option_row(row["id"], 1, recommended=2))
        db.rollback()

    def test_is_exit_outside_zero_or_one_is_rejected(self):
        thread, post = _thread_and_post()
        row = _decision_row(thread.id, post.id, thread.view_key)
        _insert_decision(**row)

        with pytest.raises(sqlite3.IntegrityError):
            _insert_option(**_option_row(row["id"], 1, is_exit=-1))
        db.rollback()
