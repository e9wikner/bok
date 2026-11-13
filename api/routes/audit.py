"""Audit log API routes."""

from typing import List, Optional

from fastapi import APIRouter, Query

from repositories.audit_repo import AuditRepository

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("/log")
async def get_audit_log(
    entity_type: Optional[List[str]] = Query(
        None,
        description="Only these entity types (voucher, period, ...); repeat the parameter for several",
    ),
    action: Optional[str] = Query(
        None, description="Filter by action (created, updated, posted, etc.)"
    ),
    limit: int = Query(100, ge=1, le=500, description="Number of entries to return"),
    offset: int = Query(0, ge=0, description="Entries to skip, newest first"),
):
    """The audit log (behandlingshistorik), newest first, a page at a time.

    `has_more` says whether an older page exists.
    """
    entries = AuditRepository.list_recent(
        limit=limit + 1, offset=offset, entity_types=entity_type, action=action
    )
    has_more = len(entries) > limit
    entries = entries[:limit]

    return {
        "total": len(entries),
        "offset": offset,
        "has_more": has_more,
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
