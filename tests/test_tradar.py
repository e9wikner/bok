"""Tests for the `tradar` module (docs/redesign/SPEC-tradar.md).

Grows across tasks T1-T14 of `tasks/tradar/todo.md`; each task gets its own
section so the file stays navigable. Test case numbers refer to the table in
SPEC-tradar.md §9.

Per SPEC §9 no LLM is ever called from a test. The double is
`FakeLLMClient`, the same pattern as `tests/test_agent_runtime.py:1420`: a
queue of ready-made `LLMTurn`s, `self.calls` to inspect what was actually
sent, injected through a factory argument — never a monkeypatch. Its one new
responsibility here is calling `on_text`/`on_tool_call` before returning its
turn (T5).
"""

import asyncio
import json
import sqlite3
import uuid
from datetime import date, datetime
from typing import Optional, cast

import pytest
from fastapi.testclient import TestClient

from api.routes.threads import stream_thread
from config import settings
from db.database import db
from domain.types import ThreadViewKey
from repositories.account_repo import AccountRepository
from repositories.agent_run_repo import AgentRunRepository
from repositories.period_repo import PeriodRepository
from repositories.thread_repo import ThreadRepository
from services.agent_runtime import (
    AgentRunner,
    AgentWorker,
    agent_state,
    get_runner,
    get_worker,
)
from services.agent_session import (
    DOCUMENT_POLICY,
    THREAD_POLICY,
    SessionOutcome,
    run_session,
    run_tool_loop,
)
from services.agent_tools import (
    AGENT_TOOL_DEFINITIONS,
    derive_posting_idempotency_key,
    derive_thread_posting_idempotency_key,
)
from services.intake import IntakeService
from services.llm import (
    LLMCapabilities,
    LLMConnectionError,
    LLMRateLimitError,
    LLMTurn,
    StopReason,
    ToolCall,
    Usage,
)
from services.thread_service import ThreadService, compact
from services.thread_session import (
    build_thread_window,
    estimate_tokens,
    render_post,
    run_thread_session,
)
from services.thread_stream import (
    EVENT_MESSAGE_COMPLETED,
    EVENT_MESSAGE_CREATED,
    EVENT_MESSAGE_DELTA,
    EVENT_VIEW_CHANGED,
    ConcurrentRunWriterError,
    ThreadBroker,
    ThreadTurnRunner,
    claim_run,
    format_sse,
    get_broker,
    live_run_ids,
    post_event_payload,
    release_run,
)

pytestmark = pytest.mark.usefixtures("test_db")


# --- helpers ----------------------------------------------------------------


def _fiscal_year(start: date = date(2026, 1, 1), end: date = date(2026, 12, 31)):
    """A fiscal year to hang a thread off — `threads.fiscal_year_id` is a real
    foreign key, so no test may invent an id."""
    return PeriodRepository.create_fiscal_year(start_date=start, end_date=end)


def _intake_source(tmp_path, name: str = "telefon.pdf"):
    """An intake source with a real file on disk — the document path reads
    bytes before it ever calls the model (pattern from
    `tests/test_agent_runtime.py`)."""
    original = settings.intake_dir
    settings.intake_dir = str(tmp_path / "intake")
    try:
        return IntakeService().create_source_from_upload_content(
            filename=name,
            content_type="application/pdf",
            content=f"%PDF-1.4 {name}".encode(),
            explanation="Telefonutgift Fello",
            source_type="receipt",
            actor="api",
        )
    finally:
        settings.intake_dir = original


@pytest.fixture
def agent_intake_dir(tmp_path):
    """`settings.intake_dir` overridden for the whole test, not just while
    the source is created: `AgentWorker.run_pass_once` calls
    `resolve_source_file` well after that point, and a path outside the
    configured root is refused. Same fixture, and same reason, as
    `tests/test_agent_runtime.py`'s."""
    original = settings.intake_dir
    settings.intake_dir = str(tmp_path / "intake")
    yield
    settings.intake_dir = original


