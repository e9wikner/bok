"""Repository for intake source material and voucher traceability."""

import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Sequence

from db.database import db
from domain.models import IntakeProcessingAttempt, IntakeSource, VoucherIntakeSource
from domain.types import IntakeSourceType, IntakeStatus
from repositories.fiscal_year_proposal_repo import NOT_WAITING_FOR_FISCAL_YEAR_SQL

# SPEC-flode-underlag.md §11.3 (D4): a file dropped in a thread is the
# thread's -- the turn reads and interprets it, and the human decides there.
# The intake pass must not abstain from it mid-conversation, so the pass's
# queue (`list_pending`/`count_pending`, and through them `las_underlag`,
# `GET /agent/intake/pending` and `queue_depth`) leaves out every source a
# `user_file` post names. A correlated `NOT EXISTS`, one statement.
_NOT_IN_A_THREAD_SQL = (
    "NOT EXISTS (SELECT 1 FROM thread_posts tp WHERE tp.type = 'user_file'"
    " AND json_extract(tp.body_json, '$.intake_source_id') = intake_sources.id)"
)

# Migration 041: a source waiting on a pending fiscal-year proposal is out of
# the pass's queue until the human has answered the card -- otherwise the pass
# would read it again, and pay for it, every pass. Created, it is back in.
_PASS_QUEUE_SQL = f"{_NOT_IN_A_THREAD_SQL} AND {NOT_WAITING_FOR_FISCAL_YEAR_SQL}"


