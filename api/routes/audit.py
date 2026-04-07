"""Audit log API routes."""

from fastapi import APIRouter, Query
from typing import Optional

from repositories.audit_repo import AuditRepository
from domain.types import AuditAction

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("/log")
async def get_audit_log(
    entity_type: Optional[str] = Query(
        None, description="Filter by entity type (voucher, fiscal_year, etc.)"
    ),
    action: Optional[str] = Query(
        None, description="Filter by action (created, updated, posted, etc.)"
    ),
    limit: int = Query(100, description="Number of entries to return"),
):
    """Get audit log entries.

    Returns recent audit log entries with optional filtering.
    """
    entries = AuditRepository.list_recent(limit=limit)

    # Filter by entity type if specified
    if entity_type:
        entries = [e for e in entries if e.entity_type == entity_type]

    # Filter by action if specified
    if action:
        entries = [e for e in entries if e.action.value == action]

    return {
        "total": len(entries),
        "entries": [
            {
                "id": e.id,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "action": e.action.value,
                "actor": e.actor,
                "payload": e.payload,
                "timestamp": e.timestamp.isoformat(),
            }
            for e in entries
        ],
    }


@router.get("/entity/{entity_type}/{entity_id}")
async def get_entity_audit_history(
    entity_type: str,
    entity_id: str,
):
    """Get audit history for a specific entity."""
    entries = AuditRepository.get_history(entity_type, entity_id)

    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "total": len(entries),
        "entries": [
            {
                "id": e.id,
                "action": e.action.value,
                "actor": e.actor,
                "payload": e.payload,
                "timestamp": e.timestamp.isoformat(),
            }
            for e in entries
        ],
    }
