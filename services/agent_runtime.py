"""Budget, cost, cap, and worker/runner primitives for the agent runtime
(SPEC §6.5/§6.1/§6.2, tasks A9/A10).

SPEC §6.5 lists four caps. Task A8 already implemented the first one --
verktygsvarv per underlag (tool turns per item) -- directly inside
`services/agent_session.py`'s `run_session` loop, and A9 added the second one
(ut-token per underlag / output tokens per item) to that same loop, since
both can only be measured turn by turn.

This module holds:

- Cost calculation (`compute_cost_ore`): a pure function from a model id and
  a `Usage` to an integer öre amount, using the price table in
  `services/llm/__init__.py`.
- The daily budget cap / "dygnstaket" (`ensure_daily_budget_available`,
  `DailyBudgetExhaustedError`): SPEC §6.5's "kostnad per dygn" cap. "Vid
  dygnstaket: stanna, aldrig nedgradera modell" (§6.5, §12.5) -- this module
  never adjusts the model; it only decides whether a pass, or the next item
  in one, is allowed to spend more today.
- The fourth cap -- "underlag per pass" (items per pass, default
  `config.settings.agent_max_items_per_pass`) -- applied in `AgentWorker.
  run_pass_once` as a plain slice/limit on the queue fetch (SPEC §9's table
  describes it as a loop bound: "stop after N items, leave the rest
  queued").
- `AgentWorker` (SPEC §6.2's pass algorithm) and `AgentRunner` (SPEC §6.1's
  thread/flock lifecycle wrapper, task A10) -- see their own docstrings
  below.

This module never imports `anthropic`/`openai`, has no HTTP concepts, and
does no SQL of its own -- it only reads through `AgentRunRepository`'s
existing methods. The reaping/budget/queue checks in `AgentWorker` never run
inside a `with db.transaction():` block; there is none anywhere in this
module, matching `services/agent_session.py` (SPEC §6.5: "aldrig inuti
`with db.transaction():`") -- the item-level posting transaction lives
entirely inside `services/voucher_posting.py`, several layers below.
"""

import fcntl
import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Optional

