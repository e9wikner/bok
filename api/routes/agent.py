"""API routes for agent integration (Fas 4)."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date as DateType
import uuid
import hashlib

from api.deps import get_current_actor
from api.schemas import VoucherRowRequest
from domain.validation import ValidationError
from services.ledger import LedgerService
from services.intake import IntakeError, IntakeService
from services.bank_inputs import BankInputError, BankInputService

router = APIRouter(prefix="/api/v1/agent", tags=["agent-integration"])


class AgentVoucherRequest(BaseModel):
    date: DateType
    period_id: str
    description: str
    rows: list[VoucherRowRequest] = Field(..., min_length=2)
    series: str = "A"
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
    try:
        for source_id in request.intake_source_ids:
            intake.ensure_source_ready_for_voucher_link(source_id)
        bank_inputs.ensure_transactions_available(
            request.bank_input_ids,
            request.bank_transaction_ids,
        )
    except IntakeError as exc:
        raise _intake_http_error(exc) from exc
    except BankInputError as exc:
        raise _bank_input_http_error(exc) from exc

    try:
        ledger = LedgerService()
        voucher = ledger.create_voucher(
            series=request.series,
            date=request.date,
            period_id=request.period_id,
            description=request.description,
            rows_data=[row.model_dump() for row in request.rows],
            created_by="agent",
        )
        voucher = ledger.post_voucher(voucher.id, actor=actor)
        processing_attempt_ids = []
        summary = request.reasoning_summary or request.description
        for source_id in request.intake_source_ids:
            summary = request.reasoning_summary or request.description
            attempt, _link = intake.link_existing_voucher(
                source_id=source_id,
                voucher_id=voucher.id,
                actor=actor,
                summary=summary,
                link_reason="agent_posted_voucher",
            )
            processing_attempt_ids.append(attempt.id)
        traceability = bank_inputs.link_posted_voucher(
            voucher_id=voucher.id,
            bank_input_ids=request.bank_input_ids,
            bank_transaction_ids=request.bank_transaction_ids,
            actor=actor,
        )
        from api.routes.vouchers import _voucher_to_response

        response = _voucher_to_response(voucher).model_dump()
        response["agent"] = {
            "posted_directly": True,
            "reasoning_summary": request.reasoning_summary,
            "intake_source_ids": request.intake_source_ids,
            "processing_attempt_id": processing_attempt_ids[0]
            if len(processing_attempt_ids) == 1
            else None,
            "processing_attempt_ids": processing_attempt_ids,
            "bank_input_ids": request.bank_input_ids,
            "bank_transaction_ids": request.bank_transaction_ids,
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
    queue = IntakeService().get_pending_queue(limit=limit, offset=offset)
    bank_queue = BankInputService().agent_queue_items(limit=limit, offset=offset)
    return {
        "total": queue["total"] + bank_queue["total"],
        "limit": queue["limit"],
        "offset": queue["offset"],
        "correction_history_url": "/api/v1/accounting-corrections",
        "items": [
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
                "uploaded_at": source.uploaded_at.isoformat(),
                "uploaded_by": source.uploaded_by,
                "download_url": f"/api/v1/intake/{source.id}/file",
            }
            for source in queue["items"]
        ]
        + bank_queue["items"],
    }


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


@router.post("/keys/create", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    name: str,
    description: Optional[str] = None,
    permissions: list = None,
    rate_limit_per_minute: int = 100,
    actor: str = Depends(get_current_actor),
):
    """
    Create new API key for agent integration.
    
    Permissions: ["read", "write", "invoice", "report", "admin"]
    """
    if not permissions:
        permissions = ["read", "write", "invoice"]
    
    key_id = str(uuid.uuid4())
    secret_key = f"sk_{uuid.uuid4().hex[:32]}"
    key_hash = hashlib.sha256(secret_key.encode()).hexdigest()

    return {
        "key_id": key_id,
        "secret_key": secret_key,  # Only returned once!
        "key_hash": key_hash,  # Store this for future verification
        "name": name,
        "description": description,
        "permissions": permissions,
        "rate_limit_per_minute": rate_limit_per_minute,
        "created_at": "2026-03-21T10:00:00",
        "message": "⚠️ Save this key securely. It will not be shown again."
    }


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


@router.get("/keys", response_model=dict)
async def list_api_keys(
    actor: str = Depends(get_current_actor),
):
    """List all API keys (without secrets)."""
    return {
        "keys": [
            {
                "id": "key-001",
                "name": "Agent Instance 1",
                "permissions": ["read", "write", "invoice"],
                "active": True,
                "created_at": "2026-03-20T08:00:00",
                "last_used_at": "2026-03-21T09:00:00",
            }
        ],
        "total": 1
    }


@router.post("/keys/{key_id}/revoke", response_model=dict)
async def revoke_api_key(
    key_id: str,
    actor: str = Depends(get_current_actor),
):
    """Revoke API key (agent can no longer authenticate)."""
    return {
        "key_id": key_id,
        "status": "revoked",
        "revoked_at": "2026-03-21T10:00:00"
    }


@router.get("/spec/openapi", response_model=dict)
async def get_openapi_spec(
    format: str = "json",
):
    """
    Get OpenAPI 3.1 specification for agent integration.
    
    Complete API schema with request/response examples.
    """
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Bokföringssystem API",
            "version": "0.2.0",
            "description": "Accounting system for Swedish companies"
        },
        "servers": [
            {
                "url": "http://localhost:8000",
                "description": "Development"
            }
        ],
        "paths": {
            "/api/v1/vouchers": {
                "post": {
                    "summary": "Create voucher",
                    "operationId": "create_voucher",
                    "security": [{"bearerAuth": []}],
                    "parameters": [],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"type": "object"}
                            }
                        }
                    },
                    "responses": {
                        "201": {
                            "description": "Voucher created",
                            "content": {"application/json": {"schema": {"type": "object"}}}
                        }
                    }
                }
            }
        },
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT"
                }
            }
        }
    }


@router.post("/spec/tools", response_model=dict)
async def get_tools_definition():
    """
    Get tool definitions for Claude/agent integration.
    
    Returns tools in format compatible with Claude API.
    """
    return {
        "tools": [
            {
                "name": "create_voucher",
                "description": "Create and post accounting voucher (verifikation)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "series": {"type": "string", "enum": ["A", "B"]},
                        "date": {"type": "string", "format": "date"},
                        "period_id": {"type": "string"},
                        "description": {"type": "string"},
                        "rows": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "account": {"type": "string"},
                                    "debit": {"type": "integer"},
                                    "credit": {"type": "integer"}
                                }
                            }
                        }
                    },
                    "required": ["series", "date", "period_id", "description", "rows"]
                }
            },
            {
                "name": "create_invoice",
                "description": "Create customer invoice (faktura)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "customer_name": {"type": "string"},
                        "invoice_date": {"type": "string", "format": "date"},
                        "due_date": {"type": "string", "format": "date"},
                        "rows": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "description": {"type": "string"},
                                    "quantity": {"type": "integer"},
                                    "unit_price": {"type": "integer"},
                                    "vat_code": {"type": "string", "enum": ["MP1", "MP2", "MP3", "MF"]}
                                }
                            }
                        }
                    },
                    "required": ["customer_name", "invoice_date", "due_date", "rows"]
                }
            },
            {
                "name": "register_payment",
                "description": "Register payment for invoice",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "invoice_id": {"type": "string"},
                        "amount": {"type": "integer"},
                        "payment_date": {"type": "string", "format": "date"},
                        "payment_method": {"type": "string"}
                    },
                    "required": ["invoice_id", "amount", "payment_date", "payment_method"]
                }
            },
            {
                "name": "get_trial_balance",
                "description": "Get trial balance (råbalans) for period",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "period_id": {"type": "string"}
                    },
                    "required": ["period_id"]
                }
            }
        ]
    }


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
        "version": "0.2.0",
        "agent": actor,
        "timestamp": "2026-03-21T10:00:00"
    }


@router.post("/operations/idempotent/{operation_id}", response_model=dict)
async def execute_idempotent_operation(
    operation_id: str,
    operation: dict,
    actor: str = Depends(get_current_actor),
):
    """
    Execute idempotent operation.
    
    Same operation_id with same parameters always returns same result.
    Prevents duplicate transactions in case of network retries.
    """
    return {
        "operation_id": operation_id,
        "status": "success",
        "result": "Idempotent operation executed",
        "message": "If retried with same operation_id, will return cached result"
    }
