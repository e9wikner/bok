"""Audit repository - data access for audit logs."""

from typing import List, Optional
from datetime import datetime
import uuid
import json
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
    ) -> AuditLogEntry:
        """Create audit log entry."""
        log_id = str(uuid.uuid4())
        sql = """
        INSERT INTO audit_log (id, entity_type, entity_id, action, actor, payload, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        now = datetime.now()
        payload_json = json.dumps(payload) if payload else None
        
        db.execute(sql, (log_id, entity_type, entity_id, action, actor, payload_json, now))
        db.commit()
        
        return AuditLogEntry(
            id=log_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=AuditAction(action),
            actor=actor,
            payload=payload,
            timestamp=now
        )
    
    @staticmethod
    def get_history(entity_type: str, entity_id: str) -> List[AuditLogEntry]:
        """Get audit history for an entity."""
        sql = """
        SELECT * FROM audit_log
        WHERE entity_type = ? AND entity_id = ?
        ORDER BY timestamp ASC
        """
        cursor = db.execute(sql, (entity_type, entity_id))
        entries = []
        
        for row in cursor.fetchall():
            payload = None
            if row["payload"]:
                payload = json.loads(row["payload"])
            
            entries.append(AuditLogEntry(
                id=row["id"],
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                action=AuditAction(row["action"]),
                actor=row["actor"],
                payload=payload,
                timestamp=datetime.fromisoformat(row["timestamp"])
            ))
        
        return entries
    
    @staticmethod
    def list_recent(limit: int = 100) -> List[AuditLogEntry]:
        """Get recent audit log entries."""
        sql = """
        SELECT * FROM audit_log
        ORDER BY timestamp DESC
        LIMIT ?
        """
        cursor = db.execute(sql, (limit,))
        entries = []
        
        for row in cursor.fetchall():
            payload = None
            if row["payload"]:
                payload = json.loads(row["payload"])
            
            entries.append(AuditLogEntry(
                id=row["id"],
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                action=AuditAction(row["action"]),
                actor=row["actor"],
                payload=payload,
                timestamp=datetime.fromisoformat(row["timestamp"])
            ))
        
        return entries
