"""Repository for `review_tokens` and their revocations (migration 056).

Append-only: insert and read, nothing else (the triggers refuse the rest).
Times are stored as ISO strings in UTC so comparisons are plain string
comparisons.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from db.database import db


@dataclass(frozen=True)
class ReviewToken:
    id: str
    fiscal_year_id: Optional[str]
    created_by: str
    created_at: str
    expires_at: str
    revoked_at: Optional[str]


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


def _row(row) -> ReviewToken:
    return ReviewToken(
        id=row["id"],
        fiscal_year_id=row["fiscal_year_id"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        revoked_at=row["revoked_at"],
    )


class ReviewTokenRepository:
    _SELECT = """
        SELECT t.id, t.fiscal_year_id, t.created_by, t.created_at, t.expires_at,
               r.created_at AS revoked_at
        FROM review_tokens t
        LEFT JOIN review_token_revocations r ON r.token_id = t.id
    """

    @staticmethod
    def create(
        *,
        token_sha256: str,
        fiscal_year_id: Optional[str],
        created_by: str,
        created_at: datetime,
        expires_at: datetime,
        _commit: bool = True,
    ) -> ReviewToken:
        token_id = str(uuid.uuid4())
        db.execute(
            """
            INSERT INTO review_tokens
            (id, token_sha256, fiscal_year_id, created_by, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                token_id,
                token_sha256,
                fiscal_year_id,
                created_by,
                _iso(created_at),
                _iso(expires_at),
            ),
        )
        if _commit:
            db.commit()
        token = ReviewTokenRepository.get(token_id)
        assert token is not None
        return token

    @staticmethod
    def get(token_id: str) -> Optional[ReviewToken]:
        row = db.execute(
            ReviewTokenRepository._SELECT + " WHERE t.id = ?", (token_id,)
        ).fetchone()
        return _row(row) if row else None

    @staticmethod
    def find_valid(token_sha256: str, now: datetime) -> Optional[ReviewToken]:
        """The unexpired, unrevoked key with this hash, or `None`."""
        row = db.execute(
            ReviewTokenRepository._SELECT
            + " WHERE t.token_sha256 = ? AND t.expires_at > ?"
            " AND r.token_id IS NULL",
            (token_sha256, _iso(now)),
        ).fetchone()
        return _row(row) if row else None

    @staticmethod
    def list_active(now: datetime) -> List[ReviewToken]:
        rows = db.execute(
            ReviewTokenRepository._SELECT
            + " WHERE t.expires_at > ? AND r.token_id IS NULL"
            " ORDER BY t.created_at DESC",
            (_iso(now),),
        ).fetchall()
        return [_row(r) for r in rows]

    @staticmethod
    def revoke(token_id: str, *, revoked_by: str, _commit: bool = True) -> None:
        db.execute(
            """
            INSERT INTO review_token_revocations (token_id, revoked_by, created_at)
            VALUES (?, ?, ?)
            """,
            (token_id, revoked_by, _iso(datetime.now(timezone.utc))),
        )
        if _commit:
            db.commit()
