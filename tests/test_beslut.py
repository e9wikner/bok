"""Tests for the `beslut` module (docs/redesign/SPEC-beslut.md).

Grows across tasks B1-B12 of `tasks/beslut/todo.md`; each task gets its own
section so the file stays navigable. Test case numbers refer to the table in
SPEC-beslut.md §9.

Per SPEC §9 no LLM is ever called from a test.
"""

import sqlite3
import uuid
from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import Any, Dict, cast

import pytest

from db.database import db
from domain.models import Decision, DecisionOption
from domain.validation import ValidationError
from repositories.decision_repo import DecisionRepository
from repositories.period_repo import PeriodRepository
from repositories.thread_repo import ThreadRepository
from services.agent_tools import (
    AGENT_TOOL_DEFINITIONS,
    RegistreraAvstaendeArgs,
    execute_tool,
)
from services.decision_service import (
    DecisionAlreadyAnswered,
    DecisionError,
    DecisionNotAnswerable,
    DecisionNotFound,
    DecisionService,
)
from services.llm import LLMCapabilities, LLMTurn, StopReason, ToolCall, Usage
from services.thread_stream import ThreadTurnRunner

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


# --- B2: DecisionRepository och domänmodellerna (SPEC §4, testfall 5, 10) ---

_fiscal_year_counter = iter(range(2000, 2100))


def _new_thread_and_post(view_key: str = "bocker.verifikationer"):
    """Like `_thread_and_post`, but safe to call more than once in the same
    test: `fiscal_years` has a `UNIQUE (start_date, end_date)`, so several
    decisions in one test each get their own fiscal year rather than
    colliding on `_thread_and_post`'s fixed 2026 range."""
    year = next(_fiscal_year_counter)
    fy = _fiscal_year(start=date(year, 1, 1), end=date(year, 12, 31))
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


def _create_decision(thread, post, **overrides) -> Decision:
    """A `decisions` row through the repository, not `_insert_decision` —
    B2's tests exercise `DecisionRepository`, not the raw schema B1 already
    covered."""
    fields = dict(
        thread_id=thread.id,
        post_id=post.id,
        view_key=thread.view_key,
        kind="abstention",
        title="Kortköp Elektronikhuset",
        reason="Kvittot saknas och beloppet ligger nära gränsen.",
        consequence="Ingenting är bokfört.",
    )
    fields.update(overrides)
    return DecisionRepository.create(**fields)


class TestDecisionRepositoryCreateAndOptions:
    def test_create_add_options_get_round_trip(self):
        """`create` + `add_options` + `get` returns the options back in
        `position` order, with `recommended`/`is_exit` as `bool` (they are
        `INTEGER 0/1` in SQL — the repository converts, per the brief)."""
        thread, post = _new_thread_and_post()
        decision = _create_decision(thread, post, amount_ore=448000)

        options_in = [
            DecisionOption(
                id="ignored",
                decision_id="ignored",
                position=0,
                title="Förbrukningsinventarier",
                rationale="Kostnadsförs direkt i juni.",
                account="5410",
                amount_ore=358400,
                recommended=True,
                is_exit=False,
            ),
            {
                "title": "Annat konto",
                "rationale": "Det är ett annat köp.",
                "is_exit": True,
            },
        ]
        created = DecisionRepository.add_options(decision.id, options_in)
        assert [o.position for o in created] == [1, 2]

        fetched = DecisionRepository.get(decision.id)
        assert fetched is not None
        assert [o.title for o in fetched.options] == [
            "Förbrukningsinventarier",
            "Annat konto",
        ]
        assert [o.position for o in fetched.options] == [1, 2]
        assert fetched.options[0].recommended is True
        assert isinstance(fetched.options[0].recommended, bool)
        assert fetched.options[1].is_exit is True
        assert isinstance(fetched.options[1].is_exit, bool)
        assert fetched.options[0].account == "5410"
        assert fetched.options[1].account is None

    def test_get_by_post_id(self):
        thread, post = _new_thread_and_post()
        decision = _create_decision(thread, post)

        by_post = DecisionRepository.get_by_post_id(post.id)
        assert by_post is not None
        assert by_post.id == decision.id

        assert DecisionRepository.get_by_post_id(str(uuid.uuid4())) is None

    def test_get_unknown_id_returns_none(self):
        assert DecisionRepository.get(str(uuid.uuid4())) is None


class TestDecisionRepositoryListDecisions:
    def test_case_5_open_decisions_come_back_oldest_first(self):
        """SPEC §9 testfall 5. `created_at` is set explicitly via a direct
        `UPDATE`, per the brief, since the repository always stamps "now"
        and the point here is the ordering, not the clock."""
        rows = []
        for offset_days in (5, 1, 3):
            thread, post = _new_thread_and_post()
            decision = _create_decision(thread, post, title=f"Beslut -{offset_days}")
            created_at = datetime.now() - timedelta(days=offset_days)
            db.execute(
                "UPDATE decisions SET created_at = ? WHERE id = ?",
                (created_at, decision.id),
            )
            db.commit()
            rows.append((offset_days, decision.id))

        expected = [decision_id for _, decision_id in sorted(rows, reverse=True)]
        result = DecisionRepository.list_decisions(status="open")
        assert [d.id for d in result] == expected

    def test_view_key_filters(self):
        thread_a, post_a = _new_thread_and_post(view_key="bocker.verifikationer")
        thread_b, post_b = _new_thread_and_post(view_key="bocker.balans")
        _create_decision(thread_a, post_a, title="A")
        decision_b = _create_decision(thread_b, post_b, title="B")

        result = DecisionRepository.list_decisions(view_key="bocker.balans")
        assert [d.id for d in result] == [decision_b.id]

    def test_status_as_a_sequence_filters(self):
        thread_a, post_a = _new_thread_and_post()
        thread_b, post_b = _new_thread_and_post()
        thread_c, post_c = _new_thread_and_post()
        open_decision = _create_decision(thread_a, post_a, title="Open")
        superseded = _create_decision(thread_b, post_b, title="Superseded")
        DecisionRepository.set_status(superseded.id, "superseded")
        answered = _create_decision(thread_c, post_c, title="Answered")
        answer_post = ThreadRepository.add_post(
            thread_id=thread_c.id,
            actor="stefan",
            post_type="user_text",
            body={"text": "Ja, det stämmer."},
        )
        DecisionRepository.set_answer(
            answered.id,
            answered_at=datetime.now(),
            answered_by="stefan",
            answer_post_id=answer_post.id,
            answer_text="Ja, det stämmer.",
        )

        result = DecisionRepository.list_decisions(status=("open", "answered"))
        ids = {d.id for d in result}
        assert ids == {open_decision.id, answered.id}
        assert superseded.id not in ids

    def test_status_none_returns_every_status(self):
        thread_a, post_a = _new_thread_and_post()
        thread_b, post_b = _new_thread_and_post()
        open_decision = _create_decision(thread_a, post_a)
        superseded = _create_decision(thread_b, post_b)
        DecisionRepository.set_status(superseded.id, "superseded")

        result = DecisionRepository.list_decisions(status=None)
        ids = {d.id for d in result}
        assert ids == {open_decision.id, superseded.id}

    def test_limit_and_offset_page_through_the_ordering(self):
        decision_ids = []
        for offset_days in (4, 3, 2, 1):
            thread, post = _new_thread_and_post()
            decision = _create_decision(thread, post)
            created_at = datetime.now() - timedelta(days=offset_days)
            db.execute(
                "UPDATE decisions SET created_at = ? WHERE id = ?",
                (created_at, decision.id),
            )
            db.commit()
            decision_ids.append(decision.id)

        full = DecisionRepository.list_decisions(status="open")
        assert [d.id for d in full] == decision_ids

        page1 = DecisionRepository.list_decisions(status="open", limit=2, offset=0)
        page2 = DecisionRepository.list_decisions(status="open", limit=2, offset=2)
        assert [d.id for d in page1] == decision_ids[0:2]
        assert [d.id for d in page2] == decision_ids[2:4]


class TestDecisionRepositoryCount:
    def test_count_open_counts_only_open(self):
        thread_a, post_a = _new_thread_and_post()
        thread_b, post_b = _new_thread_and_post()
        thread_c, post_c = _new_thread_and_post()
        _create_decision(thread_a, post_a)
        superseded = _create_decision(thread_b, post_b)
        DecisionRepository.set_status(superseded.id, "superseded")
        answered = _create_decision(thread_c, post_c)
        answer_post = ThreadRepository.add_post(
            thread_id=thread_c.id,
            actor="stefan",
            post_type="user_text",
            body={"text": "Ja."},
        )
        DecisionRepository.set_answer(
            answered.id,
            answered_at=datetime.now(),
            answered_by="stefan",
            answer_post_id=answer_post.id,
            answer_text="Ja.",
        )

        assert DecisionRepository.count_open() == 1
        assert DecisionRepository.count(status="open") == 1
        assert DecisionRepository.count() == 3
        assert DecisionRepository.count(status=("answered", "superseded")) == 2


