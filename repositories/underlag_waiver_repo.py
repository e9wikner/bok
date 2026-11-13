"""Repository for `voucher_underlag_waivers` and their revocations
(migration 051: a human approves a voucher without underlag).

All SQL for the two tables lives here -- AGENTS.md's layering rule. Both are
append-only: insert and read, nothing else (the triggers refuse the rest).
"""

import uuid
from datetime import datetime
from typing import Optional

from db.database import db
from domain.models import UnderlagWaiver
from repositories.dates import as_datetime


def _row_to_waiver(row) -> UnderlagWaiver:
    return UnderlagWaiver(
        id=row["id"],
        voucher_id=row["voucher_id"],
        reason=row["reason"],
        note=row["note"],
        waived_by=row["waived_by"],
        created_at=as_datetime(row["created_at"]),  # type: ignore[arg-type]
        revoked_at=as_datetime(row["revoked_at"]),
        revoked_by=row["revoked_by"],
    )


class UnderlagWaiverRepository:
    """`voucher_underlag_waivers` and `voucher_underlag_waiver_revocations`."""

    _SELECT = """
        SELECT w.*, r.created_at AS revoked_at, r.revoked_by AS revoked_by
        FROM voucher_underlag_waivers w
        LEFT JOIN voucher_underlag_waiver_revocations r ON r.waiver_id = w.id
    """

    @staticmethod
    def create(
        *,
        voucher_id: str,
        reason: str,
        note: Optional[str],
        waived_by: str,
        _commit: bool = True,
    ) -> UnderlagWaiver:
        waiver_id = str(uuid.uuid4())
        db.execute(
            """
            INSERT INTO voucher_underlag_waivers
            (id, voucher_id, reason, note, waived_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (waiver_id, voucher_id, reason, note, waived_by, datetime.now()),
        )
        if _commit:
            db.commit()
        waiver = UnderlagWaiverRepository.get(waiver_id)
        assert waiver is not None
        return waiver

    @staticmethod
    def get(waiver_id: str) -> Optional[UnderlagWaiver]:
        row = db.execute(
            UnderlagWaiverRepository._SELECT + " WHERE w.id = ?", (waiver_id,)
        ).fetchone()
        return _row_to_waiver(row) if row else None

    @staticmethod
    def current_for(voucher_id: str) -> Optional[UnderlagWaiver]:
        """The voucher's unrevoked waiver, or `None`."""
        row = db.execute(
            UnderlagWaiverRepository._SELECT
            + " WHERE w.voucher_id = ? AND r.waiver_id IS NULL",
            (voucher_id,),
        ).fetchone()
        return _row_to_waiver(row) if row else None

    @staticmethod
    def revoke(waiver_id: str, *, revoked_by: str, _commit: bool = True) -> None:
        db.execute(
            """
            INSERT INTO voucher_underlag_waiver_revocations
            (waiver_id, revoked_by, created_at)
            VALUES (?, ?, ?)
            """,
            (waiver_id, revoked_by, datetime.now()),
        )
        if _commit:
            db.commit()