def _posting_args(period_id: str, source_id: str, amount: int = 12500) -> dict:
    """A balanced `posta_verifikation` call that cites its source material —
    `post_agent_voucher` refuses one that doesn't, on either path."""
    return {
        "date": "2026-03-15",
        "period_id": period_id,
        "description": "Telefonutgift Fello",
        "reasoning_summary": "Kvitto matchat mot underlag",
        "intake_source_ids": [source_id],
        "rows": [
            {"account": "1920", "debit": 0, "credit": amount},
            {"account": "2640", "debit": amount // 5, "credit": 0},
            {"account": "6212", "debit": amount - amount // 5, "credit": 0},
        ],
    }


def _ensure_accounts() -> None:
    """The system prompt renders the kontoplan, so a session needs accounts to
    exist; `AgentInstructionRepository` seeds its own defaults."""
    for code, name, account_type in (
        ("1920", "Bankkonto", "asset"),
        ("2640", "Ingående moms", "vat_in"),
        ("6212", "Mobiltelefon", "expense"),
    ):
        if not AccountRepository.exists(code):
            AccountRepository.create(code, name, account_type)


def _raw_insert_post(thread_id: str, seq: int, post_type: str) -> None:
    """Insert straight past the repository, to prove a *schema* constraint
    rather than a Python guard (test case 5)."""
    db.execute(
        """
        INSERT INTO thread_posts
        (id, thread_id, seq, type, actor, created_at, body_json)
        VALUES (?, ?, ?, ?, 'agent', ?, '{}')
        """,
        (str(uuid.uuid4()), thread_id, seq, post_type, datetime.now()),
    )
    db.commit()


# --- T1: migration 025 (SPEC §4, test case 5) -------------------------------


class TestMigration025:
    def test_threads_and_thread_posts_exist(self):
        tables = {
            row["name"]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert "threads" in tables
        assert "thread_posts" in tables

    def test_one_thread_per_view_key_and_fiscal_year(self):
        """Decision §12.3, written into the schema rather than trusted to the
        service layer."""
        fy = _fiscal_year()
        db.execute(
            "INSERT INTO threads (id, view_key, fiscal_year_id, model, created_at) "
            "VALUES (?, 'bocker.verifikationer', ?, 'opencode/claude-opus-5', ?)",
            (str(uuid.uuid4()), fy.id, datetime.now()),
        )
        db.commit()

        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO threads (id, view_key, fiscal_year_id, model, created_at) "
                "VALUES (?, 'bocker.verifikationer', ?, 'opencode/claude-opus-5', ?)",
                (str(uuid.uuid4()), fy.id, datetime.now()),
            )
            db.commit()
        db.rollback()

    def test_same_view_key_in_another_fiscal_year_is_a_second_thread(self):
        first = _fiscal_year()
        second = _fiscal_year(date(2027, 1, 1), date(2027, 12, 31))

        for fiscal_year in (first, second):
            db.execute(
                "INSERT INTO threads (id, view_key, fiscal_year_id, model, created_at) "
                "VALUES (?, 'bocker.balans', ?, 'opencode/claude-opus-5', ?)",
                (str(uuid.uuid4()), fiscal_year.id, datetime.now()),
            )
        db.commit()

        count = db.execute(
            "SELECT COUNT(*) AS n FROM threads WHERE view_key = 'bocker.balans'"
        ).fetchone()["n"]
        assert count == 2

    def test_case_5_a_ninth_post_type_is_rejected_by_the_check_constraint(self):
        """SPEC §4: the eight post types are a contract against the client. A
        ninth one must fail in the schema, not merely in Python."""
        fy = _fiscal_year()
        thread = ThreadRepository.get_or_create(
            view_key="bocker.verifikationer",
            fiscal_year_id=fy.id,
            model="opencode/claude-opus-5",
        )

        with pytest.raises(sqlite3.IntegrityError):
            _raw_insert_post(thread.id, 1, "summary")
        db.rollback()

    def test_all_eight_documented_types_are_accepted(self):
        fy = _fiscal_year()
        thread = ThreadRepository.get_or_create(
            view_key="bocker.verifikationer",
            fiscal_year_id=fy.id,
            model="opencode/claude-opus-5",
        )

        for index, post_type in enumerate(
            (
                "agent_text",
                "user_text",
                "user_file",
                "decision",
                "options",
                "draft",
                "error",
                "receipt",
            ),
            start=1,
        ):
            _raw_insert_post(thread.id, index, post_type)

        count = db.execute(
            "SELECT COUNT(*) AS n FROM thread_posts WHERE thread_id = ?",
            (thread.id,),
        ).fetchone()["n"]
        assert count == 8

    def test_seq_is_unique_per_thread(self):
        fy = _fiscal_year()
        thread = ThreadRepository.get_or_create(
            view_key="bocker.verifikationer",
            fiscal_year_id=fy.id,
            model="opencode/claude-opus-5",
        )
        _raw_insert_post(thread.id, 1, "agent_text")

        with pytest.raises(sqlite3.IntegrityError):
            _raw_insert_post(thread.id, 1, "agent_text")
        db.rollback()


# --- T2: ThreadRepository (SPEC §4, test cases 1, 2, 3) ---------------------


class TestThreadRepositoryGetOrCreate:
    def test_case_1_created_once_per_view_key_and_fiscal_year(self):
        fy = _fiscal_year()

        first = ThreadRepository.get_or_create(
            view_key="bocker.verifikationer",
            fiscal_year_id=fy.id,
            model="opencode/claude-opus-5",
        )
        second = ThreadRepository.get_or_create(
            view_key="bocker.verifikationer",
            fiscal_year_id=fy.id,
            model="opencode/claude-opus-5",
        )

        assert first.id == second.id
        assert db.execute("SELECT COUNT(*) AS n FROM threads").fetchone()["n"] == 1

    def test_a_second_view_gets_its_own_thread(self):
        fy = _fiscal_year()

        balans = ThreadRepository.get_or_create(
            view_key="bocker.balans",
            fiscal_year_id=fy.id,
            model="opencode/claude-opus-5",
        )
        resultat = ThreadRepository.get_or_create(
            view_key="bocker.resultat",
            fiscal_year_id=fy.id,
            model="opencode/claude-opus-5",
        )

        assert balans.id != resultat.id

    def test_an_existing_threads_model_is_not_overwritten_by_a_later_lookup(self):
        """`model` belongs to the thread (§12.4). A plain read must never
        silently reset a choice the human made."""
        fy = _fiscal_year()
        ThreadRepository.get_or_create(
            view_key="bocker.balans",
            fiscal_year_id=fy.id,
            model="opencode/claude-sonnet-5",
        )

        again = ThreadRepository.get_or_create(
            view_key="bocker.balans",
            fiscal_year_id=fy.id,
            model="opencode/claude-opus-5",
        )

        assert again.model == "opencode/claude-sonnet-5"


class TestThreadRepositoryAddPost:
    def test_case_2_seq_is_dense_and_ascending_per_thread(self):
        fy = _fiscal_year()
        thread = ThreadRepository.get_or_create(
            view_key="bocker.verifikationer",
            fiscal_year_id=fy.id,
            model="opencode/claude-opus-5",
        )

        posts = [
            ThreadRepository.add_post(
                thread_id=thread.id,
                post_type="user_text",
                actor="stefan",
                body={"text": f"fråga {index}"},
            )
            for index in range(3)
        ]

        assert [post.seq for post in posts] == [1, 2, 3]

    def test_seq_counts_per_thread_not_globally(self):
        fy = _fiscal_year()
        first = ThreadRepository.get_or_create(
            view_key="bocker.balans",
            fiscal_year_id=fy.id,
            model="opencode/claude-opus-5",
        )
        second = ThreadRepository.get_or_create(
            view_key="bocker.resultat",
            fiscal_year_id=fy.id,
            model="opencode/claude-opus-5",
        )

        ThreadRepository.add_post(
            thread_id=first.id,
            post_type="user_text",
            actor="stefan",
            body={"text": "a"},
        )
        post = ThreadRepository.add_post(
            thread_id=second.id,
            post_type="user_text",
            actor="stefan",
            body={"text": "b"},
        )

        assert post.seq == 1

    def test_body_and_traces_round_trip_as_json(self):
        fy = _fiscal_year()
        thread = ThreadRepository.get_or_create(
            view_key="bocker.verifikationer",
            fiscal_year_id=fy.id,
            model="opencode/claude-opus-5",
        )

        ThreadRepository.add_post(
            thread_id=thread.id,
            post_type="agent_text",
            actor="agent",
            body={"text": "Bokfört på 5611, ingående moms räknad från bruttot."},
            traces=[{"label": "las_kontoplan"}, {"label": "posta_verifikation"}],
        )

        stored = ThreadRepository.list_posts(thread.id)[0]
        assert stored.body["text"].startswith("Bokfört på 5611")
        assert stored.traces == [
            {"label": "las_kontoplan"},
            {"label": "posta_verifikation"},
        ]

    def test_traces_stay_none_when_not_given(self):
        fy = _fiscal_year()
        thread = ThreadRepository.get_or_create(
            view_key="bocker.verifikationer",
            fiscal_year_id=fy.id,
            model="opencode/claude-opus-5",
        )

        ThreadRepository.add_post(
            thread_id=thread.id,
            post_type="user_text",
            actor="stefan",
            body={"text": "hej"},
        )

        assert ThreadRepository.list_posts(thread.id)[0].traces is None


class TestThreadRepositoryListPosts:
    def test_posts_come_back_oldest_first(self):
        fy = _fiscal_year()
        thread = ThreadRepository.get_or_create(
            view_key="bocker.verifikationer",
            fiscal_year_id=fy.id,
            model="opencode/claude-opus-5",
        )
        for index in range(4):
            ThreadRepository.add_post(
                thread_id=thread.id,
                post_type="user_text",
                actor="stefan",
                body={"text": str(index)},
            )

        posts = ThreadRepository.list_posts(thread.id)

        assert [post.body["text"] for post in posts] == ["0", "1", "2", "3"]

    def test_case_3_since_returns_exactly_what_came_after(self):
        fy = _fiscal_year()
        thread = ThreadRepository.get_or_create(
            view_key="bocker.verifikationer",
            fiscal_year_id=fy.id,
            model="opencode/claude-opus-5",
        )
        for index in range(5):
            ThreadRepository.add_post(
                thread_id=thread.id,
                post_type="user_text",
                actor="stefan",
                body={"text": str(index)},
            )

        posts = ThreadRepository.list_posts(thread.id, since=2)

        assert [post.seq for post in posts] == [3, 4, 5]

    def test_since_at_the_last_seq_returns_nothing(self):
        fy = _fiscal_year()
        thread = ThreadRepository.get_or_create(
            view_key="bocker.verifikationer",
            fiscal_year_id=fy.id,
            model="opencode/claude-opus-5",
        )
        last = ThreadRepository.add_post(
            thread_id=thread.id,
            post_type="user_text",
            actor="stefan",
            body={"text": "enda"},
        )

        assert ThreadRepository.list_posts(thread.id, since=last.seq) == []

    def test_limit_takes_the_oldest_of_what_remains(self):
        fy = _fiscal_year()
        thread = ThreadRepository.get_or_create(
            view_key="bocker.verifikationer",
            fiscal_year_id=fy.id,
            model="opencode/claude-opus-5",
        )
        for index in range(5):
            ThreadRepository.add_post(
                thread_id=thread.id,
                post_type="user_text",
                actor="stefan",
                body={"text": str(index)},
            )

        posts = ThreadRepository.list_posts(thread.id, since=1, limit=2)

        assert [post.seq for post in posts] == [2, 3]


class TestThreadRepositoryArchive:
    def test_list_fiscal_years_returns_the_years_this_view_has_threads_in(self):
        first = _fiscal_year()
        second = _fiscal_year(date(2027, 1, 1), date(2027, 12, 31))
        for fiscal_year in (first, second):
            ThreadRepository.get_or_create(
                view_key="bocker.verifikationer",
                fiscal_year_id=fiscal_year.id,
                model="opencode/claude-opus-5",
            )
        ThreadRepository.get_or_create(
            view_key="bocker.balans",
            fiscal_year_id=first.id,
            model="opencode/claude-opus-5",
        )

        years = ThreadRepository.list_fiscal_years("bocker.verifikationer")

        assert years == [second.id, first.id]

    def test_a_view_without_threads_has_an_empty_archive(self):
        _fiscal_year()
        assert ThreadRepository.list_fiscal_years("bokslut.rapporter") == []


class TestThreadRepositoryGet:
    def test_find_returns_none_when_the_view_has_no_thread_in_that_year(self):
        fy = _fiscal_year()
        assert ThreadRepository.find("bocker.balans", fy.id) is None

    def test_find_returns_the_existing_thread(self):
        fy = _fiscal_year()
        created = ThreadRepository.get_or_create(
            view_key="bocker.balans",
            fiscal_year_id=fy.id,
            model="opencode/claude-opus-5",
        )

        found = ThreadRepository.find("bocker.balans", fy.id)

        assert found is not None
        assert found.id == created.id

    def test_set_model_changes_the_threads_model(self):
        fy = _fiscal_year()
        thread = ThreadRepository.get_or_create(
            view_key="bocker.balans",
            fiscal_year_id=fy.id,
            model="opencode/claude-opus-5",
        )

        ThreadRepository.set_model(thread.id, "opencode/gpt-5.5")

        assert ThreadRepository.get(thread.id).model == "opencode/gpt-5.5"


# --- T3: since_seq on list_events (SPEC §2, test case 6) --------------------


class TestListEventsSinceSeq:
    """SPEC §2: `agent_run_events.seq` is the marker form SSE follows, and
    `list_events` had no cursor at all before this."""

    @staticmethod
    def _run_with_events(count: int):
        run = AgentRunRepository.create(
            trigger="thread", model="opencode/claude-opus-5", protocol="messages"
        )
        for index in range(count):
            AgentRunRepository.add_event(run.id, "text", f'{{"n": {index}}}')
        return run

    def test_case_6_only_events_after_the_marker(self):
        run = self._run_with_events(5)

        events = AgentRunRepository.list_events(run.id, since_seq=2)

        assert [event.seq for event in events] == [3, 4, 5]

    def test_a_marker_at_the_last_seq_returns_nothing(self):
        run = self._run_with_events(3)

        assert AgentRunRepository.list_events(run.id, since_seq=3) == []

    def test_existing_callers_are_unchanged(self):
        """The acceptance criterion in T3: omitting the marker still returns
        the whole run, in order."""
        run = self._run_with_events(4)

        assert [event.seq for event in AgentRunRepository.list_events(run.id)] == [
            1,
            2,
            3,
            4,
        ]

    def test_the_marker_does_not_leak_across_runs(self):
        first = self._run_with_events(3)
        second = self._run_with_events(3)

        events = AgentRunRepository.list_events(second.id, since_seq=1)

        assert [event.run_id for event in events] == [second.id, second.id]
        assert first.id not in {event.run_id for event in events}


# --- T4: the generic tool loop (SPEC §11, test cases 7, 8) ------------------


def _usage(output_tokens: int = 0) -> Usage:
    return Usage(input_tokens=0, output_tokens=output_tokens, cache_read_input_tokens=0)


def _turn(
    text: str = "",
    tool_calls: Optional[list] = None,
    stop: str = "end",
    output_tokens: int = 0,
) -> LLMTurn:
    return LLMTurn(
        text=text,
        tool_calls=tool_calls or [],
        # `cast`, not a `StopReason` annotation on the parameter: one test
        # deliberately passes a value outside the Literal ("something_new")
        # to prove the loop refuses to treat an uncategorized stop reason as
        # a silent success.
        stop=cast(StopReason, stop),
        usage=_usage(output_tokens),
    )


class FakeLLMClient:
    """Structural `LLMClient` double (SPEC §9), the pattern from
    `tests/test_agent_runtime.py`: a queue of ready-made `LLMTurn`s, never a
    network call. `self.calls` records what was actually sent.

    Its one new responsibility for `tradar` (T5) is calling `on_text` /
    `on_tool_call` before it returns its turn — a real adapter streams
    increments out as they arrive, and a double that returns a finished turn
    in silence could never show that the session wires the hooks up.
    """

    def __init__(
        self,
        turns: list,
        capabilities: Optional[LLMCapabilities] = None,
        text_increments: Optional[list] = None,
    ):
        self._turns = list(turns)
        self.capabilities = capabilities or LLMCapabilities(
            cache_breakpoint=True,
            pdf_document_blocks=True,
            refusal_stop_reason=True,
            streaming=True,
        )
        #: What the adapter "streams" per turn. `None` means: stream the
        #: turn's own text as one increment, which is what an adapter that
        #: cannot stream at all would effectively deliver.
        self._text_increments = text_increments
        self.calls: list[dict] = []

    def run_turn(
        self,
        system: str,
        messages: list,
        tools: list,
        model: str,
        max_tokens: int,
        on_text=None,
        on_tool_call=None,
    ) -> LLMTurn:
        self.calls.append(
            {
                "system": system,
                "messages": messages,
                "tools": tools,
                "model": model,
                "max_tokens": max_tokens,
                "on_text": on_text,
                "on_tool_call": on_tool_call,
            }
        )
        turn = self._turns.pop(0) if len(self._turns) > 1 else self._turns[0]
        if on_text is not None:
            increments = (
                self._text_increments
                if self._text_increments is not None
                else ([turn.text] if turn.text else [])
            )
            for increment in increments:
                on_text(increment)
        if on_tool_call is not None:
            for tool_call in turn.tool_calls:
                on_tool_call(tool_call.name)
        return turn


def _loop(client, policy, **overrides) -> SessionOutcome:
    """Drive `run_tool_loop` directly, with no document and no thread around
    it — the generic loop is what T4 extracted, so it is what T4 tests."""
    kwargs = {
        "system_prompt": "systemprompt",
        "messages": [{"role": "user", "content": [{"type": "text", "text": "hej"}]}],
        "tools": AGENT_TOOL_DEFINITIONS,
        "model": "opencode/claude-opus-5",
        "actor": "agent",
        "policy": policy,
        "turn_limit": 5,
    }
    kwargs.update(overrides)
    return run_tool_loop(client, **kwargs)


class TestTerminalPolicyBareEnd:
    """Test case 8 — the one row of §11's table where the two paths differ."""

    def test_case_8_a_bare_end_is_an_answer_on_the_thread_path(self):
        client = FakeLLMClient([_turn(text="Den ligger redan bokförd i mars.")])

        outcome = _loop(client, THREAD_POLICY)

        assert outcome.kind == "answered"
        assert outcome.reason is None
        assert outcome.text == "Den ligger redan bokförd i mars."

    def test_case_8_a_bare_end_is_agent_no_outcome_on_the_document_path(self):
        client = FakeLLMClient([_turn(text="Den ligger redan bokförd i mars.")])

        outcome = _loop(client, DOCUMENT_POLICY)

        assert outcome.kind == "abstained"
        assert outcome.reason == "agent_no_outcome"

    def test_an_empty_answer_is_still_an_answer_on_the_thread_path(self):
        client = FakeLLMClient([_turn(text="")])

        outcome = _loop(client, THREAD_POLICY)

        assert outcome.kind == "answered"
        assert outcome.text == ""


class TestTerminalPolicySharedRows:
    """The other five rows of §11's table are identical on both paths — that
    sameness is the point, so it is asserted for both policies."""

    @pytest.mark.parametrize("policy", [DOCUMENT_POLICY, THREAD_POLICY])
    def test_a_refusal_abstains_on_both_paths(self, policy):
        client = FakeLLMClient([_turn(text="Nej.", stop="refusal")])

        outcome = _loop(client, policy)

        assert outcome.kind == "abstained"
        assert outcome.reason.startswith("agent_refusal")

    @pytest.mark.parametrize("policy", [DOCUMENT_POLICY, THREAD_POLICY])
    def test_a_truncated_turn_abstains_on_both_paths(self, policy):
        client = FakeLLMClient([_turn(text="halv", stop="max_tokens")])

        outcome = _loop(client, policy)

        assert outcome.kind == "abstained"
        assert outcome.reason == "agent_output_truncated"

    @pytest.mark.parametrize("policy", [DOCUMENT_POLICY, THREAD_POLICY])
    def test_the_turn_limit_abstains_on_both_paths(self, policy):
        looping_turn = _turn(
            tool_calls=[ToolCall(id="t1", name="las_kontoplan", arguments={})],
            stop="tool_calls",
        )
        client = FakeLLMClient([looping_turn])

        outcome = _loop(client, policy, turn_limit=2)

        assert outcome.kind == "abstained"
        assert outcome.reason == "agent_turn_limit"
        assert len(client.calls) == 2

    @pytest.mark.parametrize("policy", [DOCUMENT_POLICY, THREAD_POLICY])
    def test_an_unknown_stop_reason_fails_on_both_paths(self, policy):
        client = FakeLLMClient([_turn(stop="something_new")])

        outcome = _loop(client, policy)

        assert outcome.kind == "failed"
        assert "unknown_stop_reason" in outcome.reason

    @pytest.mark.parametrize("policy", [DOCUMENT_POLICY, THREAD_POLICY])
    def test_the_output_token_cap_abstains_between_turns_on_both_paths(self, policy):
        looping_turn = _turn(
            tool_calls=[ToolCall(id="t1", name="las_kontoplan", arguments={})],
            stop="tool_calls",
            output_tokens=100,
        )
        client = FakeLLMClient([looping_turn])

        outcome = _loop(client, policy, turn_limit=5, max_output_tokens=50)

        assert outcome.kind == "abstained"
        assert outcome.reason == "agent_output_limit"
        # Cut off the *next* call, never aborted mid-turn: exactly one turn
        # ran, and its tool call was executed.
        assert len(client.calls) == 1


class TestRunSessionStillDelegates:
    """Test case 7 at the unit level; the whole-suite half of it is
    `pytest tests/ -v` staying green after the extraction."""

    def test_run_session_still_abstains_on_a_bare_end(self, tmp_path):
        source = _intake_source(tmp_path)
        client = FakeLLMClient([_turn(text="vet inte")])

        outcome = run_session(
            client=client,
            source=source,
            file_bytes=b"%PDF-1.4 fake, no real text layer",
            open_periods=[],
            today=date(2026, 3, 15),
            model="opencode/claude-opus-5",
            actor="agent",
        )

        assert outcome.kind == "abstained"
        assert outcome.reason == "agent_no_outcome"

    def test_run_session_still_refuses_an_unreadable_document_without_calling_the_llm(
        self, tmp_path
    ):
        source = _intake_source(tmp_path)
        client = FakeLLMClient(
            [_turn(text="")],
            capabilities=LLMCapabilities(
                cache_breakpoint=False,
                pdf_document_blocks=False,
                refusal_stop_reason=False,
            ),
        )

        outcome = run_session(
            client=client,
            source=source,
            file_bytes=b"%PDF-1.4 fake, no real text layer",
            open_periods=[],
            today=date(2026, 3, 15),
            model="opencode/claude-opus-5",
            actor="agent",
        )

        assert outcome.kind == "abstained"
        assert client.calls == []


# --- T5: streaming hooks on LLMClient (SPEC §12.1, test cases 9, 10, 11) ----


class TestAdapterWithoutStreaming:
    """Test case 10 — a complete answer, just without the deltas."""

    def test_case_10_hooks_are_never_called_and_the_turn_is_complete(self):
        client = FakeLLMClient(
            [_turn(text="Svaret i sin helhet.")],
            capabilities=LLMCapabilities(
                cache_breakpoint=False,
                pdf_document_blocks=False,
                refusal_stop_reason=False,
                streaming=False,
            ),
        )
        seen: list = []

        outcome = _loop(
            client, THREAD_POLICY, on_text=seen.append, on_tool_call=seen.append
        )

        assert outcome.kind == "answered"
        assert outcome.text == "Svaret i sin helhet."
        assert seen == []
        # Not merely ignored by the adapter — never handed to it at all, so
        # an adapter written before the hooks existed is called as it always
        # was.
        assert client.calls[0]["on_text"] is None
        assert client.calls[0]["on_tool_call"] is None

    def test_a_streaming_adapter_does_get_the_hooks(self):
        client = FakeLLMClient([_turn(text="Hej.")])
        seen: list = []

        _loop(client, THREAD_POLICY, on_text=seen.append)

        assert seen == ["Hej."]
        assert client.calls[0]["on_text"] is not None
        # Only the hook that was actually given is passed on.
        assert client.calls[0]["on_tool_call"] is None


class TestCurrentActivityCarriesTheToolName:
    """Test case 11 — what A10 deliberately left coarse, now that T5's hook
    exists."""

    def test_case_11_current_activity_is_the_tool_name_during_a_tool_call(
        self, tmp_path, agent_intake_dir
    ):
        _ensure_accounts()
        # Created for its effect on the queue: the pass needs something
        # pending to work on.
        _intake_source(tmp_path)
        worker = AgentWorker()
        observed: list = []

        class _ObservingClient(FakeLLMClient):
            def run_turn(self, *args, **kwargs):
                turn = super().run_turn(*args, **kwargs)
                # Read *after* the hook fired for this turn's tool calls,
                # which is exactly when a status request would see it.
                observed.append(worker.current_activity)
                return turn

        client = _ObservingClient(
            [
                _turn(
                    tool_calls=[ToolCall(id="t1", name="las_kontoplan", arguments={})],
                    stop="tool_calls",
                ),
                _turn(text="klart"),
            ]
        )

        worker.run_pass_once(client_factory=lambda model: client)

        assert observed[0] == "las_kontoplan"

    def test_current_activity_starts_coarse_and_is_cleared_between_items(
        self, tmp_path, agent_intake_dir
    ):
        _ensure_accounts()
        # Created for its effect on the queue: the pass needs something
        # pending to work on.
        _intake_source(tmp_path)
        worker = AgentWorker()
        before_any_tool_call: list = []

        class _ObservingClient(FakeLLMClient):
            def run_turn(self, *args, **kwargs):
                before_any_tool_call.append(worker.current_activity)
                return super().run_turn(*args, **kwargs)

        client = _ObservingClient([_turn(text="vet inte")])

        worker.run_pass_once(client_factory=lambda model: client)

        assert before_any_tool_call == ["processing"]
        assert worker.current_activity is None


# --- T6: the thread session (SPEC §6.1/§6.3/§6.4, cases 12-15, 29, 30) ------


def _thread_with_posts(*texts: str, model: str = "opencode/claude-opus-5"):
    """A thread plus one `user_text` post per text, and the fiscal year they
    hang off."""
    fy = _fiscal_year()
    thread = ThreadRepository.get_or_create(
        view_key="bocker.verifikationer", fiscal_year_id=fy.id, model=model
    )
    posts = [
        ThreadRepository.add_post(
            thread_id=thread.id,
            post_type="user_text",
            actor="stefan",
            body={"text": text},
        )
        for text in texts
    ]
    return thread, posts


def _run_thread(client, thread, trigger_post, message="Hur ligger mars till?", **kw):
    kwargs = dict(
        history=[],
        open_periods=[],
        today=date(2026, 3, 15),
        model="opencode/claude-opus-5",
        actor="agent",
    )
    kwargs.update(kw)
    return run_thread_session(client, thread, trigger_post, message, **kwargs)


class TestSystemPromptIsShared:
    """Test case 12 — the cache breakpoint must not move for the thread's
    sake (SPEC-agentruntime §6.6)."""

    def test_case_12_thread_turn_sends_the_identical_system_prompt(self, tmp_path):
        _ensure_accounts()
        source = _intake_source(tmp_path)
        thread, posts = _thread_with_posts("hej")

        document_client = FakeLLMClient([_turn(text="vet inte")])
        run_session(
            client=document_client,
            source=source,
            file_bytes=b"%PDF-1.4 fake, no real text layer",
            open_periods=[],
            today=date(2026, 3, 15),
            model="opencode/claude-opus-5",
            actor="agent",
        )

        thread_client = FakeLLMClient([_turn(text="Svar.")])
        _run_thread(thread_client, thread, posts[0])

        assert thread_client.calls[0]["system"] == document_client.calls[0]["system"]

    def test_todays_date_is_in_the_user_turn_not_the_system_prompt(self):
        _ensure_accounts()
        thread, posts = _thread_with_posts("hej")
        client = FakeLLMClient([_turn(text="Svar.")])

        _run_thread(client, thread, posts[0])

        call = client.calls[0]
        assert "2026-03-15" not in call["system"]
        assert "2026-03-15" in call["messages"][0]["content"][0]["text"]

    def test_the_new_message_and_open_periods_reach_the_user_turn(self):
        _ensure_accounts()
        thread, posts = _thread_with_posts("hej")
        period = PeriodRepository.create_period(
            fiscal_year_id=thread.fiscal_year_id,
            year=2026,
            month=3,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        )
        client = FakeLLMClient([_turn(text="Svar.")])

        _run_thread(
            client,
            thread,
            posts[0],
            message="Bokför kvittot från Fello.",
            open_periods=[period],
        )

        text = client.calls[0]["messages"][0]["content"][0]["text"]
        assert "Bokför kvittot från Fello." in text
        assert period.id in text


class TestThreadWindow:
    """Test case 13 — clipped at the budget, and what fell away is *left
    out*, never summarized (SPEC §6.3)."""

    @staticmethod
    def _posts(count: int, text: str = "x" * 300):
        fy = _fiscal_year()
        thread = ThreadRepository.get_or_create(
            view_key="bocker.balans",
            fiscal_year_id=fy.id,
            model="opencode/claude-opus-5",
        )
        return [
            ThreadRepository.add_post(
                thread_id=thread.id,
                post_type="user_text",
                actor="stefan",
                body={"text": f"{index}-{text}"},
            )
            for index in range(count)
        ]

    def test_case_13_the_window_is_cut_at_the_token_budget(self):
        posts = self._posts(10)

        window = build_thread_window(posts, budget_tokens=300)

        assert 0 < len(window) < 10
        rendered = "".join(render_post(post) for post in window)
        assert estimate_tokens(rendered) <= 300

    def test_case_13_the_newest_posts_are_the_ones_kept(self):
        posts = self._posts(10)

        window = build_thread_window(posts, budget_tokens=300)

        assert window[-1].seq == posts[-1].seq
        assert window == posts[-len(window) :]

    def test_the_window_stays_in_chronological_order(self):
        posts = self._posts(10)

        window = build_thread_window(posts, budget_tokens=600)

        assert [post.seq for post in window] == sorted(post.seq for post in window)

    def test_a_thread_that_fits_is_kept_whole(self):
        posts = self._posts(3, text="kort")

        assert build_thread_window(posts, budget_tokens=10_000) == posts

    def test_case_13_what_fell_away_is_stated_as_omitted_never_summarized(self):
        """The prompt says posts are missing, and says they were left out.
        A paraphrase the human cannot check is exactly what §6.3 forbids."""
        _ensure_accounts()
        thread, posts = _thread_with_posts(
            *[f"meddelande {i} " + "y" * 400 for i in range(8)]
        )
        client = FakeLLMClient([_turn(text="Svar.")])

        _run_thread(client, thread, posts[-1], history=posts, window_budget_tokens=300)

        text = client.calls[0]["messages"][0]["content"][0]["text"]
        assert "utelämnade, inte sammanfattade" in text
        # The oldest post's content is genuinely gone -- not condensed.
        assert "meddelande 0" not in text

    def test_an_empty_thread_produces_an_empty_window(self):
        assert build_thread_window([], budget_tokens=1000) == []


class TestThreadToolSurface:
    """Test case 14 **is** test case 17 from `agentruntime`, run against the
    thread path. The append-only rule's only automatic check through the
    agent's surface — it must break if someone adds a convenient tool."""

    def test_case_14_the_thread_is_offered_exactly_the_same_tools(self):
        """The thread gets `AGENT_TOOL_DEFINITIONS` and nothing of its own.

        The assertion is equality with that list, not a count: the surface
        grew to ten with `beslut`'s `be_om_beslut` (SPEC-beslut.md §11.3),
        and what this test exists to catch is a tool the *thread path* hands
        out that the document path does not — which a hardcoded number would
        miss the day the shared list changes for a legitimate reason.
        """
        _ensure_accounts()
        thread, posts = _thread_with_posts("hej")
        client = FakeLLMClient([_turn(text="Svar.")])

        _run_thread(client, thread, posts[0])

        offered = client.calls[0]["tools"]
        assert offered == AGENT_TOOL_DEFINITIONS

    def test_case_14_no_tool_offered_to_the_thread_can_change_a_posted_voucher(self):
        _ensure_accounts()
        thread, posts = _thread_with_posts("hej")
        client = FakeLLMClient([_turn(text="Svar.")])

        _run_thread(client, thread, posts[0])

        forbidden = [
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
        for tool in client.calls[0]["tools"]:
            lowered = tool["name"].lower()
            for fragment in forbidden:
                assert fragment not in lowered, f"{tool['name']!r} has {fragment!r}"

    def test_case_14_only_posta_verifikation_touches_the_ledger(self):
        _ensure_accounts()
        thread, posts = _thread_with_posts("hej")
        client = FakeLLMClient([_turn(text="Svar.")])

        _run_thread(client, thread, posts[0])

        for tool in client.calls[0]["tools"]:
            if tool["name"] != "posta_verifikation":
                assert "huvudboken" not in tool["description"].lower()

    def test_the_tool_order_is_not_reordered_for_the_threads_sake(self):
        """`_TOOL_SPECS`' order is part of the cached prefix — an accidental
        reorder is a silent cache-buster (SPEC-agentruntime §6.6)."""
        _ensure_accounts()
        thread, posts = _thread_with_posts("hej")
        client = FakeLLMClient([_turn(text="Svar.")])

        _run_thread(client, thread, posts[0])

        assert [tool["name"] for tool in client.calls[0]["tools"]] == [
            tool["name"] for tool in AGENT_TOOL_DEFINITIONS
        ]


class TestThreadIdempotencyKey:
    """Test case 15, and §6.4's "hängd på användarinlägget, inte på tiden"."""

    def test_the_key_is_derived_from_thread_and_post_not_from_the_clock(self):
        first = derive_thread_posting_idempotency_key("thread-1", "post-1")
        second = derive_thread_posting_idempotency_key("thread-1", "post-1")

        assert first == second
        assert uuid.UUID(first)

    def test_different_posts_derive_different_keys(self):
        assert derive_thread_posting_idempotency_key(
            "t1", "p1"
        ) != derive_thread_posting_idempotency_key("t1", "p2")

    def test_it_is_a_separate_namespace_from_intake(self):
        """§6.4: a namespace *beside* `intake:{source_id}`, so a thread key
        can never collide with a document one."""
        assert derive_thread_posting_idempotency_key(
            "t1", "p1"
        ) != derive_posting_idempotency_key("p1")

    def test_case_15_two_postings_from_the_same_user_post_give_one_voucher(
        self, tmp_path
    ):
        _ensure_accounts()
        period = PeriodRepository.create_period(
            fiscal_year_id=_fiscal_year().id,
            year=2026,
            month=3,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        )
        thread = ThreadRepository.get_or_create(
            view_key="bocker.verifikationer",
            fiscal_year_id=period.fiscal_year_id,
            model="opencode/claude-opus-5",
        )
        trigger = ThreadRepository.add_post(
            thread_id=thread.id,
            post_type="user_text",
            actor="stefan",
            body={"text": "Bokför kvittot."},
        )
        # A posting always cites its source material -- `post_agent_voucher`
        # refuses one that doesn't (`missing_source_traceability`), on the
        # thread path exactly as on the document path.
        source = _intake_source(tmp_path)
        args = _posting_args(period.id, source.id)
        posting_turn = _turn(
            tool_calls=[ToolCall(id="t1", name="posta_verifikation", arguments=args)],
            stop="tool_calls",
        )

        first = _run_thread(
            FakeLLMClient([posting_turn]),
            thread,
            trigger,
            message="Bokför kvittot.",
        )
        second = _run_thread(
            FakeLLMClient([posting_turn]),
            thread,
            trigger,
            message="Bokför kvittot.",
        )

        assert first.kind == "posted"
        assert second.kind == "posted"
        # The second one replayed the stored response instead of writing a
        # second voucher into a book that cannot be tidied up.
        assert second.tool_result.get("idempotent_replay") is True
        assert db.execute("SELECT COUNT(*) AS n FROM vouchers").fetchone()["n"] == 1

    def test_a_different_user_post_is_a_different_intent(self, tmp_path):
        """Two separate messages are two intents, even with identical text:
        the key hangs on the post, so the second one is not swallowed."""
        _ensure_accounts()
        thread, posts = _thread_with_posts("Bokför kvittot.", "Bokför kvittot.")

        assert derive_thread_posting_idempotency_key(
            thread.id, posts[0].id
        ) != derive_thread_posting_idempotency_key(thread.id, posts[1].id)


class TestThreadKeyDoesNotDefeatTheIntakeGuard:
    """The thread key wins over the intake-derived one (§6.4). The risk that
    creates is a source posted once from each path under two different keys —
    so this pins the guard that actually stops it, which is not the key at
    all but `intake_already_linked`."""

    def test_a_source_posted_from_the_thread_cannot_be_posted_again(self, tmp_path):
        _ensure_accounts()
        period = PeriodRepository.create_period(
            fiscal_year_id=_fiscal_year().id,
            year=2026,
            month=3,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        )
        thread = ThreadRepository.get_or_create(
            view_key="bocker.verifikationer",
            fiscal_year_id=period.fiscal_year_id,
            model="opencode/claude-opus-5",
        )
        trigger = ThreadRepository.add_post(
            thread_id=thread.id,
            post_type="user_text",
            actor="stefan",
            body={"text": "Bokför."},
        )
        source = _intake_source(tmp_path)
        args = _posting_args(period.id, source.id)

        first = _run_thread(
            FakeLLMClient(
                [
                    _turn(
                        tool_calls=[
                            ToolCall(id="t1", name="posta_verifikation", arguments=args)
                        ],
                        stop="tool_calls",
                    )
                ]
            ),
            thread,
            trigger,
        )
        assert first.kind == "posted"

        # A *different* user post, so a different key -- the idempotency
        # layer has nothing to say here. The intake link is what refuses.
        second_trigger = ThreadRepository.add_post(
            thread_id=thread.id,
            post_type="user_text",
            actor="stefan",
            body={"text": "Bokför igen."},
        )
        second = _run_thread(
            FakeLLMClient(
                [
                    _turn(
                        tool_calls=[
                            ToolCall(id="t2", name="posta_verifikation", arguments=args)
                        ],
                        stop="tool_calls",
                    )
                ]
            ),
            thread,
            second_trigger,
            max_tool_turns=1,
        )

        assert second.kind != "posted"
        assert db.execute("SELECT COUNT(*) AS n FROM vouchers").fetchone()["n"] == 1


class TestThreadFailureOutcomes:
    """Test case 29 — a refusal, a truncated turn and an uncorrected tool
    error are never postings."""

    def test_case_29_a_refusal_is_an_abstention_not_a_posting(self):
        _ensure_accounts()
        thread, posts = _thread_with_posts("hej")

        outcome = _run_thread(
            FakeLLMClient([_turn(text="Nej.", stop="refusal")]), thread, posts[0]
        )

        assert outcome.kind == "abstained"
        assert outcome.reason.startswith("agent_refusal")
        assert outcome.voucher_id is None
        assert db.execute("SELECT COUNT(*) AS n FROM vouchers").fetchone()["n"] == 0

    def test_case_29_a_truncated_turn_is_an_abstention_not_a_posting(self):
        _ensure_accounts()
        thread, posts = _thread_with_posts("hej")

        outcome = _run_thread(
            FakeLLMClient([_turn(text="halv", stop="max_tokens")]), thread, posts[0]
        )

        assert outcome.kind == "abstained"
        assert outcome.reason == "agent_output_truncated"
        assert db.execute("SELECT COUNT(*) AS n FROM vouchers").fetchone()["n"] == 0

    def test_case_29_an_uncorrected_tool_error_never_becomes_a_posting(self):
        _ensure_accounts()
        thread, posts = _thread_with_posts("hej")
        failing_turn = _turn(
            tool_calls=[
                ToolCall(id="t1", name="posta_verifikation", arguments={"rows": []})
            ],
            stop="tool_calls",
        )

        outcome = _run_thread(
            FakeLLMClient([failing_turn]), thread, posts[0], max_tool_turns=2
        )

        assert outcome.kind == "abstained"
        assert outcome.reason == "agent_turn_limit"
        assert db.execute("SELECT COUNT(*) AS n FROM vouchers").fetchone()["n"] == 0
        # The error reached the model as a correctable tool_result, which is
        # what "får rätta sig själv inom varvtaket" means.
        failed = outcome.turns[0].executed_tool_calls[0]
        assert failed.ok is False
        assert failed.error


class TestThreadCapsBetweenTurns:
    """Test case 30 — the daily cap stops a thread turn *between* turns."""

    def test_case_30_the_check_stops_the_next_turn_and_never_aborts_one(self):
        _ensure_accounts()
        thread, posts = _thread_with_posts("hej")
        looping_turn = _turn(
            tool_calls=[ToolCall(id="t1", name="las_kontoplan", arguments={})],
            stop="tool_calls",
        )
        client = FakeLLMClient([looping_turn])
        checks: list = []

        def _budget_exhausted():
            checks.append("checked")
            return "budget_exhausted: spent 5000 of 5000 öre"

        outcome = _run_thread(
            client,
            thread,
            posts[0],
            max_tool_turns=5,
            check_between_turns=_budget_exhausted,
        )

        assert outcome.kind == "abstained"
        assert outcome.reason.startswith("budget_exhausted")
        # One turn ran, its tool call completed, and the *next* call never
        # happened. The check ran after the turn, not inside it.
        assert len(client.calls) == 1
        assert checks == ["checked"]
        assert outcome.turns[0].executed_tool_calls[0].ok is True

    def test_a_check_that_says_continue_does_not_stop_the_loop(self):
        _ensure_accounts()
        thread, posts = _thread_with_posts("hej")
        client = FakeLLMClient(
            [
                _turn(
                    tool_calls=[ToolCall(id="t1", name="las_kontoplan", arguments={})],
                    stop="tool_calls",
                ),
                _turn(text="Klart."),
            ]
        )

        outcome = _run_thread(
            client,
            thread,
            posts[0],
            max_tool_turns=5,
            check_between_turns=lambda: None,
        )

        assert outcome.kind == "answered"
        assert outcome.text == "Klart."
        assert len(client.calls) == 2

    def test_a_posting_turn_is_never_overridden_by_the_check(self, tmp_path):
        """The check only ever prevents the *next* call; a turn that already
        reached a terminal outcome returns it."""
        _ensure_accounts()
        period = PeriodRepository.create_period(
            fiscal_year_id=_fiscal_year().id,
            year=2026,
            month=3,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        )
        thread = ThreadRepository.get_or_create(
            view_key="bocker.verifikationer",
            fiscal_year_id=period.fiscal_year_id,
            model="opencode/claude-opus-5",
        )
        trigger = ThreadRepository.add_post(
            thread_id=thread.id,
            post_type="user_text",
            actor="stefan",
            body={"text": "Bokför."},
        )
        source = _intake_source(tmp_path)
        posting_turn = _turn(
            tool_calls=[
                ToolCall(
                    id="t1",
                    name="posta_verifikation",
                    arguments=_posting_args(period.id, source.id),
                )
            ],
            stop="tool_calls",
        )

        outcome = _run_thread(
            FakeLLMClient([posting_turn]),
            thread,
            trigger,
            check_between_turns=lambda: "budget_exhausted",
        )

        assert outcome.kind == "posted"


# --- T7: runtime events → posts (SPEC §6.2, test cases 16, 17) -------------


def _run_with_tool_calls(*calls) -> str:
    """An `agent_runs` row with one `tool_call` event per `(name, result)`."""
    run = AgentRunRepository.create(
        trigger="thread", model="opencode/claude-opus-5", protocol="messages"
    )
    for name, result in calls:
        AgentRunRepository.add_event(
            run.id,
            "tool_call",
            json.dumps({"name": name, "args": {}, "result": result}),
        )
    return run.id


class TestTracesAreChipsNotPosts:
    """Test case 16 — nine tool calls are one reply with nine chips, never
    nine replies (`komponenter.md`: `SparChip` is a row under the text)."""

    def test_case_16_a_tool_call_becomes_a_trace_not_its_own_post(self):
        thread, _ = _thread_with_posts()
        run_id = _run_with_tool_calls(
            ("las_kontoplan", {"items": []}),
            ("las_perioder", {"items": []}),
        )

        post = ThreadService.record_outcome(
            thread, run_id, SessionOutcome(kind="answered", text="Svar.")
        )

        assert post.type == "agent_text"
        assert [trace["tool"] for trace in post.traces] == [
            "las_kontoplan",
            "las_perioder",
        ]
        # One post, not three.
        assert len(ThreadRepository.list_posts(thread.id)) == 1

    def test_traces_are_in_the_order_the_calls_happened(self):
        thread, _ = _thread_with_posts()
        run_id = _run_with_tool_calls(
            ("las_underlag", {}),
            ("las_kontoplan", {}),
            ("las_perioder", {}),
        )

        post = ThreadService.record_outcome(
            thread, run_id, SessionOutcome(kind="answered", text="Svar.")
        )

        assert [trace["tool"] for trace in post.traces] == [
            "las_underlag",
            "las_kontoplan",
            "las_perioder",
        ]

    def test_a_chip_says_what_happened_not_which_function_ran(self):
        thread, _ = _thread_with_posts()
        run_id = _run_with_tool_calls(("las_kontoplan", {}))

        post = ThreadService.record_outcome(
            thread, run_id, SessionOutcome(kind="answered", text="Svar.")
        )

        assert post.traces[0]["label"] == "kontoplanen läst"

    def test_a_posting_chip_carries_the_voucher_number(self):
        thread, _ = _thread_with_posts()
        run_id = _run_with_tool_calls(
            ("posta_verifikation", {"id": "v-1", "series": "A", "number": 118})
        )

        post = ThreadService.record_outcome(
            thread, run_id, SessionOutcome(kind="posted", voucher_id="v-1")
        )

        assert post.traces[0]["detail"] == "A-118"
        assert post.traces[0]["voucher_id"] == "v-1"

    def test_a_run_without_tool_calls_has_no_traces(self):
        thread, _ = _thread_with_posts()
        run_id = _run_with_tool_calls()

        post = ThreadService.record_outcome(
            thread, run_id, SessionOutcome(kind="answered", text="Svar.")
        )

        assert post.traces is None

    def test_non_tool_call_events_are_not_chips(self):
        thread, _ = _thread_with_posts()
        run = AgentRunRepository.create(
            trigger="thread", model="opencode/claude-opus-5", protocol="messages"
        )
        AgentRunRepository.add_event(run.id, "text", json.dumps({"text": "tänker"}))
        AgentRunRepository.add_event(run.id, "posted", json.dumps({"reason": None}))

        post = ThreadService.record_outcome(
            thread, run.id, SessionOutcome(kind="answered", text="Svar.")
        )

        assert post.traces is None


class TestBase64NeverReachesAPost:
    """Test case 17 — the `_compact_tool_result` precedent, applied again
    where a post is built."""

    _BASE64 = "JVBERi0xLjQKJeLjz9MK" * 500

    def test_case_17_a_document_block_result_is_stripped_from_traces(self):
        thread, _ = _thread_with_posts()
        run_id = _run_with_tool_calls(
            (
                "hamta_underlagsfil",
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": self._BASE64,
                    },
                },
            )
        )

        post = ThreadService.record_outcome(
            thread, run_id, SessionOutcome(kind="answered", text="Svar.")
        )

        stored = db.execute(
            "SELECT traces_json, body_json FROM thread_posts WHERE id = ?",
            (post.id,),
        ).fetchone()
        assert self._BASE64[:64] not in (stored["traces_json"] or "")
        assert self._BASE64[:64] not in stored["body_json"]

    def test_case_17_an_image_block_is_stripped_too(self):
        thread, _ = _thread_with_posts()
        run_id = _run_with_tool_calls(
            (
                "hamta_underlagsfil",
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": self._BASE64,
                    },
                },
            )
        )

        post = ThreadService.record_outcome(
            thread, run_id, SessionOutcome(kind="answered", text="Svar.")
        )

        stored = db.execute(
            "SELECT traces_json FROM thread_posts WHERE id = ?", (post.id,)
        ).fetchone()
        assert self._BASE64[:64] not in (stored["traces_json"] or "")

    def test_a_nested_data_field_is_replaced_not_truncated(self):
        """A truncated base64 string is not smaller in any way that matters,
        and is no longer valid for anything."""
        compacted = compact(
            {"rows": [{"source": {"data": self._BASE64, "media_type": "image/png"}}]}
        )

        assert compacted["rows"][0]["source"]["data"] == "<binary content omitted>"
        assert compacted["rows"][0]["source"]["media_type"] == "image/png"

    def test_a_long_plain_string_is_truncated_not_dropped(self):
        """An over-long ordinary value is shortened, not lost — a chip is one
        line, but the reader should still see what it was about."""
        compacted = compact({"summary": "x" * 500})

        assert compacted["summary"].endswith("…")
        assert len(compacted["summary"]) < 500
        assert compacted["summary"].startswith("xxx")

    def test_ordinary_values_pass_through_untouched(self):
        payload = {"items": [1, 2, 3], "total": 12500, "note": "kort text"}

        assert compact(payload) == payload

    def test_deep_nesting_is_floored_rather_than_recursing_forever(self):
        deep: dict = {"a": {}}
        node = deep["a"]
        for _ in range(20):
            node["a"] = {}
            node = node["a"]

        compact(deep)  # must return, not raise RecursionError


