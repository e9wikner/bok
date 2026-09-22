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

import pytest

from db.database import db
from domain.models import Decision, DecisionOption
from repositories.decision_repo import DecisionRepository
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
