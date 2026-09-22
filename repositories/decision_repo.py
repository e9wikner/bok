"""Repository for decisions and their options (migration 026, SPEC-beslut.md §4).

All SQL for `decisions` / `decision_options` lives here — see AGENTS.md's
layering rule. Same `@staticmethod` form as `repositories/thread_repo.py`,
which this file deliberately mirrors: `_commit: bool = True` on every
writing method, so a service can fold several writes into one transaction
(`DecisionService.answer`, B3, needs exactly that for §6.2 steps 4-5).

Nothing here rewrites the agent's own text (`reason`, `consequence`,
`rationale`) — it is stored and returned verbatim, the same stance
`thread_repo.py` takes on a post's body.
"""

import uuid
from datetime import date, datetime
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Union

from db.database import db
from domain.models import Decision, DecisionOption


class DecisionRepository:
    """Manage `decisions` / `decision_options` persistence."""

    # -- decisions ----------------------------------------------------------

    @staticmethod
    def create(
        *,
        thread_id: str,
        post_id: str,
        view_key: str,
        kind: str,
        title: str,
        reason: str,
        consequence: str,
        amount_ore: Optional[int] = None,
        source_kind: Optional[str] = None,
        source_id: Optional[str] = None,
        source_date: Optional[date] = None,
        _commit: bool = True,
    ) -> Decision:
        """Insert one `decisions` row, `status='open'` by the column default.

        `id`/`created_at` are generated here, the same shape as
        `ThreadRepository.add_post` — a caller never invents either.
        """
        decision_id = str(uuid.uuid4())
        now = datetime.now()
        db.execute(
            """
            INSERT INTO decisions
            (id, thread_id, post_id, view_key, kind, title, reason,
             consequence, amount_ore, source_kind, source_id, source_date,
             created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_id,
                thread_id,
                post_id,
                view_key,
                kind,
                title,
                reason,
                consequence,
                amount_ore,
                source_kind,
                source_id,
                source_date,
                now,
            ),
        )
        if _commit:
            db.commit()
        return Decision(
            id=decision_id,
            thread_id=thread_id,
            post_id=post_id,
            view_key=view_key,
            kind=kind,
            status="open",
            title=title,
            reason=reason,
            consequence=consequence,
            amount_ore=amount_ore,
            source_kind=source_kind,
            source_id=source_id,
            source_date=source_date,
            created_at=now,
            options=[],
        )

    @staticmethod
    def add_options(
        decision_id: str,
        options: Iterable[Union[DecisionOption, Mapping[str, Any]]],
        _commit: bool = True,
    ) -> List[DecisionOption]:
        """Write `options` as `decision_options` rows, `position` 1..n in
        the order they arrived — the order is part of the contract (§4),
        since the last option is always a way out (§6.3).

        Each item is either a `DecisionOption`-like object (attribute
        access) or a mapping with the same keys: `title`, `rationale`,
        `account`, `amount_ore`, `recommended`, `is_exit`.
        """
        created: List[DecisionOption] = []
        for position, item in enumerate(options, start=1):
            option_id = str(uuid.uuid4())
            title = _field(item, "title")
            rationale = _field(item, "rationale")
            account = _field(item, "account", default=None)
            amount_ore = _field(item, "amount_ore", default=None)
            recommended = bool(_field(item, "recommended", default=False))
            is_exit = bool(_field(item, "is_exit", default=False))
            db.execute(
                """
                INSERT INTO decision_options
                (id, decision_id, position, title, account, amount_ore,
                 rationale, recommended, is_exit)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    option_id,
                    decision_id,
                    position,
                    title,
                    account,
                    amount_ore,
                    rationale,
                    int(recommended),
                    int(is_exit),
                ),
            )
            created.append(
                DecisionOption(
                    id=option_id,
                    decision_id=decision_id,
                    position=position,
                    title=title,
                    rationale=rationale,
                    account=account,
                    amount_ore=amount_ore,
                    recommended=recommended,
                    is_exit=is_exit,
                )
            )
        if _commit:
            db.commit()
        return created

    @staticmethod
    def get(decision_id: str) -> Optional[Decision]:
        row = db.execute(
            "SELECT * FROM decisions WHERE id = ? LIMIT 1", (decision_id,)
        ).fetchone()
        if row is None:
            return None
        decision = DecisionRepository._row_to_decision(row)
        decision.options = DecisionRepository.list_options(decision_id)
        return decision

    @staticmethod
    def get_by_post_id(post_id: str) -> Optional[Decision]:
        row = db.execute(
            "SELECT * FROM decisions WHERE post_id = ? LIMIT 1", (post_id,)
        ).fetchone()
        if row is None:
            return None
        decision = DecisionRepository._row_to_decision(row)
        decision.options = DecisionRepository.list_options(decision.id)
        return decision

    @staticmethod
    def list_decisions(
        *,
        status: Optional[Union[str, Sequence[str]]] = None,
        view_key: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Decision]:
        """Decisions oldest first (`created_at ASC`, `id ASC` as a stable
        tie-breaker) — SPEC §6.1: "Äldst först."

        `status` is `None` (all statuses), a single status, or a sequence of
        them. `options` is filled in with a single second `SELECT ...
        WHERE decision_id IN (...)`, grouped in Python, rather than one
        query per decision — an N+1 here would turn a list endpoint into a
        waterfall (§6.1's own reason for shipping `options` inline).
        """
        sql = "SELECT * FROM decisions"
        clauses = []
        params: List[Any] = []

        status_values = _as_sequence(status)
        if status_values is not None:
            placeholders = ", ".join("?" for _ in status_values)
            clauses.append(f"status IN ({placeholders})")
            params.extend(status_values)
        if view_key is not None:
            clauses.append("view_key = ?")
            params.append(view_key)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at ASC, id ASC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
            if offset is not None:
                sql += " OFFSET ?"
                params.append(offset)
        elif offset is not None:
            # SQLite requires a LIMIT before OFFSET; -1 means "no limit".
            sql += " LIMIT -1 OFFSET ?"
            params.append(offset)

        rows = db.execute(sql, tuple(params)).fetchall()
        decisions = [DecisionRepository._row_to_decision(row) for row in rows]
        DecisionRepository._attach_options(decisions)
        return decisions

    @staticmethod
    def count(
        *,
        status: Optional[Union[str, Sequence[str]]] = None,
        view_key: Optional[str] = None,
    ) -> int:
        sql = "SELECT COUNT(*) AS n FROM decisions"
        clauses = []
        params: List[Any] = []

        status_values = _as_sequence(status)
        if status_values is not None:
            placeholders = ", ".join("?" for _ in status_values)
            clauses.append(f"status IN ({placeholders})")
            params.extend(status_values)
        if view_key is not None:
            clauses.append("view_key = ?")
            params.append(view_key)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)

        row = db.execute(sql, tuple(params)).fetchone()
        return row["n"]

    @staticmethod
    def count_open() -> int:
        """`status = 'open'` in this table alone. `DecisionService` (B9)
        is where the union with the two synthetic sources happens — this
        is just the table's own count."""
        return DecisionRepository.count(status="open")

    @staticmethod
    def set_answer(
        decision_id: str,
        *,
        answered_at: datetime,
        answered_by: str,
        answer_post_id: str,
        option_id: Optional[str] = None,
        answer_text: Optional[str] = None,
        _commit: bool = True,
    ) -> Optional[Decision]:
        """`status='open' -> 'answered'` plus the five answer columns, in
        one `UPDATE` — the schema's own `CHECK` (migration 026) rejects a
        half-answer, and one statement is what makes that guarantee hold
        even under a concurrent reader.
        """
        db.execute(
            """
            UPDATE decisions
            SET status = 'answered',
                answered_at = ?,
                answered_by = ?,
                answer_option_id = ?,
                answer_text = ?,
                answer_post_id = ?
            WHERE id = ?
            """,
            (
                answered_at,
                answered_by,
                option_id,
                answer_text,
                answer_post_id,
                decision_id,
            ),
        )
        if _commit:
            db.commit()
        return DecisionRepository.get(decision_id)

    @staticmethod
    def set_status(
        decision_id: str, status: str, _commit: bool = True
    ) -> Optional[Decision]:
        """Used for `superseded` (§4): the decision leaves the queue, the
        post stays in the thread untouched."""
        db.execute(
            "UPDATE decisions SET status = ? WHERE id = ?", (status, decision_id)
        )
        if _commit:
            db.commit()
        return DecisionRepository.get(decision_id)

    @staticmethod
    def set_reminded(
        decision_id: str, reminded_at: datetime, _commit: bool = True
    ) -> None:
        db.execute(
            "UPDATE decisions SET reminded_at = ? WHERE id = ?",
            (reminded_at, decision_id),
        )
        if _commit:
            db.commit()

    @staticmethod
    def list_due_reminders(
        *, before: datetime, limit: Optional[int] = None
    ) -> List[Decision]:
        """Open decisions never reminded, created at or before `before` —
        the caller (`DecisionService`, B10) passes `today - 7 days`. Oldest
        first, same ordering as `list_decisions`.
        """
        sql = (
            "SELECT * FROM decisions WHERE status = 'open' "
            "AND reminded_at IS NULL AND created_at <= ? "
            "ORDER BY created_at ASC, id ASC"
        )
        params: List[Any] = [before]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = db.execute(sql, tuple(params)).fetchall()
        decisions = [DecisionRepository._row_to_decision(row) for row in rows]
        DecisionRepository._attach_options(decisions)
        return decisions

    # -- options --------------------------------------------------------

    @staticmethod
    def get_option(option_id: str) -> Optional[DecisionOption]:
        row = db.execute(
            "SELECT * FROM decision_options WHERE id = ? LIMIT 1", (option_id,)
        ).fetchone()
        return DecisionRepository._row_to_option(row) if row else None

    @staticmethod
    def list_options(decision_id: str) -> List[DecisionOption]:
        rows = db.execute(
            "SELECT * FROM decision_options WHERE decision_id = ? "
            "ORDER BY position ASC",
            (decision_id,),
        ).fetchall()
        return [DecisionRepository._row_to_option(row) for row in rows]

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _attach_options(decisions: List[Decision]) -> None:
        """Fill in `.options` for a batch of decisions with one `SELECT ...
        WHERE decision_id IN (...)` instead of one query per decision —
        avoids the N+1 that would otherwise turn `list_decisions` into a
        waterfall of round-trips.
        """
        if not decisions:
            return
        ids = [d.id for d in decisions]
        placeholders = ", ".join("?" for _ in ids)
        rows = db.execute(
            f"SELECT * FROM decision_options WHERE decision_id IN ({placeholders}) "
            "ORDER BY decision_id ASC, position ASC",
            tuple(ids),
        ).fetchall()
        by_decision: dict[str, List[DecisionOption]] = {}
        for row in rows:
            option = DecisionRepository._row_to_option(row)
            by_decision.setdefault(option.decision_id, []).append(option)
        for decision in decisions:
            decision.options = by_decision.get(decision.id, [])

    # -- row mapping ------------------------------------------------------

    @staticmethod
    def _row_to_decision(row) -> Decision:
        return Decision(
            id=row["id"],
            thread_id=row["thread_id"],
            post_id=row["post_id"],
            view_key=row["view_key"],
            kind=row["kind"],
            status=row["status"],
            title=row["title"],
            reason=row["reason"],
            consequence=row["consequence"],
            amount_ore=row["amount_ore"],
            source_kind=row["source_kind"],
            source_id=row["source_id"],
            source_date=(
                date.fromisoformat(row["source_date"]) if row["source_date"] else None
            ),
            created_at=_parse_required_datetime(row["created_at"]),
            answered_at=_parse_datetime(row["answered_at"]),
            answered_by=row["answered_by"],
            answer_option_id=row["answer_option_id"],
            answer_text=row["answer_text"],
            answer_post_id=row["answer_post_id"],
            reminded_at=_parse_datetime(row["reminded_at"]),
            options=[],
        )

    @staticmethod
    def _row_to_option(row) -> DecisionOption:
        return DecisionOption(
            id=row["id"],
            decision_id=row["decision_id"],
            position=row["position"],
            title=row["title"],
            rationale=row["rationale"],
            account=row["account"],
            amount_ore=row["amount_ore"],
            recommended=bool(row["recommended"]),
            is_exit=bool(row["is_exit"]),
        )


def _field(
    item: Union[DecisionOption, Mapping[str, Any]], name: str, *, default: Any = None
) -> Any:
    """Read `name` off either a mapping or an attribute-bearing object
    (`DecisionOption` or anything shaped like it), so `add_options` accepts
    both dicts and dataclass-like values without a second code path."""
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


def _as_sequence(
    status: Optional[Union[str, Sequence[str]]],
) -> Optional[Sequence[str]]:
    """`status=None` means "all statuses" (no filter); a bare string is one
    status; anything else is taken as already a sequence of them."""
    if status is None:
        return None
    if isinstance(status, str):
        return (status,)
    return status


def _parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _parse_required_datetime(value: Any) -> datetime:
    """`created_at` is `NOT NULL` in the schema — a thin, non-`Optional`
    wrapper so `_row_to_decision` doesn't need to narrow `_parse_datetime`'s
    `Optional[datetime]` back down at every call site."""
    parsed = _parse_datetime(value)
    assert parsed is not None
    return parsed