class TestDecisionRepositorySetAnswerAndSetStatus:
    def test_set_answer_with_option_sets_status_and_all_five_columns(self):
        thread, post = _new_thread_and_post()
        decision = _create_decision(thread, post)
        options = DecisionRepository.add_options(
            decision.id,
            [
                {
                    "title": "Förbrukningsinventarier",
                    "rationale": "Kostnadsförs direkt.",
                    "account": "5410",
                    "amount_ore": 358400,
                    "is_exit": False,
                },
                {
                    "title": "Annat konto",
                    "rationale": "Det är ett annat köp.",
                    "is_exit": True,
                },
            ],
        )
        answer_post = ThreadRepository.add_post(
            thread_id=thread.id,
            actor="stefan",
            post_type="user_text",
            body={"text": "Förbrukningsinventarier, 5410."},
        )
        answered_at = datetime.now()

        updated = DecisionRepository.set_answer(
            decision.id,
            answered_at=answered_at,
            answered_by="stefan",
            answer_post_id=answer_post.id,
            option_id=options[0].id,
        )

        assert updated is not None
        assert updated.status == "answered"
        assert updated.answered_by == "stefan"
        assert updated.answer_option_id == options[0].id
        assert updated.answer_post_id == answer_post.id
        assert updated.answer_text is None
        assert updated.answered_at is not None

    def test_set_answer_with_free_text_sets_the_same_five_columns(self):
        thread, post = _new_thread_and_post()
        decision = _create_decision(thread, post)
        answer_post = ThreadRepository.add_post(
            thread_id=thread.id,
            actor="stefan",
            post_type="user_text",
            body={"text": "Nej, boka om till 6250."},
        )

        updated = DecisionRepository.set_answer(
            decision.id,
            answered_at=datetime.now(),
            answered_by="stefan",
            answer_post_id=answer_post.id,
            answer_text="Nej, boka om till 6250.",
        )

        assert updated is not None
        assert updated.status == "answered"
        assert updated.answer_text == "Nej, boka om till 6250."
        assert updated.answer_option_id is None
        assert updated.answer_post_id == answer_post.id

    def test_set_status_supersedes_without_touching_the_post(self):
        thread, post = _new_thread_and_post()
        decision = _create_decision(thread, post)

        updated = DecisionRepository.set_status(decision.id, "superseded")

        assert updated is not None
        assert updated.status == "superseded"
        # The post the human saw is untouched — SPEC §4: superseded leaves
        # the card in the thread and only takes it out of the queue.
        stored_post = ThreadRepository.get_post(post.id)
        assert stored_post is not None
        assert stored_post.body == post.body


class TestDecisionRepositoryReminders:
    def test_list_due_reminders_and_set_reminded(self):
        thread_old, post_old = _new_thread_and_post()
        thread_fresh, post_fresh = _new_thread_and_post()
        old_decision = _create_decision(thread_old, post_old, title="Gammalt")
        _create_decision(thread_fresh, post_fresh, title="Färskt")

        eight_days_ago = datetime.now() - timedelta(days=8)
        db.execute(
            "UPDATE decisions SET created_at = ? WHERE id = ?",
            (eight_days_ago, old_decision.id),
        )
        db.commit()

        threshold = datetime.now() - timedelta(days=7)
        due = DecisionRepository.list_due_reminders(before=threshold)
        assert [d.id for d in due] == [old_decision.id]

        DecisionRepository.set_reminded(old_decision.id, datetime.now())

        due_after = DecisionRepository.list_due_reminders(before=threshold)
        assert due_after == []

    def test_answered_decisions_are_never_due(self):
        thread, post = _new_thread_and_post()
        decision = _create_decision(thread, post)
        old = datetime.now() - timedelta(days=10)
        db.execute(
            "UPDATE decisions SET created_at = ? WHERE id = ?", (old, decision.id)
        )
        db.commit()
        answer_post = ThreadRepository.add_post(
            thread_id=thread.id,
            actor="stefan",
            post_type="user_text",
            body={"text": "Ja."},
        )
        DecisionRepository.set_answer(
            decision.id,
            answered_at=datetime.now(),
            answered_by="stefan",
            answer_post_id=answer_post.id,
            answer_text="Ja.",
        )

        due = DecisionRepository.list_due_reminders(before=datetime.now())
        assert due == []


class TestDecisionRepositoryOptionsLookup:
    def test_get_option_and_list_options(self):
        thread, post = _new_thread_and_post()
        decision = _create_decision(thread, post)
        created = DecisionRepository.add_options(
            decision.id,
            [
                {
                    "title": "Förbrukningsinventarier",
                    "rationale": "…",
                    "is_exit": False,
                },
                {"title": "Annat konto", "rationale": "…", "is_exit": True},
            ],
        )

        fetched = DecisionRepository.get_option(created[0].id)
        assert fetched is not None
        assert fetched.title == "Förbrukningsinventarier"

        assert DecisionRepository.get_option(str(uuid.uuid4())) is None

        listed = DecisionRepository.list_options(decision.id)
        assert [o.id for o in listed] == [o.id for o in created]


class TestDecisionRepositoryCommitFalse:
    def test_commit_false_writes_nothing_until_a_commit(self):
        """The premise B3's `answer()` atomicity is built on (§6.2 steps
        4-5, todo.md B3): a `_commit=False` write only exists inside the
        current transaction, and a `db.rollback()` leaves no trace — proven
        here, one layer below the service that will rely on it."""
        thread, post = _new_thread_and_post()
        decision = DecisionRepository.create(
            thread_id=thread.id,
            post_id=post.id,
            view_key=thread.view_key,
            kind="abstention",
            title="Kortköp Elektronikhuset",
            reason="Kvittot saknas.",
            consequence="Ingenting är bokfört.",
            _commit=False,
        )
        DecisionRepository.add_options(
            decision.id,
            [{"title": "Förbrukningsinventarier", "rationale": "…", "is_exit": True}],
            _commit=False,
        )

        db.rollback()

        assert DecisionRepository.get(decision.id) is None
        assert DecisionRepository.list_options(decision.id) == []

    def test_commit_false_on_set_answer_leaves_status_open_until_commit(self):
        thread, post = _new_thread_and_post()
        decision = _create_decision(thread, post)
        answer_post = ThreadRepository.add_post(
            thread_id=thread.id,
            actor="stefan",
            post_type="user_text",
            body={"text": "Ja."},
        )

        DecisionRepository.set_answer(
            decision.id,
            answered_at=datetime.now(),
            answered_by="stefan",
            answer_post_id=answer_post.id,
            answer_text="Ja.",
            _commit=False,
        )
        db.rollback()

        still_open = DecisionRepository.get(decision.id)
        assert still_open is not None
        assert still_open.status == "open"


class TestDecisionOptionChangesTheBooks:
    """SPEC §6.3: `changes_the_books` is `account` set **and** `amount_ore`
    non-zero — checked here with no database at all, four cases."""

    @staticmethod
    def _base() -> DecisionOption:
        return DecisionOption(
            id="o1",
            decision_id="d1",
            position=1,
            title="Förbrukningsinventarier",
            rationale="Kostnadsförs direkt.",
        )

    def test_account_and_amount_changes_the_books(self):
        option = replace(self._base(), account="5410", amount_ore=358400)
        assert option.changes_the_books is True

    def test_account_and_zero_amount_does_not_change_the_books(self):
        option = replace(self._base(), account="5410", amount_ore=0)
        assert option.changes_the_books is False

    def test_amount_without_account_does_not_change_the_books(self):
        option = replace(self._base(), account=None, amount_ore=358400)
        assert option.changes_the_books is False

    def test_neither_account_nor_amount_does_not_change_the_books(self):
        option = replace(self._base(), account=None, amount_ore=None)
        assert option.changes_the_books is False


class TestDecisionAgeDays:
    """SPEC §9 testfall 10. `age_days` is a `Decision` method, checked here
    both without a database (the whole point of keeping the rule in the
    domain) and through the repository's round trip."""

    def test_case_10_age_days_without_a_database(self):
        decision = Decision(
            id="d1",
            thread_id="t1",
            post_id="p1",
            view_key="bocker.verifikationer",
            kind="abstention",
            status="open",
            title="…",
            reason="…",
            consequence="…",
            created_at=datetime(2026, 9, 1, 8, 0, 0),
        )
        assert decision.age_days(today=date(2026, 9, 1)) == 0
        assert decision.age_days(today=date(2026, 9, 8)) == 7
        assert decision.age_days(today=date(2026, 9, 22)) == 21

    def test_age_days_is_never_negative(self):
        decision = Decision(
            id="d1",
            thread_id="t1",
            post_id="p1",
            view_key="bocker.verifikationer",
            kind="abstention",
            status="open",
            title="…",
            reason="…",
            consequence="…",
            created_at=datetime(2026, 9, 22, 8, 0, 0),
        )
        # `today` before `created_at` should not happen, but the domain
        # rule never reports a negative age.
        assert decision.age_days(today=date(2026, 9, 1)) == 0

    def test_age_days_defaults_to_date_today(self):
        decision = Decision(
            id="d1",
            thread_id="t1",
            post_id="p1",
            view_key="bocker.verifikationer",
            kind="abstention",
            status="open",
            title="…",
            reason="…",
            consequence="…",
            created_at=datetime.now(),
        )
        assert decision.age_days() == 0

    def test_case_10_zero_for_a_decision_created_today_via_the_repository(self):
        thread, post = _new_thread_and_post()
        decision = _create_decision(thread, post)

        fetched = DecisionRepository.get(decision.id)
        assert fetched is not None
        assert fetched.age_days() == 0


