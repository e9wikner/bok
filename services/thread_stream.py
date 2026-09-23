"""SSE for a thread: the bridge from a worker thread to a client (SPEC §3, §6.5).

Three constraints shape every line here, and none of them is negotiable:

1. **Thread-local SQLite with WAL** (`db/database.py`, AGENTS.md). A session
   runs in its **own worker thread** with its own connection, and the queue
   between that thread and the SSE generator carries only serialized events
   -- never a row, never a connection, never an open cursor.
2. **One writer per `run_id`** (§6.5). `AgentRunRepository.add_event`
   allocates `seq` read-then-write on a documented single-writer premise. A
   thread run gets its **own** `agent_runs` row, never a shared one, so the
   premise holds; `_RUN_REGISTRY` is what makes that checkable rather than
   merely intended.
3. **The flock guards the intake pass, not every LLM call** (§6.5). A thread
   run deliberately walks past `AgentRunner`'s lock: it never touches the
   intake queue, and two people must be able to write in two views at once.
   Nothing in this module takes that lock, and a test pins that it doesn't.

No new dependency (§3): `StreamingResponse` and an `asyncio.Queue`, not
`sse-starlette`. The bridge between the worker thread and the event loop is
`loop.call_soon_threadsafe`, which is the only thread-safe way into a running
loop.
"""

import json
import logging
import threading
from datetime import date
from typing import Any, Optional

from domain.models import Thread, ThreadPost
from repositories.agent_run_repo import AgentRunRepository
from repositories.period_repo import PeriodRepository
from repositories.thread_repo import ThreadRepository
from services.agent_session import SessionOutcome
from services.llm import (
    LLMConnectionError,
    LLMRateLimitError,
    UnknownModelError,
    get_model_info,
)
from services.thread_service import ThreadService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# The four event types (SPEC §6.5)
# ---------------------------------------------------------------------------

EVENT_MESSAGE_CREATED = "message.created"
EVENT_MESSAGE_DELTA = "message.delta"
EVENT_MESSAGE_COMPLETED = "message.completed"
EVENT_VIEW_CHANGED = "view.changed"


def format_sse(event: str, data: dict) -> str:
    """One `text/event-stream` frame.

    `ensure_ascii=False` so `ö`/`å`/`ä` stay literal on the wire, matching
    this codebase's convention everywhere else. The blank line at the end is
    what terminates a frame -- without it the client buffers forever.
    """
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def post_event_payload(post: ThreadPost) -> dict:
    """A stored post, as the stream sends it.

    The same fields `GET /threads/{view_key}` returns, so a client can
    replace an optimistic row with this one without a second shape to
    handle (SPEC §4).
    """
    return {
        "id": post.id,
        "seq": post.seq,
        "type": post.type,
        "actor": post.actor,
        "created_at": post.created_at.isoformat(),
        "body": post.body,
        "traces": post.traces,
        "run_id": post.run_id,
    }


# ---------------------------------------------------------------------------
# One writer per run_id (SPEC §6.5, test case 21)
# ---------------------------------------------------------------------------


class ConcurrentRunWriterError(Exception):
    """Raised if a second writer is ever started for a `run_id` already in
    flight.

    `UNIQUE (run_id, seq)` would catch the breach eventually, but as an
    IntegrityError in the middle of somebody's answer -- SPEC §6.5 is
    explicit that this is "inte en acceptabel upptäcktsmekanism". This is the
    same guarantee, raised before a single event is written.
    """

    def __init__(self, run_id: str) -> None:
        super().__init__(
            f"Agent run {run_id!r} already has a live writer. "
            "One writer per run_id (SPEC-tradar.md §6.5)."
        )
        self.run_id = run_id


_run_registry: set[str] = set()
_run_registry_guard = threading.Lock()


def claim_run(run_id: str) -> None:
    """Claim sole writership of `run_id`, or raise."""
    with _run_registry_guard:
        if run_id in _run_registry:
            raise ConcurrentRunWriterError(run_id)
        _run_registry.add(run_id)


def release_run(run_id: str) -> None:
    with _run_registry_guard:
        _run_registry.discard(run_id)


def live_run_ids() -> set[str]:
    """Snapshot of the runs currently being written, for tests and logging."""
    with _run_registry_guard:
        return set(_run_registry)


# ---------------------------------------------------------------------------
# Subscribers
# ---------------------------------------------------------------------------


