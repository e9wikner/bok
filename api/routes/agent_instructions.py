"""API routes for versioned Markdown agent instructions."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_current_actor
from repositories.agent_instruction_repo import AgentInstructionRepository

router = APIRouter(prefix="/api/v1/agent-instructions", tags=["agent-instructions"])


class UpdateAgentInstructionRequest(BaseModel):
    content_markdown: str = Field(..., min_length=1)
    change_summary: Optional[str] = None


@router.get("/accounting", response_model=dict)
async def get_accounting_instructions(actor: str = Depends(get_current_actor)):
    """Get the active Markdown instructions for the accounting agent."""
    try:
        return AgentInstructionRepository.get_active("accounting")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/invoicing", response_model=dict)
async def get_invoicing_instructions(actor: str = Depends(get_current_actor)):
    """Get the active Markdown instructions for the invoicing agent."""
    try:
        return AgentInstructionRepository.get_active("invoicing")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/accounting", response_model=dict)
async def update_accounting_instructions(
    request: UpdateAgentInstructionRequest,
    actor: str = Depends(get_current_actor),
):
    """Create a new active version of the accounting agent instructions."""
    try:
        return AgentInstructionRepository.update(
            scope="accounting",
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
    """Create a new active version of the invoicing agent instructions."""
    try:
        return AgentInstructionRepository.update(
            scope="invoicing",
            content_markdown=request.content_markdown,
            change_summary=request.change_summary,
            created_by=actor,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/accounting/versions", response_model=dict)
async def list_accounting_instruction_versions(actor: str = Depends(get_current_actor)):
    """List accounting instruction versions, newest first."""
    try:
        versions = AgentInstructionRepository.list_versions("accounting")
        return {"scope": "accounting", "total": len(versions), "versions": versions}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/invoicing/versions", response_model=dict)
async def list_invoicing_instruction_versions(actor: str = Depends(get_current_actor)):
    """List invoicing instruction versions, newest first."""
    try:
        versions = AgentInstructionRepository.list_versions("invoicing")
        return {"scope": "invoicing", "total": len(versions), "versions": versions}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
