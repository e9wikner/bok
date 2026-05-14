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
from repositories.agent_instruction_repo import AgentInstructionRepository
from repositories.system_instructions import (
    get_accounting_system_instructions,
    get_invoicing_system_instructions,
)

router = APIRouter(prefix="/api/v1/agent-instructions", tags=["agent-instructions"])


class UpdateAgentInstructionRequest(BaseModel):
    content_markdown: str = Field(..., min_length=1)
    change_summary: Optional[str] = None


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