class ThreadBroker:
    """Fan-out of a thread's live events to whoever is listening.

    One queue per subscriber, not one shared queue: two browsers on the same
    view must both see the whole answer, and a shared queue would let the
    first reader consume frames the second never gets.

    Every publish goes through `loop.call_soon_threadsafe`, because the
    publisher is a worker thread and the queues belong to the event loop.
    `asyncio.Queue` is not thread-safe and touching one from another thread
    is the kind of bug that works until it doesn't.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[tuple[Any, Any]]] = {}
        # What an in-flight turn has said so far, per thread: its
        # `message.created` payload plus the accumulated `text` and the
        # latest `activity`. The turn starts inside `POST .../messages` and
        # the client subscribes after the response, so without this the
        # first frames of the first answer went to nobody (SPEC-chattyta
        # §15, question 5).
        self._inflight: dict[str, dict] = {}
        self._guard = threading.Lock()

    def subscribe(self, thread_id: str, queue: Any, loop: Any) -> Optional[dict]:
        """Add a subscriber, and return the turn in progress, if any.

        Taken under the same lock as `publish` updates it, so the snapshot
        and the subscription agree: everything before is in the snapshot,
        everything after arrives in the queue. The caller sends it as a
        `message.created` carrying `text` and `activity` -- a client treats
        that as "the placeholder is this", so a reconnect mid-turn replaces
        its text rather than doubling it.
        """
        with self._guard:
            self._subscribers.setdefault(thread_id, []).append((queue, loop))
            snapshot = self._inflight.get(thread_id)
            return dict(snapshot) if snapshot is not None else None

    def unsubscribe(self, thread_id: str, queue: Any) -> None:
        with self._guard:
            remaining = [
                entry
                for entry in self._subscribers.get(thread_id, [])
                if entry[0] is not queue
            ]
            if remaining:
                self._subscribers[thread_id] = remaining
            else:
                self._subscribers.pop(thread_id, None)

    def subscriber_count(self, thread_id: str) -> int:
        with self._guard:
            return len(self._subscribers.get(thread_id, []))

    def publish(self, thread_id: str, event: str, data: dict) -> None:
        """Push one event to every subscriber of `thread_id`.

        Safe to call from any thread, and safe to call with no subscribers
        at all: a session that nobody is watching still runs to completion
        and still writes its posts. The stream is a view onto the work, not
        the work itself.
        """
        frame = (event, data)
        with self._guard:
            self._track_inflight(thread_id, event, data)
            targets = list(self._subscribers.get(thread_id, []))
        for queue, loop in targets:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, frame)
            except RuntimeError:
                # The loop closed while we held a reference to it -- the
                # subscriber is gone. Never fatal to the session.
                logger.debug("Dropped a thread event for a closed loop")

    def _track_inflight(self, thread_id: str, event: str, data: dict) -> None:
        """Keep `_inflight` in step with the frames. Called under the lock."""
        if event == EVENT_MESSAGE_CREATED:
            self._inflight[thread_id] = {**data, "text": "", "activity": None}
            return
        current = self._inflight.get(thread_id)
        if current is None:
            return
        if event == EVENT_MESSAGE_DELTA and data.get("id") == current.get("id"):
            if isinstance(data.get("text"), str):
                current["text"] += data["text"]
            if isinstance(data.get("activity"), str):
                current["activity"] = data["activity"]
        elif event == EVENT_MESSAGE_COMPLETED and data.get("run_id") == current.get(
            "run_id"
        ):
            # The runner publishes `completed` once, for the turn's final
            # post (`ThreadTurnRunner._publish_completed`).
            del self._inflight[thread_id]


_broker = ThreadBroker()


def get_broker() -> ThreadBroker:
    """The process-wide broker."""
    return _broker


# ---------------------------------------------------------------------------
# Running a thread turn
# ---------------------------------------------------------------------------


class ThreadTurnRunner:
    """Run one thread turn in a worker thread and publish as it goes.

    Deliberately not `AgentWorker`: that class owns the intake queue's pass
    algorithm, its flock and its reaping. A thread turn shares none of that.
    What it does share -- the session engine, the caps, the cost accounting,
    the event rows -- it reaches through the same functions the worker does.
    """

    def __init__(self, broker: Optional[ThreadBroker] = None) -> None:
        self.broker = broker or get_broker()

    def start(
        self,
        thread: Thread,
        trigger_post: ThreadPost,
        message: str,
        actor: str = "agent",
        client_factory: Any = None,
    ) -> threading.Thread:
        """Start the turn in its own worker thread and return immediately.

        Its own thread, because `db/database.py` hands out **thread-local**
        connections: the session must not share the request's connection,
        and the SSE generator must not block on the session.
        """
        worker = threading.Thread(
            target=self.run,
            args=(thread, trigger_post, message),
            kwargs={"actor": actor, "client_factory": client_factory},
            name=f"thread-turn-{thread.view_key}",
            daemon=True,
        )
        worker.start()
        return worker

    def run(
        self,
        thread: Thread,
        trigger_post: ThreadPost,
        message: str,
        actor: str = "agent",
        client_factory: Any = None,
    ) -> Optional[SessionOutcome]:
        """Run one turn to completion. Safe to call synchronously in a test.

        Sequencing, and why each step is where it is:

        1. Resolve the model and its protocol -- `UnknownModelError` before
           any `agent_runs` row exists (SPEC-agentruntime §2).
        2. Create this turn's **own** `agent_runs` row with
           `trigger='thread'` and claim sole writership of it (§6.5).
           `agent_runs.trigger` already lists `'thread'` and carries no
           CHECK constraint, so no migration was needed.
        3. Announce the agent's post as created, run the session, stream the
           deltas.
        4. Store the finished post, announce it completed, and -- only if
           something was actually posted -- announce `view.changed`.

        Any failure becomes an `error` post and a completed event: §6.7's
        "Tråden tappar aldrig en tur i tysthet."
        """
        from services.agent_runtime import (
            DailyBudgetExhaustedError,
            build_llm_client,
            compute_cost_ore,
            ensure_daily_budget_available,
        )
        from services.thread_session import run_thread_session

        factory = client_factory or build_llm_client
        model = thread.model

        try:
            protocol = get_model_info(model).protocol
        except UnknownModelError as exc:
            self._publish_error(thread, f"unknown_model: {exc}")
            return None

        try:
            ensure_daily_budget_available()
        except DailyBudgetExhaustedError as exc:
            # Before any `agent_runs` row exists, exactly as the intake pass
            # refuses to start (SPEC-agentruntime §9 test case 8).
            self._publish_error(
                thread,
                f"budget_exhausted: spent {exc.spent_ore} of {exc.budget_ore} öre",
            )
            return None

        run = AgentRunRepository.create(
            trigger="thread", model=model, protocol=protocol
        )
        claim_run(run.id)

        # A placeholder id for the post being streamed: `message.created`
        # has to name something before the post exists, and the client
        # swaps its optimistic row for the stored post at
        # `message.completed` (SPEC §4).
        streaming_id = f"streaming-{run.id}"
        self.broker.publish(
            thread.id,
            EVENT_MESSAGE_CREATED,
            {
                "id": streaming_id,
                "type": "agent_text",
                "actor": actor,
                "run_id": run.id,
            },
        )

        collected: list[str] = []

        def _on_text(increment: str) -> None:
            # Deltas are a delivery, not an event worth a row (§8.5): they
            # go over the stream and are accumulated here only so the post
            # that gets stored is what the human actually watched appear.
            collected.append(increment)
            self.broker.publish(
                thread.id,
                EVENT_MESSAGE_DELTA,
                {"id": streaming_id, "text": increment},
            )

        def _on_tool_call(tool_name: str) -> None:
            # What `SkriverIndikator` says. "Aldrig en anonym spinner."
            self.broker.publish(
                thread.id,
                EVENT_MESSAGE_DELTA,
                {"id": streaming_id, "activity": tool_name},
            )

        def _check_between_turns() -> Optional[str]:
            try:
                ensure_daily_budget_available()
            except DailyBudgetExhaustedError as exc:
                return (
                    f"budget_exhausted: spent {exc.spent_ore} of "
                    f"{exc.budget_ore} öre"
                )
            return None

        try:
            history = ThreadRepository.list_posts(thread.id)
            open_periods = [
                period
                for period in PeriodRepository.list_periods(thread.fiscal_year_id)
                if not period.locked
            ]
            try:
                outcome = run_thread_session(
                    factory(model),
                    thread,
                    trigger_post,
                    message,
                    history=history,
                    open_periods=open_periods,
                    today=date.today(),
                    model=model,
                    actor=actor,
                    on_text=_on_text,
                    on_tool_call=_on_tool_call,
                    check_between_turns=_check_between_turns,
                )
            except (LLMConnectionError, LLMRateLimitError) as exc:
                reason = f"{_error_code(exc)}: {exc}"
                logger.error("Thread run %s failed: %s", run.id, reason)
                AgentRunRepository.update_status(run.id, "failed", last_error=reason)
                post = ThreadService.record_error(thread, reason, run_id=run.id)
                self._publish_completed(thread, post)
                return None

            AgentRunRepository.add_usage(
                run.id,
                input_tokens=outcome.usage.input_tokens,
                output_tokens=outcome.usage.output_tokens,
                cache_read_tokens=outcome.usage.cache_read_input_tokens,
                cost_ore=compute_cost_ore(model, outcome.usage),
            )
            AgentRunRepository.increment_items(
                run.id,
                seen=1,
                posted=1 if outcome.kind == "posted" else 0,
                abstained=1 if outcome.kind == "abstained" else 0,
            )
            _write_run_events(run.id, outcome)

            post = ThreadService.record_outcome(
                thread,
                run.id,
                outcome,
                actor=actor,
                answer_text="".join(collected) if collected else None,
            )
            AgentRunRepository.update_status(run.id, "completed")
            self._publish_completed(thread, post)

            if outcome.kind == "posted":
                # Derived from the posting's own outcome -- never from a
                # guessed interval, never as a periodic "something may have
                # happened" (§6.6).
                self.broker.publish(
                    thread.id,
                    EVENT_VIEW_CHANGED,
                    {
                        "view_key": thread.view_key,
                        "changed": {
                            "voucher_id": outcome.voucher_id,
                            "kind": "voucher_posted",
                        },
                    },
                )
            return outcome
        except Exception as exc:  # noqa: BLE001 -- §6.7: the thread never
            # loses a turn in silence, whatever went wrong.
            logger.exception("Thread run %s raised", run.id)
            AgentRunRepository.update_status(
                run.id, "failed", last_error=f"{type(exc).__name__}: {exc}"
            )
            post = ThreadService.record_error(
                thread, f"{type(exc).__name__}: {exc}", run_id=run.id
            )
            self._publish_completed(thread, post)
            return None
        finally:
            release_run(run.id)

    def _publish_completed(self, thread: Thread, post: ThreadPost) -> None:
        self.broker.publish(
            thread.id, EVENT_MESSAGE_COMPLETED, post_event_payload(post)
        )

    def _publish_error(self, thread: Thread, reason: str) -> None:
        """An error that happened before a run existed -- still a post, still
        a completed event."""
        post = ThreadService.record_error(thread, reason)
        self._publish_completed(thread, post)


def _error_code(exc: Exception) -> str:
    return (
        "llm_rate_limit_error"
        if isinstance(exc, LLMRateLimitError)
        else "llm_connection_error"
    )


def _write_run_events(run_id: str, outcome: SessionOutcome) -> None:
    """`agent_run_events` rows for a thread turn.

    The same rows, in the same shapes, as `AgentWorker._write_events` writes
    for a document -- `services/thread_service.py` reads them back as chips,
    and it must not have to care which entry point produced them.
    `source_id` is left unset: a thread turn is not about one intake source.
    """
    from services.agent_runtime import _compact_tool_result, _event_payload

    for turn_record in outcome.turns:
        if turn_record.turn.text:
            AgentRunRepository.add_event(
                run_id, "text", _event_payload(text=turn_record.turn.text)
            )
        for executed in turn_record.executed_tool_calls:
            if executed.ok:
                AgentRunRepository.add_event(
                    run_id,
                    "tool_call",
                    _event_payload(
                        name=executed.tool_call.name,
                        args=executed.tool_call.arguments,
                        result=_compact_tool_result(executed.result),
                    ),
                )
            else:
                AgentRunRepository.add_event(
                    run_id,
                    "error",
                    _event_payload(
                        name=executed.tool_call.name,
                        args=executed.tool_call.arguments,
                        error=executed.error,
                    ),
                )

    kind = {
        "posted": "posted",
        "abstained": "abstained",
        "answered": "text",
        "failed": "error",
    }[outcome.kind]
    AgentRunRepository.add_event(
        run_id,
        kind,
        _event_payload(reason=outcome.reason),
        voucher_id=outcome.voucher_id,
    )