# --- B3: DecisionService, livscykeln (SPEC §6.2, testfall 15, 17, 18, 32) ---


def _new_thread(view_key: str = "bocker.verifikationer"):
    """A bare thread with no posts yet -- unlike `_new_thread_and_post`
    (B2), which pre-writes a `decision` post for repository-level tests
    that need an existing post to bind a row to. `DecisionService.create`
    writes its own post, so a test of it must start from an empty thread."""
    year = next(_fiscal_year_counter)
    fy = _fiscal_year(start=date(year, 1, 1), end=date(year, 12, 31))
    return ThreadRepository.get_or_create(
        view_key=view_key,
        fiscal_year_id=fy.id,
        model="opencode/claude-opus-5",
    )


class TestDecisionServiceCreateWithoutOptions:
    def test_creates_one_post_and_one_row(self):
        thread = _new_thread()
        service = DecisionService()

        decision = service.create(
            thread,
            title="Kortköp Elektronikhuset",
            reason="Kvittot saknas och beloppet ligger nära gränsen.",
            consequence="Ingenting är bokfört.",
            amount_ore=448000,
        )

        posts = ThreadRepository.list_posts(thread.id)
        assert len(posts) == 1
        assert posts[0].type == "decision"
        assert posts[0].id == decision.post_id

        fetched = DecisionRepository.get(decision.id)
        assert fetched is not None
        assert fetched.view_key == thread.view_key
        assert fetched.status == "open"
        assert fetched.options == []

    def test_decision_post_body_matches_beslutkort_keys(self):
        """Same key set `_decision_body` (services/thread_service.py)
        already produces — `title`, `amount`, `reason`, `source`,
        `consequence` — plus the `decision_id` that makes the card
        answerable without a second request and a join on `post_id`."""
        thread = _new_thread()
        service = DecisionService()

        decision = service.create(
            thread,
            title="Kortköp Elektronikhuset",
            reason="Kvittot saknas.",
            consequence="Ingenting är bokfört.",
            amount_ore=448000,
            source={"kind": "bank_input", "id": "src-1", "date": date(2026, 6, 3)},
        )

        post = ThreadRepository.get_post(decision.post_id)
        assert post is not None
        assert post.body == {
            "decision_id": decision.id,
            "title": "Kortköp Elektronikhuset",
            "amount": 448000,
            "reason": "Kvittot saknas.",
            "source": {"kind": "bank_input", "id": "src-1"},
            "consequence": "Ingenting är bokfört.",
        }
        assert decision.source_kind == "bank_input"
        assert decision.source_id == "src-1"
        assert decision.source_date == date(2026, 6, 3)

    def test_create_with_post_binds_the_given_post_instead_of_writing_a_new_one(self):
        """B6's path: a `decision` post already written elsewhere is bound
        to a new row, rather than `create` writing a second post."""
        thread = _new_thread()
        existing_post = ThreadRepository.add_post(
            thread_id=thread.id,
            post_type="decision",
            actor="agent",
            body={"title": "Kortköp Elektronikhuset"},
        )
        service = DecisionService()

        decision = service.create(
            thread,
            title="Kortköp Elektronikhuset",
            reason="Kvittot saknas.",
            consequence="Ingenting är bokfört.",
            post=existing_post,
        )

        assert decision.post_id == existing_post.id
        posts = ThreadRepository.list_posts(thread.id)
        assert len(posts) == 1
        assert posts[0].id == existing_post.id
        # The already-written post is untouched -- append-only.
        assert posts[0].body == {"title": "Kortköp Elektronikhuset"}


class TestDecisionServiceCreateWithOptions:
    def test_creates_two_posts_a_row_and_the_option_rows(self):
        thread = _new_thread()
        service = DecisionService()

        decision = service.create(
            thread,
            title="Kortköp Elektronikhuset",
            reason="Kvittot saknas.",
            consequence="Ingenting är bokfört.",
            options=[
                {
                    "title": "Förbrukningsinventarier",
                    "account": "5410",
                    "amount_ore": 358400,
                    "rationale": "Kostnadsförs direkt i juni.",
                    "recommended": True,
                    "is_exit": False,
                },
                {
                    "title": "Annat konto",
                    "rationale": "Det är ett annat köp.",
                    "is_exit": True,
                },
            ],
            footnote="Moms 25 % · 896 kr dras av i båda alternativen",
        )

        posts = ThreadRepository.list_posts(thread.id)
        assert [p.type for p in posts] == ["decision", "options"]

        options = DecisionRepository.list_options(decision.id)
        assert len(options) == 2
        assert [o.position for o in options] == [1, 2]
        assert decision.options == options

    def test_options_post_body_matches_spec_section_4_shape(self):
        thread = _new_thread()
        service = DecisionService()

        decision = service.create(
            thread,
            title="Kortköp Elektronikhuset",
            reason="Kvittot saknas.",
            consequence="Ingenting är bokfört.",
            options=[
                {
                    "title": "Förbrukningsinventarier",
                    "account": "5410",
                    "amount_ore": 358400,
                    "rationale": "Kostnadsförs direkt i juni.",
                    "recommended": True,
                    "is_exit": False,
                },
                {
                    "title": "Annat konto",
                    "rationale": "Det är ett annat köp.",
                    "is_exit": True,
                },
            ],
            footnote="Moms 25 % · 896 kr dras av i båda alternativen",
        )

        posts = ThreadRepository.list_posts(thread.id)
        options_post = posts[1]
        assert options_post.type == "options"
        options = DecisionRepository.list_options(decision.id)
        assert options_post.body == {
            "decision_id": decision.id,
            "options": [
                {
                    "option_id": options[0].id,
                    "title": "Förbrukningsinventarier",
                    "account": "5410",
                    "amount_ore": 358400,
                    "rationale": "Kostnadsförs direkt i juni.",
                    "recommended": True,
                    "is_exit": False,
                },
                {
                    "option_id": options[1].id,
                    "title": "Annat konto",
                    "account": None,
                    "amount_ore": None,
                    "rationale": "Det är ett annat köp.",
                    "recommended": False,
                    "is_exit": True,
                },
            ],
            "footnote": "Moms 25 % · 896 kr dras av i båda alternativen",
        }

    def test_no_options_post_when_options_is_empty(self):
        thread = _new_thread()
        service = DecisionService()

        service.create(
            thread,
            title="Kortköp Elektronikhuset",
            reason="Kvittot saknas.",
            consequence="Ingenting är bokfört.",
            options=[],
        )

        posts = ThreadRepository.list_posts(thread.id)
        assert [p.type for p in posts] == ["decision"]


class TestDecisionServiceCreateVerbatimText:
    """SPEC §7.4, testfall 34 (the create() half): `reason`, `consequence`
    and each option's `rationale` come back byte for byte, quotes,
    newlines and Swedish characters included -- no rewording, no
    truncation, no normalisation."""

    _REASON = (
        'Kvittot saknas – kunden skrev "tack" men bifogade inget kvitto.\n'
        "Beloppet 4 480,00 kr ligger nära gränsen för förbrukningsinventarier."
    )
    _CONSEQUENCE = (
        'Ingenting är bokfört.\nBeslutet ligger kvar tills du svarar "ja" eller "nej".'
    )
    _RATIONALE = (
        "Kostnadsförs direkt – momsen (25 %) dras av i juni.\nÅterköp sker inte."
    )

    def test_reason_and_consequence_round_trip_verbatim(self):
        thread = _new_thread()
        service = DecisionService()

        decision = service.create(
            thread,
            title="Kortköp Elektronikhuset",
            reason=self._REASON,
            consequence=self._CONSEQUENCE,
        )

        assert decision.reason == self._REASON
        assert decision.consequence == self._CONSEQUENCE

        fetched = DecisionRepository.get(decision.id)
        assert fetched is not None
        assert fetched.reason == self._REASON
        assert fetched.consequence == self._CONSEQUENCE

        post = ThreadRepository.get_post(decision.post_id)
        assert post is not None
        assert post.body["reason"] == self._REASON
        assert post.body["consequence"] == self._CONSEQUENCE

    def test_option_rationale_round_trips_verbatim(self):
        thread = _new_thread()
        service = DecisionService()

        decision = service.create(
            thread,
            title="Kortköp Elektronikhuset",
            reason="…",
            consequence="…",
            options=[
                {"title": "A", "rationale": self._RATIONALE, "is_exit": False},
                {"title": "B", "rationale": "Väg ut.", "is_exit": True},
            ],
        )

        options = DecisionRepository.list_options(decision.id)
        assert options[0].rationale == self._RATIONALE

        posts = ThreadRepository.list_posts(thread.id)
        options_post = posts[1]
        assert options_post.body["options"][0]["rationale"] == self._RATIONALE


