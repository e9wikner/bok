"""API routes for versioned Markdown agent instructions.

This module provides endpoints for agent instructions with a clear separation
between:
- System instructions: Read-only, version-controlled documentation about how
  the system works (SIE4 import, API behavior, etc.)
- Company instructions: Writable instructions for company-specific rules and
  learnings.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_current_actor
from config import settings
from repositories.agent_instruction_repo import AgentInstructionRepository
from repositories.system_instructions import (
    get_accounting_system_instructions,
    get_invoicing_system_instructions,
)

router = APIRouter(prefix="/api/v1/agent-instructions", tags=["agent-instructions"])


class UpdateAgentInstructionRequest(BaseModel):
    content_markdown: str = Field(..., min_length=1)
    change_summary: Optional[str] = None


@router.get("/entrypoint", response_model=dict)
async def get_agent_instruction_entrypoint():
    """Return the public-safe startup contract for external bookkeeping agents."""
    return {
        "service": "bokfoering-api",
        "version": settings.api_version,
        "purpose": (
            "Machine-readable startup instructions for an external agent that "
            "posts Bok vouchers from uploaded source material while the backend "
            "enforces formal Swedish bookkeeping constraints."
        ),
        "auth": {
            "type": "bearer",
            "header": "Authorization",
            "value_format": "Bearer <BOKFOERING_API_KEY>",
            "check": {
                "method": "POST",
                "path": "/api/v1/agent/test/ping",
                "expected_status": 200,
            },
        },
        "links": {
            "health": "/api/v1/health",
            "docs": "/docs",
            "redoc": "/redoc",
            "openapi": "/openapi.json",
        },
        "startup_sequence": [
            {
                "step": 1,
                "action": "read_entrypoint",
                "method": "GET",
                "path": "/api/v1/agent-instructions/entrypoint",
                "auth_required": False,
            },
            {
                "step": 2,
                "action": "verify_auth",
                "method": "POST",
                "path": "/api/v1/agent/test/ping",
                "auth_required": True,
            },
            {
                "step": 3,
                "action": "read_accounting_instructions",
                "method": "GET",
                "path": "/api/v1/agent-instructions/accounting",
                "auth_required": True,
            },
            {
                "step": 4,
                "action": "read_recent_corrections",
                "method": "GET",
                "path": "/api/v1/accounting-corrections",
                "auth_required": True,
            },
            {
                "step": 5,
                "action": "scan_pending_intake",
                "method": "GET",
                "path": "/api/v1/agent/intake/pending",
                "auth_required": True,
            },
            {
                "step": 6,
                "action": "process_pending_items",
                "guidance": (
                    "Process all pending items automatically, one item at a time. "
                    "Mark an item processing before work, post a voucher when the "
                    "bookkeeping decision is complete, and record failed or warning "
                    "outcomes instead of guessing."
                ),
            },
        ],
        "workflow_endpoints": {
            "ping": {
                "method": "POST",
                "path": "/api/v1/agent/test/ping",
            },
            "accounting_instructions": {
                "method": "GET",
                "path": "/api/v1/agent-instructions/accounting",
            },
            "correction_history": {
                "method": "GET",
                "path": "/api/v1/accounting-corrections",
            },
            "pending_intake": {
                "method": "GET",
                "path": "/api/v1/agent/intake/pending",
            },
            "mark_processing": {
                "method": "POST",
                "path": "/api/v1/agent/intake/{source_id}/processing",
            },
            "mark_failed": {
                "method": "POST",
                "path": "/api/v1/agent/intake/{source_id}/failed",
            },
            "post_voucher": {
                "method": "POST",
                "path": "/api/v1/agent/vouchers",
            },
            "source_context": {
                "method": "GET",
                "path": "/api/v1/vouchers/{voucher_id}/source-context",
            },
        },
        "guardrails": [
            "Posted vouchers are immutable; corrections must use correction vouchers.",
            "Use source material, accounting instructions, and correction history before posting.",
            "Post directly when the decision is complete; user review happens after posting.",
            "Keep voucher source material and bank statement/status inputs conceptually separate.",
            "If an item cannot be completed, record failed or warning context instead of guessing.",
        ],
        "unsupported_features": [
            "Persistent per-agent credential lifecycle is not implemented; use the configured bearer credential.",
            "Generated tool-schema discovery is not implemented; use /openapi.json for the current HTTP schema.",
            "Durable idempotency for agent operations is not implemented.",
        ],
        "agent_start_instructions": (
            "The owner should send this entrypoint URL to OpenClaw. Read this payload, "
            "verify bearer access with the ping endpoint, then read accounting "
            "instructions and recent corrections before scanning pending intake. "
            "Process pending items automatically one at a time."
        ),
    }


@router.get("/accounting", response_model=dict)
async def get_accounting_instructions(actor: str = Depends(get_current_actor)):
    """Get both system and company instructions for the accounting agent.
    
    Returns:
        - system: Read-only system instructions (how the system works)
        - company: Writable company-specific instructions
    """
    try:
        system_instructions = get_accounting_system_instructions()
        company_instructions = AgentInstructionRepository.get_active("accounting_company")
        
        return {
            "scope": "accounting",
            "system": system_instructions,
            "company": company_instructions,
            "note": "Systeminstruktioner är skrivskyddade. Endast company-instruktioner kan uppdateras."
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/invoicing", response_model=dict)
async def get_invoicing_instructions(actor: str = Depends(get_current_actor)):
    """Get both system and company instructions for the invoicing agent.
    
    Returns:
        - system: Read-only system instructions
        - company: Writable company-specific instructions
    """
    try:
        system_instructions = get_invoicing_system_instructions()
        company_instructions = AgentInstructionRepository.get_active("invoicing_company")
        
        return {
            "scope": "invoicing",
            "system": system_instructions,
            "company": company_instructions,
            "note": "Systeminstruktioner är skrivskyddade. Endast company-instruktioner kan uppdateras."
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/accounting", response_model=dict)
async def update_accounting_instructions(
    request: UpdateAgentInstructionRequest,
    actor: str = Depends(get_current_actor),
):
    """Update company-specific accounting instructions.
    
    System instructions cannot be modified through this endpoint.
    Only company-specific rules and learnings should be updated here.
    """
    try:
        return AgentInstructionRepository.update(
            scope="accounting_company",
            content_markdown=request.content_markdown,
            change_summary=request.change_summary,
            created_by=actor,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/invoicing", response_model=dict)
async def update_invoicing_instructions(
    request: UpdateAgentInstructionRequest,
    actor: str = Depends(get_current_actor),
):
    """Update company-specific invoicing instructions.
    
    System instructions cannot be modified through this endpoint.
    Only company-specific rules and learnings should be updated here.
    """
    try:
        return AgentInstructionRepository.update(
            scope="invoicing_company",
            content_markdown=request.content_markdown,
            change_summary=request.change_summary,
            created_by=actor,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/accounting/versions", response_model=dict)
async def list_accounting_instruction_versions(actor: str = Depends(get_current_actor)):
    """List company instruction versions, newest first.
    
    System instructions are version-controlled in Git and not listed here.
    """
    try:
        versions = AgentInstructionRepository.list_versions("accounting_company")
        return {
            "scope": "accounting_company",
            "total": len(versions),
            "versions": versions,
            "note": "Visar endast versionshistorik för company-instruktioner. Systeminstruktioner versionshanteras i Git."
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/invoicing/versions", response_model=dict)
async def list_invoicing_instruction_versions(actor: str = Depends(get_current_actor)):
    """List company instruction versions, newest first.
    
    System instructions are version-controlled in Git and not listed here.
    """
    try:
        versions = AgentInstructionRepository.list_versions("invoicing_company")
        return {
            "scope": "invoicing_company",
            "total": len(versions),
            "versions": versions,
            "note": "Visar endast versionshistorik för company-instruktioner. Systeminstruktioner versionshanteras i Git."
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/system/accounting", response_model=dict)
async def get_accounting_system_instructions_only(
    actor: str = Depends(get_current_actor)
):
    """Get only the system instructions for accounting.
    
    These are read-only and describe how the system works.
    """
    try:
        return get_accounting_system_instructions()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/system/invoicing", response_model=dict)
async def get_invoicing_system_instructions_only(
    actor: str = Depends(get_current_actor)
):
    """Get only the system instructions for invoicing.
    
    These are read-only and describe how the system works.
    """
    try:
        return get_invoicing_system_instructions()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# Legacy endpoints for backward compatibility
@router.get("/accounting/legacy", response_model=dict)
async def get_accounting_instructions_legacy(
    actor: str = Depends(get_current_actor)
):
    """Legacy endpoint: Get combined instructions (deprecated).
    
    This endpoint returns the old combined format for backward compatibility.
    New integrations should use GET /accounting which separates system and company.
    """
    try:
        # Get company instructions (which may have been updated from legacy data)
        company = AgentInstructionRepository.get_active("accounting")
        
        return {
            "scope": "accounting",
            "version_id": company.get("version_id"),
            "version": company.get("version"),
            "content_markdown": company.get("content_markdown"),
            "change_summary": company.get("change_summary"),
            "created_by": company.get("created_by"),
            "created_at": company.get("created_at"),
            "updated_at": company.get("updated_at"),
            "deprecated": True,
            "note": "Detta är ett legacy-endpoint. Använd GET /accounting för separerade system/company-instruktioner."
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
