"""Repository for voucher correction notes."""

import uuid
from datetime import datetime
from typing import List, Optional, Sequence

from db.database import db
from domain.models import CorrectionNote


class CorrectionNoteRepository:
    """Manage correction note persistence."""

    @staticmethod
    def create(
        voucher_id: str,
        note_text: str,
        created_by: str,
        _commit: bool = True,
    ) -> CorrectionNote:
        note_id = str(uuid.uuid4())
        now = datetime.now()
        db.execute(
            """
            INSERT INTO correction_notes
            (id, voucher_id, note_text, status, created_at, created_by, updated_at)
            VALUES (?, ?, ?, 'pending', ?, ?, ?)
            """,
            (note_id, voucher_id, note_text, now, created_by, now),
        )
        if _commit:
            db.commit()
        return CorrectionNote(
            id=note_id,
            voucher_id=voucher_id,
            note_text=note_text,
            status="pending",
            created_at=now,
            created_by=created_by,
            updated_at=now,
        )

    @staticmethod
    def get(note_id: str) -> Optional[CorrectionNote]:
        row = db.execute(
            "SELECT * FROM correction_notes WHERE id = ? LIMIT 1",
            (note_id,),
        ).fetchone()
        return CorrectionNoteRepository._row_to_note(row) if row else None

    @staticmethod
    def list_for_voucher(voucher_id: str) -> List[CorrectionNote]:
        rows = db.execute(
            """
            SELECT * FROM correction_notes
            WHERE voucher_id = ?
            ORDER BY created_at DESC
            """,
            (voucher_id,),
        ).fetchall()
        return [CorrectionNoteRepository._row_to_note(row) for row in rows]

    @staticmethod
    def get_active_for_voucher(voucher_id: str) -> Optional[CorrectionNote]:
        row = db.execute(
            """
            SELECT * FROM correction_notes
            WHERE voucher_id = ? AND status IN ('pending', 'suggested')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (voucher_id,),
        ).fetchone()
        return CorrectionNoteRepository._row_to_note(row) if row else None

    @staticmethod
    def list_pending(limit: int = 100, offset: int = 0) -> List[CorrectionNote]:
        rows = db.execute(
            """
            SELECT * FROM correction_notes
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        return [CorrectionNoteRepository._row_to_note(row) for row in rows]

    @staticmethod
    def list_by_statuses(statuses: Sequence[str]) -> List[CorrectionNote]:
        """Every note whose status is in `statuses`, oldest `created_at`
        first with `id` as a stable tie-breaker -- added for
        `DecisionService.list_decisions` (SPEC-beslut.md §5, §6.1, B7),
        which unions `correction_notes` (`pending`/`suggested`) with two
        other sources and sorts and paginates the merged result itself.
        Unlike `list_pending`, this takes several statuses in one query and
        is deliberately unbounded, for the same reason
        `IntakeRepository.list_by_statuses` is: `limit`/`offset` apply to
        the union in the caller, not to any one source.
        """
        if not statuses:
            return []
        placeholders = ", ".join("?" for _ in statuses)
        rows = db.execute(
            f"""
            SELECT * FROM correction_notes
            WHERE status IN ({placeholders})
            ORDER BY created_at ASC, id ASC
            """,
            tuple(statuses),
        ).fetchall()
        return [CorrectionNoteRepository._row_to_note(row) for row in rows]

    @staticmethod
    def count_open() -> int:
        """Notes still awaiting a decision: raised, or suggested but unapplied."""
        row = db.execute(
            "SELECT COUNT(*) AS count FROM correction_notes "
            "WHERE status IN ('pending', 'suggested')"
        ).fetchone()
        return row["count"]

    @staticmethod
    def count_pending() -> int:
        row = db.execute(
            "SELECT COUNT(*) AS count FROM correction_notes WHERE status = 'pending'"
        ).fetchone()
        return row["count"]

    @staticmethod
    def set_suggested(
        note_id: str,
        suggested_voucher_id: str,
        _commit: bool = True,
    ) -> Optional[CorrectionNote]:
        now = datetime.now()
        db.execute(
            """
            UPDATE correction_notes
            SET status = 'suggested', suggested_voucher_id = ?, updated_at = ?
            WHERE id = ? AND status = 'pending'
            """,
            (suggested_voucher_id, now, note_id),
        )
        if _commit:
            db.commit()
        return CorrectionNoteRepository.get(note_id)

    @staticmethod
    def set_applied(note_id: str, _commit: bool = True) -> Optional[CorrectionNote]:
        now = datetime.now()
        db.execute(
            """
            UPDATE correction_notes
            SET status = 'applied', updated_at = ?, resolved_at = ?
            WHERE id = ? AND status = 'suggested'
            """,
            (now, now, note_id),
        )
        if _commit:
            db.commit()
        return CorrectionNoteRepository.get(note_id)

    @staticmethod
    def set_dismissed(note_id: str, _commit: bool = True) -> Optional[CorrectionNote]:
        now = datetime.now()
        db.execute(
            """
            UPDATE correction_notes
            SET status = 'dismissed', updated_at = ?, resolved_at = ?
            WHERE id = ? AND status IN ('pending', 'suggested')
            """,
            (now, now, note_id),
        )
        if _commit:
            db.commit()
        return CorrectionNoteRepository.get(note_id)

    @staticmethod
    def set_rejected(
        note_id: str,
        rejection_reason: str,
        _commit: bool = True,
    ) -> Optional[CorrectionNote]:
        now = datetime.now()
        db.execute(
            """
            UPDATE correction_notes
            SET status = 'rejected', rejection_reason = ?, updated_at = ?, resolved_at = ?
            WHERE id = ? AND status IN ('pending', 'suggested')
            """,
            (rejection_reason, now, now, note_id),
        )
        if _commit:
            db.commit()
        return CorrectionNoteRepository.get(note_id)

    @staticmethod
    def _row_to_note(row) -> CorrectionNote:
        return CorrectionNote(
            id=row["id"],
            voucher_id=row["voucher_id"],
            note_text=row["note_text"],
            status=row["status"],
            suggested_voucher_id=row["suggested_voucher_id"],
            rejection_reason=row["rejection_reason"],
            created_at=datetime.fromisoformat(row["created_at"]),
            created_by=row["created_by"],
            updated_at=(
                datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None
            ),
            resolved_at=(
                datetime.fromisoformat(row["resolved_at"])
                if row["resolved_at"]
                else None
            ),
        )