from config import settings
from domain.models import AgentRun, IntakeSource
from repositories.agent_run_repo import AgentRunRepository
from repositories.period_repo import PeriodRepository
from services.agent_session import SessionOutcome, run_session
from services.intake import IntakeService
from services.llm import (
    LLMClient,
    LLMConnectionError,
    LLMRateLimitError,
    Usage,
    get_model_info,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cost calculation (SPEC §5: "cost_ore beräknas ur usage och prislistan")
# ---------------------------------------------------------------------------


def compute_cost_ore(model: str, usage: Usage) -> int:
    """Compute the integer öre cost of one `Usage` on `model`.

    Looks up `model`'s price row via `services.llm.get_model_info` and
    applies the formula documented on `ModelPrice`
    (`services/llm/__init__.py`): each token category is priced
    independently at its own per-million-tokens rate with integer floor
    division, and the three results are summed at the end -- never summed
    first and divided once, which would round differently.

    Critically, `usage.cache_read_input_tokens` is priced at
    `price.cache_read_ore_per_million_tokens`, *not*
    `price.input_ore_per_million_tokens` -- conflating the two would silently
    misprice every cached turn from the second item in a pass onward
    (SPEC §6.6).

    Raises `services.llm.UnknownModelError` unhandled if `model` has no price
    row -- SPEC §2: "en modell utan prisrad är ett fel, inte ett
    standardvärde." A pass on an unpriced model is a hard stop; it is not
    this function's job to catch that and fall back to a cost of 0.
    """
    price = get_model_info(model).price
    input_cost_ore = (
        usage.input_tokens * price.input_ore_per_million_tokens // 1_000_000
    )
    output_cost_ore = (
        usage.output_tokens * price.output_ore_per_million_tokens // 1_000_000
    )
    cache_read_cost_ore = (
        usage.cache_read_input_tokens
        * price.cache_read_ore_per_million_tokens
        // 1_000_000
    )
    return input_cost_ore + output_cost_ore + cache_read_cost_ore


# ---------------------------------------------------------------------------
# Daily budget cap / "dygnstaket" (SPEC §6.5, §9 test case 8)
# ---------------------------------------------------------------------------


class DailyBudgetExhaustedError(Exception):
    """Raised when today's spend already meets or exceeds the daily budget.

    Carries `spent_ore` and `budget_ore` so a caller can log or report the
    refusal (SPEC §9 test case 8: "passet startar inte" -- and that refusal
    must be logged, never silently swallowed). Never carries anything from
    `Usage` or the LLM response itself -- just the two öre amounts needed to
    explain the refusal.
    """

    def __init__(self, spent_ore: int, budget_ore: int) -> None:
        super().__init__(
            f"Daily budget exhausted: spent {spent_ore} öre of a "
            f"{budget_ore} öre daily budget."
        )
        self.spent_ore = spent_ore
        self.budget_ore = budget_ore


def ensure_daily_budget_available(
    agent_run_repo: type[AgentRunRepository] = AgentRunRepository,
) -> None:
    """Raise `DailyBudgetExhaustedError` if today's spend already meets or
    exceeds `config.settings.agent_daily_budget_ore` (SPEC §6.5's "kostnad
    per dygn" cap, 5000 öre / 50 kr by default).

    `agent_run_repo` accepts `AgentRunRepository` itself (all of its methods
    are `@staticmethod`, so the class is callable exactly like an instance --
    see `repositories/agent_run_repo.py`) and defaults to it; a test may pass
    a different object exposing the same `sum_cost_today_ore() -> int` shape
    if it ever needs to.

    This function does not, by itself, wire up *when* it gets called -- it
    is meant to be invoked from two distinct points once A10 builds the
    worker's pass loop around `services/agent_runtime.py`:

    1. **Before a pass starts, before the `agent_runs` row is created.**
       SPEC §9 test case 8: "Dygnstaket redan nått" -> "Passet startar inte,
       ingen agent_runs-rad, loggat." A10's worker calls this first thing
       inside its "passet startas" step (SPEC §6.2), before
       `AgentRunRepository.create(...)`, and logs the refusal (this
       exception's `spent_ore`/`budget_ore`) rather than swallowing it.
    2. **Between items, after finishing each one, for the rest of the
       pass.** SPEC §6.5's table: "Kostnad per dygn -> Avsluta passet,
       status='completed', logga budget_exhausted." A10's per-item loop
       (SPEC §6.2's "för varje post, en i taget") calls this again after each
       item's session finishes (and its cost has been added via
       `AgentRunRepository.add_usage`), and on this exception ends the pass
       cleanly with `status='completed'` -- never mid-item, never inside the
       item's own `with db.transaction():`.

    Comparison is `>=`, not `>`: a spend exactly equal to the budget has
    exhausted it, matching SPEC §6.5's "redan nått" framing in test case 8.
    """
    spent_ore = agent_run_repo.sum_cost_today_ore()
    if spent_ore >= settings.agent_daily_budget_ore:
        raise DailyBudgetExhaustedError(
            spent_ore=spent_ore, budget_ore=settings.agent_daily_budget_ore
        )


# ---------------------------------------------------------------------------
# LLM client factory (task A10)
# ---------------------------------------------------------------------------


class UnsupportedProtocolError(Exception):
    """Raised by `build_llm_client` for any protocol besides `"messages"`.

    Deliberately narrow for now: `services/llm/chat.py` (the Chat Completions
    adapter, task A12) does not exist yet, so this is the explicit,
    documented stand-in until A12 lands -- not a placeholder that silently
    falls back to something. When A12 lands, this factory gets a second
    branch (`if protocol == "chat": ... return ChatClient(...)`), not a
    redesign; this class then only ever fires for a genuinely unhandled
    third protocol.
    """

    def __init__(self, protocol: str) -> None:
        super().__init__(
            f"No LLM client factory wired up for protocol {protocol!r} yet. "
            'Only "messages" (services.llm.messages.MessagesClient) is wired '
            'in this build -- the "chat" adapter (services/llm/chat.py) '
            "lands in task A12; see build_llm_client in services/agent_runtime.py."
        )
        self.protocol = protocol


def build_llm_client(model: str) -> LLMClient:
    """Resolve `model` to its protocol and construct the matching adapter.

    Called once per pass by `AgentWorker.run_pass_once` (not once per item --
    SPEC doesn't require a fresh client per item, and building one Anthropic
    client per pass is cheaper and behaves identically since `MessagesClient`
    carries no per-call state).

    The `services.llm.messages` import is deferred inside this function
    (not at module level) so that importing `services/agent_runtime.py`
    itself never pulls in `anthropic` -- only actually resolving a
    Messages-protocol model does. This is what keeps
    `grep -r "^import anthropic\\|^from anthropic" services/agent_runtime.py`
    empty, per SPEC §4/§10's "anthropic/openai importeras bara i
    services/llm/".
    """
    protocol = get_model_info(model).protocol
    if protocol == "messages":
        from services.llm.messages import MessagesClient

        return MessagesClient(
            api_key=settings.llm_api_key, base_url=settings.llm_base_url
        )
    raise UnsupportedProtocolError(protocol)


# ---------------------------------------------------------------------------
# agent_run_events payload helpers (SPEC §5)
# ---------------------------------------------------------------------------


def _compact_tool_result(result: Any) -> Any:
    """Compact a tool result before it goes into an `agent_run_events` row.

    `hamta_underlagsfil` can return a `document`/`image` content block whose
    payload is a base64-encoded PDF or image -- easily hundreds of KB. SPEC
    §8 wants `agent_run_events` readable by a human via `GET /agent/status`
    (A11), not a second copy of every underlag's raw bytes, so this keeps
    only the block's `type` for those two, and passes everything else
    (`text` blocks, the plain dicts every other tool returns) through
    unchanged.
    """
    if isinstance(result, dict) and result.get("type") in ("document", "image"):
        return {"type": result["type"], "note": "<binary content omitted>"}
    return result


def _event_payload(**fields: Any) -> str:
    """`json.dumps` with `ensure_ascii=False` (so `ö`/`å`/`ä` stay literal,
    matching this codebase's Swedish-text convention elsewhere) and
    `default=str` as a backstop for anything not natively JSON-serializable.
    """
    return json.dumps(fields, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# AgentWorker: one pass (SPEC §6.2)
# ---------------------------------------------------------------------------

#: Outcome-to-event-kind mapping for a session's *final* event (SPEC §5's
#: documented `agent_run_events.kind` values). `SessionOutcome.kind ==
#: "failed"` is `run_session`'s own defensive branch for a stop reason no
#: adapter should ever produce (see that module's docstring) -- logged as
#: an "error" event here rather than a new fourth item-outcome bucket, since
#: SPEC §5's `items_seen/items_posted/items_abstained` counters only have
#: room for two dispositions besides "seen".
_OUTCOME_EVENT_KIND = {"posted": "posted", "abstained": "abstained", "failed": "error"}


class AgentWorker:
    """Run one pass over the pending intake queue (SPEC §6.2).

    Fully synchronous and directly callable -- no threading here. The
    thread/flock lifecycle lives one layer up, in `AgentRunner`, so this
    class (and its single public method, `run_pass_once`) can be exercised
    directly and deterministically by nearly every test in this module.
    """

    def _reap_abandoned_runs(self) -> None:
        """SPEC §6.2 step 1: any `agent_runs` row still `'running'` when a
        new pass begins is definitionally stale.

        This worker only ever runs one pass at a time synchronously --
        enforced one layer up by `AgentRunner`'s flock, and by this method
        never being re-entrant within a process -- so a row still `'running'`
        here can only be left over from a crashed process or a thread that
        died mid-pass without reaching its own `update_status` call (SPEC
        §9 test case 12).
        """
        for run in AgentRunRepository.find_running():
            logger.warning(
                "Agent run %s is still 'running' with no live pass behind it -- "
                "marking abandoned (crashed process or thread, SPEC §6.1/§9#12)",
                run.id,
            )
            AgentRunRepository.update_status(
                run.id,
                "abandoned",
                last_error="Abandoned: still 'running' at the next pass's start",
            )

    def run_pass_once(
        self,
        model: Optional[str] = None,
        trigger: str = "manual",
        client_factory: Callable[[str], LLMClient] = build_llm_client,
    ) -> Optional[AgentRun]:
        """Run exactly one pass over the pending intake queue (SPEC §6.2).

        `client_factory` defaults to the real `build_llm_client` and exists
        purely for tests to inject a fake `LLMClient` without monkeypatching
        module state -- every test in this file except the lock/enabled
        ones (SPEC §9 test cases 13, 16) calls this method directly with a
        `FakeLLMClient`-returning factory.

        Returns `None` if the pending queue was empty (no `agent_runs` row
        written, no LLM call made -- SPEC §9 test case 9). Otherwise returns
        the finished `AgentRun` (`status` one of `'completed'`/`'failed'`).

        Sequencing, exactly as SPEC §6.2 orders it:

        1. Reap abandoned runs (`_reap_abandoned_runs`).
        2. Resolve the model and look it up -- `UnknownModelError` propagates
           unhandled, before any `agent_runs` row exists (SPEC §2).
        3. Check the daily budget -- `DailyBudgetExhaustedError` propagates
           unhandled, before any `agent_runs` row exists (SPEC §9 test case 8).
        4. Fetch the queue, capped at `settings.agent_max_items_per_pass`
           (the fourth cap, SPEC §6.5).
        5. Empty queue -> return `None`.
        6. Create the `agent_runs` row.
        7. One item at a time: re-check the daily budget; optionally log a
           processing attempt; resolve and read the file; run one session;
           handle `LLMConnectionError`/`LLMRateLimitError` by ending the pass
           with `status='failed'`; otherwise accumulate usage/items/events
           from the `SessionOutcome`.
        8. Mark the run `status='completed'` once the queue is exhausted.
        """
        self._reap_abandoned_runs()

        resolved_model = model or settings.llm_default_model
        model_info = get_model_info(resolved_model)

        ensure_daily_budget_available()

        intake_service = IntakeService()
        queue = intake_service.get_pending_queue(
            limit=settings.agent_max_items_per_pass, offset=0
        )
        sources: list[IntakeSource] = queue["items"]
        if not sources:
            logger.info("Agent pass: pending queue is empty, nothing to do")
            return None

        run = AgentRunRepository.create(
            trigger=trigger, model=resolved_model, protocol=model_info.protocol
        )
        logger.info(
            "Agent run %s started (trigger=%s, model=%s, protocol=%s, items=%d)",
            run.id,
            trigger,
            resolved_model,
            model_info.protocol,
            len(sources),
        )

        client = client_factory(resolved_model)
        open_periods = [
            period
            for period in PeriodRepository.list_all_periods()
            if not period.locked
        ]

        for source in sources:
            try:
                ensure_daily_budget_available()
            except DailyBudgetExhaustedError as exc:
                logger.warning(
                    "Agent run %s stopping: daily budget exhausted "
                    "(spent=%d, budget=%d öre)",
                    run.id,
                    exc.spent_ore,
                    exc.budget_ore,
                )
                AgentRunRepository.update_status(
                    run.id,
                    "completed",
                    last_error=(
                        f"budget_exhausted: spent {exc.spent_ore} of "
                        f"{exc.budget_ore} öre"
                    ),
                )
                return AgentRunRepository.get(run.id)

            try:
                intake_service.record_processing(
                    source.id,
                    summary="Agent-pass bearbetar underlaget",
                    actor="agent",
                )
            except Exception:
                # Nice-to-have audit trail entry, not a correctness
                # requirement (see this method's docstring point 7) --
                # `record_attempt` only INSERTs an `intake_processing_
                # attempts` row (repositories/intake_repo.py); it never
                # touches `intake_sources.status`, so a failure here can
                # never leave the source itself in a bad state.
                logger.exception(
                    "Agent run %s: could not record a processing attempt "
                    "for source %s (non-fatal, continuing)",
                    run.id,
                    source.id,
                )

            file_bytes = intake_service.resolve_source_file(source).read_bytes()

            try:
                outcome = run_session(
                    client=client,
                    source=source,
                    file_bytes=file_bytes,
                    open_periods=open_periods,
                    today=date.today(),
                    model=resolved_model,
                    actor="agent",
                )
            except LLMConnectionError as exc:
                logger.error(
                    "Agent run %s: connection error talking to the LLM " "gateway: %s",
                    run.id,
                    exc,
                )
                AgentRunRepository.update_status(
                    run.id, "failed", last_error=f"llm_connection_error: {exc}"
                )
                # Investigated per this task's instructions: `IntakeService.
                # record_processing` (called above) only writes a row to
                # `intake_processing_attempts` via `IntakeRepository.
                # record_attempt` -- it never runs an UPDATE against
                # `intake_sources.status` (see `record_failed`, a few lines
                # down in services/intake.py, for the method that *does*
                # transition status, via `sources.update_status`).  So the
                # source's queryable `status` column is still `'pending'`
                # at this point, exactly as `record_processing`'s docstring
                # ("leaving the source pending") says -- there is nothing to
                # revert here. Writing a speculative revert-to-pending call
                # would be a no-op at best and a second, unnecessary write
                # at worst.
                return AgentRunRepository.get(run.id)
            except LLMRateLimitError as exc:
                logger.error(
                    "Agent run %s: rate limited by the LLM gateway "
                    "(retry_after_seconds=%s)",
                    run.id,
                    exc.retry_after_seconds,
                )
                AgentRunRepository.update_status(
                    run.id,
                    "failed",
                    last_error=(
                        "llm_rate_limit_error: retry_after_seconds="
                        f"{exc.retry_after_seconds}"
                    ),
                )
                return AgentRunRepository.get(run.id)

            self._record_outcome(run.id, resolved_model, source, outcome)

        AgentRunRepository.update_status(run.id, "completed")
        logger.info("Agent run %s completed", run.id)
        return AgentRunRepository.get(run.id)

    def _record_outcome(
        self,
        run_id: str,
        model: str,
        source: IntakeSource,
        outcome: SessionOutcome,
    ) -> None:
        """SPEC §6.2 step 7e/f: accumulate usage/cost, item counters, and
        write `agent_run_events` rows for one finished session."""
        AgentRunRepository.add_usage(
            run_id,
            input_tokens=outcome.usage.input_tokens,
            output_tokens=outcome.usage.output_tokens,
            cache_read_tokens=outcome.usage.cache_read_input_tokens,
            cost_ore=compute_cost_ore(model, outcome.usage),
        )
        AgentRunRepository.increment_items(
            run_id,
            seen=1,
            posted=1 if outcome.kind == "posted" else 0,
            abstained=1 if outcome.kind == "abstained" else 0,
        )
        self._write_events(run_id, source, outcome)

    def _write_events(
        self, run_id: str, source: IntakeSource, outcome: SessionOutcome
    ) -> None:
        """One `agent_run_events` row per tool call (`'tool_call'` on
        success, `'error'` on a raised exception), one per non-empty turn
        text (`'text'`), and one final row for the session's own outcome
        (`'posted'`/`'abstained'`/`'error'`) -- not a serialization of every
        raw `LLMTurn`, just enough for a human reading `GET /agent/status`
        (A11) to follow what happened.
        """
        for turn_record in outcome.turns:
            if turn_record.turn.text:
                AgentRunRepository.add_event(
                    run_id,
                    "text",
                    _event_payload(text=turn_record.turn.text),
                    source_id=source.id,
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
                        source_id=source.id,
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
                        source_id=source.id,
                    )

        AgentRunRepository.add_event(
            run_id,
            _OUTCOME_EVENT_KIND[outcome.kind],
            _event_payload(reason=outcome.reason),
            source_id=source.id,
            voucher_id=outcome.voucher_id,
        )


# ---------------------------------------------------------------------------
# AgentRunner: thread/flock lifecycle (SPEC §6.1, task A10)
# ---------------------------------------------------------------------------
#
# Exact same form as `services.dropzone.DropzoneRunner`, on purpose (SPEC
# §6.1: "mönstret är redan i drift på hubbabubba och dess fallgropar är redan
# lösta där") -- background thread started from `lifespan`, off by default,
# `flock` on a lock file rather than a PID file, `stop()` sets an `Event` and
# joins with a timeout. The one deliberate difference: SPEC §12.3 says no
# timer drives a pass yet, so `_run` waits idle on a second `Event`
# (`_trigger`) instead of looping on a fixed scan interval like
# `DropzoneRunner._run` does. The wait's timeout below is not a scan
# interval -- it exists purely so `stop()` can interrupt an idle thread
# promptly; the loop does nothing on each timeout besides re-checking
# `_stop`.

LOCK_FILENAME = ".agent_runtime.lock"

#: Purely a responsiveness knob for `stop()`, not a scan interval (SPEC
#: §12.3: this module runs no schedule of its own yet).
_TRIGGER_POLL_TIMEOUT_SECONDS = 5.0


def _lock_path() -> Path:
    """A dedicated lock file, deliberately not `services.dropzone`'s own
    (SPEC §6.1's flock guards one subsystem at a time; sharing a lock file
    between the dropzone scanner and the agent runtime would make an
    unrelated change to one able to break exclusivity for the other).
    Lives alongside `settings.intake_dir`, which -- unlike
    `settings.dropzone_dir` -- is always configured, even when the runtime
    itself is disabled.
    """
    return Path(settings.intake_dir) / LOCK_FILENAME


# Locks this process holds, keyed by absolute lock path, so a second
# AgentRunner started within the same process (rather than a second OS
# process) is refused too -- same reasoning and shape as
# `services.dropzone._held_locks`.
_held_locks: set[str] = set()
_held_locks_guard = threading.Lock()


@dataclass
class _AgentRuntimeLock:
    """An open handle holding the `flock` -- closing it releases the lock.

    `handle` is typed `Any`, not `object` (unlike `services.dropzone.
    _DropzoneLock`, which is part of this module's untouched pre-existing
    mypy baseline and already carries the two `attr-defined` errors that
    typing it `object` produces): `_acquire_lock`/`_release_lock` below call
    `.fileno()`/`.close()` on it, and this task's instructions require
    adding zero new mypy errors in this module's own files.
    """

    path: Path
    handle: Any


def _acquire_lock(lock_path: Path) -> Optional["_AgentRuntimeLock"]:
    """Take an exclusive `flock` on the lock file so only one `AgentRunner`
    runs a pass at a time.

    Deliberately a duplicate of `services.dropzone._acquire_lock`, not a
    shared helper the two subsystems both call -- these are separate
    subsystems with separate lock files (see `_lock_path`), and coupling
    them through shared code would let an unrelated change to one break
    exclusivity for the other. The reasoning itself is identical, copied
    rather than paraphrased so it can't drift from the original:

    A PID written into the file cannot tell a live holder from a stale one
    under a container runtime that reuses the same PID namespace layout on
    every restart (rootless Podman gives uvicorn PID ~8 every time) -- after
    an unclean restart the PID in a leftover lock file matches the *new*
    process, so a staleness check based on it wrongly reports the lock as
    live. `flock` sidesteps the problem entirely: it is held by the open
    file description, not by a PID we write and compare, so it is released
    by the kernel the moment the holding process exits or its fd closes,
    regardless of what PID gets reused afterwards. Two agent workers
    bookkeeping the same queue in parallel is worse than no worker at all
    (SPEC §6.1, §10: "Två workers mot samma databas" is in the "Aldrig"
    list).
    """
    key = os.path.abspath(lock_path)
    with _held_locks_guard:
        if key in _held_locks:
            return None
        try:
            handle = open(lock_path, "w")
        except OSError as exc:
            logger.error("Could not open agent runtime lock %s: %s", lock_path, exc)
            return None
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return None
        handle.write(str(os.getpid()))
        handle.flush()
        _held_locks.add(key)
        return _AgentRuntimeLock(path=lock_path, handle=handle)


def _release_lock(lock: Optional["_AgentRuntimeLock"]) -> None:
    if lock is None:
        return
    with _held_locks_guard:
        _held_locks.discard(os.path.abspath(lock.path))
        try:
            fcntl.flock(lock.handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            lock.handle.close()
        except OSError:
            pass
        try:
            lock.path.unlink()
        except OSError:
            pass


class AgentRunner:
    """Run `AgentWorker` passes in a background thread (SPEC §6.1).

    Manual start only (SPEC §12.3): the background thread, once started,
    waits idle until `trigger_pass_now` is called -- nothing loops on a
    timer here yet. Whoever adds scheduling later only needs to call
    `trigger_pass_now` on an interval and change `trigger='manual'` to
    `'schedule'`; this class's shape does not change.
    """

    def __init__(self, worker: Optional[AgentWorker] = None):
        self.worker = worker or AgentWorker()
        self._stop = threading.Event()
        self._trigger = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock: Optional[_AgentRuntimeLock] = None
        self._pending_model: Optional[str] = None
        self._pass_in_progress = False
        self._last_run_id: Optional[str] = None
        self._last_error: Optional[str] = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        """Start the idle background thread. Returns `False`, and does
        nothing else, if the runtime is disabled (SPEC §9 test case 16,
        mirroring `dropzone.start_background_scanner`'s own
        `if not settings.dropzone_enabled` guard exactly) or if the lock
        could not be taken (SPEC §9 test case 13).
        """
        if not settings.agent_runtime_enabled:
            logger.info("Agent runtime disabled (AGENT_RUNTIME_ENABLED=false)")
            return False
        if self.running:
            return True

        lock_path = _lock_path()
        try:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.error(
                "Agent runtime lock directory %s is unusable: %s",
                lock_path.parent,
                exc,
            )
            return False

        self._lock = _acquire_lock(lock_path)
        if self._lock is None:
            logger.warning(
                "Agent runtime not started: %s is held by another process",
                lock_path,
            )
            return False

        self._stop.clear()
        self._trigger.clear()
        self._thread = threading.Thread(
            target=self._run, name="agent-runtime", daemon=True
        )
        self._thread.start()
        logger.info("Agent runtime started, waiting for a manual trigger")
        return True

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the thread to stop and join it, then release the flock.

        A pass already in flight is never interrupted mid-item: `_stop`
        is only checked between the idle wait's timeouts, and
        `AgentWorker.run_pass_once` itself has no cooperative-cancellation
        point -- it runs to completion or fails on its own (SPEC §6.1: "En
        pågående LLM-tur avbryts inte mitt i en postning").
        """
        self._stop.set()
        self._trigger.set()  # wake an idle wait so it notices _stop promptly
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
        self._thread = None
        _release_lock(self._lock)
        self._lock = None

    def trigger_pass_now(self, model: Optional[str] = None) -> None:
        """Ask the background thread to run one pass with `trigger='manual'`.

        Fire-and-forget: this does not block for, or return, the resulting
        `AgentRun`. Nearly every test in this module calls `AgentWorker.
        run_pass_once` directly instead, precisely to get a synchronous,
        deterministic result without going through a thread -- only the
        lock-exclusivity and disabled-runtime tests (SPEC §9 test cases 13,
        16) need the actual thread/lock machinery this class provides.
        """
        self._pending_model = model
        self._trigger.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            triggered = self._trigger.wait(timeout=_TRIGGER_POLL_TIMEOUT_SECONDS)
            if self._stop.is_set():
                break
            if not triggered:
                continue
            self._trigger.clear()
            model = self._pending_model
            self._pending_model = None
            self._pass_in_progress = True
            try:
                run = self.worker.run_pass_once(model=model, trigger="manual")
                if run is not None:
                    self._last_run_id = run.id
                self._last_error = None
            except Exception as exc:
                # A pass is allowed to raise (UnknownModelError,
                # DailyBudgetExhaustedError, ...) -- see run_pass_once's
                # docstring. It must never take this background thread down
                # with it; the next trigger should still get a fresh
                # attempt.
                logger.exception("Agent pass failed")
                self._last_error = f"{type(exc).__name__}: {exc}"
            finally:
                self._pass_in_progress = False

    def status(self) -> dict:
        """Snapshot for the status endpoint. A11 (not built yet) composes
        the full `GET /agent/status` payload (SPEC §8) on top of this plus
        `AgentRunRepository.get_current()`/`get_last_completed_or_failed()`/
        `sum_cost_today_ore()` -- this just exposes what only `AgentRunner`
        itself knows: whether it's enabled/running and what its last
        in-thread pass attempt did.
        """
        return {
            "enabled": settings.agent_runtime_enabled,
            "running": self.running,
            "pass_in_progress": self._pass_in_progress,
            "last_run_id": self._last_run_id,
            "last_error": self._last_error,
        }


_worker = AgentWorker()
_runner = AgentRunner(_worker)


def get_worker() -> AgentWorker:
    """Return the process-wide `AgentWorker`."""
    return _worker


def get_runner() -> AgentRunner:
    """Return the process-wide `AgentRunner`."""
    return _runner


def start_agent_runtime() -> bool:
    """Start the agent runtime's background thread if enabled. Safe to call
    when it is not (mirrors `dropzone.start_background_scanner`)."""
    return _runner.start()


def stop_agent_runtime() -> None:
    _runner.stop()


def agent_runtime_status() -> dict:
    """Status of the agent runtime, for the status endpoint (A11)."""
    return _runner.status()
