"""Repository for idempotency keys."""

import sqlite3
from datetime import datetime
from typing import Optional

from db.database import db
from domain.models import IdempotencyKey


class IdempotencyRepository:
    """Manage idempotency key persistence."""

    @staticmethod
    def reserve(
        key: str,
        endpoint: str,
        fingerprint: str,
        actor: str,
    ) -> bool:
        """Claim the key. Returns False if another request already holds it.

        Commits immediately: a reservation inside the caller's transaction is
        invisible to a concurrent request and would protect nothing.
        """
        try:
            db.execute(
                """
                INSERT INTO idempotency_keys
                (key, endpoint, request_fingerprint, state, actor, created_at)
                VALUES (?, ?, ?, 'in_flight', ?, ?)
                """,
                (key, endpoint, fingerprint, actor, datetime.now()),
            )
            db.commit()
            return True
        except sqlite3.IntegrityError:
            db.rollback()
            return False

    @staticmethod
    def get(key: str, endpoint: str) -> Optional[IdempotencyKey]:
        """Look up one key for one endpoint."""
        row = db.execute(
            "SELECT * FROM idempotency_keys WHERE key = ? AND endpoint = ?",
            (key, endpoint),
        ).fetchone()
        if not row:
            return None
        return IdempotencyRepository._to_model(row)

    @staticmethod
    def complete(
        key: str,
        endpoint: str,
        response_status: int,
        response_body: str,
        entity_type: str,
        entity_id: str,
        _commit: bool = True,
    ) -> None:
        """Record the outcome. Call inside the same transaction as the write."""
        db.execute(
            """
            UPDATE idempotency_keys
            SET state = 'completed', response_status = ?, response_body = ?,
                entity_type = ?, entity_id = ?, completed_at = ?
            WHERE key = ? AND endpoint = ?
            """,
            (
                response_status,
                response_body,
                entity_type,
                entity_id,
                datetime.now(),
                key,
                endpoint,
            ),
        )
        if _commit:
            db.commit()

    @staticmethod
    def release(key: str, endpoint: str, _commit: bool = True) -> None:
        """Drop a reservation whose work never completed.

        Only `in_flight` rows are removed. A completed key records a real
        posting and must survive so a late retry still replays it.
        """
        db.execute(
            """
            DELETE FROM idempotency_keys
            WHERE key = ? AND endpoint = ? AND state = 'in_flight'
            """,
            (key, endpoint),
        )
        if _commit:
            db.commit()

    @staticmethod
    def _to_model(row: sqlite3.Row) -> IdempotencyKey:
        return IdempotencyKey(
            key=row["key"],
            endpoint=row["endpoint"],
            request_fingerprint=row["request_fingerprint"],
            state=row["state"],
            actor=row["actor"],
            response_status=row["response_status"],
            response_body=row["response_body"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            created_at=IdempotencyRepository._required_datetime(row["created_at"]),
            completed_at=IdempotencyRepository._to_datetime(row["completed_at"]),
        )

    @staticmethod
    def _required_datetime(value) -> datetime:
        parsed = IdempotencyRepository._to_datetime(value)
        if parsed is None:
            raise ValueError("idempotency_keys.created_at is missing")
        return parsed

    @staticmethod
    def _to_datetime(value) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(value)
