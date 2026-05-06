"""Repository for accounting correction history."""

from datetime import datetime
import json
from typing import Optional, List
import uuid

from db.database import db
from domain.models import CorrectionHistory


class AccountingCorrectionRepository:
    """Manage agent-readable correction history."""

    @staticmethod
    def create(
        original_voucher_id: str,
        corrected_voucher_id: Optional[str] = None,
        original_data: Optional[dict] = None,
        corrected_data: Optional[dict] = None,
        change_type: Optional[str] = None,
        was_successful: Optional[bool] = None,
        corrected_by: Optional[str] = None,
        correction_reason: Optional[str] = None,
    ) -> CorrectionHistory:
        history_id = str(uuid.uuid4())
        now = datetime.now()

        db.execute(
            """
            INSERT INTO correction_history
            (id, original_voucher_id, corrected_voucher_id,
             original_data, corrected_data, change_type, was_successful,
             corrected_by, correction_reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                history_id,
                original_voucher_id,
                corrected_voucher_id,
                json.dumps(original_data) if original_data else None,
                json.dumps(corrected_data) if corrected_data else None,
                change_type,
                was_successful,
                corrected_by,
                correction_reason,
                now,
            ),
        )
        db.commit()

        return CorrectionHistory(
            id=history_id,
            original_voucher_id=original_voucher_id,
            corrected_voucher_id=corrected_voucher_id,
            original_data=original_data,
            corrected_data=corrected_data,
            change_type=change_type,
            was_successful=was_successful,
            corrected_by=corrected_by,
            correction_reason=correction_reason,
            created_at=now,
        )

    @staticmethod
    def list(
        limit: int = 100,
        voucher_id: Optional[str] = None,
    ) -> List[CorrectionHistory]:
        if voucher_id:
            rows = db.execute(
                """
                SELECT * FROM correction_history
                WHERE original_voucher_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (voucher_id, limit),
            ).fetchall()
        else:
            rows = db.execute(
                """
                SELECT * FROM correction_history
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [AccountingCorrectionRepository._row_to_history(row) for row in rows]

    @staticmethod
    def _row_to_history(row) -> CorrectionHistory:
        original_data = None
        corrected_data = None

        if row["original_data"]:
            try:
                original_data = json.loads(row["original_data"])
            except json.JSONDecodeError:
                pass

        if row["corrected_data"]:
            try:
                corrected_data = json.loads(row["corrected_data"])
            except json.JSONDecodeError:
                pass

        return CorrectionHistory(
            id=row["id"],
            original_voucher_id=row["original_voucher_id"],
            corrected_voucher_id=row["corrected_voucher_id"],
            original_data=original_data,
            corrected_data=corrected_data,
            change_type=row["change_type"],
            was_successful=bool(row["was_successful"])
            if row["was_successful"] is not None
            else None,
            corrected_by=row["corrected_by"],
            correction_reason=row["correction_reason"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