class TestOutcomeRendering:
    """The §6.2/§11 mapping from an outcome to a post type."""

    def test_an_answer_becomes_agent_text(self):
        thread, _ = _thread_with_posts()
        run_id = _run_with_tool_calls()

        post = ThreadService.record_outcome(
            thread, run_id, SessionOutcome(kind="answered", text="Mars är klar.")
        )

        assert post.type == "agent_text"
        assert post.body["text"] == "Mars är klar."

    def test_a_posting_becomes_agent_text_carrying_the_voucher_id(self):
        thread, _ = _thread_with_posts()
        run_id = _run_with_tool_calls()

        post = ThreadService.record_outcome(
            thread,
            run_id,
            SessionOutcome(kind="posted", voucher_id="v-1", text="Bokförd på 6212."),
        )

        assert post.type == "agent_text"
        assert post.body["voucher_id"] == "v-1"

    def test_a_silent_posting_states_the_fact_rather_than_inventing_words(self):
        thread, _ = _thread_with_posts()
        run_id = _run_with_tool_calls()

        post = ThreadService.record_outcome(
            thread, run_id, SessionOutcome(kind="posted", voucher_id="v-1", text="")
        )

        assert post.body["text"] == "Verifikationen är postad."

    def test_a_registered_abstention_becomes_a_decision(self):
        """§11: `registrera_avstaende` → `abstained`, blir ett
        `decision`-inlägg."""
        thread, _ = _thread_with_posts()
        run_id = _run_with_tool_calls()

        post = ThreadService.record_outcome(
            thread,
            run_id,
            SessionOutcome(
                kind="abstained",
                reason="Oklart om det är representation eller kontorsmaterial",
                tool_result={"summary": "Behöver veta vad inköpet avsåg"},
            ),
        )

        assert post.type == "decision"
        assert post.body["title"] == "Behöver veta vad inköpet avsåg"
        # The agent's own wording, never rewritten (datakontrakt.md §2).
        assert "representation" in post.body["reason"]

    def test_a_refusal_becomes_an_error_with_cause_and_consequence(self):
        thread, _ = _thread_with_posts()
        run_id = _run_with_tool_calls()

        post = ThreadService.record_outcome(
            thread,
            run_id,
            SessionOutcome(kind="abstained", reason="agent_refusal: nej"),
        )

        assert post.type == "error"
        assert post.body["cause"] == "agent_refusal: nej"
        # The consequence is in bookkeeping terms (§6.7), not agent terms.
        assert "bokfördes" in post.body["consequence"]

    def test_each_named_failure_gets_its_own_consequence(self):
        thread, _ = _thread_with_posts()
        run_id = _run_with_tool_calls()

        truncated = ThreadService.record_outcome(
            thread,
            run_id,
            SessionOutcome(kind="abstained", reason="agent_output_truncated"),
        )
        turn_limit = ThreadService.record_outcome(
            thread, run_id, SessionOutcome(kind="abstained", reason="agent_turn_limit")
        )

        assert truncated.body["consequence"] != turn_limit.body["consequence"]
        assert "klipptes" in truncated.body["consequence"]

    def test_a_failed_outcome_becomes_an_error(self):
        thread, _ = _thread_with_posts()
        run_id = _run_with_tool_calls()

        post = ThreadService.record_outcome(
            thread,
            run_id,
            SessionOutcome(kind="failed", reason="unknown_stop_reason: 'x'"),
        )

        assert post.type == "error"

    def test_a_connection_failure_becomes_an_error_post_with_no_run(self):
        """§6.7: the thread never loses a turn in silence."""
        thread, _ = _thread_with_posts()

        post = ThreadService.record_error(thread, "llm_connection_error: gateway nere")

        assert post.type == "error"
        assert "försök igen" in post.body["consequence"].lower()
        assert post.run_id is None

    def test_retry_carries_the_same_draft_id(self):
        """§6.7: `Försök igen` bär **samma utkast-id**."""
        thread, _ = _thread_with_posts()

        post = ThreadService.record_error(
            thread, "agent_turn_limit", retry_draft_id="draft-7"
        )

        assert post.body["retry_draft_id"] == "draft-7"

    def test_the_streamed_text_is_what_gets_stored(self):
        """What the human watched appear is what ends up in the thread — the
        client replaces its optimistic rows with this post (§4)."""
        thread, _ = _thread_with_posts()
        run_id = _run_with_tool_calls()

        post = ThreadService.record_outcome(
            thread,
            run_id,
            SessionOutcome(kind="answered", text="ignoreras"),
            answer_text="Det som strömmade ut.",
        )

        assert post.body["text"] == "Det som strömmade ut."

    def test_the_post_is_bound_to_the_run_that_made_it(self):
        """§4: `run_id` is what makes a model switch mid-thread visible
        afterwards."""
        thread, _ = _thread_with_posts()
        run_id = _run_with_tool_calls()

        post = ThreadService.record_outcome(
            thread, run_id, SessionOutcome(kind="answered", text="Svar.")
        )

        assert post.run_id == run_id


