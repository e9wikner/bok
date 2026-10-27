"""Resetting a view's conversation (migration 034).

A reset is a context boundary, not a deletion: every post stays in the
thread, and only the posts after the boundary go into the agent's window.
"""

import json

import pytest

from db.database import db
from repositories.audit_repo import AuditRepository
from repositories.thread_repo import ThreadRepository
from services.thread_service import ThreadService
from services.thread_stream import EVENT_MESSAGE_CREATED, get_broker
from tests import test_tradar
from tests.test_tradar import (
    THREADS_URL,
    FakeLLMClient,
    _ensure_accounts,
    _run_thread,
    _thread_with_posts,
    _turn,
)

# The route tests' fixtures, shared with `test_tradar.py` rather than copied.
client = test_tradar.client
auth_headers = test_tradar.auth_headers
current_fiscal_year = test_tradar.current_fiscal_year

pytestmark = pytest.mark.usefixtures("test_db")


def _prompt(client_double: FakeLLMClient) -> str:
    return client_double.calls[0]["messages"][0]["content"][0]["text"]


class TestResetContext:
    def test_a_new_thread_has_never_been_reset(self):
        thread, _ = _thread_with_posts("hej")

        assert thread.context_from_seq == 0
        assert thread.context_reset_at is None

    def test_reset_moves_the_boundary_to_the_last_seq(self):
        thread, posts = _thread_with_posts("ett", "två", "tre")

        updated = ThreadService.reset_context(thread, actor="stefan")

        assert updated.context_from_seq == posts[-1].seq
        assert updated.context_reset_at is not None
        assert ThreadRepository.get(thread.id).context_from_seq == posts[-1].seq

    def test_no_post_is_changed_or_removed(self):
        thread, posts = _thread_with_posts("ett", "två")
        before = [(p.id, p.seq, p.body) for p in posts]

        ThreadService.reset_context(thread, actor="stefan")

        after = [(p.id, p.seq, p.body) for p in ThreadRepository.list_posts(thread.id)]
        assert after == before

    def test_the_reset_is_audit_logged_with_both_boundaries(self):
        thread, posts = _thread_with_posts("ett", "två")

        ThreadService.reset_context(thread, actor="stefan")

        history = AuditRepository.get_history("thread", thread.id)
        assert [entry.action.value for entry in history] == ["context_reset"]
        assert history[0].actor == "stefan"
        assert history[0].payload["context_from_seq_before"] == 0
        assert history[0].payload["context_from_seq"] == posts[-1].seq


class TestWindowAfterReset:
    def test_posts_before_the_boundary_never_reach_the_model(self):
        _ensure_accounts()
        thread, _ = _thread_with_posts("gammal fråga om mars")
        thread = ThreadService.reset_context(thread, actor="stefan")
        new_post = ThreadRepository.add_post(
            thread_id=thread.id,
            post_type="user_text",
            actor="stefan",
            body={"text": "ny fråga om april"},
        )
        client_double = FakeLLMClient([_turn(text="Svar.")])

        _run_thread(
            client_double,
            thread,
            new_post,
            history=ThreadRepository.list_posts(thread.id),
        )

        text = _prompt(client_double)
        assert "gammal fråga om mars" not in text
        assert "ny fråga om april" in text
        assert "nollställt konversationen: 1 tidigare inlägg" in text
        # A reset is not the budget cut, and is not described as one.
        assert "inte fick plats" not in text

    def test_a_thread_that_was_never_reset_says_nothing_about_it(self):
        _ensure_accounts()
        thread, posts = _thread_with_posts("hej")
        client_double = FakeLLMClient([_turn(text="Svar.")])

        _run_thread(client_double, thread, posts[-1], history=posts)

        assert "nollställt" not in _prompt(client_double)


class TestResetEndpoint:
    def test_reset_answers_with_the_new_boundary(
        self, client, auth_headers, current_fiscal_year
    ):
        for text in ("ett", "två"):
            client.post(
                f"{THREADS_URL}/bocker.balans/messages",
                json={"text": text},
                headers=auth_headers,
            )

        response = client.post(
            f"{THREADS_URL}/bocker.balans/reset", headers=auth_headers
        )

        assert response.status_code == 200
        body = response.json()
        assert body["context_from_seq"] == 2
        assert body["context_reset_at"] is not None

    def test_get_still_returns_every_post_and_the_boundary(
        self, client, auth_headers, current_fiscal_year
    ):
        client.post(
            f"{THREADS_URL}/bocker.balans/messages",
            json={"text": "ett"},
            headers=auth_headers,
        )
        client.post(f"{THREADS_URL}/bocker.balans/reset", headers=auth_headers)

        body = client.get(f"{THREADS_URL}/bocker.balans", headers=auth_headers).json()

        assert [p["body"]["text"] for p in body["posts"]] == ["ett"]
        assert body["context_from_seq"] == 1
        assert body["context_reset_at"] is not None

    def test_a_view_without_a_thread_is_404(
        self, client, auth_headers, current_fiscal_year
    ):
        response = client.post(
            f"{THREADS_URL}/bocker.balans/reset", headers=auth_headers
        )

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "thread_not_found"

    def test_an_unknown_view_key_is_404(self, client, auth_headers):
        response = client.post(
            f"{THREADS_URL}/bocker.verifikatoner/reset", headers=auth_headers
        )

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "unknown_view_key"

    def test_a_turn_in_progress_is_409(self, client, auth_headers, current_fiscal_year):
        client.post(
            f"{THREADS_URL}/bocker.balans/messages",
            json={"text": "ett"},
            headers=auth_headers,
        )
        thread = ThreadRepository.find("bocker.balans", current_fiscal_year.id)
        broker = get_broker()
        broker.publish(
            thread.id,
            EVENT_MESSAGE_CREATED,
            {"id": "streaming-run-1", "run_id": "run-1"},
        )
        try:
            response = client.post(
                f"{THREADS_URL}/bocker.balans/reset", headers=auth_headers
            )
        finally:
            broker._inflight.pop(thread.id, None)

        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "turn_in_progress"
        assert ThreadRepository.get(thread.id).context_from_seq == 0

    def test_the_reset_is_published_to_the_threads_subscribers(
        self, client, auth_headers, current_fiscal_year
    ):
        client.post(
            f"{THREADS_URL}/bocker.balans/messages",
            json={"text": "ett"},
            headers=auth_headers,
        )
        thread = ThreadRepository.find("bocker.balans", current_fiscal_year.id)
        received: list = []

        class _Loop:
            @staticmethod
            def call_soon_threadsafe(fn, frame):
                fn(frame)

        class _Queue:
            @staticmethod
            def put_nowait(frame):
                received.append(frame)

        queue = _Queue()
        get_broker().subscribe(thread.id, queue, _Loop())
        try:
            client.post(f"{THREADS_URL}/bocker.balans/reset", headers=auth_headers)
        finally:
            get_broker().unsubscribe(thread.id, queue)

        assert [event for event, _ in received] == ["thread.reset"]
        data = received[0][1]
        assert data["id"] == thread.id
        assert data["context_from_seq"] == 1
        json.dumps(data)  # it goes over SSE as JSON


def test_migration_034_adds_the_boundary_columns():
    columns = {row["name"] for row in db.execute("PRAGMA table_info(threads)")}

    assert {"context_from_seq", "context_reset_at"} <= columns
