"""API routes for agent integration (Fas 4)."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import date as DateType, datetime, timezone

from api.deps import get_current_actor
from api.schemas import VoucherRowRequest
from config import settings
from db.database import db
from domain.validation import ValidationError
from repositories.correction_note_repo import CorrectionNoteRepository
from services.ledger import LedgerService
from services.intake import IntakeError, IntakeService
from services.bank_inputs import BankInputError, BankInputService

router = APIRouter(prefix="/api/v1/agent", tags=["agent-integration"])


class AgentVoucherRequest(BaseModel):
    date: DateType
    period_id: str
    description: str
    rows: list[VoucherRowRequest] = Field(..., min_length=2)
    series: Literal["A", "B"] = "A"
    reasoning_summary: Optional[str] = None
    intake_source_ids: list[str] = Field(default_factory=list)
    bank_input_ids: list[str] = Field(default_factory=list)
    bank_transaction_ids: list[str] = Field(default_factory=list)


class AgentProcessingRequest(BaseModel):
    summary: str = Field(..., min_length=1)
    warnings: Optional[list[str]] = None


class AgentFailedRequest(BaseModel):
    summary: str = Field(..., min_length=1)
    error_detail: str = Field(..., min_length=1)
    warnings: Optional[list[str]] = None


@router.post("/seed", response_model=dict, status_code=status.HTTP_201_CREATED)
async def seed_demo_data(
    actor: str = Depends(get_current_actor),
):
    """Seed demo/test data (idempotent - safe to call multiple times)."""
    try:
        from scripts.seed_test_data import seed_test_company
        seed_test_company()
        return {"status": "ok", "message": "Demo data seeded successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/vouchers", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_and_post_agent_voucher(
    request: AgentVoucherRequest,
    actor: str = Depends(get_current_actor),
):
    """Create and post a voucher directly from an accounting agent."""
    intake = IntakeService()
    bank_inputs = BankInputService()
    intake_source_ids = _unique_preserve_order(request.intake_source_ids)
    bank_input_ids = _unique_preserve_order(request.bank_input_ids)
    bank_transaction_ids = _unique_preserve_order(request.bank_transaction_ids)
    try:
        for source_id in intake_source_ids:
            intake.ensure_source_ready_for_voucher_link(source_id)
        _ensure_agent_voucher_has_traceability(intake_source_ids, bank_input_ids)
        bank_inputs.ensure_transactions_available(
            bank_input_ids,
            bank_transaction_ids,
        )
    except IntakeError as exc:
        raise _intake_http_error(exc) from exc
    except BankInputError as exc:
        raise _bank_input_http_error(exc) from exc

    try:
        fiscal_year_id = None
        voucher_series = None
        with db.transaction():
            ledger = LedgerService()
            voucher = ledger.create_voucher(
                series=request.series,
                date=request.date,
                period_id=request.period_id,
                description=request.description,
                rows_data=[row.model_dump() for row in request.rows],
                created_by="agent",
                _commit=False,
            )
            voucher = ledger.post_voucher(
                voucher.id,
                actor=actor,
                _commit=False,
                update_opening_balance=False,
            )
            processing_attempt_ids = []
            summary = request.reasoning_summary or request.description
            for source_id in intake_source_ids:
                attempt, _link = intake.link_existing_voucher(
                    source_id=source_id,
                    voucher_id=voucher.id,
                    actor=actor,
                    summary=summary,
                    link_reason="agent_posted_voucher",
                    _commit=False,
                )
                processing_attempt_ids.append(attempt.id)
            traceability = bank_inputs.link_posted_voucher(
                voucher_id=voucher.id,
                bank_input_ids=bank_input_ids,
                bank_transaction_ids=bank_transaction_ids,
                actor=actor,
                _commit=False,
            )
            fiscal_year_id = voucher.fiscal_year_id
            voucher_series = voucher.series.value
        if fiscal_year_id and voucher_series != "IB":
            try:
                from services.opening_balance import OpeningBalanceService

                OpeningBalanceService().update_opening_balances_for_next_year(
                    fiscal_year_id,
                    actor,
                )
            except Exception:
                pass
        from api.routes.vouchers import _voucher_to_response

        response = _voucher_to_response(voucher).model_dump()
        response["agent"] = {
            "posted_directly": True,
            "reasoning_summary": request.reasoning_summary,
            "intake_source_ids": intake_source_ids,
            "processing_attempt_id": processing_attempt_ids[0]
            if len(processing_attempt_ids) == 1
            else None,
            "processing_attempt_ids": processing_attempt_ids,
            "bank_input_ids": bank_input_ids,
            "bank_transaction_ids": bank_transaction_ids,
            "traceability": traceability,
        }
        return response
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": exc.message, "code": exc.code, "details": exc.details},
        )
    except IntakeError as exc:
        raise _intake_http_error(exc) from exc
    except BankInputError as exc:
        raise _bank_input_http_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/intake/pending", response_model=dict)
async def list_pending_intake_sources(
    limit: int = 100,
    offset: int = 0,
    actor: str = Depends(get_current_actor),
):
    """List pending intake source material for agent processing."""
    source_limit = limit + offset
    queue = IntakeService().get_pending_queue(limit=source_limit, offset=0)
    bank_queue = BankInputService().agent_queue_items(limit=source_limit, offset=0)
    correction_note_repo = CorrectionNoteRepository()
    correction_notes = correction_note_repo.list_pending(
        limit=source_limit,
        offset=0,
    )
    source_items = [
        {
            "kind": "voucher_source",
            "id": source.id,
            "source_type": source.source_type.value if source.source_type else None,
            "status": source.status.value,
            "original_filename": source.original_filename,
            "mime_type": source.mime_type,
            "size_bytes": source.size_bytes,
            "sha256": source.sha256,
            "explanation": source.explanation,
            "guidance": source.agent_guidance,
            "uploaded_at": source.uploaded_at.isoformat(),
            "uploaded_by": source.uploaded_by,
            "download_url": f"/api/v1/intake/{source.id}/file",
        }
        for source in queue["items"]
    ]
    correction_note_items = [
        {
            "kind": "correction_note",
            "id": note.id,
            "voucher_id": note.voucher_id,
            "original_voucher_id": note.voucher_id,
            "note_text": note.note_text,
            "status": note.status,
            "created_at": note.created_at.isoformat(),
            "created_by": note.created_by,
            "source_context_url": f"/api/v1/vouchers/{note.voucher_id}/source-context",
            "correction_draft_url": f"/api/v1/vouchers/{note.voucher_id}/correction-draft",
            "suggest_url": (
                f"/api/v1/vouchers/{note.voucher_id}/correction-notes/"
                f"{note.id}/suggest"
            ),
        }
        for note in correction_notes
    ]
    items = sorted(
        source_items + bank_queue["items"] + correction_note_items,
        key=_agent_queue_timestamp,
    )
    return {
        "total": queue["total"] + bank_queue["total"] + correction_note_repo.count_pending(),
        "limit": limit,
        "offset": offset,
        "correction_history_url": "/api/v1/accounting-corrections",
        "items": items[offset : offset + limit],
    }


def _agent_queue_timestamp(item: dict) -> str:
    return item.get("uploaded_at") or item.get("created_at") or ""


@router.post("/intake/{source_id}/processing", response_model=dict)
async def record_intake_processing(
    source_id: str,
    request: AgentProcessingRequest,
    actor: str = Depends(get_current_actor),
):
    """Record that the agent has started processing an intake source."""
    try:
        attempt = IntakeService().record_processing(
            source_id=source_id,
            summary=request.summary,
            warnings=request.warnings,
            actor=actor,
        )
        return _attempt_to_response(attempt)
    except IntakeError as exc:
        raise _intake_http_error(exc) from exc


@router.post("/intake/{source_id}/failed", response_model=dict)
async def record_intake_failed(
    source_id: str,
    request: AgentFailedRequest,
    actor: str = Depends(get_current_actor),
):
    """Record failed agent processing for an intake source."""
    try:
        attempt = IntakeService().record_failed(
            source_id=source_id,
            summary=request.summary,
            error_detail=request.error_detail,
            warnings=request.warnings,
            actor=actor,
        )
        return _attempt_to_response(attempt)
    except IntakeError as exc:
        raise _intake_http_error(exc) from exc


def _attempt_to_response(attempt) -> dict:
    return {
        "id": attempt.id,
        "intake_source_id": attempt.intake_source_id,
        "status": attempt.status.value,
        "summary": attempt.summary,
        "warnings": attempt.warnings,
        "error_detail": attempt.error_detail,
        "voucher_id": attempt.voucher_id,
        "actor": attempt.actor,
        "created_at": attempt.created_at.isoformat(),
    }


def _intake_http_error(exc: IntakeError) -> HTTPException:
    if exc.code in {"intake_not_found", "voucher_not_found"}:
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code in {"intake_not_processable", "intake_already_linked", "voucher_not_posted"}:
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_400_BAD_REQUEST
    return HTTPException(
        status_code=status_code,
        detail={"error": exc.message, "code": exc.code, "details": exc.details},
    )


def _bank_input_http_error(exc: BankInputError) -> HTTPException:
    if exc.code in {"bank_input_not_found", "bank_connection_not_found", "bank_transaction_not_found"}:
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code in {
        "bank_input_not_processed",
        "bank_transaction_not_linked",
        "bank_transaction_already_booked",
        "bank_transaction_already_matched",
    }:
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_400_BAD_REQUEST
    return HTTPException(
        status_code=status_code,
        detail={"error": exc.message, "code": exc.code, "details": exc.details},
    )


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values


def _ensure_agent_voucher_has_traceability(
    intake_source_ids: list[str],
    bank_input_ids: list[str],
) -> None:
    if intake_source_ids or bank_input_ids:
        return
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "error": "Agent vouchers must reference intake source material",
            "code": "missing_source_traceability",
            "details": (
                "Provide intake_source_ids for voucher sources or bank_input_ids "
                "for bank inputs"
            ),
        },
    )


@router.get("/operations/log", response_model=dict)
async def get_agent_operations_log(
    limit: int = 100,
    actor: str = Depends(get_current_actor),
):
    """Get log of all agent operations for audit."""
    return {
        "operations": [],
        "total": 0,
        "limit": limit,
        "message": "Agent operation log (for audit trail)"
    }


@router.post("/test/ping", response_model=dict)
async def test_agent_connectivity(
    actor: str = Depends(get_current_actor),
):
    """
    Test agent connectivity.
    
    Simple ping endpoint to verify API key and connection.
    """
    return {
        "status": "ok",
        "service": "bokfoering-api",
        "version": settings.api_version,
        "agent": actor,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
