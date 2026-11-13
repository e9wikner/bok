"""Audit repository - data access for audit logs."""

import json
import uuid
from datetime import datetime
from typing import List, Optional

from db.database import db
from domain.models import AuditLogEntry
from domain.types import AuditAction


class AuditRepository:
    """Manage audit logs (Behandlingshistorik)."""

    @staticmethod
    def log(
        entity_type: str,
        entity_id: str,
        action: str,
        actor: str = "system",
        payload: Optional[dict] = None,
        _commit: bool = True,
    ) -> AuditLogEntry:
        """Create audit log entry."""
        log_id = str(uuid.uuid4())
        sql = """
        INSERT INTO audit_log (id, entity_type, entity_id, action, actor, payload, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        now = datetime.now()
        payload_json = json.dumps(payload) if payload else None

        db.execute(
            sql, (log_id, entity_type, entity_id, action, actor, payload_json, now)
        )
        if _commit:
            db.commit()

        return AuditLogEntry(
            id=log_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=AuditAction(action),
            actor=actor,
            payload=payload,
            timestamp=now,
        )

    @staticmethod
    def get_history(entity_type: str, entity_id: str) -> List[AuditLogEntry]:
        """Get audit history for an entity."""
        sql = """
        SELECT * FROM audit_log
        WHERE entity_type = ? AND entity_id = ?
        ORDER BY timestamp ASC
        """
        return [
            _row_to_entry(row)
            for row in db.execute(sql, (entity_type, entity_id)).fetchall()
        ]

    @staticmethod
    def list_recent(
        limit: int = 100,
        offset: int = 0,
        entity_types: Optional[List[str]] = None,
        action: Optional[str] = None,
    ) -> List[AuditLogEntry]:
        """Audit log entries, newest first.

        The filters are applied before `limit`/`offset`, so a page holds
        `limit` matching entries, and the trail can be read back page by page.
        """
        where = []
        params: list = []
        if entity_types:
            where.append(f"entity_type IN ({', '.join('?' for _ in entity_types)})")
            params.extend(entity_types)
        if action:
            where.append("action = ?")
            params.append(action)
        sql = "SELECT * FROM audit_log"
        if where:
            sql += " WHERE " + " AND ".join(where)
        # `rowid` breaks ties within the same timestamp in write order.
        sql += " ORDER BY timestamp DESC, rowid DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return [_row_to_entry(row) for row in db.execute(sql, tuple(params)).fetchall()]


def _row_to_entry(row) -> AuditLogEntry:
    return AuditLogEntry(
        id=row["id"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        action=AuditAction(row["action"]),
        actor=row["actor"],
        payload=json.loads(row["payload"]) if row["payload"] else None,
        timestamp=datetime.fromisoformat(row["timestamp"]),
    )