class TestUserPosts:
    def test_a_file_post_carries_metadata_and_a_reference_never_content(self):
        """§6.2: the file card's metadata and a reference, never the bytes."""
        thread, _ = _thread_with_posts()

        post = ThreadService.record_user_file(
            thread,
            filename="kvitto.pdf",
            size_bytes=218_000,
            pages=1,
            intake_source_id="src-1",
            actor="stefan",
        )

        assert post.type == "user_file"
        assert post.body == {
            "filename": "kvitto.pdf",
            "size_bytes": 218_000,
            "pages": 1,
            "intake_source_id": "src-1",
        }
        assert "data" not in post.body

    def test_a_user_message_is_written_as_the_person_not_the_agent(self):
        thread, _ = _thread_with_posts()

        post = ThreadService.record_user_message(thread, "Hej!", actor="stefan")

        assert post.type == "user_text"
        assert post.actor == "stefan"


class TestRuntimeKnowsNothingOfThreads:
    """SPEC §8.1 — the boundary, checked structurally so it breaks loudly if
    a `thread_id` is ever threaded down into the runtime.

    Checked against the parsed code, not the file's text: a docstring may
    perfectly well *explain* what its caller passes (and one does, where
    `run_tool_loop` documents the key the thread path names for it). The
    rule is that the runtime must not take, hold or import one — that is a
    fact about identifiers and imports, so that is what is asserted.
    """

    _RUNTIME_MODULES = ("services/agent_runtime.py", "services/agent_session.py")

    @staticmethod
    def _parse(module: str):
        import ast
        from pathlib import Path

        return ast.parse(
            (Path(__file__).parent.parent / module).read_text(encoding="utf-8")
        )

    def test_no_runtime_function_takes_a_thread_argument(self):
        import ast

        for module in self._RUNTIME_MODULES:
            for node in ast.walk(self._parse(module)):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                arguments = node.args
                names = [
                    argument.arg
                    for argument in (
                        arguments.args + arguments.kwonlyargs + arguments.posonlyargs
                    )
                ]
                for name in names:
                    assert "thread" not in name.lower(), (
                        f"{module}:{node.name} takes {name!r} -- the runtime "
                        "must not know what a thread is (SPEC §8.1)"
                    )

    def test_no_runtime_module_imports_thread_storage_or_the_thread_session(self):
        import ast

        forbidden = {
            "repositories.thread_repo",
            "services.thread_service",
            "services.thread_session",
        }
        for module in self._RUNTIME_MODULES:
            for node in ast.walk(self._parse(module)):
                if isinstance(node, ast.ImportFrom):
                    assert (
                        node.module not in forbidden
                    ), f"{module} imports {node.module}"
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        assert (
                            alias.name not in forbidden
                        ), f"{module} imports {alias.name}"

    def test_no_runtime_code_references_a_thread_identifier(self):
        """Names and attributes, with every docstring and comment already
        gone — `ast.parse` keeps neither comments nor a docstring's text as
        an identifier."""
        import ast

        for module in self._RUNTIME_MODULES:
            for node in ast.walk(self._parse(module)):
                if isinstance(node, ast.Name):
                    assert (
                        "thread_id" not in node.id.lower()
                    ), f"{module} references {node.id!r}"
                elif isinstance(node, ast.Attribute):
                    assert (
                        "thread_id" not in node.attr.lower()
                    ), f"{module} references .{node.attr}"


