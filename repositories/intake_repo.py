"""Repository for intake source material and voucher traceability."""

from datetime import datetime
import json
from typing import Optional, List
import uuid

from db.database import db
from domain.models import IntakeProcessingAttempt, IntakeSource, VoucherIntakeSource
from domain.types import IntakeSourceType, IntakeStatus


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
        status: str = IntakeStatus.PENDING.value,
        _commit: bool = True,
    ) -> IntakeSource:
        now = datetime.now()
        db.execute(
            """
            INSERT INTO intake_sources
            (id, source_type, status, original_filename, mime_type, size_bytes,
             sha256, stored_path, explanation, uploaded_by, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            "SELECT * FROM intake_sources WHERE sha256 = ? LIMIT 1",
            (sha256,),
        ).fetchone()
        return IntakeRepository._row_to_source(row) if row else None

    @staticmethod
    def list_pending(limit: int = 100, offset: int = 0) -> List[IntakeSource]:
        rows = db.execute(
            """
            SELECT * FROM intake_sources
            WHERE status = ?
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
    def count_pending() -> int:
        row = db.execute(
            "SELECT COUNT(*) AS count FROM intake_sources WHERE status = ?",
            (IntakeStatus.PENDING.value,),
        ).fetchone()
        return row["count"] if row else 0

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

    @staticmethod
    def get_link_by_source_id(source_id: str) -> Optional[VoucherIntakeSource]:
        row = db.execute(
            "SELECT * FROM voucher_intake_sources WHERE intake_source_id = ? LIMIT 1",
            (source_id,),
        ).fetchone()
        return IntakeRepository._row_to_link(row) if row else None

    @staticmethod
    def list_links_for_voucher(voucher_id: str) -> List[VoucherIntakeSource]:
        rows = db.execute(
            """
            SELECT * FROM voucher_intake_sources
            WHERE voucher_id = ?
            ORDER BY linked_at ASC
            """,
            (voucher_id,),
        ).fetchall()
        return [IntakeRepository._row_to_link(row) for row in rows]

    @staticmethod
    def list_links_for_source(source_id: str) -> List[VoucherIntakeSource]:
        rows = db.execute(
            """
            SELECT * FROM voucher_intake_sources
            WHERE intake_source_id = ?
            ORDER BY linked_at ASC
            """,
            (source_id,),
        ).fetchall()
        return [IntakeRepository._row_to_link(row) for row in rows]

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
            linked_at=datetime.fromisoformat(row["linked_at"]),
            link_reason=row["link_reason"],
        )