class TestDecisionServiceAnswer:
    def test_answer_requires_exactly_one_of_option_or_free_text(self):
        thread, post = _new_thread_and_post()
        decision = _create_decision(thread, post)
        service = DecisionService()

        with pytest.raises(ValidationError) as neither:
            service.answer(decision.id, actor="stefan")
        assert neither.value.code == "invalid_answer"

        with pytest.raises(ValidationError) as both:
            service.answer(
                decision.id,
                option_id="whatever",
                free_text="Ja.",
                actor="stefan",
            )
        assert both.value.code == "invalid_answer"

    def test_answer_unknown_decision_id_raises_not_found(self):
        service = DecisionService()

        with pytest.raises(DecisionNotFound):
            service.answer(str(uuid.uuid4()), free_text="Ja.", actor="stefan")

    def test_answer_with_option_from_another_decision_is_a_validation_error(self):
        thread_a, post_a = _new_thread_and_post()
        thread_b, post_b = _new_thread_and_post()
        decision_a = _create_decision(thread_a, post_a)
        decision_b = _create_decision(thread_b, post_b)
        options_b = DecisionRepository.add_options(
            decision_b.id,
            [{"title": "Annat konto", "rationale": "…", "is_exit": True}],
        )
        service = DecisionService()

        with pytest.raises(ValidationError) as excinfo:
            service.answer(decision_a.id, option_id=options_b[0].id, actor="stefan")
        assert excinfo.value.code == "invalid_answer"

        # No reply was written to either thread -- rejected before any write.
        assert ThreadRepository.list_posts(thread_a.id) == [post_a]
        fetched_a = DecisionRepository.get(decision_a.id)
        assert fetched_a is not None
        assert fetched_a.status == "open"

    def test_answer_with_option_writes_titled_reply_and_flips_status(self):
        thread, post = _new_thread_and_post()
        decision = _create_decision(thread, post)
        options = DecisionRepository.add_options(
            decision.id,
            [
                {
                    "title": "Förbrukningsinventarier",
                    "account": "5410",
                    "rationale": "…",
                    "is_exit": False,
                },
                {"title": "Annat konto", "rationale": "…", "is_exit": True},
            ],
        )
        service = DecisionService()

        updated, answer_post = service.answer(
            decision.id, option_id=options[0].id, actor="stefan"
        )

        assert updated.status == "answered"
        assert updated.answer_option_id == options[0].id
        assert updated.answer_text is None
        assert updated.answer_post_id == answer_post.id
        assert answer_post.type == "user_text"
        assert answer_post.body == {"text": "Förbrukningsinventarier, 5410."}

    def test_answer_with_free_text_stores_it_verbatim_and_the_reply_matches(self):
        thread, post = _new_thread_and_post()
        decision = _create_decision(thread, post)
        service = DecisionService()
        free_text = 'Nej, boka om till 6250 – "resekostnader", inte 5410.'

        updated, answer_post = service.answer(
            decision.id, free_text=free_text, actor="stefan"
        )

        assert updated.status == "answered"
        assert updated.answer_text == free_text
        assert updated.answer_option_id is None
        assert answer_post.body == {"text": free_text}

    def test_answer_never_starts_a_turn(self):
        """B3's `answer()` only writes the reply and flips status; starting
        `ThreadTurnRunner` is B8's job, after this call returns."""
        thread, post = _new_thread_and_post()
        decision = _create_decision(thread, post)
        service = DecisionService()

        service.answer(decision.id, free_text="Ja.", actor="stefan")

        # Exactly the reply post plus the original decision post -- nothing
        # from a turn (no agent_text/error post exists).
        posts = ThreadRepository.list_posts(thread.id)
        assert [p.type for p in posts] == ["decision", "user_text"]

    def test_case_15_a_second_answer_raises_already_answered_and_writes_no_second_post(
        self,
    ):
        thread, post = _new_thread_and_post()
        decision = _create_decision(thread, post)
        service = DecisionService()

        first, first_post = service.answer(
            decision.id, free_text="Ja, det stämmer.", actor="stefan"
        )

        with pytest.raises(DecisionAlreadyAnswered) as excinfo:
            service.answer(decision.id, free_text="Nej, ångrar mig.", actor="stefan")

        assert excinfo.value.decision.id == decision.id
        assert excinfo.value.decision.answered_at == first.answered_at
        assert excinfo.value.decision.answer_post_id == first_post.id
        assert excinfo.value.decision.answer_text == "Ja, det stämmer."
        assert isinstance(excinfo.value, DecisionError)

        posts = ThreadRepository.list_posts(thread.id)
        user_text_posts = [p for p in posts if p.type == "user_text"]
        assert len(user_text_posts) == 1

    def test_case_17_a_rolled_back_transaction_leaves_no_post_and_status_open(
        self, monkeypatch
    ):
        """SPEC §6.2 steps 4-5 share one transaction: if anything inside it
        fails, neither the reply post nor the status change survives. This
        is not an LLM monkeypatch (SPEC §9's rule is about faking the LLM
        client) -- it patches `DecisionRepository.set_answer` directly to
        simulate a failure between the two writes."""
        thread, post = _new_thread_and_post()
        decision = _create_decision(thread, post)
        service = DecisionService()

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated failure between the two writes")

        monkeypatch.setattr(DecisionRepository, "set_answer", _boom)

        with pytest.raises(RuntimeError):
            service.answer(decision.id, free_text="Ja.", actor="stefan")

        still_open = DecisionRepository.get(decision.id)
        assert still_open is not None
        assert still_open.status == "open"
        assert still_open.answer_post_id is None

        posts = ThreadRepository.list_posts(thread.id)
        assert [p.type for p in posts] == ["decision"]


class TestDecisionServiceCountOpen:
    def test_case_18_an_answered_decision_falls_out_of_open_and_count_open(self):
        thread_a, post_a = _new_thread_and_post()
        thread_b, post_b = _new_thread_and_post()
        decision_a = _create_decision(thread_a, post_a)
        decision_b = _create_decision(thread_b, post_b)
        service = DecisionService()

        assert service.count_open() == 2

        service.answer(decision_a.id, free_text="Ja.", actor="stefan")

        assert service.count_open() == 1
        open_ids = {d.id for d in DecisionRepository.list_decisions(status="open")}
        assert open_ids == {decision_b.id}
        assert decision_a.id not in open_ids


class TestDecisionServiceSupersede:
    def test_case_32_supersede_takes_the_decision_out_of_the_queue_and_leaves_the_post(
        self,
    ):
        thread, post = _new_thread_and_post()
        decision = _create_decision(thread, post)
        service = DecisionService()
        before = ThreadRepository.get_post(post.id)
        assert before is not None

        updated = service.supersede(decision.id)

        assert updated.status == "superseded"
        assert service.count_open() == 0

        after = ThreadRepository.get_post(post.id)
        assert after is not None
        assert after.body == before.body
        assert after == before

    def test_supersede_unknown_id_raises_not_found(self):
        service = DecisionService()
        with pytest.raises(DecisionNotFound):
            service.supersede(str(uuid.uuid4()))


class TestDecisionNotAnswerableIsDefined:
    """B3 defines `DecisionNotAnswerable` but never raises it (that's B7/B8,
    once the synthetic `intake:`/`correction:` ids from the union exist).
    This only checks the shape is right and ready to be raised later."""

    def test_shape_matches_the_other_typed_errors(self):
        error = DecisionNotAnswerable(
            "intake:abc123", existing_path="PUT /intake/abc123/agent-guidance"
        )

        assert isinstance(error, DecisionError)
        assert error.code == "decision_not_answerable"
        assert error.decision_id == "intake:abc123"
        assert error.details == "PUT /intake/abc123/agent-guidance"


# --- B4: eskaleringsinvarianten och alternativens kontraktsregler (SPEC §6.3, §11.1, testfall 19-23) ---


def _exit_option(**overrides) -> dict:
    """A minimal way-out option -- no account, no amount, `is_exit=True`.
    Used to close a list off in tests that are about some other option in
    it, so that only the rule under test can fail."""
    option = {
        "title": "Annat konto",
        "rationale": "Det är ett annat köp.",
        "is_exit": True,
    }
    option.update(overrides)
    return option


def _count_rows(table: str) -> int:
    """Total row count in `table` -- used to prove a rejected `options`
    list leaves no partial trace anywhere it could have written one."""
    row = db.execute("SELECT COUNT(*) AS n FROM " + table).fetchone()
    return row["n"]