# --- T8: the HTTP routes (SPEC §1, §5, test cases 4, 18) -------------------


THREADS_URL = "/api/v1/threads"


@pytest.fixture
def client(test_db):
    """Test client bound after the database swap (pattern from
    `tests/test_oversikt.py`)."""
    _ensure_accounts()
    from api.main import app

    return TestClient(app)


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {settings.api_key}"}


@pytest.fixture
def current_fiscal_year():
    """A fiscal year containing today, so the route's own resolution finds
    it the way it will in production."""
    today = date.today()
    return PeriodRepository.create_fiscal_year(
        start_date=date(today.year, 1, 1), end_date=date(today.year, 12, 31)
    )


class TestViewKeyIsAClosedList:
    """Test case 4 — an unknown key gives `404`, **not an empty thread**."""

    def test_case_4_an_unknown_view_key_is_404(self, client, auth_headers):
        response = client.get(
            f"{THREADS_URL}/bocker.verifikatoner", headers=auth_headers
        )

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "unknown_view_key"

    def test_case_4_an_unknown_view_key_creates_no_thread(
        self, client, auth_headers, current_fiscal_year
    ):
        client.get(f"{THREADS_URL}/bocker.verifikatoner", headers=auth_headers)
        client.post(
            f"{THREADS_URL}/hittepa.vy/messages",
            json={"text": "hej"},
            headers=auth_headers,
        )

        assert db.execute("SELECT COUNT(*) AS n FROM threads").fetchone()["n"] == 0

    def test_posting_to_an_unknown_view_key_is_404(self, client, auth_headers):
        response = client.post(
            f"{THREADS_URL}/hittepa.vy/messages",
            json={"text": "hej"},
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.parametrize(
        "view_key",
        [
            "bocker.balans",
            "bocker.resultat",
            "bocker.verifikationer",
            "betala.fakturering",
            "betala.loner",
            "bokslut.rapporter",
            "bokslut.atgarder",
        ],
    )
    def test_all_seven_documented_views_are_accepted(
        self, client, auth_headers, view_key
    ):
        response = client.get(f"{THREADS_URL}/{view_key}", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["view_key"] == view_key

    def test_there_are_exactly_seven(self):
        """§5's list is closed — an eighth is a "fråga först" (§8)."""
        assert len(list(ThreadViewKey)) == 7

    def test_a_view_key_carries_no_company_part(self):
        """Decision §12.2: single-tenant. A company prefix would look like a
        separation boundary without being one."""
        for key in ThreadViewKey:
            assert key.value.count(".") == 1

    def test_the_endpoint_requires_authentication(self, client):
        assert client.get(f"{THREADS_URL}/bocker.balans").status_code == 401


class TestGetThread:
    def test_an_unwritten_view_reads_as_an_empty_thread_not_an_error(
        self, client, auth_headers, current_fiscal_year
    ):
        response = client.get(f"{THREADS_URL}/bocker.balans", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["posts"] == []
        assert body["thread_id"] is None

    def test_a_get_creates_nothing(self, client, auth_headers, current_fiscal_year):
        """A pure read. The thread is created by the first message."""
        client.get(f"{THREADS_URL}/bocker.balans", headers=auth_headers)

        assert db.execute("SELECT COUNT(*) AS n FROM threads").fetchone()["n"] == 0

    def test_posts_come_back_oldest_first(
        self, client, auth_headers, current_fiscal_year
    ):
        for text in ("första", "andra", "tredje"):
            client.post(
                f"{THREADS_URL}/bocker.balans/messages",
                json={"text": text},
                headers=auth_headers,
            )

        body = client.get(f"{THREADS_URL}/bocker.balans", headers=auth_headers).json()

        assert [post["body"]["text"] for post in body["posts"]] == [
            "första",
            "andra",
            "tredje",
        ]

    def test_since_returns_only_what_came_after(
        self, client, auth_headers, current_fiscal_year
    ):
        for text in ("a", "b", "c"):
            client.post(
                f"{THREADS_URL}/bocker.balans/messages",
                json={"text": text},
                headers=auth_headers,
            )

        body = client.get(
            f"{THREADS_URL}/bocker.balans?since=1", headers=auth_headers
        ).json()

        assert [post["body"]["text"] for post in body["posts"]] == ["b", "c"]

    def test_a_post_carries_the_fields_the_contract_names(
        self, client, auth_headers, current_fiscal_year
    ):
        """`datakontrakt.md` §1: id, created_at, actor and optional
        traces[]."""
        client.post(
            f"{THREADS_URL}/bocker.balans/messages",
            json={"text": "hej"},
            headers=auth_headers,
        )

        post = client.get(f"{THREADS_URL}/bocker.balans", headers=auth_headers).json()[
            "posts"
        ][0]

        assert set(post) >= {"id", "created_at", "actor", "type", "body", "traces"}
        assert post["traces"] is None

    def test_each_view_has_its_own_thread(
        self, client, auth_headers, current_fiscal_year
    ):
        """`README.md`: "Byter man vy byter man tråd"."""
        client.post(
            f"{THREADS_URL}/bocker.balans/messages",
            json={"text": "till balansen"},
            headers=auth_headers,
        )

        other = client.get(
            f"{THREADS_URL}/bocker.resultat", headers=auth_headers
        ).json()

        assert other["posts"] == []

    def test_an_older_fiscal_year_is_reachable_as_an_archive(
        self, client, auth_headers, current_fiscal_year
    ):
        """Decision §12.3: the thread resets at the turn of the year, and
        older ones are reachable rather than gone."""
        old_year = PeriodRepository.create_fiscal_year(
            start_date=date(2019, 1, 1), end_date=date(2019, 12, 31)
        )
        old_thread = ThreadRepository.get_or_create(
            view_key="bocker.balans",
            fiscal_year_id=old_year.id,
            model="opencode/claude-opus-5",
        )
        ThreadRepository.add_post(
            thread_id=old_thread.id,
            post_type="user_text",
            actor="stefan",
            body={"text": "förra året"},
        )
        client.post(
            f"{THREADS_URL}/bocker.balans/messages",
            json={"text": "i år"},
            headers=auth_headers,
        )

        current = client.get(
            f"{THREADS_URL}/bocker.balans", headers=auth_headers
        ).json()
        archived = client.get(
            f"{THREADS_URL}/bocker.balans?fiscal_year_id={old_year.id}",
            headers=auth_headers,
        ).json()

        assert [p["body"]["text"] for p in current["posts"]] == ["i år"]
        assert [p["body"]["text"] for p in archived["posts"]] == ["förra året"]
        assert old_year.id in current["archive_fiscal_year_ids"]


class TestPostMessage:
    def test_case_18_the_humans_reply_is_written_before_the_agent_answers(
        self, client, auth_headers, current_fiscal_year
    ):
        """§6.1 step 2 — and the response carries her posts and nothing
        else. The agent's answer arrives over the stream."""
        response = client.post(
            f"{THREADS_URL}/bocker.verifikationer/messages",
            json={"text": "Vad ligger i kundfordringar?"},
            headers=auth_headers,
        )

        assert response.status_code == 201
        body = response.json()
        assert len(body["posts"]) == 1
        post = body["posts"][0]
        assert post["type"] == "user_text"
        assert post["actor"] != "agent"
        assert post["body"]["text"] == "Vad ligger i kundfordringar?"
        # It is already durable, not merely echoed back.
        stored = ThreadRepository.list_posts(body["thread_id"])
        assert [p.id for p in stored] == [post["id"]]

    def test_the_response_carries_a_cursor_to_subscribe_from(
        self, client, auth_headers, current_fiscal_year
    ):
        body = client.post(
            f"{THREADS_URL}/bocker.balans/messages",
            json={"text": "hej"},
            headers=auth_headers,
        ).json()

        assert body["cursor"] == 1

    def test_the_first_message_creates_the_thread_once(
        self, client, auth_headers, current_fiscal_year
    ):
        first = client.post(
            f"{THREADS_URL}/bocker.balans/messages",
            json={"text": "ett"},
            headers=auth_headers,
        ).json()
        second = client.post(
            f"{THREADS_URL}/bocker.balans/messages",
            json={"text": "två"},
            headers=auth_headers,
        ).json()

        assert first["thread_id"] == second["thread_id"]
        assert db.execute("SELECT COUNT(*) AS n FROM threads").fetchone()["n"] == 1

    def test_an_empty_message_is_rejected(
        self, client, auth_headers, current_fiscal_year
    ):
        response = client.post(
            f"{THREADS_URL}/bocker.balans/messages",
            json={"text": ""},
            headers=auth_headers,
        )

        assert response.status_code == 422

    def test_without_a_fiscal_year_the_refusal_is_explicit(self, client, auth_headers):
        """A thread belongs to a view *and* a fiscal year — there is nothing
        to hang one off yet, and saying so beats a 500."""
        response = client.post(
            f"{THREADS_URL}/bocker.balans/messages",
            json={"text": "hej"},
            headers=auth_headers,
        )

        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "no_fiscal_year"

    def test_an_attachment_becomes_a_user_file_post_with_no_bytes(
        self, client, auth_headers, current_fiscal_year, tmp_path
    ):
        source = _intake_source(tmp_path, name="kvitto.pdf")

        body = client.post(
            f"{THREADS_URL}/bocker.verifikationer/messages",
            json={"text": "Bokför det här", "attachments": [source.id]},
            headers=auth_headers,
        ).json()

        types = [post["type"] for post in body["posts"]]
        assert types == ["user_text", "user_file"]
        file_post = body["posts"][1]
        assert file_post["body"]["filename"] == "kvitto.pdf"
        assert file_post["body"]["intake_source_id"] == source.id
        assert "data" not in file_post["body"]

    def test_an_unknown_attachment_is_404(
        self, client, auth_headers, current_fiscal_year
    ):
        response = client.post(
            f"{THREADS_URL}/bocker.balans/messages",
            json={"text": "hej", "attachments": ["finns-inte"]},
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "attachment_not_found"

    def test_the_decision_channel_is_plain_text(
        self, client, auth_headers, current_fiscal_year
    ):
        """`README.md`: "Beslutskortets primärknapp är aldrig den enda
        vägen: samma beslut ska gå att uttrycka i text i chattfältet." No
        option id, no special shape — the same endpoint."""
        response = client.post(
            f"{THREADS_URL}/bocker.verifikationer/messages",
            json={"text": "Det är kontorsmaterial, bokför på 6110."},
            headers=auth_headers,
        )

        assert response.status_code == 201


# --- T9: the stream (SPEC §6.5, test cases 19, 20, 21, 22) ----------------


@pytest.fixture
def agent_enabled(monkeypatch):
    """The global switch on — a thread turn is a paid LLM call, and `POST
    /messages` refuses to start one while the agent is off (§7)."""
    monkeypatch.setattr(settings, "agent_runtime_enabled", True)


class _RecordingBroker(ThreadBroker):
    """A broker that also keeps every published frame, so a synchronous test
    can assert on the order events went out in."""

    def __init__(self):
        super().__init__()
        self.published: list = []

    def publish(self, thread_id, event, data):
        self.published.append((event, data))
        super().publish(thread_id, event, data)


def _run_turn_synchronously(thread, trigger_post, client, message="Hur ser mars ut?"):
    """Drive `ThreadTurnRunner.run` in-process rather than through its own
    worker thread: the threading is what `start()` adds, and a test that
    races a background thread proves less than one that doesn't."""
    broker = _RecordingBroker()
    runner = ThreadTurnRunner(broker=broker)
    outcome = runner.run(
        thread, trigger_post, message, client_factory=lambda model: client
    )
    return broker, outcome


class TestStreamEventOrder:
    """Test case 19 — `message.created` → `message.delta`* →
    `message.completed`, in that order."""

    def test_case_19_created_then_deltas_then_completed(self, agent_enabled):
        _ensure_accounts()
        thread, posts = _thread_with_posts("Hej")
        client = FakeLLMClient(
            [_turn(text="Mars är klar.")],
            text_increments=["Mars ", "är ", "klar."],
        )

        broker, outcome = _run_turn_synchronously(thread, posts[0], client)

        kinds = [event for event, _ in broker.published]
        assert kinds[0] == EVENT_MESSAGE_CREATED
        assert kinds[-1] == EVENT_MESSAGE_COMPLETED
        assert kinds[1:-1] == [EVENT_MESSAGE_DELTA] * 3
        assert outcome.kind == "answered"

    def test_case_19_the_deltas_are_increments_not_the_whole_answer(
        self, agent_enabled
    ):
        _ensure_accounts()
        thread, posts = _thread_with_posts("Hej")
        client = FakeLLMClient(
            [_turn(text="Mars är klar.")],
            text_increments=["Mars ", "är ", "klar."],
        )

        broker, _ = _run_turn_synchronously(thread, posts[0], client)

        deltas = [
            data["text"]
            for event, data in broker.published
            if event == EVENT_MESSAGE_DELTA and "text" in data
        ]
        assert deltas == ["Mars ", "är ", "klar."]

    def test_the_deltas_arrive_during_the_turn_not_in_a_burst_after_it(
        self, agent_enabled
    ):
        """Framgångskriterium 4. The deltas must already have been published
        by the time the turn returns — not replayed from a finished post."""
        _ensure_accounts()
        thread, posts = _thread_with_posts("Hej")
        seen_during_turn: list = []

        class _WatchingClient(FakeLLMClient):
            def run_turn(self, *args, **kwargs):
                turn = super().run_turn(*args, **kwargs)
                seen_during_turn.extend(
                    event for event, _ in broker_holder[0].published
                )
                return turn

        broker_holder: list = []
        broker = _RecordingBroker()
        broker_holder.append(broker)
        client = _WatchingClient([_turn(text="Klart.")], text_increments=["Kl", "art."])
        ThreadTurnRunner(broker=broker).run(
            thread, posts[0], "fråga", client_factory=lambda model: client
        )

        assert seen_during_turn.count(EVENT_MESSAGE_DELTA) == 2
        assert EVENT_MESSAGE_COMPLETED not in seen_during_turn

    def test_a_tool_call_is_announced_as_an_activity_not_as_text(self, agent_enabled):
        """`SkriverIndikator` says what is being done. "Aldrig en anonym
        spinner."""
        _ensure_accounts()
        thread, posts = _thread_with_posts("Hej")
        client = FakeLLMClient(
            [
                _turn(
                    tool_calls=[ToolCall(id="t1", name="las_kontoplan", arguments={})],
                    stop="tool_calls",
                ),
                _turn(text="Klart."),
            ]
        )

        broker, _ = _run_turn_synchronously(thread, posts[0], client)

        activities = [
            data["activity"]
            for event, data in broker.published
            if event == EVENT_MESSAGE_DELTA and "activity" in data
        ]
        assert activities == ["las_kontoplan"]

    def test_the_completed_event_carries_the_stored_post(self, agent_enabled):
        _ensure_accounts()
        thread, posts = _thread_with_posts("Hej")
        client = FakeLLMClient([_turn(text="Klart.")])

        broker, _ = _run_turn_synchronously(thread, posts[0], client)

        completed = [d for e, d in broker.published if e == EVENT_MESSAGE_COMPLETED][0]
        stored = ThreadRepository.list_posts(thread.id)[-1]
        assert completed["id"] == stored.id
        assert completed["seq"] == stored.seq
        assert completed["body"]["text"] == "Klart."

    def test_what_streamed_is_what_gets_stored(self, agent_enabled):
        """§4: the client replaces its optimistic rows with the stored post
        at `message.completed` — so they had better agree."""
        _ensure_accounts()
        thread, posts = _thread_with_posts("Hej")
        client = FakeLLMClient(
            [_turn(text="Hela svaret.")], text_increments=["Hela ", "svaret."]
        )

        broker, _ = _run_turn_synchronously(thread, posts[0], client)

        deltas = "".join(
            data["text"]
            for event, data in broker.published
            if event == EVENT_MESSAGE_DELTA and "text" in data
        )
        assert ThreadRepository.list_posts(thread.id)[-1].body["text"] == deltas

    def test_no_delta_is_ever_stored_as_a_post(self, agent_enabled):
        """§8.5: "Deltan lagras inte. Ett strömmat tecken är en leverans,
        inte en händelse värd en rad."""
        _ensure_accounts()
        thread, posts = _thread_with_posts("Hej")
        client = FakeLLMClient([_turn(text="abc")], text_increments=["a", "b", "c"])

        _run_turn_synchronously(thread, posts[0], client)

        # The user's post plus exactly one agent post -- not one per
        # character.
        assert len(ThreadRepository.list_posts(thread.id)) == 2


class _FakeRequest:
    """The only thing `stream_thread` asks a `Request` for is whether the
    client is still there."""

    def __init__(self, disconnected_after: int = 10_000):
        self._checks = 0
        self._disconnect_at = disconnected_after

    async def is_disconnected(self) -> bool:
        self._checks += 1
        return self._checks > self._disconnect_at


async def _collect_frames(response, expected: int, timeout: float = 5.0) -> list[dict]:
    """Read `expected` frames off a `StreamingResponse`'s own generator.

    The endpoint is driven directly rather than over a transport, because
    neither of httpx's in-process transports can read an endless response:
    `ASGITransport` buffers the whole body before returning, and
    `TestClient` never delivers the disconnect that would end the generator.
    Iterating `body_iterator` is the production generator, minus the
    transport that cannot represent it.
    """
    frames: list[dict] = []
    event: Optional[str] = None

    async def _read():
        nonlocal event
        async for chunk in response.body_iterator:
            text = chunk.decode() if isinstance(chunk, bytes) else chunk
            for line in text.splitlines():
                if line.startswith("event:"):
                    event = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    frames.append(
                        {
                            "event": event,
                            "data": json.loads(line.split(":", 1)[1].strip()),
                        }
                    )
            if len(frames) >= expected:
                return

    try:
        await asyncio.wait_for(_read(), timeout=timeout)
    finally:
        await response.body_iterator.aclose()
    return frames


class TestStreamReconnect:
    """Test case 20 — a reconnecting client gets what it missed, nothing
    twice."""

    @pytest.mark.asyncio
    async def test_case_20_since_replays_only_the_missed_posts(
        self, current_fiscal_year
    ):
        thread = ThreadRepository.get_or_create(
            view_key="bocker.balans",
            fiscal_year_id=current_fiscal_year.id,
            model="opencode/claude-opus-5",
        )
        for text in ("första", "andra", "tredje"):
            ThreadRepository.add_post(
                thread_id=thread.id,
                post_type="agent_text",
                actor="agent",
                body={"text": text},
            )

        response = await stream_thread(
            view_key="bocker.balans",
            request=_FakeRequest(),
            since=1,
            actor="api",
        )
        frames = await _collect_frames(response, expected=2)

        assert response.media_type == "text/event-stream"
        assert [frame["event"] for frame in frames] == [
            EVENT_MESSAGE_COMPLETED,
            EVENT_MESSAGE_COMPLETED,
        ]
        # What it missed -- and not "första", which it already had.
        assert [frame["data"]["body"]["text"] for frame in frames] == [
            "andra",
            "tredje",
        ]

    @pytest.mark.asyncio
    async def test_a_turn_under_way_is_sent_first_then_the_missed_posts(
        self, current_fiscal_year
    ):
        """chattyta open question 5: the first answer in an empty thread lost
        its opening frames, because the turn started before anyone listened."""
        thread = ThreadRepository.get_or_create(
            view_key="bocker.balans",
            fiscal_year_id=current_fiscal_year.id,
            model="opencode/claude-opus-5",
        )
        ThreadRepository.add_post(
            thread_id=thread.id,
            post_type="user_text",
            actor="stefan",
            body={"text": "Vad är kundfordringarna?"},
        )
        broker = get_broker()
        broker.publish(
            thread.id,
            EVENT_MESSAGE_CREATED,
            {
                "id": "streaming-r7",
                "type": "agent_text",
                "actor": "agent",
                "run_id": "r7",
            },
        )
        broker.publish(
            thread.id, EVENT_MESSAGE_DELTA, {"id": "streaming-r7", "text": "148 500"}
        )
        try:
            response = await stream_thread(
                view_key="bocker.balans", request=_FakeRequest(), since=0, actor="api"
            )
            frames = await _collect_frames(response, expected=2)
        finally:
            broker.publish(
                thread.id, EVENT_MESSAGE_COMPLETED, {"id": "x", "run_id": "r7"}
            )

        assert frames[0]["event"] == EVENT_MESSAGE_CREATED
        assert frames[0]["data"]["id"] == "streaming-r7"
        assert frames[0]["data"]["text"] == "148 500"
        assert frames[1]["event"] == EVENT_MESSAGE_COMPLETED
        assert frames[1]["data"]["body"]["text"] == "Vad är kundfordringarna?"

    @pytest.mark.asyncio
    async def test_the_replay_carries_the_same_shape_as_a_live_event(
        self, current_fiscal_year
    ):
        """One shape for the client to handle, not two."""
        thread = ThreadRepository.get_or_create(
            view_key="bocker.balans",
            fiscal_year_id=current_fiscal_year.id,
            model="opencode/claude-opus-5",
        )
        ThreadRepository.add_post(
            thread_id=thread.id,
            post_type="user_text",
            actor="stefan",
            body={"text": "a"},
        )
        stored = ThreadRepository.add_post(
            thread_id=thread.id,
            post_type="agent_text",
            actor="agent",
            body={"text": "svar"},
            traces=[{"tool": "las_kontoplan", "label": "kontoplanen läst"}],
        )

        response = await stream_thread(
            view_key="bocker.balans", request=_FakeRequest(), since=1, actor="api"
        )
        frame = (await _collect_frames(response, expected=1))[0]

        assert frame["data"] == post_event_payload(stored)
        assert set(frame["data"]) >= {
            "id",
            "seq",
            "type",
            "actor",
            "created_at",
            "body",
            "traces",
        }

    @pytest.mark.asyncio
    async def test_live_events_reach_a_subscriber(self, current_fiscal_year):
        """The half `?since=` cannot show: an event published while the
        client is connected arrives on the open stream."""
        thread = ThreadRepository.get_or_create(
            view_key="bocker.balans",
            fiscal_year_id=current_fiscal_year.id,
            model="opencode/claude-opus-5",
        )

        response = await stream_thread(
            view_key="bocker.balans", request=_FakeRequest(), since=None, actor="api"
        )
        collector = asyncio.ensure_future(_collect_frames(response, expected=2))
        # Let the generator subscribe before anything is published.
        await asyncio.sleep(0.05)
        get_broker().publish(
            thread.id,
            EVENT_MESSAGE_CREATED,
            {"id": "streaming-1", "type": "agent_text"},
        )
        get_broker().publish(
            thread.id, EVENT_MESSAGE_DELTA, {"id": "streaming-1", "text": "hej"}
        )

        frames = await asyncio.wait_for(collector, timeout=5.0)

        assert [frame["event"] for frame in frames] == [
            EVENT_MESSAGE_CREATED,
            EVENT_MESSAGE_DELTA,
        ]
        assert frames[1]["data"]["text"] == "hej"

    @pytest.mark.asyncio
    async def test_case_20_a_reconnect_sees_no_post_twice(self, current_fiscal_year):
        """The subscription is taken out *before* the replay is read, so an
        event landing mid-replay is queued rather than lost — and the cursor
        keeps the replay and the live feed from overlapping."""
        thread = ThreadRepository.get_or_create(
            view_key="bocker.balans",
            fiscal_year_id=current_fiscal_year.id,
            model="opencode/claude-opus-5",
        )
        missed = ThreadRepository.add_post(
            thread_id=thread.id,
            post_type="agent_text",
            actor="agent",
            body={"text": "missat"},
        )

        response = await stream_thread(
            view_key="bocker.balans", request=_FakeRequest(), since=0, actor="api"
        )
        collector = asyncio.ensure_future(_collect_frames(response, expected=2))
        await asyncio.sleep(0.05)
        live = ThreadRepository.add_post(
            thread_id=thread.id,
            post_type="agent_text",
            actor="agent",
            body={"text": "live"},
        )
        get_broker().publish(
            thread.id, EVENT_MESSAGE_COMPLETED, post_event_payload(live)
        )

        frames = await asyncio.wait_for(collector, timeout=5.0)

        seqs = [frame["data"]["seq"] for frame in frames]
        assert seqs == [missed.seq, live.seq]
        assert len(seqs) == len(set(seqs))

    @pytest.mark.asyncio
    async def test_the_generator_unsubscribes_when_the_client_goes_away(
        self, current_fiscal_year
    ):
        """A subscriber that is never removed is a queue that grows forever
        behind a browser tab somebody closed."""
        thread = ThreadRepository.get_or_create(
            view_key="bocker.balans",
            fiscal_year_id=current_fiscal_year.id,
            model="opencode/claude-opus-5",
        )
        ThreadRepository.add_post(
            thread_id=thread.id,
            post_type="agent_text",
            actor="agent",
            body={"text": "a"},
        )

        response = await stream_thread(
            view_key="bocker.balans", request=_FakeRequest(), since=0, actor="api"
        )
        await _collect_frames(response, expected=1)

        assert get_broker().subscriber_count(thread.id) == 0

    def test_a_stream_for_a_view_without_a_thread_is_404(
        self, client, auth_headers, current_fiscal_year
    ):
        response = client.get(
            f"{THREADS_URL}/bokslut.rapporter/stream", headers=auth_headers
        )

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "thread_not_found"

    def test_an_unknown_view_key_stream_is_404(self, client, auth_headers):
        assert (
            client.get(
                f"{THREADS_URL}/hittepa.vy/stream", headers=auth_headers
            ).status_code
            == 404
        )


class TestOneWriterPerRun:
    """Test case 21 — `add_event` allocates `seq` read-then-write on a
    single-writer premise. `UNIQUE (run_id, seq)` would catch a breach as an
    error in the middle of somebody's answer, which §6.5 says is not an
    acceptable detection mechanism."""

    def test_case_21_two_concurrent_turns_never_share_a_run_id(self, agent_enabled):
        _ensure_accounts()
        fy = _fiscal_year()
        first = ThreadRepository.get_or_create(
            view_key="bocker.balans",
            fiscal_year_id=fy.id,
            model="opencode/claude-opus-5",
        )
        second = ThreadRepository.get_or_create(
            view_key="bocker.resultat",
            fiscal_year_id=fy.id,
            model="opencode/claude-opus-5",
        )
        trigger_one = ThreadRepository.add_post(
            thread_id=first.id, post_type="user_text", actor="a", body={"text": "1"}
        )
        trigger_two = ThreadRepository.add_post(
            thread_id=second.id, post_type="user_text", actor="b", body={"text": "2"}
        )

        _run_turn_synchronously(first, trigger_one, FakeLLMClient([_turn(text="A")]))
        _run_turn_synchronously(second, trigger_two, FakeLLMClient([_turn(text="B")]))

        run_ids = [
            row["run_id"]
            for row in db.execute(
                "SELECT run_id FROM thread_posts WHERE run_id IS NOT NULL"
            ).fetchall()
        ]
        assert len(run_ids) == 2
        assert len(set(run_ids)) == 2

    def test_case_21_a_second_writer_for_one_run_is_refused_before_it_writes(self):
        run_id = "run-under-way"
        claim_run(run_id)
        try:
            with pytest.raises(ConcurrentRunWriterError):
                claim_run(run_id)
        finally:
            release_run(run_id)

    def test_a_run_is_released_when_its_turn_ends(self, agent_enabled):
        _ensure_accounts()
        thread, posts = _thread_with_posts("Hej")

        _run_turn_synchronously(thread, posts[0], FakeLLMClient([_turn(text="A")]))

        assert live_run_ids() == set()

    def test_a_run_is_released_even_when_the_turn_blows_up(self, agent_enabled):
        _ensure_accounts()
        thread, posts = _thread_with_posts("Hej")

        class _ExplodingClient(FakeLLMClient):
            def run_turn(self, *args, **kwargs):
                raise RuntimeError("oväntat")

        _run_turn_synchronously(thread, posts[0], _ExplodingClient([_turn()]))

        assert live_run_ids() == set()

    def test_every_thread_run_has_trigger_thread(self, agent_enabled):
        """`agent_runs.trigger` already listed `'thread'` and carries no
        CHECK constraint — no migration was needed for it."""
        _ensure_accounts()
        thread, posts = _thread_with_posts("Hej")

        _run_turn_synchronously(thread, posts[0], FakeLLMClient([_turn(text="A")]))

        triggers = [
            row["trigger"]
            for row in db.execute("SELECT trigger FROM agent_runs").fetchall()
        ]
        assert triggers == ["thread"]


class TestFlockGuardsTheIntakePassOnly:
    """Test case 22 — "Flocken vaktar intag-passet, inte varje LLM-anrop."
    Two people must be able to write in two views while the intake pass
    holds its lock."""

    def test_case_22_a_thread_turn_runs_while_the_runner_holds_the_flock(
        self, agent_enabled, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(settings, "intake_dir", str(tmp_path / "intake"))
        _ensure_accounts()
        thread, posts = _thread_with_posts("Hej")

        runner = AgentRunner()
        assert runner.start() is True
        try:
            assert runner.running is True
            broker, outcome = _run_turn_synchronously(
                thread, posts[0], FakeLLMClient([_turn(text="Går ändå.")])
            )
        finally:
            runner.stop()

        assert outcome.kind == "answered"
        assert ThreadRepository.list_posts(thread.id)[-1].body["text"] == "Går ändå."

    def test_the_thread_path_never_touches_the_runtime_lock(self):
        """Structural: the lock lives in `services/agent_runtime.py` and the
        thread path must not reach for it.

        Checked against the parsed code rather than the file's text, for the
        same reason as `TestRuntimeKnowsNothingOfThreads`: these modules
        *explain* the flock at length, and must go on doing so. What they
        must not do is call it."""
        import ast
        from pathlib import Path

        forbidden = {"_acquire_lock", "_release_lock", "flock", "LOCK_FILENAME"}
        repo_root = Path(__file__).parent.parent
        for module in (
            "services/thread_stream.py",
            "services/thread_session.py",
            "services/thread_service.py",
            "api/routes/threads.py",
        ):
            tree = ast.parse((repo_root / module).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    assert node.id not in forbidden, f"{module} uses {node.id}"
                elif isinstance(node, ast.Attribute):
                    assert node.attr not in forbidden, f"{module} uses .{node.attr}"
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        assert (
                            alias.name not in forbidden
                        ), f"{module} imports {alias.name}"


class TestStreamNeverLeaksTheKey:
    """Test case 28's stream half — `LLM_API_KEY` in no SSE frame and no
    post (SPEC-agentruntime §12.6)."""

    def test_case_28_the_key_is_in_no_frame_and_no_post(
        self, agent_enabled, monkeypatch
    ):
        monkeypatch.setattr(settings, "llm_api_key", "sk-hemlig-nyckel-42")
        _ensure_accounts()
        thread, posts = _thread_with_posts("Hej")

        broker, _ = _run_turn_synchronously(
            thread, posts[0], FakeLLMClient([_turn(text="Svar.")])
        )

        published = json.dumps(broker.published, ensure_ascii=False, default=str)
        assert "sk-hemlig-nyckel-42" not in published
        stored = json.dumps(
            [dict(row) for row in db.execute("SELECT * FROM thread_posts").fetchall()],
            ensure_ascii=False,
            default=str,
        )
        assert "sk-hemlig-nyckel-42" not in stored

    def test_case_28_an_error_post_never_carries_the_key_either(
        self, agent_enabled, monkeypatch
    ):
        monkeypatch.setattr(settings, "llm_api_key", "sk-hemlig-nyckel-42")
        _ensure_accounts()
        thread, posts = _thread_with_posts("Hej")

        class _FailingClient(FakeLLMClient):
            def run_turn(self, *args, **kwargs):
                raise LLMConnectionError("Connection error talking to the Messages API")

        broker, _ = _run_turn_synchronously(thread, posts[0], _FailingClient([_turn()]))

        post = ThreadRepository.list_posts(thread.id)[-1]
        assert post.type == "error"
        assert "sk-hemlig-nyckel-42" not in json.dumps(post.body, default=str)


class TestTurnFailuresBecomeErrorPosts:
    """§6.7: "Tråden tappar aldrig en tur i tysthet"."""

    def test_a_connection_failure_becomes_an_error_post_and_a_failed_run(
        self, agent_enabled
    ):
        _ensure_accounts()
        thread, posts = _thread_with_posts("Hej")

        class _FailingClient(FakeLLMClient):
            def run_turn(self, *args, **kwargs):
                raise LLMConnectionError("gateway nere")

        broker, outcome = _run_turn_synchronously(
            thread, posts[0], _FailingClient([_turn()])
        )

        assert outcome is None
        post = ThreadRepository.list_posts(thread.id)[-1]
        assert post.type == "error"
        assert "gateway nere" in post.body["cause"]
        # Still a completed event -- the client's optimistic row must be
        # replaced by something.
        assert broker.published[-1][0] == EVENT_MESSAGE_COMPLETED
        assert (
            db.execute("SELECT status FROM agent_runs").fetchone()["status"] == "failed"
        )

    def test_a_rate_limit_becomes_an_error_post(self, agent_enabled):
        _ensure_accounts()
        thread, posts = _thread_with_posts("Hej")

        class _LimitedClient(FakeLLMClient):
            def run_turn(self, *args, **kwargs):
                raise LLMRateLimitError(retry_after_seconds=30)

        _run_turn_synchronously(thread, posts[0], _LimitedClient([_turn()]))

        post = ThreadRepository.list_posts(thread.id)[-1]
        assert post.type == "error"
        assert "llm_rate_limit_error" in post.body["cause"]

    def test_the_daily_budget_refuses_before_a_run_row_exists(
        self, agent_enabled, monkeypatch
    ):
        """Same shape as the intake pass's refusal (SPEC-agentruntime §9 #8):
        no `agent_runs` row, and the refusal is visible."""
        _ensure_accounts()
        thread, posts = _thread_with_posts("Hej")
        run = AgentRunRepository.create(
            trigger="thread", model="opencode/claude-opus-5", protocol="messages"
        )
        AgentRunRepository.add_usage(run.id, cost_ore=settings.agent_daily_budget_ore)
        AgentRunRepository.update_status(run.id, "completed")

        _run_turn_synchronously(thread, posts[0], FakeLLMClient([_turn(text="A")]))

        post = ThreadRepository.list_posts(thread.id)[-1]
        assert post.type == "error"
        assert "budget_exhausted" in post.body["cause"]
        assert db.execute("SELECT COUNT(*) AS n FROM agent_runs").fetchone()["n"] == 1


class TestSseFraming:
    def test_a_frame_is_event_then_data_then_a_blank_line(self):
        frame = format_sse("message.delta", {"id": "x", "text": "hej"})

        assert frame.startswith("event: message.delta\ndata: ")
        assert frame.endswith("\n\n")

    def test_swedish_characters_stay_literal_on_the_wire(self):
        frame = format_sse("message.delta", {"text": "räkenskapsår"})

        assert "räkenskapsår" in frame

    def test_a_broker_with_no_subscribers_is_not_an_error(self):
        """A session nobody is watching still runs and still stores its
        posts. The stream is a view onto the work, not the work itself."""
        ThreadBroker().publish("no-such-thread", "message.delta", {"text": "hej"})

    def test_each_subscriber_gets_its_own_queue(self):
        """Two browsers on the same view must both see the whole answer."""
        import asyncio as asyncio_module

        broker = ThreadBroker()
        loop = asyncio_module.new_event_loop()
        try:
            first: asyncio_module.Queue = asyncio_module.Queue()
            second: asyncio_module.Queue = asyncio_module.Queue()
            broker.subscribe("t1", first, loop)
            broker.subscribe("t1", second, loop)

            assert broker.subscriber_count("t1") == 2

            broker.publish("t1", "message.delta", {"text": "hej"})
            loop.call_soon(loop.stop)
            loop.run_forever()

            assert first.qsize() == 1
            assert second.qsize() == 1
        finally:
            loop.close()

    def test_a_late_subscriber_gets_the_turn_in_progress(self):
        """chattyta open question 5: the turn starts inside `POST .../messages`
        and the client subscribes after the response, so `message.created`
        and the first deltas went to nobody. The broker keeps what an
        in-flight turn has said so far and hands it to a new subscriber."""
        import asyncio as asyncio_module

        broker = ThreadBroker()
        broker.publish(
            "t1",
            "message.created",
            {
                "id": "streaming-r1",
                "type": "agent_text",
                "actor": "agent",
                "run_id": "r1",
            },
        )
        broker.publish("t1", "message.delta", {"id": "streaming-r1", "text": "Jag "})
        broker.publish(
            "t1",
            "message.delta",
            {"id": "streaming-r1", "activity": "las_bankhandelser"},
        )
        broker.publish("t1", "message.delta", {"id": "streaming-r1", "text": "läser."})

        loop = asyncio_module.new_event_loop()
        try:
            snapshot = broker.subscribe("t1", asyncio_module.Queue(), loop)
        finally:
            loop.close()

        assert snapshot == {
            "id": "streaming-r1",
            "type": "agent_text",
            "actor": "agent",
            "run_id": "r1",
            "text": "Jag läser.",
            "activity": "las_bankhandelser",
        }

    def test_no_turn_in_progress_means_no_snapshot(self):
        import asyncio as asyncio_module

        broker = ThreadBroker()
        loop = asyncio_module.new_event_loop()
        try:
            assert broker.subscribe("t1", asyncio_module.Queue(), loop) is None
        finally:
            loop.close()

    def test_a_completed_turn_leaves_no_snapshot(self):
        import asyncio as asyncio_module

        broker = ThreadBroker()
        broker.publish("t1", "message.created", {"id": "streaming-r1", "run_id": "r1"})
        broker.publish("t1", "message.delta", {"id": "streaming-r1", "text": "Klart."})
        broker.publish(
            "t1",
            "message.completed",
            {"id": "p-9", "run_id": "r1", "type": "agent_text"},
        )

        loop = asyncio_module.new_event_loop()
        try:
            assert broker.subscribe("t1", asyncio_module.Queue(), loop) is None
        finally:
            loop.close()

    def test_a_completed_post_from_another_run_keeps_the_snapshot(self):
        """Only `ThreadTurnRunner` publishes `message.completed`, once, for
        the turn's final post (`_publish_completed`). A completed frame that
        does not carry the snapshot's run id -- here a post with none -- is
        not the end of that turn."""
        import asyncio as asyncio_module

        broker = ThreadBroker()
        broker.publish("t1", "message.created", {"id": "streaming-r1", "run_id": "r1"})
        broker.publish(
            "t1",
            "message.completed",
            {"id": "p-2", "run_id": None, "type": "user_text"},
        )

        loop = asyncio_module.new_event_loop()
        try:
            snapshot = broker.subscribe("t1", asyncio_module.Queue(), loop)
        finally:
            loop.close()

        assert snapshot is not None and snapshot["run_id"] == "r1"

    def test_unsubscribing_removes_only_that_subscriber(self):
        import asyncio as asyncio_module

        broker = ThreadBroker()
        loop = asyncio_module.new_event_loop()
        try:
            first: asyncio_module.Queue = asyncio_module.Queue()
            second: asyncio_module.Queue = asyncio_module.Queue()
            broker.subscribe("t1", first, loop)
            broker.subscribe("t1", second, loop)

            broker.unsubscribe("t1", first)

            assert broker.subscriber_count("t1") == 1
        finally:
            loop.close()


# --- T10: view.changed (SPEC §6.6, test case 23) ---------------------------


def _posting_thread(tmp_path):
    """A thread, its trigger post, a period and an intake source — enough for
    a real posting to go through `posta_verifikation`."""
    _ensure_accounts()
    period = PeriodRepository.create_period(
        fiscal_year_id=_fiscal_year().id,
        year=2026,
        month=3,
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
    )
    thread = ThreadRepository.get_or_create(
        view_key="bocker.verifikationer",
        fiscal_year_id=period.fiscal_year_id,
        model="opencode/claude-opus-5",
    )
    trigger = ThreadRepository.add_post(
        thread_id=thread.id,
        post_type="user_text",
        actor="stefan",
        body={"text": "Bokför kvittot."},
    )
    source = _intake_source(tmp_path)
    return thread, trigger, period, source


class TestViewChanged:
    """Test case 23 — sent after a posting, and **not** after an answer
    without one. §6.6: derived from the posting's own outcome, never from a
    guessed interval and never as a periodic "something may have happened"."""

    def test_case_23_view_changed_is_sent_after_a_posting(
        self, agent_enabled, tmp_path
    ):
        thread, trigger, period, source = _posting_thread(tmp_path)
        client = FakeLLMClient(
            [
                _turn(
                    tool_calls=[
                        ToolCall(
                            id="t1",
                            name="posta_verifikation",
                            arguments=_posting_args(period.id, source.id),
                        )
                    ],
                    stop="tool_calls",
                )
            ]
        )

        broker, outcome = _run_turn_synchronously(thread, trigger, client)

        assert outcome.kind == "posted"
        changed = [d for e, d in broker.published if e == EVENT_VIEW_CHANGED]
        assert len(changed) == 1
        assert changed[0]["view_key"] == "bocker.verifikationer"
        assert changed[0]["changed"]["voucher_id"] == outcome.voucher_id

    def test_case_23_view_changed_is_not_sent_after_an_answer_without_a_posting(
        self, agent_enabled
    ):
        """The half that matters: an ordinary reply must not make the client
        refetch the whole view."""
        _ensure_accounts()
        thread, posts = _thread_with_posts("Hur ser mars ut?")

        broker, outcome = _run_turn_synchronously(
            thread, posts[0], FakeLLMClient([_turn(text="Mars är klar.")])
        )

        assert outcome.kind == "answered"
        assert EVENT_VIEW_CHANGED not in [event for event, _ in broker.published]

    def test_view_changed_is_not_sent_after_a_read_only_tool_turn(self, agent_enabled):
        """Reading the kontoplan changes nothing in the view."""
        _ensure_accounts()
        thread, posts = _thread_with_posts("Vad finns på 1920?")
        client = FakeLLMClient(
            [
                _turn(
                    tool_calls=[ToolCall(id="t1", name="las_kontoplan", arguments={})],
                    stop="tool_calls",
                ),
                _turn(text="1920 är bankkontot."),
            ]
        )

        broker, _ = _run_turn_synchronously(thread, posts[0], client)

        assert EVENT_VIEW_CHANGED not in [event for event, _ in broker.published]

    def test_view_changed_is_not_sent_after_an_error(self, agent_enabled):
        _ensure_accounts()
        thread, posts = _thread_with_posts("Hej")

        broker, _ = _run_turn_synchronously(
            thread, posts[0], FakeLLMClient([_turn(text="Nej.", stop="refusal")])
        )

        assert EVENT_VIEW_CHANGED not in [event for event, _ in broker.published]

    def test_view_changed_comes_after_the_answer_is_complete(
        self, agent_enabled, tmp_path
    ):
        """The thread settles first, then the numbers move — otherwise the
        view refreshes under a reply that has not landed yet."""
        thread, trigger, period, source = _posting_thread(tmp_path)
        client = FakeLLMClient(
            [
                _turn(
                    text="Bokför den på 6212.",
                    tool_calls=[
                        ToolCall(
                            id="t1",
                            name="posta_verifikation",
                            arguments=_posting_args(period.id, source.id),
                        )
                    ],
                    stop="tool_calls",
                )
            ]
        )

        broker, _ = _run_turn_synchronously(thread, trigger, client)

        kinds = [event for event, _ in broker.published]
        assert kinds.index(EVENT_MESSAGE_COMPLETED) < kinds.index(EVENT_VIEW_CHANGED)

    def test_nothing_publishes_view_changed_on_a_timer(self):
        """§6.6: "aldrig ur ett intervall, aldrig som en periodisk 'kanske
        har något hänt'". Structural — no scheduling primitive anywhere near
        the event."""
        import ast
        from pathlib import Path

        tree = ast.parse(
            (Path(__file__).parent.parent / "services" / "thread_stream.py").read_text(
                encoding="utf-8"
            )
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in {
                    "sleep",
                    "call_later",
                    "Timer",
                }, f"thread_stream schedules with .{node.attr}"


# --- T11: model per thread (SPEC §12.4, test cases 24, 25) -----------------


class TestModelPerThread:
    """Test case 24 — a model switch mid-thread is visible afterwards, via
    `agent_runs.model` per run and no new table."""

    def test_case_24_a_switch_mid_thread_is_visible_in_the_runs(self, agent_enabled):
        _ensure_accounts()
        thread, posts = _thread_with_posts("Hej", model="opencode/claude-opus-5")

        _run_turn_synchronously(thread, posts[0], FakeLLMClient([_turn(text="A")]))
        ThreadRepository.set_model(thread.id, "opencode/gpt-5.5")
        switched = ThreadRepository.get(thread.id)
        trigger = ThreadRepository.add_post(
            thread_id=thread.id,
            post_type="user_text",
            actor="stefan",
            body={"text": "Och nu?"},
        )
        _run_turn_synchronously(switched, trigger, FakeLLMClient([_turn(text="B")]))

        runs = db.execute(
            "SELECT model, protocol FROM agent_runs ORDER BY started_at ASC"
        ).fetchall()
        assert [row["model"] for row in runs] == [
            "opencode/claude-opus-5",
            "opencode/gpt-5.5",
        ]
        # The protocol travels with the run too, so the difference is
        # legible without re-deriving it from the model name later.
        assert [row["protocol"] for row in runs] == ["messages", "chat"]

    def test_case_24_each_post_is_bound_to_the_run_that_made_it(self, agent_enabled):
        """That binding is what lets a reader see which answer came from
        which model (§4)."""
        _ensure_accounts()
        thread, posts = _thread_with_posts("Hej")

        _run_turn_synchronously(thread, posts[0], FakeLLMClient([_turn(text="A")]))

        agent_post = ThreadRepository.list_posts(thread.id)[-1]
        run = db.execute(
            "SELECT model FROM agent_runs WHERE id = ?", (agent_post.run_id,)
        ).fetchone()
        assert run["model"] == "opencode/claude-opus-5"

    def test_the_run_uses_the_threads_model_not_the_global_default(
        self, agent_enabled, monkeypatch
    ):
        monkeypatch.setattr(settings, "llm_default_model", "opencode/claude-opus-5")
        _ensure_accounts()
        thread, posts = _thread_with_posts("Hej", model="opencode/grok-4")

        _run_turn_synchronously(thread, posts[0], FakeLLMClient([_turn(text="A")]))

        assert (
            db.execute("SELECT model FROM agent_runs").fetchone()["model"]
            == "opencode/grok-4"
        )

    def test_a_model_without_a_price_row_never_starts_a_run(self, agent_enabled):
        """SPEC-agentruntime §2: an unpriced model is an error, not a
        default — and a cap that cannot compute a cost must not spend."""
        _ensure_accounts()
        thread, posts = _thread_with_posts("Hej", model="opencode/ingen-prisrad")

        broker, outcome = _run_turn_synchronously(
            thread, posts[0], FakeLLMClient([_turn(text="A")])
        )

        assert outcome is None
        assert db.execute("SELECT COUNT(*) AS n FROM agent_runs").fetchone()["n"] == 0
        assert ThreadRepository.list_posts(thread.id)[-1].type == "error"


class TestModelEndpoint:
    """Test case 25 — the protocol differences travel up and are shown."""

    def _thread(self, client, auth_headers):
        client.post(
            f"{THREADS_URL}/bocker.balans/messages",
            json={"text": "hej"},
            headers=auth_headers,
        )

    def test_case_25_a_chat_protocol_thread_says_it_cannot_read_pdfs(
        self, client, auth_headers, current_fiscal_year
    ):
        self._thread(client, auth_headers)

        body = client.put(
            f"{THREADS_URL}/bocker.balans/model",
            json={"model": "opencode/gpt-5.5"},
            headers=auth_headers,
        ).json()

        assert body["protocol"] == "chat"
        assert body["reads_pdf_documents"] is False
        assert body["has_cache_economy"] is False
        assert any("PDF" in line for line in body["limitations"])
        assert any("cache" in line.lower() for line in body["limitations"])

    def test_case_25_the_limitation_is_that_it_abstains_rather_than_guesses(
        self, client, auth_headers, current_fiscal_year
    ):
        """§12.4: a product truth, not a detail to hide — and the honest
        wording is what the code actually does (`DocumentUnreadableError`
        before any call)."""
        self._thread(client, auth_headers)

        body = client.put(
            f"{THREADS_URL}/bocker.balans/model",
            json={"model": "opencode/gpt-5.5"},
            headers=auth_headers,
        ).json()

        pdf_line = next(line for line in body["limitations"] if "PDF" in line)
        assert "avstår" in pdf_line

    def test_a_messages_protocol_thread_has_no_such_limitations(
        self, client, auth_headers, current_fiscal_year
    ):
        self._thread(client, auth_headers)

        body = client.put(
            f"{THREADS_URL}/bocker.balans/model",
            json={"model": "opencode/claude-opus-5"},
            headers=auth_headers,
        ).json()

        assert body["protocol"] == "messages"
        assert body["reads_pdf_documents"] is True
        assert body["has_cache_economy"] is True
        assert body["limitations"] == []

    def test_the_choice_is_stored_on_the_thread(
        self, client, auth_headers, current_fiscal_year
    ):
        self._thread(client, auth_headers)

        client.put(
            f"{THREADS_URL}/bocker.balans/model",
            json={"model": "opencode/grok-4"},
            headers=auth_headers,
        )

        assert (
            client.get(f"{THREADS_URL}/bocker.balans", headers=auth_headers).json()[
                "model"
            ]
            == "opencode/grok-4"
        )

    def test_an_unpriced_model_is_refused_when_it_is_chosen(
        self, client, auth_headers, current_fiscal_year
    ):
        """The honest moment to say so is at the choice, not at the first
        turn."""
        self._thread(client, auth_headers)

        response = client.put(
            f"{THREADS_URL}/bocker.balans/model",
            json={"model": "opencode/finns-inte"},
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "unknown_model"
        assert (
            client.get(f"{THREADS_URL}/bocker.balans", headers=auth_headers).json()[
                "model"
            ]
            != "opencode/finns-inte"
        )

    def test_the_model_endpoint_needs_a_thread(
        self, client, auth_headers, current_fiscal_year
    ):
        response = client.get(
            f"{THREADS_URL}/bokslut.atgarder/model", headers=auth_headers
        )

        assert response.status_code == 404


# --- T12: GET /agent/status (SPEC §7, test cases 26, 27, 28) ---------------


STATUS_URL = "/api/v1/agent/status"


class TestAgentStatusFields:
    """Test case 26 — the four fields `datakontrakt.md` §7 asks for."""

    def test_case_26_the_four_fields_are_present(self, client, auth_headers):
        body = client.get(STATUS_URL, headers=auth_headers).json()

        assert set(body) >= {"state", "since", "current_task", "paused_reason"}

    def test_the_existing_fields_are_not_removed(self, client, auth_headers):
        """This endpoint already has a consumer — the four are additive."""
        body = client.get(STATUS_URL, headers=auth_headers).json()

        assert set(body) >= {
            "enabled",
            "running",
            "current_run",
            "last_run",
            "queue_depth",
            "cost_today_ore",
            "budget_today_ore",
            "last_error",
        }

    def test_since_is_the_running_passs_start(self, client, auth_headers):
        run = AgentRunRepository.create(
            trigger="thread", model="opencode/claude-opus-5", protocol="messages"
        )

        body = client.get(STATUS_URL, headers=auth_headers).json()

        assert body["since"] is not None
        assert body["since"].startswith(run.started_at.isoformat()[:19])

    def test_since_is_none_when_nothing_is_running(self, client, auth_headers):
        assert client.get(STATUS_URL, headers=auth_headers).json()["since"] is None

    def test_current_task_is_the_live_tool_name(
        self, client, auth_headers, monkeypatch
    ):
        """Possible only since T5's hook — A11 had to leave it coarse."""
        worker = get_worker()
        monkeypatch.setattr(worker, "current_activity", "las_kontoplan", raising=False)

        body = client.get(STATUS_URL, headers=auth_headers).json()

        assert body["current_task"] == "las_kontoplan"


class TestAgentStatusState:
    """The three named modes of `komponenter.md`'s `AgentStatus`, plus the
    ordinary case of nothing happening."""

    def test_posting_is_its_own_mode(self):
        assert agent_state("posta_verifikation", None) == "postar"

    def test_any_other_tool_is_working(self):
        assert agent_state("las_kontoplan", None) == "arbetar"

    def test_nothing_happening_is_not_a_mode_the_design_draws(self):
        assert agent_state(None, None) == "vilande"

    def test_paused_wins_over_everything_else(self):
        """A paused agent is paused even if a stale activity is still set."""
        assert agent_state("posta_verifikation", "agent_runtime_disabled") == "pausad"

    def test_the_state_is_reported_over_http(self, client, auth_headers, monkeypatch):
        monkeypatch.setattr(settings, "agent_runtime_enabled", True)
        worker = get_worker()
        monkeypatch.setattr(
            worker, "current_activity", "posta_verifikation", raising=False
        )
        monkeypatch.setattr(type(get_runner()), "running", property(lambda self: True))

        body = client.get(STATUS_URL, headers=auth_headers).json()

        assert body["state"] == "postar"
        assert body["paused_reason"] is None

    def test_the_mode_is_global_not_per_view(self, client, auth_headers):
        """§7, answering the design's own open question 2: one worker, one
        flock, one budget. The payload has no per-view dimension at all."""
        body = client.get(STATUS_URL, headers=auth_headers).json()

        assert "view_key" not in body
        assert "views" not in body
        assert isinstance(body["state"], str)


class TestPausedReasonPersists:
    """Test case 27 — "Pausad ska visas så länge den är pausad, inte bara i
    felinlägget"."""

    def test_case_27_the_reason_stays_across_repeated_reads(
        self, client, auth_headers, monkeypatch
    ):
        monkeypatch.setattr(settings, "agent_runtime_enabled", False)

        first = client.get(STATUS_URL, headers=auth_headers).json()
        second = client.get(STATUS_URL, headers=auth_headers).json()
        third = client.get(STATUS_URL, headers=auth_headers).json()

        assert first["paused_reason"] == "agent_runtime_disabled"
        assert second["paused_reason"] == first["paused_reason"]
        assert third["paused_reason"] == first["paused_reason"]
        assert {first["state"], second["state"], third["state"]} == {"pausad"}

    def test_the_switch_being_off_is_the_reason(self, monkeypatch):
        monkeypatch.setattr(settings, "agent_runtime_enabled", False)

        assert AgentRunner().paused_reason() == "agent_runtime_disabled"

    def test_enabled_but_not_started_is_its_own_reason(self, monkeypatch):
        """The flock is held by another process, or nobody called
        `start()` — a different thing to fix than a switch being off."""
        monkeypatch.setattr(settings, "agent_runtime_enabled", True)

        assert AgentRunner().paused_reason() == "agent_runtime_not_started"

    def test_a_spent_budget_is_not_a_pause(self, client, auth_headers, monkeypatch):
        """A cap on spending that resets at midnight is not a fault somebody
        has to clear — it is reported as cost, not as a pause."""
        monkeypatch.setattr(settings, "agent_runtime_enabled", True)
        monkeypatch.setattr(type(get_runner()), "running", property(lambda self: True))
        run = AgentRunRepository.create(
            trigger="thread", model="opencode/claude-opus-5", protocol="messages"
        )
        AgentRunRepository.add_usage(run.id, cost_ore=settings.agent_daily_budget_ore)

        body = client.get(STATUS_URL, headers=auth_headers).json()

        assert body["paused_reason"] is None
        assert body["cost_today_ore"] >= body["budget_today_ore"]

    def test_a_running_agent_has_no_paused_reason(
        self, client, auth_headers, monkeypatch
    ):
        monkeypatch.setattr(settings, "agent_runtime_enabled", True)
        monkeypatch.setattr(type(get_runner()), "running", property(lambda self: True))

        assert (
            client.get(STATUS_URL, headers=auth_headers).json()["paused_reason"] is None
        )


class TestStatusNeverLeaksTheKey:
    """Test case 28 — the key is in no status row, whole or masked."""

    def test_case_28_the_key_is_absent_from_the_whole_payload(
        self, client, auth_headers, monkeypatch
    ):
        monkeypatch.setattr(settings, "llm_api_key", "sk-hemlig-nyckel-42")

        raw = client.get(STATUS_URL, headers=auth_headers).text

        assert "sk-hemlig-nyckel-42" not in raw

    def test_case_28_not_even_a_masked_form_is_present(
        self, client, auth_headers, monkeypatch
    ):
        """Masked is still leaked: a prefix and a length are enough to
        confirm a guess."""
        monkeypatch.setattr(settings, "llm_api_key", "sk-hemlig-nyckel-42")

        body = client.get(STATUS_URL, headers=auth_headers).json()

        flattened = json.dumps(body, ensure_ascii=False).lower()
        for fragment in ("sk-hemlig", "nyckel-42", "llm_api_key", "api_key"):
            assert fragment not in flattened
