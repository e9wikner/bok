"""Repository for agent runtime runs and their events (migration 024).

All SQL for `agent_runs` / `agent_run_events` lives here — see AGENTS.md's
layering rule. Nothing above `services/` should ever see a query.
"""

import uuid
from datetime import date, datetime, time
from typing import List, Optional

from db.database import db
from domain.models import AgentRun, AgentRunEvent

_FINISHED_STATUSES = ("completed", "failed", "abandoned")


class AgentRunRepository:
    """Manage `agent_runs` / `agent_run_events` persistence."""

    @staticmethod
    def create(
        trigger: str, model: str, protocol: str, _commit: bool = True
    ) -> AgentRun:
        run_id = str(uuid.uuid4())
        now = datetime.now()
        db.execute(
            """
            INSERT INTO agent_runs
            (id, trigger, status, started_at, model, protocol)
            VALUES (?, ?, 'running', ?, ?, ?)
            """,
            (run_id, trigger, now, model, protocol),
        )
        if _commit:
            db.commit()
        return AgentRun(
            id=run_id,
            trigger=trigger,
            status="running",
            started_at=now,
            model=model,
            protocol=protocol,
        )

    @staticmethod
    def update_status(
        run_id: str,
        status: str,
        *,
        last_error: Optional[str] = None,
        _commit: bool = True,
    ) -> Optional[AgentRun]:
        """Transition a run out of 'running'.

        A single generic method rather than `mark_completed`/`mark_failed`/
        `mark_abandoned`: the three transitions share identical SQL — guard
        on `status = 'running'`, set `finished_at`, optionally set
        `last_error` — and differ only in the target literal. The `WHERE
        status = 'running'` guard is what enforces that only
        running -> {completed, failed, abandoned} is possible; a run already
        finished cannot be re-finished.
        """
        if status not in _FINISHED_STATUSES:
            raise ValueError(f"invalid target status: {status!r}")
        now = datetime.now()
        db.execute(
            """
            UPDATE agent_runs
            SET status = ?, finished_at = ?, last_error = COALESCE(?, last_error)
            WHERE id = ? AND status = 'running'
            """,
            (status, now, last_error, run_id),
        )
        if _commit:
            db.commit()
        return AgentRunRepository.get(run_id)

    @staticmethod
    def add_usage(
        run_id: str,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cost_ore: int = 0,
        _commit: bool = True,
    ) -> Optional[AgentRun]:
        """Accumulate token/cost counters additively.

        Uses `col = col + ?` so concurrent or repeated calls within a pass
        never lose an update by reading a stale value in Python first.
        """
        db.execute(
            """
            UPDATE agent_runs
            SET input_tokens = input_tokens + ?,
                output_tokens = output_tokens + ?,
                cache_read_tokens = cache_read_tokens + ?,
                cost_ore = cost_ore + ?
            WHERE id = ?
            """,
            (input_tokens, output_tokens, cache_read_tokens, cost_ore, run_id),
        )
        if _commit:
            db.commit()
        return AgentRunRepository.get(run_id)

    @staticmethod
    def increment_items(
        run_id: str,
        *,
        seen: int = 0,
        posted: int = 0,
        abstained: int = 0,
        _commit: bool = True,
    ) -> Optional[AgentRun]:
        """Accumulate item counters additively, same reasoning as `add_usage`."""
        db.execute(
            """
            UPDATE agent_runs
            SET items_seen = items_seen + ?,
                items_posted = items_posted + ?,
                items_abstained = items_abstained + ?
            WHERE id = ?
            """,
            (seen, posted, abstained, run_id),
        )
        if _commit:
            db.commit()
        return AgentRunRepository.get(run_id)

    @staticmethod
    def add_event(
        run_id: str,
        kind: str,
        payload_json: str,
        *,
        source_id: Optional[str] = None,
        voucher_id: Optional[str] = None,
        _commit: bool = True,
    ) -> AgentRunEvent:
        """Append an event, computing the next `seq` for this run.

        Read-then-insert, not atomic INSERT...SELECT: acceptable because this
        repository is only ever driven by the single thread-local connection
        of one worker (AGENTS.md's SQLite threading model) — there is no
        second writer that could interleave between the two statements. The
        `UNIQUE (run_id, seq)` constraint stays as a backstop that should
        never actually fire.
        """
        next_seq_row = db.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq FROM agent_run_events WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        seq = next_seq_row["next_seq"]
        event_id = str(uuid.uuid4())
        now = datetime.now()
        db.execute(
            """
            INSERT INTO agent_run_events
            (id, run_id, seq, kind, source_id, voucher_id, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, run_id, seq, kind, source_id, voucher_id, payload_json, now),
        )
        if _commit:
            db.commit()
        return AgentRunEvent(
            id=event_id,
            run_id=run_id,
            seq=seq,
            kind=kind,
            payload_json=payload_json,
            created_at=now,
            source_id=source_id,
            voucher_id=voucher_id,
        )

    @staticmethod
    def find_running() -> List[AgentRun]:
        """Every run currently marked 'running'.

        Whether a given row actually still has a live thread behind it is a
        runtime concern, not a storage one: this repository has no notion of
        threads. The caller (A10's worker startup) is expected to intersect
        this list with its own record of live threads and call
        `update_status(..., 'abandoned')` on whatever is left over.
        """
        rows = db.execute(
            "SELECT * FROM agent_runs WHERE status = 'running' ORDER BY started_at ASC"
        ).fetchall()
        return [AgentRunRepository._row_to_run(row) for row in rows]

    @staticmethod
    def get(run_id: str) -> Optional[AgentRun]:
        row = db.execute(
            "SELECT * FROM agent_runs WHERE id = ? LIMIT 1", (run_id,)
        ).fetchone()
        return AgentRunRepository._row_to_run(row) if row else None

    @staticmethod
    def get_current() -> Optional[AgentRun]:
        """Most recent run with `status = 'running'`, or None."""
        row = db.execute("""
            SELECT * FROM agent_runs
            WHERE status = 'running'
            ORDER BY started_at DESC
            LIMIT 1
            """).fetchone()
        return AgentRunRepository._row_to_run(row) if row else None

    @staticmethod
    def get_last_completed_or_failed() -> Optional[AgentRun]:
        """Most recent finished run, for the status endpoint's `last_run`."""
        row = db.execute("""
            SELECT * FROM agent_runs
            WHERE status IN ('completed', 'failed')
            ORDER BY started_at DESC
            LIMIT 1
            """).fetchone()
        return AgentRunRepository._row_to_run(row) if row else None

    @staticmethod
    def sum_cost_today_ore() -> int:
        """Sum `cost_ore` across all runs started since local midnight.

        No existing repository in this codebase does `date('now')`-style
        SQLite date filtering for a "today" window, so this uses a
        Python-computed midnight boundary compared against `started_at`,
        matching how `datetime.now()` is passed as a parameter elsewhere in
        this file rather than relying on SQLite date functions.
        """
        midnight = datetime.combine(date.today(), time.min)
        row = db.execute(
            "SELECT COALESCE(SUM(cost_ore), 0) AS total FROM agent_runs WHERE started_at >= ?",
            (midnight,),
        ).fetchone()
        return row["total"]

    @staticmethod
    def list_events(
        run_id: str, since_seq: Optional[int] = None
    ) -> List[AgentRunEvent]:
        """Events for one run, oldest first.

        `since_seq` is exclusive: it returns only what came after that
        marker. `agent_run_events.seq` is the cursor form `tradar` follows
        (SPEC-tradar.md §2) -- a caller that has already seen up to `n` asks
        for `since_seq=n` and gets what it missed, nothing it already has.
        Omitting it returns the whole run, exactly as before.
        """
        sql = "SELECT * FROM agent_run_events WHERE run_id = ?"
        params: tuple = (run_id,)
        if since_seq is not None:
            sql += " AND seq > ?"
            params = (run_id, since_seq)
        sql += " ORDER BY seq ASC"
        rows = db.execute(sql, params).fetchall()
        return [AgentRunRepository._row_to_event(row) for row in rows]

    @staticmethod
    def _row_to_run(row) -> AgentRun:
        return AgentRun(
            id=row["id"],
            trigger=row["trigger"],
            status=row["status"],
            started_at=datetime.fromisoformat(row["started_at"]),
            model=row["model"],
            protocol=row["protocol"],
            finished_at=(
                datetime.fromisoformat(row["finished_at"])
                if row["finished_at"]
                else None
            ),
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            cache_read_tokens=row["cache_read_tokens"],
            cost_ore=row["cost_ore"],
            items_seen=row["items_seen"],
            items_posted=row["items_posted"],
            items_abstained=row["items_abstained"],
            last_error=row["last_error"],
        )

    @staticmethod
    def _row_to_event(row) -> AgentRunEvent:
        return AgentRunEvent(
            id=row["id"],
            run_id=row["run_id"],
            seq=row["seq"],
            kind=row["kind"],
            payload_json=row["payload_json"],
            created_at=datetime.fromisoformat(row["created_at"]),
            source_id=row["source_id"],
            voucher_id=row["voucher_id"],
        )