class TestValidateOptionsTableSection11_1:
    """SPEC §11.1's table is the contract for the escalation invariant --
    one test per row, each citing its own row and testfall number."""

    def test_flow1_step2_5410_mot_1250_open_decision_changes_the_books_is_allowed(
        self,
    ):
        """§11.1 row 1: "Flöde 1 steg 2 -- 5410 mot 1250 | ja | ja ->
        `options`, tillåtet". Testfall 20."""
        service = DecisionService()
        options = [
            {
                "title": "Förbrukningsinventarier",
                "account": "5410",
                "amount_ore": 358400,
                "rationale": "Kostnadsförs direkt i juni.",
                "recommended": True,
                "is_exit": False,
            },
            _exit_option(),
        ]

        service.validate_options(options, under_open_decision=True)  # must not raise

    def test_flow4_exakt_match_step_is_skipped_empty_list_needs_no_permission(self):
        """§11.1 row 2: "Flöde 4 -- exakt match | nej | nej | hoppas över |
        'Exakt match ska hoppa över det här steget'". No `options` list is
        ever produced for this case; `create()` never calls
        `validate_options` for an empty one (SPEC §6.3: "En tom lista
        valideras inte"). Checked directly here: an empty list raises
        nothing, under either an open or a closed decision."""
        service = DecisionService()

        service.validate_options([], under_open_decision=False)
        service.validate_options([], under_open_decision=True)

    def test_flow4_koppla_utan_att_andra_is_allowed_without_an_open_decision(self):
        """§11.1 row 3: "Flöde 4 -- `koppla utan att ändra` | nej | nej ->
        `options`, tillåtet". Testfall 21."""
        service = DecisionService()
        options = [
            {
                "title": "Koppla mot befintlig faktura",
                "rationale": "Beloppet och datumet matchar en öppen post.",
                "is_exit": False,
            },
            _exit_option(),
        ]

        service.validate_options(options, under_open_decision=False)  # must not raise

    def test_flow4_bokfor_skillnaden_120kr_is_rejected_without_an_open_decision(self):
        """§11.1 row 4: "Flöde 4 -- `bokför skillnaden 120 kr` | nej | ja
        -> `decision` | 'bör bli ett beslutskort'". Testfall 19."""
        service = DecisionService()
        options = [
            {
                "title": "Bokför skillnaden",
                "account": "6990",
                "amount_ore": 12000,
                "rationale": "Öresavrundning mot bankens underlag.",
                "is_exit": True,
            },
        ]

        with pytest.raises(ValidationError) as exc_info:
            service.validate_options(options, under_open_decision=False)

        assert exc_info.value.code == "options_require_open_decision"


class TestValidateOptionsAtMostOneRecommended:
    """Testfall 22: fler än ett `recommended` är ett fel; noll och ett är
    tillåtna -- `recommended: true` är ett märke, inte en förvald rad."""

    def test_two_recommended_options_is_rejected(self):
        service = DecisionService()
        options = [
            {"title": "A", "rationale": "…", "recommended": True, "is_exit": False},
            _exit_option(recommended=True),
        ]

        with pytest.raises(ValidationError) as exc_info:
            service.validate_options(options, under_open_decision=False)

        assert exc_info.value.code == "multiple_recommended_options"

    def test_zero_recommended_options_is_allowed(self):
        service = DecisionService()
        options = [
            {"title": "A", "rationale": "…", "is_exit": False},
            _exit_option(),
        ]

        service.validate_options(options, under_open_decision=False)  # must not raise

    def test_one_recommended_option_is_allowed(self):
        service = DecisionService()
        options = [
            {"title": "A", "rationale": "…", "recommended": True, "is_exit": False},
            _exit_option(),
        ]

        service.validate_options(options, under_open_decision=False)  # must not raise


class TestValidateOptionsLastOptionIsExit:
    """Testfall 23: sista alternativet saknar `is_exit` -> avvisas. Ett
    `is_exit` på en tidigare rad är **medvetet tillåtet**: SPEC §6.3
    säger bara att den sista alltid är en väg ut, aldrig att bara den
    sista får vara det -- en lista får erbjuda mer än en dörr."""

    def test_last_option_without_is_exit_is_rejected(self):
        service = DecisionService()
        options = [
            {"title": "A", "rationale": "…", "is_exit": False},
            {"title": "B", "rationale": "…", "is_exit": False},
        ]

        with pytest.raises(ValidationError) as exc_info:
            service.validate_options(options, under_open_decision=False)

        assert exc_info.value.code == "options_without_exit"

    def test_is_exit_on_a_non_last_row_is_allowed(self):
        service = DecisionService()
        options = [
            _exit_option(title="Annat konto"),
            _exit_option(title="Det är inte alls detta köp"),
        ]

        service.validate_options(options, under_open_decision=False)  # must not raise


class TestValidateOptionsChangesTheBooksEdgeCasesAsARule:
    """Same predicate B2 already tested on `DecisionOption` directly
    (`TestDecisionOptionChangesTheBooks`) -- what's under test here is the
    consequence for the *rule*: an option that does not change the books
    never triggers the escalation invariant, with no open decision behind
    it at all."""

    def test_account_with_zero_amount_does_not_require_an_open_decision(self):
        service = DecisionService()
        options = [
            {
                "title": "A",
                "account": "5410",
                "amount_ore": 0,
                "rationale": "…",
                "is_exit": True,
            },
        ]

        service.validate_options(options, under_open_decision=False)  # must not raise

    def test_amount_without_account_does_not_require_an_open_decision(self):
        service = DecisionService()
        options = [
            {"title": "A", "amount_ore": 12000, "rationale": "…", "is_exit": True},
        ]

        service.validate_options(options, under_open_decision=False)  # must not raise


class TestValidateOptionsAcceptsDecisionOptionObjects:
    """`DecisionRepository.add_options` takes `DecisionOption` objects or
    dicts (`OptionInput`); `validate_options` has to read both shapes the
    same way, since `create()` never converts one into the other before
    calling it."""

    @staticmethod
    def _option(**overrides: Any) -> DecisionOption:
        base: Dict[str, Any] = dict(
            id=str(uuid.uuid4()),
            decision_id="d1",
            position=1,
            title="Förbrukningsinventarier",
            rationale="Kostnadsförs direkt.",
        )
        base.update(overrides)
        return DecisionOption(**base)

    def test_changes_the_books_option_without_open_decision_is_rejected(self):
        service = DecisionService()
        options = [
            self._option(account="5410", amount_ore=358400, position=1),
            self._option(title="Annat konto", is_exit=True, position=2),
        ]

        with pytest.raises(ValidationError) as exc_info:
            service.validate_options(options, under_open_decision=False)

        assert exc_info.value.code == "options_require_open_decision"

    def test_two_recommended_decision_options_is_rejected(self):
        service = DecisionService()
        options = [
            self._option(recommended=True, position=1),
            self._option(
                title="Annat konto", recommended=True, is_exit=True, position=2
            ),
        ]

        with pytest.raises(ValidationError) as exc_info:
            service.validate_options(options, under_open_decision=True)

        assert exc_info.value.code == "multiple_recommended_options"

    def test_last_decision_option_without_is_exit_is_rejected(self):
        service = DecisionService()
        options = [
            self._option(position=1),
            self._option(title="B", position=2),
        ]

        with pytest.raises(ValidationError) as exc_info:
            service.validate_options(options, under_open_decision=True)

        assert exc_info.value.code == "options_without_exit"

    def test_a_well_formed_list_of_decision_options_is_allowed(self):
        service = DecisionService()
        options = [
            self._option(
                account="5410", amount_ore=358400, recommended=True, position=1
            ),
            self._option(title="Annat konto", is_exit=True, position=2),
        ]

        service.validate_options(options, under_open_decision=True)  # must not raise


class TestValidateOptionsEnforcedThroughCreate:
    """The rule is a server rule, not a client rule (BRIEF.md, todo.md
    B4): `create()` calls `validate_options` itself, inside its own
    transaction, so a bad list is rejected no matter what wrote it --
    and rejecting it writes **nothing at all**, neither the `decision`
    post, the `decisions` row, the `options` post, nor any
    `decision_options` row (testfall 23, through `create()` rather than
    `validate_options` called directly, as the other classes above do)."""

    def test_create_with_a_list_missing_exit_on_the_last_row_writes_nothing(self):
        thread = _new_thread()
        service = DecisionService()

        posts_before = _count_rows("thread_posts")
        decisions_before = _count_rows("decisions")
        options_before = _count_rows("decision_options")

        with pytest.raises(ValidationError) as exc_info:
            service.create(
                thread,
                title="Kortköp Elektronikhuset",
                reason="Kvittot saknas.",
                consequence="Ingenting är bokfört.",
                options=[
                    {"title": "A", "rationale": "…", "is_exit": False},
                    {"title": "B", "rationale": "…", "is_exit": False},
                ],
            )

        assert exc_info.value.code == "options_without_exit"
        assert _count_rows("thread_posts") == posts_before
        assert _count_rows("decisions") == decisions_before
        assert _count_rows("decision_options") == options_before
        assert ThreadRepository.list_posts(thread.id) == []


# --- B5: verktyget be_om_beslut (SPEC §6.4, §8, testfall 24-27) ------------
#
# `be_om_beslut` is the redesign's one new tool -- a "fråga först" question
# already asked and answered (SPEC §11.3): a tenth entry in `_TOOL_SPECS`,
# appended last so the cached system-prompt prefix (SPEC-agentruntime §6.6)
# stays byte-identical for the first nine. Every test below drives it
# through `services.agent_tools.execute_tool`, exactly the entry point
# `run_tool_loop` uses -- never the handler function directly -- so a test
# failure here means the *tool surface*, not just the service underneath
# it (already covered by B2-B4), is wrong.