class IntakeRepository:
    """Manage uploaded voucher source material and processing history."""

    @staticmethod
    def create_source(
        source_id: str,
        original_filename: str,
        mime_type: str,
        size_bytes: int,
        sha256: str,
        stored_path: str,
        uploaded_by: str,
        source_type: Optional[str] = None,
        explanation: Optional[str] = None,
        agent_guidance: Optional[str] = None,
        status: str = IntakeStatus.PENDING.value,
        _commit: bool = True,
    ) -> IntakeSource:
        now = datetime.now()
        db.execute(
            """
            INSERT INTO intake_sources
            (id, source_type, status, original_filename, mime_type, size_bytes,
             sha256, stored_path, explanation, agent_guidance, uploaded_by, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                source_type,
                status,
                original_filename,
                mime_type,
                size_bytes,
                sha256,
                stored_path,
                explanation,
                agent_guidance,
                uploaded_by,
                now,
            ),
        )
        if _commit:
            db.commit()

        return IntakeSource(
            id=source_id,
            source_type=IntakeSourceType(source_type) if source_type else None,
            status=IntakeStatus(status),
            original_filename=original_filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            sha256=sha256,
            stored_path=stored_path,
            explanation=explanation,
            agent_guidance=agent_guidance,
            uploaded_by=uploaded_by,
            uploaded_at=now,
        )

    @staticmethod
    def get_source(source_id: str) -> Optional[IntakeSource]:
        row = db.execute(
            "SELECT * FROM intake_sources WHERE id = ? LIMIT 1",
            (source_id,),
        ).fetchone()
        return IntakeRepository._row_to_source(row) if row else None

    @staticmethod
    def get_by_sha256(sha256: str) -> Optional[IntakeSource]:
        row = db.execute(
            "SELECT * FROM intake_sources WHERE sha256 = ? AND status != ? LIMIT 1",
            (sha256, IntakeStatus.DELETED.value),
        ).fetchone()
        return IntakeRepository._row_to_source(row) if row else None

    @staticmethod
    def list_pending(limit: int = 100, offset: int = 0) -> List[IntakeSource]:
        """The intake pass's queue: `pending`, without the sources a thread
        owns (`_NOT_IN_A_THREAD_SQL`) or that wait on a fiscal-year proposal.
        The intake page reads `list_by_status`, which still shows them."""
        rows = db.execute(
            f"""
            SELECT * FROM intake_sources
            WHERE status = ? AND {_PASS_QUEUE_SQL}
            ORDER BY uploaded_at ASC
            LIMIT ? OFFSET ?
            """,
            (IntakeStatus.PENDING.value, limit, offset),
        ).fetchall()
        return [IntakeRepository._row_to_source(row) for row in rows]

    @staticmethod
    def list_by_status(
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[IntakeSource]:
        if status:
            rows = db.execute(
                """
                SELECT * FROM intake_sources
                WHERE status = ?
                ORDER BY uploaded_at ASC
                LIMIT ? OFFSET ?
                """,
                (status, limit, offset),
            ).fetchall()
        else:
            rows = db.execute(
                """
                SELECT * FROM intake_sources
                WHERE status != ?
                ORDER BY uploaded_at ASC
                LIMIT ? OFFSET ?
                """,
                (IntakeStatus.DELETED.value, limit, offset),
            ).fetchall()
        return [IntakeRepository._row_to_source(row) for row in rows]

    @staticmethod
    def list_by_statuses(statuses: Sequence[str]) -> List[IntakeSource]:
        """Every source whose status is in `statuses`, oldest `uploaded_at`
        first with `id` as a stable tie-breaker -- added for
        `DecisionService.list_decisions` (SPEC-beslut.md §5, §6.1, B7),
        which unions `intake_sources` (`failed`/`needs_attention`) with two
        other sources and sorts and paginates the merged, sorted result
        itself. Unlike `list_by_status`, this takes several statuses at
        once (so the two `intake` statuses are one query, not two) and is
        deliberately unbounded -- `limit`/`offset` apply to the union in
        the caller, not to any one source (§11.2's "priset" for choosing a
        union: every matching row is fetched on every call).
        """
        if not statuses:
            return []
        placeholders = ", ".join("?" for _ in statuses)
        rows = db.execute(
            f"""
            SELECT * FROM intake_sources
            WHERE status IN ({placeholders})
            ORDER BY uploaded_at ASC, id ASC
            """,
            tuple(statuses),
        ).fetchall()
        return [IntakeRepository._row_to_source(row) for row in rows]

    @staticmethod
    def list_by_status_and_uploaded_by(
        status: str, uploaded_by: str, limit: int = 500, offset: int = 0
    ) -> List[IntakeSource]:
        rows = db.execute(
            """
            SELECT * FROM intake_sources
            WHERE status = ? AND uploaded_by = ?
            ORDER BY uploaded_at ASC
            LIMIT ? OFFSET ?
            """,
            (status, uploaded_by, limit, offset),
        ).fetchall()
        return [IntakeRepository._row_to_source(row) for row in rows]

    @staticmethod
    def list_latest_attempts(
        source_ids: Sequence[str],
    ) -> Dict[str, IntakeProcessingAttempt]:
        """The most recent `intake_processing_attempts` row per source id,
        in one query -- added for `DecisionService.list_decisions` /
        `.get_decision` (SPEC-beslut.md §5): an `intake` row's `reason` is
        "agentens egen text ur senaste `intake_processing_attempts.summary`
        / `.error_detail`", and finding "latest" with one call to
        `list_attempts_for_source` per source would turn a list endpoint
        into a waterfall the same way an N+1 on `decision_options` would
        (see `DecisionRepository._attach_options`'s docstring, which this
        mirrors for attempts instead of options).

        `ROW_NUMBER()` (SQLite 3.25+; this project runs 3.53) numbers each
        source's attempts newest-first and keeps only the top one --
        a `GROUP BY intake_source_id` on `MAX(created_at)` would return two
        rows for a source whose two attempts happen to share a timestamp,
        which `datetime.now()` resolution does not rule out.
        """
        if not source_ids:
            return {}
        placeholders = ", ".join("?" for _ in source_ids)
        rows = db.execute(
            f"""
            SELECT * FROM (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY intake_source_id
                    ORDER BY created_at DESC, id DESC
                ) AS rn
                FROM intake_processing_attempts
                WHERE intake_source_id IN ({placeholders})
            )
            WHERE rn = 1
            """,
            tuple(source_ids),
        ).fetchall()
        return {
            row["intake_source_id"]: IntakeRepository._row_to_attempt(row)
            for row in rows
        }

    @staticmethod
    def count_by_status(status: str | None = None) -> int:
        if status:
            row = db.execute(
                "SELECT COUNT(*) AS count FROM intake_sources WHERE status = ?",
                (status,),
            ).fetchone()
        else:
            row = db.execute(
                "SELECT COUNT(*) AS count FROM intake_sources WHERE status != ?",
                (IntakeStatus.DELETED.value,),
            ).fetchone()
        return row["count"] if row else 0

    @staticmethod
    def is_in_a_thread(source_id: str) -> bool:
        """Whether a `user_file` post names the source (`_NOT_IN_A_THREAD_SQL`
        negated): a thread owns it, not the intake pass."""
        row = db.execute(
            f"SELECT 1 FROM intake_sources WHERE id = ? AND NOT {_NOT_IN_A_THREAD_SQL}",
            (source_id,),
        ).fetchone()
        return row is not None

    @staticmethod
    def count_pending() -> int:
        """`list_pending`'s count, with the same filter."""
        row = db.execute(
            "SELECT COUNT(*) AS count FROM intake_sources "
            f"WHERE status = ? AND {_PASS_QUEUE_SQL}",
            (IntakeStatus.PENDING.value,),
        ).fetchone()
        return row["count"] if row else 0

    @staticmethod
    def update_agent_guidance(
        source_id: str,
        agent_guidance: Optional[str],
        _commit: bool = True,
    ) -> None:
        db.execute(
            "UPDATE intake_sources SET agent_guidance = ? WHERE id = ?",
            (agent_guidance, source_id),
        )
        if _commit:
            db.commit()

    @staticmethod
    def update_status(
        source_id: str,
        status: str,
        actor: Optional[str] = None,
        _commit: bool = True,
    ) -> None:
        if status == IntakeStatus.DELETED.value:
            db.execute(
                """
                UPDATE intake_sources
                SET status = ?, deleted_at = ?, deleted_by = ?
                WHERE id = ?
                """,
                (status, datetime.now(), actor, source_id),
            )
        else:
            db.execute(
                "UPDATE intake_sources SET status = ? WHERE id = ?",
                (status, source_id),
            )
        if _commit:
            db.commit()

    @staticmethod
    def record_attempt(
        intake_source_id: str,
        status: str,
        summary: str,
        actor: str,
        warnings: Optional[list[str]] = None,
        error_detail: Optional[str] = None,
        voucher_id: Optional[str] = None,
        _commit: bool = True,
    ) -> IntakeProcessingAttempt:
        attempt_id = str(uuid.uuid4())
        now = datetime.now()
        warnings_json = json.dumps(warnings) if warnings else None
        db.execute(
            """
            INSERT INTO intake_processing_attempts
            (id, intake_source_id, status, summary, warnings, error_detail,
             voucher_id, actor, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attempt_id,
                intake_source_id,
                status,
                summary,
                warnings_json,
                error_detail,
                voucher_id,
                actor,
                now,
            ),
        )
        if _commit:
            db.commit()

        return IntakeProcessingAttempt(
            id=attempt_id,
            intake_source_id=intake_source_id,
            status=IntakeStatus(status),
            summary=summary,
            warnings=warnings,
            error_detail=error_detail,
            voucher_id=voucher_id,
            actor=actor,
            created_at=now,
        )

    @staticmethod
    def create_voucher_link(
        intake_source_id: str,
        voucher_id: str,
        linked_by: str,
        link_reason: Optional[str] = None,
        _commit: bool = True,
    ) -> VoucherIntakeSource:
        link_id = str(uuid.uuid4())
        now = datetime.now()
        db.execute(
            """
            INSERT INTO voucher_intake_sources
            (id, voucher_id, intake_source_id, linked_by, linked_at, link_reason)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (link_id, voucher_id, intake_source_id, linked_by, now, link_reason),
        )
        if _commit:
            db.commit()

        return VoucherIntakeSource(
            id=link_id,
            voucher_id=voucher_id,
            intake_source_id=intake_source_id,
            linked_by=linked_by,
            linked_at=now,
            link_reason=link_reason,
        )

    # A link is *current* while it has no row in `voucher_intake_unlinks`
    # (migration 035). Every read below says which it returns: the current
    # link, or the history with the undone ones marked.
    _LINK_SELECT = """
        SELECT vis.*, u.created_at AS unlinked_at, u.actor AS unlinked_by,
               u.reason AS unlink_reason
        FROM voucher_intake_sources vis
        LEFT JOIN voucher_intake_unlinks u ON u.link_id = vis.id
    """

    @staticmethod
    def get_link_by_source_id(source_id: str) -> Optional[VoucherIntakeSource]:
        """The source's current link, or `None` -- never an undone one."""
        row = db.execute(
            IntakeRepository._LINK_SELECT
            + " WHERE vis.intake_source_id = ? AND u.link_id IS NULL LIMIT 1",
            (source_id,),
        ).fetchone()
        return IntakeRepository._row_to_link(row) if row else None

    @staticmethod
    def list_links_for_voucher(voucher_id: str) -> List[VoucherIntakeSource]:
        """The voucher's current links: the underlag it has now."""
        rows = db.execute(
            IntakeRepository._LINK_SELECT
            + " WHERE vis.voucher_id = ? AND u.link_id IS NULL"
            " ORDER BY vis.linked_at ASC, vis.rowid ASC",
            (voucher_id,),
        ).fetchall()
        return [IntakeRepository._row_to_link(row) for row in rows]

    @staticmethod
    def list_unlinked_for_voucher(voucher_id: str) -> List[VoucherIntakeSource]:
        """The voucher's undone links, oldest first: the trace a replaced
        underlag leaves (underlag-ersatt)."""
        rows = db.execute(
            IntakeRepository._LINK_SELECT
            + " WHERE vis.voucher_id = ? AND u.link_id IS NOT NULL"
            " ORDER BY vis.linked_at ASC, vis.rowid ASC",
            (voucher_id,),
        ).fetchall()
        return [IntakeRepository._row_to_link(row) for row in rows]

    @staticmethod
    def list_links_for_source(
        source_id: str, *, include_unlinked: bool = False
    ) -> List[VoucherIntakeSource]:
        """The source's current link as a list (at most one), or its whole
        history with *include_unlinked*, oldest first."""
        where = " WHERE vis.intake_source_id = ?"
        if not include_unlinked:
            where += " AND u.link_id IS NULL"
        rows = db.execute(
            IntakeRepository._LINK_SELECT
            + where
            + " ORDER BY vis.linked_at ASC, vis.rowid ASC",
            (source_id,),
        ).fetchall()
        return [IntakeRepository._row_to_link(row) for row in rows]

    @staticmethod
    def latest_link(source_id: str, voucher_id: str) -> Optional[VoucherIntakeSource]:
        """The latest link between the two, current or undone."""
        row = db.execute(
            IntakeRepository._LINK_SELECT
            + " WHERE vis.intake_source_id = ? AND vis.voucher_id = ?"
            " ORDER BY vis.linked_at DESC, vis.rowid DESC LIMIT 1",
            (source_id, voucher_id),
        ).fetchone()
        return IntakeRepository._row_to_link(row) if row else None

    @staticmethod
    def was_unlinked_from(source_id: str, voucher_id: str) -> bool:
        """Whether a link between the two has ever been undone."""
        row = db.execute(
            "SELECT 1 FROM voucher_intake_unlinks"
            " WHERE intake_source_id = ? AND voucher_id = ? LIMIT 1",
            (source_id, voucher_id),
        ).fetchone()
        return row is not None

    @staticmethod
    def list_attempts_for_source(source_id: str) -> List[IntakeProcessingAttempt]:
        rows = db.execute(
            """
            SELECT * FROM intake_processing_attempts
            WHERE intake_source_id = ?
            ORDER BY created_at ASC
            """,
            (source_id,),
        ).fetchall()
        return [IntakeRepository._row_to_attempt(row) for row in rows]

    @staticmethod
    def _row_to_source(row) -> IntakeSource:
        source_type = row["source_type"]
        deleted_at = row["deleted_at"]
        return IntakeSource(
            id=row["id"],
            source_type=IntakeSourceType(source_type) if source_type else None,
            status=IntakeStatus(row["status"]),
            original_filename=row["original_filename"],
            mime_type=row["mime_type"],
            size_bytes=row["size_bytes"],
            sha256=row["sha256"],
            stored_path=row["stored_path"],
            explanation=row["explanation"],
            agent_guidance=row["agent_guidance"],
            uploaded_by=row["uploaded_by"],
            uploaded_at=datetime.fromisoformat(row["uploaded_at"]),
            deleted_at=datetime.fromisoformat(deleted_at) if deleted_at else None,
            deleted_by=row["deleted_by"],
        )

    @staticmethod
    def _row_to_attempt(row) -> IntakeProcessingAttempt:
        warnings = None
        if row["warnings"]:
            try:
                warnings = json.loads(row["warnings"])
            except json.JSONDecodeError:
                warnings = None

        return IntakeProcessingAttempt(
            id=row["id"],
            intake_source_id=row["intake_source_id"],
            status=IntakeStatus(row["status"]),
            summary=row["summary"],
            warnings=warnings,
            error_detail=row["error_detail"],
            voucher_id=row["voucher_id"],
            actor=row["actor"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_link(row) -> VoucherIntakeSource:
        return VoucherIntakeSource(
            id=row["id"],
            voucher_id=row["voucher_id"],
            intake_source_id=row["intake_source_id"],
            linked_by=row["linked_by"],
            linked_at=_as_datetime(row["linked_at"]),
            link_reason=row["link_reason"],
            unlinked_at=(
                _as_datetime(row["unlinked_at"])
                if "unlinked_at" in row.keys() and row["unlinked_at"]
                else None
            ),
            unlinked_by=row["unlinked_by"] if "unlinked_by" in row.keys() else None,
            unlink_reason=(
                row["unlink_reason"] if "unlink_reason" in row.keys() else None
            ),
        )


def _as_datetime(value) -> datetime:
    """A timestamp column as SQLite hands it back: already parsed, or text."""
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)
