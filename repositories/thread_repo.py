"""Repository for threads and their posts (migration 025, SPEC-tradar.md §4).

All SQL for `threads` / `thread_posts` lives here — see AGENTS.md's layering
rule. Same `@staticmethod` form as `repositories/agent_run_repo.py`, which
this file deliberately mirrors: the two tables are read by the same layer,
for the same endpoint, and a second shape would be one more thing to hold in
your head while following a post from `agent_run_events` to the client.

Nothing here updates or deletes a post. A correction is a new post
(SPEC §8.4), exactly as a correction in the ledger is a new voucher.
"""

import json
import uuid
from datetime import datetime
from typing import Any, List, Optional

from db.database import db
from domain.models import Thread, ThreadPost

#: The eight post types `datakontrakt.md` §1 lists, in the order it lists
#: them. Mirrors the `CHECK` constraint in migration 025 — the schema is the
#: enforcement, this tuple is what lets a caller (and test case 5) name the
#: contract without reading SQL. A ninth type is a "fråga först" (SPEC §8).
THREAD_POST_TYPES: tuple[str, ...] = (
    "agent_text",
    "user_text",
    "user_file",
    "decision",
    "options",
    "draft",
    "error",
    "receipt",
)


class ThreadRepository:
    """Manage `threads` / `thread_posts` persistence."""

    # -- threads ----------------------------------------------------------

    @staticmethod
    def get_or_create(
        view_key: str, fiscal_year_id: str, model: str, _commit: bool = True
    ) -> Thread:
        """The thread for this view and fiscal year, creating it if needed.

        `model` is only used when the row is actually created: an existing
        thread's model is the human's own choice (§12.4), and a plain lookup
        must never reset it. Changing it is `set_model`, explicitly.
        """
        existing = ThreadRepository.find(view_key, fiscal_year_id)
        if existing is not None:
            return existing

        thread_id = str(uuid.uuid4())
        now = datetime.now()
        db.execute(
            """
            INSERT INTO threads (id, view_key, fiscal_year_id, model, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (thread_id, view_key, fiscal_year_id, model, now),
        )
        if _commit:
            db.commit()
        return Thread(
            id=thread_id,
            view_key=view_key,
            fiscal_year_id=fiscal_year_id,
            model=model,
            created_at=now,
        )

    @staticmethod
    def find(view_key: str, fiscal_year_id: str) -> Optional[Thread]:
        row = db.execute(
            "SELECT * FROM threads WHERE view_key = ? AND fiscal_year_id = ? LIMIT 1",
            (view_key, fiscal_year_id),
        ).fetchone()
        return ThreadRepository._row_to_thread(row) if row else None

    @staticmethod
    def get(thread_id: str) -> Optional[Thread]:
        row = db.execute(
            "SELECT * FROM threads WHERE id = ? LIMIT 1", (thread_id,)
        ).fetchone()
        return ThreadRepository._row_to_thread(row) if row else None

    @staticmethod
    def set_model(thread_id: str, model: str, _commit: bool = True) -> Optional[Thread]:
        """Change which model this thread talks to (§12.4).

        The switch itself is not history: `agent_runs.model`/`.protocol` per
        run is what makes a change mid-thread visible afterwards, which is
        why this needs no second table and no audit row of its own.
        """
        db.execute("UPDATE threads SET model = ? WHERE id = ?", (model, thread_id))
        if _commit:
            db.commit()
        return ThreadRepository.get(thread_id)

    @staticmethod
    def list_fiscal_years(view_key: str) -> List[str]:
        """Fiscal year ids this view has a thread in, newest year first.

        The archive listing behind `GET /threads/{view_key}`'s optional
        `fiscal_year_id` (§12.3): a thread is reset at the turn of the year,
        and older years are reachable, not gone.
        """
        rows = db.execute(
            """
            SELECT t.fiscal_year_id AS fiscal_year_id
            FROM threads t
            JOIN fiscal_years fy ON fy.id = t.fiscal_year_id
            WHERE t.view_key = ?
            ORDER BY fy.start_date DESC
            """,
            (view_key,),
        ).fetchall()
        return [row["fiscal_year_id"] for row in rows]

    # -- posts ------------------------------------------------------------

    @staticmethod
    def add_post(
        thread_id: str,
        post_type: str,
        actor: str,
        body: dict,
        *,
        traces: Optional[List[dict]] = None,
        run_id: Optional[str] = None,
        _commit: bool = True,
    ) -> ThreadPost:
        """Append a post, computing the next `seq` for this thread.

        Read-then-insert, the same shape and the same premise as
        `AgentRunRepository.add_event`: one thread-local connection per
        writer, and `UNIQUE (thread_id, seq)` as a backstop that should never
        actually fire. The premise that matters here is SPEC §6.5's "en
        skrivare per `run_id`" — a thread run is its own `agent_runs` row and
        its own writer, so two runs never interleave on the same thread's
        `seq` allocation from two directions at once.

        `post_type` is not validated here: migration 025's `CHECK` is the
        enforcement (test case 5), and a second copy of the list in Python
        would be a second thing to keep in step.
        """
        next_seq_row = db.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq FROM thread_posts "
            "WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
        seq = next_seq_row["next_seq"]
        post_id = str(uuid.uuid4())
        now = datetime.now()
        db.execute(
            """
            INSERT INTO thread_posts
            (id, thread_id, seq, type, actor, created_at, body_json, traces_json, run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                post_id,
                thread_id,
                seq,
                post_type,
                actor,
                now,
                _dump(body),
                _dump(traces) if traces is not None else None,
                run_id,
            ),
        )
        if _commit:
            db.commit()
        return ThreadPost(
            id=post_id,
            thread_id=thread_id,
            seq=seq,
            type=post_type,
            actor=actor,
            body=body,
            created_at=now,
            traces=traces,
            run_id=run_id,
        )

    @staticmethod
    def list_posts(
        thread_id: str, since: Optional[int] = None, limit: Optional[int] = None
    ) -> List[ThreadPost]:
        """Posts in the order they came, oldest first (§1's endpoint contract).

        `since` is a `thread_posts.seq` cursor and is exclusive: a client
        reconnecting with the last seq it saw gets what it missed and nothing
        it already has (§6.5, test case 20).
        """
        sql = "SELECT * FROM thread_posts WHERE thread_id = ?"
        params: list[Any] = [thread_id]
        if since is not None:
            sql += " AND seq > ?"
            params.append(since)
        sql += " ORDER BY seq ASC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = db.execute(sql, tuple(params)).fetchall()
        return [ThreadRepository._row_to_post(row) for row in rows]

    @staticmethod
    def get_post(post_id: str) -> Optional[ThreadPost]:
        row = db.execute(
            "SELECT * FROM thread_posts WHERE id = ? LIMIT 1", (post_id,)
        ).fetchone()
        return ThreadRepository._row_to_post(row) if row else None

    @staticmethod
    def last_seq(thread_id: str) -> int:
        """Highest `seq` in this thread, or 0 for an empty one.

        The cursor a stream hands a fresh subscriber, so that what it later
        receives live and what it could read back through `GET /threads/...`
        meet exactly once.
        """
        row = db.execute(
            "SELECT COALESCE(MAX(seq), 0) AS last_seq FROM thread_posts "
            "WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
        return row["last_seq"]

    # -- row mapping ------------------------------------------------------

    @staticmethod
    def _row_to_thread(row) -> Thread:
        return Thread(
            id=row["id"],
            view_key=row["view_key"],
            fiscal_year_id=row["fiscal_year_id"],
            model=row["model"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_post(row) -> ThreadPost:
        return ThreadPost(
            id=row["id"],
            thread_id=row["thread_id"],
            seq=row["seq"],
            type=row["type"],
            actor=row["actor"],
            body=json.loads(row["body_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            traces=json.loads(row["traces_json"]) if row["traces_json"] else None,
            run_id=row["run_id"],
        )


def _dump(payload: Any) -> str:
    """`json.dumps` with `ensure_ascii=False` (so `ö`/`å`/`ä` stay literal,
    matching this codebase's Swedish-text convention) and `default=str` as a
    backstop for anything not natively JSON-serializable — the same helper
    shape as `services.agent_runtime._event_payload`.
    """
    return json.dumps(payload, ensure_ascii=False, default=str)