def _capabilities() -> LLMCapabilities:
    """A capable, streaming adapter -- what both shipped adapters report.
    Never consulted by `be_om_beslut` itself; only here because
    `execute_tool` requires one for every tool."""
    return LLMCapabilities(
        cache_breakpoint=True,
        pdf_document_blocks=True,
        refusal_stop_reason=True,
        streaming=True,
    )


class TestBeOmBeslutWritesDecisionPostRowAndOptions:
    """Testfall 24: `be_om_beslut` writes a `decision` post, a `decisions`
    row and `decision_options` rows -- and an `options` post, in that
    order -- through `execute_tool`, exactly as `DecisionService.create`
    already does one layer down (B3)."""

    def test_case_24_writes_decision_then_options_post_in_seq_order(self):
        thread = _new_thread()

        result = execute_tool(
            "be_om_beslut",
            {
                "title": "Kortköp Elektronikhuset",
                "reason": "Kvittot saknas och beloppet ligger nära gränsen.",
                "consequence": "Ingenting är bokfört.",
                "amount_ore": 358400,
                "options": [
                    {
                        "title": "Förbrukningsinventarier",
                        "rationale": "Matchar tidigare köp av samma typ.",
                        "account": "5410",
                        "amount_ore": 358400,
                        "recommended": True,
                    },
                    _exit_option(),
                ],
            },
            actor="agent",
            capabilities=_capabilities(),
            tool_context={"thread": thread},
        )

        posts = ThreadRepository.list_posts(thread.id)
        assert [post.type for post in posts] == ["decision", "options"]
        # "rätt ordning" — `decision` strictly before `options` by `seq`.
        assert posts[0].seq < posts[1].seq

        decision = DecisionRepository.get(result["decision_id"])
        assert decision is not None
        assert decision.post_id == posts[0].id
        assert decision.thread_id == thread.id
        assert len(decision.options) == 2
        assert [o.position for o in decision.options] == [1, 2]

    def test_case_24_writes_only_the_decision_post_when_options_is_empty(self):
        thread = _new_thread()

        result = execute_tool(
            "be_om_beslut",
            {
                "title": "Oklar leverantör",
                "reason": "Motparten går inte att identifiera.",
                "consequence": "Ingenting är bokfört.",
            },
            actor="agent",
            capabilities=_capabilities(),
            tool_context={"thread": thread},
        )

        posts = ThreadRepository.list_posts(thread.id)
        assert [post.type for post in posts] == ["decision"]
        decision = DecisionRepository.get(result["decision_id"])
        assert decision.options == []


class TestBeOmBeslutIsLastInAgentToolDefinitions:
    """Testfall 25: `be_om_beslut` is last in `AGENT_TOOL_DEFINITIONS`, and
    the first nine names are in their unchanged order -- a list that only
    checked "last" would miss a reorder hidden among the first nine."""

    _EXPECTED_FIRST_NINE = [
        "las_kontoplan",
        "las_perioder",
        "las_verifikationer",
        "las_korrigeringar",
        "las_underlag",
        "hamta_underlagsfil",
        "las_bankhandelser",
        "posta_verifikation",
        "registrera_avstaende",
    ]

    def test_case_25_be_om_beslut_is_last_and_the_first_nine_are_unchanged(self):
        names = [tool["name"] for tool in AGENT_TOOL_DEFINITIONS]

        assert len(names) == 10
        assert names[:9] == self._EXPECTED_FIRST_NINE
        assert names[-1] == "be_om_beslut"


class TestCaseTwentySixAppendOnlyToolSurfaceExtended:
    """Testfall 26 **is** test case 17 from `tests/test_agent_runtime.py`
    (`TestAppendOnlyToolSurface`), run against the ten-tool surface --
    SPEC-beslut.md §8: "Testfall 17 ... körs mot den utökade listan och ska
    passera oförändrat." The two checks below are copied from that class
    rather than imported, since they assert against module-level constants,
    not a shared fixture. `test_case_26_be_om_beslut_never_touches_vouchers`
    adds the structural check §8 asks for specifically about the new tool:
    counting `vouchers`/`voucher_rows` rows before and after a call."""

    _FORBIDDEN_NAME_FRAGMENTS = [
        "uppdatera",
        "andra",
        "ändra",
        "redigera",
        "radera",
        "ta_bort",
        "delete",
        "update",
        "edit",
        "patch",
        "remove",
    ]

    _FORBIDDEN_DESCRIPTION_PHRASES = [
        "ändra en postad",
        "ändra postad",
        "redigera en postad",
        "radera en postad",
        "radera verifikation",
        "ta bort en postad",
        "ta bort verifikation",
        "update the voucher",
        "edit the voucher",
        "delete the voucher",
        "modify a posted",
    ]

    def test_case_26_no_tool_name_contains_a_mutate_or_delete_verb(self):
        for tool in AGENT_TOOL_DEFINITIONS:
            lowered = tool["name"].lower()
            for fragment in self._FORBIDDEN_NAME_FRAGMENTS:
                assert (
                    fragment not in lowered
                ), f"tool name {tool['name']!r} contains {fragment!r}"

    def test_case_26_no_tool_description_implies_editing_a_posted_voucher(self):
        for tool in AGENT_TOOL_DEFINITIONS:
            haystack = tool["description"].lower()
            for phrase in self._FORBIDDEN_DESCRIPTION_PHRASES:
                assert (
                    phrase not in haystack
                ), f"tool {tool['name']!r} description contains {phrase!r}"

    def test_case_26_only_posta_verifikation_touches_the_ledger_in_its_description(
        self,
    ):
        for tool in AGENT_TOOL_DEFINITIONS:
            if tool["name"] != "posta_verifikation":
                assert "huvudboken" not in tool["description"].lower()

    def test_case_26_be_om_beslut_never_touches_vouchers_or_voucher_rows(self):
        thread = _new_thread()
        vouchers_before = _count_rows("vouchers")
        lines_before = _count_rows("voucher_rows")

        execute_tool(
            "be_om_beslut",
            {
                "title": "Oläsligt kvitto",
                "reason": "Beloppet går inte att läsa.",
                "consequence": "Ingenting är bokfört förrän beloppet är säkert.",
                "options": [_exit_option()],
            },
            actor="agent",
            capabilities=_capabilities(),
            tool_context={"thread": thread},
        )

        assert _count_rows("vouchers") == vouchers_before
        assert _count_rows("voucher_rows") == lines_before


class TestCaseTwentySevenRegistreraAvstaendeIsUnchanged:
    """Testfall 27: `registrera_avstaende` behaves exactly as before the
    module -- same name, same description, same `input_schema`, same
    position (ninth, index 8) in `AGENT_TOOL_DEFINITIONS`."""

    def test_case_27_registrera_avstaende_definition_is_byte_for_byte_unchanged(
        self,
    ):
        names = [tool["name"] for tool in AGENT_TOOL_DEFINITIONS]
        assert names[8] == "registrera_avstaende"

        tool = AGENT_TOOL_DEFINITIONS[8]
        assert tool["name"] == "registrera_avstaende"
        assert tool["description"] == (
            "Registrera ett dokumenterat avstående för ett underlag, med en "
            "motivering till varför det inte gick att bokföra. Skapar aldrig "
            "någon verifikation."
        )
        assert tool["input_schema"] == RegistreraAvstaendeArgs.model_json_schema()

    def test_case_27_a_bare_tool_call_still_creates_no_decision(self, tmp_path):
        """Before B6, this test's docstring read: "The bridge that gives an
        abstention its own `decisions` row is B6's job -- until then a call
        through the unchanged tool writes no `decisions` row at all." That
        was wrong about *where* B6's bridge lives, and B6 leaves this
        specific assertion true rather than changing it.

        `execute_tool("registrera_avstaende", ...)` on its own -- as this
        test does -- never reaches `ThreadService.record_outcome`: that
        only runs at the end of a full turn (`ThreadTurnRunner.run` ->
        `run_thread_session`), and `_run_registrera_avstaende`
        (`services/agent_tools.py`) itself only ever writes an
        `intake_processing_attempts` row via `IntakeService.record_failed`
        -- no thread post, no `decisions` row, not before B6 and not after.
        The bridge B6 actually builds is in `record_outcome`, reached only
        through a real thread turn -- see
        `TestAbstentionInThreadGetsATrackedDecision` below, which is the
        test that exercises it and would have failed before B6."""
        from config import settings
        from services.intake import IntakeService

        original_dir = settings.intake_dir
        settings.intake_dir = str(tmp_path / "intake")
        try:
            source = IntakeService().create_source_from_upload_content(
                filename="kvitto.pdf",
                content_type="application/pdf",
                content=b"%PDF-1.4 kvitto",
                explanation="Kvitto",
                source_type="receipt",
                actor="api",
            )
        finally:
            settings.intake_dir = original_dir

        decisions_before = _count_rows("decisions")

        execute_tool(
            "registrera_avstaende",
            {
                "source_id": source.id,
                "summary": "Kan inte läsas.",
                "error_detail": "Filen är korrupt.",
            },
            actor="agent",
            capabilities=_capabilities(),
        )

        assert _count_rows("decisions") == decisions_before


class TestBeOmBeslutRequiresAThread:
    """`thread=None` (the document path's shape, or a bare `execute_tool`
    call with nothing passed) raises `ValidationError(code=
    "decision_requires_thread")` and writes nothing -- SPEC §7 gräns:
    "en decisions-rad utan thread_id" is exactly the silent "fråga först"
    case the module must refuse to let happen."""

    def _args(self, **overrides) -> dict:
        args = {
            "title": "X",
            "reason": "Y",
            "consequence": "Z",
        }
        args.update(overrides)
        return args

    def test_thread_none_raises_decision_requires_thread(self):
        posts_before = _count_rows("thread_posts")
        decisions_before = _count_rows("decisions")

        with pytest.raises(ValidationError) as exc_info:
            execute_tool(
                "be_om_beslut",
                self._args(),
                actor="agent",
                capabilities=_capabilities(),
                tool_context=None,
            )

        assert exc_info.value.code == "decision_requires_thread"
        assert _count_rows("thread_posts") == posts_before
        assert _count_rows("decisions") == decisions_before

    def test_thread_omitted_entirely_also_raises(self):
        """`execute_tool`'s `thread` keyword defaults to `None` -- the
        document path never passes it at all, and the same refusal must
        happen whether the caller passed `thread=None` explicitly or left
        it out."""
        with pytest.raises(ValidationError) as exc_info:
            execute_tool(
                "be_om_beslut",
                self._args(),
                actor="agent",
                capabilities=_capabilities(),
            )

        assert exc_info.value.code == "decision_requires_thread"


class TestBeOmBeslutEnforcesTheEscalationInvariantThroughTheTool:
    """B4's rule is a server rule (BRIEF.md, todo.md B5 Obs), and
    `be_om_beslut` is the only path an agent has into it -- these repeat
    B4's own escalation-invariant tests, but driven through the tool
    surface rather than `DecisionService.validate_options` directly."""

    def test_options_without_a_final_exit_is_rejected_through_the_tool(self):
        thread = _new_thread()

        with pytest.raises(ValidationError) as exc_info:
            execute_tool(
                "be_om_beslut",
                {
                    "title": "Kortköp",
                    "reason": "Oklart konto.",
                    "consequence": "Ingenting är bokfört.",
                    "options": [
                        {"title": "A", "rationale": "…", "is_exit": False},
                        {"title": "B", "rationale": "…", "is_exit": False},
                    ],
                },
                actor="agent",
                capabilities=_capabilities(),
                tool_context={"thread": thread},
            )

        assert exc_info.value.code == "options_without_exit"
        assert _count_rows("decisions") == 0

    def test_two_recommended_options_is_rejected_through_the_tool(self):
        thread = _new_thread()

        with pytest.raises(ValidationError) as exc_info:
            execute_tool(
                "be_om_beslut",
                {
                    "title": "Kortköp",
                    "reason": "Oklart konto.",
                    "consequence": "Ingenting är bokfört.",
                    "options": [
                        {"title": "A", "rationale": "…", "recommended": True},
                        {
                            "title": "B",
                            "rationale": "…",
                            "recommended": True,
                            "is_exit": True,
                        },
                    ],
                },
                actor="agent",
                capabilities=_capabilities(),
                tool_context={"thread": thread},
            )

        assert exc_info.value.code == "multiple_recommended_options"

    def test_options_that_change_the_books_without_being_a_decision_first_is_impossible(
        self,
    ):
        """The tool always raises the `decisions` row first (SPEC §11.1's
        first table row): `be_om_beslut`'s own call writes `decision` then
        `options` inside one `create()` transaction, so there is no way to
        call it with `options` and *not* have an open decision under them
        -- `validate_options`'s `options_require_open_decision` branch is
        therefore unreachable through this tool, which is itself part of
        the invariant: only `create()`'s call site can ever pass
        `under_open_decision=False`, and that is B7's synthetic-source path
        (§11.1's third row), never this tool's."""
        thread = _new_thread()

        result = execute_tool(
            "be_om_beslut",
            {
                "title": "Kortköp",
                "reason": "Oklart konto.",
                "consequence": "Ingenting är bokfört.",
                "options": [
                    {
                        "title": "Förbrukningsinventarier",
                        "rationale": "Matchar tidigare köp.",
                        "account": "5410",
                        "amount_ore": 12000,
                    },
                    _exit_option(),
                ],
            },
            actor="agent",
            capabilities=_capabilities(),
            tool_context={"thread": thread},
        )

        decision = DecisionRepository.get(result["decision_id"])
        assert decision.status == "open"
        assert any(o.changes_the_books for o in decision.options)


class TestBeOmBeslutStoresAgentTextVerbatim:
    """Testfall 34 (the tool's part): `reason`, `consequence` and each
    option's `rationale` reach `decisions`/`decision_options` exactly as
    the agent wrote them -- no rewording, no truncation, no
    normalisation (SPEC §7.4)."""

    def test_reason_consequence_and_rationale_survive_the_whole_tool_path(self):
        thread = _new_thread()
        reason = (
            "Kvittot är suddigt och sista siffran går inte att läsa med "
            "säkerhet -- det kan vara 358400 öre eller 388400 öre."
        )
        consequence = "Ingenting är bokfört förrän du bekräftar beloppet."
        rationale = (
            "Matchar mönstret för tidigare köp hos samma leverantör, men "
            "jag är inte säker eftersom sista siffran är oläslig."
        )
        footnote = "Två tolkningar av samma kvitto är möjliga."

        result = execute_tool(
            "be_om_beslut",
            {
                "title": "Oläsligt kvitto",
                "reason": reason,
                "consequence": consequence,
                "footnote": footnote,
                "options": [
                    {
                        "title": "Bokför som 3 584 kr",
                        "rationale": rationale,
                        "account": "5410",
                        "amount_ore": 358400,
                    },
                    _exit_option(),
                ],
            },
            actor="agent",
            capabilities=_capabilities(),
            tool_context={"thread": thread},
        )

        decision = DecisionRepository.get(result["decision_id"])
        assert decision.reason == reason
        assert decision.consequence == consequence
        assert decision.options[0].rationale == rationale

        options_post = [
            post
            for post in ThreadRepository.list_posts(thread.id)
            if post.type == "options"
        ][0]
        assert options_post.body["footnote"] == footnote
        assert options_post.body["options"][0]["rationale"] == rationale


def _turn(
    text: str = "",
    tool_calls: Any = None,
    stop: str = "end",
) -> LLMTurn:
    """A finished `LLMTurn`, the shape `tests/test_tradar.py`'s own `_turn`
    helper builds -- reimplemented locally so this module drives its one
    full-turn test (below) without importing fixtures from another test
    module."""
    return LLMTurn(
        text=text,
        tool_calls=tool_calls or [],
        stop=cast(StopReason, stop),
        usage=Usage(input_tokens=0, output_tokens=0, cache_read_input_tokens=0),
    )


class _FakeLLMClient:
    """Structural `LLMClient` double (SPEC §9) -- a queue of ready-made
    `LLMTurn`s, never a network call. Same pattern as
    `tests/test_tradar.py::FakeLLMClient`, reimplemented locally rather than
    imported, per BRIEF.md's rule to keep this module's own fixtures."""

    def __init__(self, turns: list[LLMTurn]):
        self._turns = list(turns)
        self.capabilities = _capabilities()

    def run_turn(
        self,
        system: str,
        messages: list,
        tools: list,
        model: str,
        max_tokens: int,
        on_text: Any = None,
        on_tool_call: Any = None,
    ) -> LLMTurn:
        return self._turns.pop(0) if len(self._turns) > 1 else self._turns[0]


class TestRunThreadSessionReachesBeOmBeslutWithAThread:
    """BRIEF.md §3's whole point, proven end to end: a real thread turn,
    `ThreadTurnRunner.run` -> `run_thread_session` -> `run_tool_loop` ->
    `execute_tool` -> `_run_be_om_beslut`, with the LLM faked via
    `client_factory` (never monkeypatch) and run synchronously (never
    `.start`)."""

    def test_a_thread_turn_that_calls_be_om_beslut_creates_the_decision(self):
        thread = _new_thread()
        trigger = ThreadRepository.add_post(
            thread_id=thread.id,
            post_type="user_text",
            actor="stefan",
            body={"text": "Vad gör jag med det här kvittot?"},
        )
        tool_call = ToolCall(
            id="call-1",
            name="be_om_beslut",
            arguments={
                "title": "Oläsligt kvitto",
                "reason": "Beloppet går inte att läsa med säkerhet.",
                "consequence": "Ingenting är bokfört.",
                "options": [_exit_option()],
            },
        )
        client = _FakeLLMClient(
            [
                _turn(tool_calls=[tool_call], stop="tool_calls"),
                _turn(text="Jag har lagt fram ett beslut åt dig.", stop="end"),
            ]
        )

        outcome = ThreadTurnRunner().run(
            thread,
            trigger,
            "Vad gör jag med det här kvittot?",
            client_factory=lambda model: client,
        )

        assert outcome is not None
        assert outcome.kind == "answered"

        decisions = DecisionRepository.list_decisions(
            status="open", view_key=thread.view_key
        )
        assert len(decisions) == 1
        assert decisions[0].thread_id == thread.id
        assert decisions[0].title == "Oläsligt kvitto"


class TestDocumentPathUnchangedByBeOmBeslut:
    """The document path (`execute_tool` with no `thread`) behaves exactly
    as it did before B5 for the nine original tools -- `thread` is a purely
    additive, ignored parameter for all of them."""

    def test_an_old_tool_still_works_with_no_thread_argument_at_all(self):
        result = execute_tool(
            "las_kontoplan",
            {"active_only": True},
            actor="agent",
            capabilities=_capabilities(),
        )

        assert isinstance(result, list)

    def test_an_old_tool_still_works_when_thread_is_explicitly_none(self):
        result = execute_tool(
            "las_kontoplan",
            {"active_only": True},
            actor="agent",
            capabilities=_capabilities(),
            tool_context=None,
        )

        assert isinstance(result, list)


# --- B6: avståendet i tråden blir ett spårat beslut (SPEC §2, testfall 34) ---


def _intake_source_for_abstention(tmp_path):
    """A real `intake_sources` row via `IntakeService`, so
    `registrera_avstaende`'s `source_id` foreign key is genuine -- the same
    setup `TestCaseTwentySevenRegistreraAvstaendeIsUnchanged` already uses,
    reused here because a full turn's `registrera_avstaende` call needs one
    too."""
    from config import settings
    from services.intake import IntakeService

    original_dir = settings.intake_dir
    settings.intake_dir = str(tmp_path / "intake")
    try:
        return IntakeService().create_source_from_upload_content(
            filename="kvitto.pdf",
            content_type="application/pdf",
            content=b"%PDF-1.4 kvitto",
            explanation="Kvitto",
            source_type="receipt",
            actor="api",
        )
    finally:
        settings.intake_dir = original_dir


def _run_abstention_turn(
    tmp_path,
    *,
    summary: str,
    error_detail: str,
    view_key: str = "bocker.verifikationer",
):
    """A real thread turn whose only tool call is `registrera_avstaende` --
    `ThreadTurnRunner.run`, synchronous, LLM faked via `client_factory`
    (never monkeypatch), exactly BRIEF.md's arbetssätt §2. This is the path
    `_thread_service.record_outcome` actually runs on, unlike a bare
    `execute_tool` call (see the corrected `test_case_27_...` above)."""
    thread = _new_thread(view_key=view_key)
    trigger = ThreadRepository.add_post(
        thread_id=thread.id,
        post_type="user_text",
        actor="stefan",
        body={"text": "Kan du bokföra det här kvittot?"},
    )
    source = _intake_source_for_abstention(tmp_path)
    tool_call = ToolCall(
        id="call-1",
        name="registrera_avstaende",
        arguments={
            "source_id": source.id,
            "summary": summary,
            "error_detail": error_detail,
        },
    )
    client = _FakeLLMClient([_turn(tool_calls=[tool_call], stop="tool_calls")])
    outcome = ThreadTurnRunner().run(
        thread,
        trigger,
        "Kan du bokföra det här kvittot?",
        client_factory=lambda model: client,
    )
    return thread, outcome


class TestAbstentionInThreadGetsATrackedDecision:
    """B6 (`tasks/beslut/todo.md`): a `registrera_avstaende` call inside a
    real thread turn already produced a `decision` post (`tradar`, B1).
    Before this task the post had no row behind it -- exactly the orphaned
    card SPEC-beslut.md §2 describes: visible in the thread, but impossible
    to list, age or answer. `ThreadService.record_outcome` now binds the
    post to a fresh `decisions` row, in the same transaction."""

    def test_the_decision_post_gets_exactly_one_bound_row(self, tmp_path):
        thread, outcome = _run_abstention_turn(
            tmp_path,
            summary="Behöver veta vad inköpet avsåg",
            error_detail="Beloppet går inte att utläsa på kvittot",
        )
        assert outcome is not None
        assert outcome.kind == "abstained"

        posts = [
            post
            for post in ThreadRepository.list_posts(thread.id)
            if post.type == "decision"
        ]
        assert len(posts) == 1
        post = posts[0]

        decision = DecisionRepository.get_by_post_id(post.id)
        assert decision is not None
        assert decision.thread_id == thread.id
        assert decision.kind == "abstention"
        assert decision.status == "open"
        assert decision.view_key == thread.view_key

    def test_no_decision_post_is_ever_left_without_a_row(self, tmp_path):
        """The task's real acceptance criterion (todo.md B6's Obs): every
        `decision` post the turn produced -- not just "a" post -- has a row
        bound to it, checked by listing the thread's own posts rather than
        assuming there is exactly one."""
        thread, _ = _run_abstention_turn(
            tmp_path,
            summary="Oklart om det är representation eller kontorsmaterial",
            error_detail="Kvittot saknar specifikation",
        )

        decision_posts = [
            post
            for post in ThreadRepository.list_posts(thread.id)
            if post.type == "decision"
        ]
        assert decision_posts, "the turn should have produced a decision post"
        for post in decision_posts:
            assert DecisionRepository.get_by_post_id(post.id) is not None

    def test_the_post_and_the_row_carry_the_same_decision_id(self, tmp_path):
        thread, _ = _run_abstention_turn(
            tmp_path,
            summary="Behöver veta vad inköpet avsåg",
            error_detail="Beloppet går inte att utläsa på kvittot",
        )
        post = [
            p for p in ThreadRepository.list_posts(thread.id) if p.type == "decision"
        ][0]
        decision = DecisionRepository.get_by_post_id(post.id)

        assert post.body["decision_id"] == decision.id

    def test_case_34_reason_and_consequence_survive_verbatim_in_post_and_row(
        self, tmp_path
    ):
        """Testfall 34 (SPEC §7.4): the agent's own wording -- quotes, a
        line break, Swedish characters -- reaches both the post and the row
        unchanged, and the two agree exactly: `DecisionService.create`
        (called with `post=` already written) does not re-derive or
        retruncate what `_decision_body` already produced."""
        summary = (
            'Kvittot säger "Elektronikhuset – Örebro",\n'
            "men beloppet 4 480 kr går inte att läsa med säkerhet."
        )
        thread, _ = _run_abstention_turn(
            tmp_path,
            summary=summary,
            error_detail="Suddig bild, sista siffran oläslig.",
        )
        post = [
            p for p in ThreadRepository.list_posts(thread.id) if p.type == "decision"
        ][0]
        decision = DecisionRepository.get_by_post_id(post.id)

        assert post.body["reason"] == summary
        assert decision.reason == summary
        assert decision.reason == post.body["reason"]
        assert decision.consequence == post.body["consequence"]

    def test_the_decision_is_answerable(self, tmp_path):
        """The whole point of B6 (todo.md's Obs): the card is no longer
        orphaned -- it counts toward `DecisionService.count_open()` and
        `DecisionService.answer()` closes it, exactly like any other open
        decision."""
        thread, _ = _run_abstention_turn(
            tmp_path,
            summary="Behöver veta vad inköpet avsåg",
            error_detail="Beloppet går inte att utläsa på kvittot",
        )
        post = [
            p for p in ThreadRepository.list_posts(thread.id) if p.type == "decision"
        ][0]
        decision = DecisionRepository.get_by_post_id(post.id)
        service = DecisionService()

        assert service.count_open() >= 1

        answered, answer_post = service.answer(
            decision.id, free_text="Det är representation.", actor="stefan"
        )

        assert answered.status == "answered"
        assert answer_post.body["text"] == "Det är representation."

    def test_an_answered_turn_writes_no_decision(self):
        """Only the `decision` branch of `_render`/`record_outcome` is
        touched by B6 -- an `answered` outcome (no tool call at all) must
        still write no `decisions` row."""
        thread = _new_thread()
        trigger = ThreadRepository.add_post(
            thread_id=thread.id,
            post_type="user_text",
            actor="stefan",
            body={"text": "Vad är saldot på 1930?"},
        )
        client = _FakeLLMClient([_turn(text="Saldot är 12 345 kr.", stop="end")])
        before = _count_rows("decisions")

        outcome = ThreadTurnRunner().run(
            thread,
            trigger,
            "Vad är saldot på 1930?",
            client_factory=lambda model: client,
        )

        assert outcome.kind == "answered"
        assert _count_rows("decisions") == before

    def test_a_failed_turn_writes_no_decision(self):
        """Same for `failed` -- an unrecognized stop reason must not leave
        a decision behind either."""
        thread = _new_thread()
        trigger = ThreadRepository.add_post(
            thread_id=thread.id,
            post_type="user_text",
            actor="stefan",
            body={"text": "Bokför det här."},
        )
        client = _FakeLLMClient([_turn(text="", stop="bogus_stop_reason")])
        before = _count_rows("decisions")

        outcome = ThreadTurnRunner().run(
            thread,
            trigger,
            "Bokför det här.",
            client_factory=lambda model: client,
        )

        assert outcome.kind == "failed"
        assert _count_rows("decisions") == before
