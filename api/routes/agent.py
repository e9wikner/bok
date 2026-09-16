"""API routes for agent integration (Fas 4)."""

from datetime import date as DateType
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.deps import get_current_actor, get_idempotency_key
from api.schemas import (
    AgentCurrentRunResponse,
    AgentLastRunResponse,
    AgentStatusResponse,
    VoucherRowRequest,
)
from config import settings
from domain.models import AgentRun
from domain.validation import ValidationError
from repositories.agent_run_repo import AgentRunRepository
from repositories.correction_note_repo import CorrectionNoteRepository
from repositories.intake_repo import IntakeRepository
from services.agent_runtime import get_runner, get_worker
from services.bank_inputs import BankInputError, BankInputService
from services.idempotency import IdempotencyOutcome, IdempotencyService
from services.intake import IntakeError, IntakeService
from services.voucher_posting import VoucherPostingRequest, post_agent_voucher

AGENT_VOUCHER_ENDPOINT = "POST /api/v1/agent/vouchers"

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
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/vouchers", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_and_post_agent_voucher(
    request: AgentVoucherRequest,
    actor: str = Depends(get_current_actor),
    idempotency_key: Optional[str] = Depends(get_idempotency_key),
):
    """Create and post a voucher directly from an accounting agent."""
    idempotency = IdempotencyService()
    reserved = False

    if idempotency_key:
        outcome = idempotency.begin(
            key=idempotency_key,
            endpoint=AGENT_VOUCHER_ENDPOINT,
            body=jsonable_encoder(request),
            actor=actor,
        )
        if outcome.kind == IdempotencyOutcome.REPLAY:
            return JSONResponse(
                status_code=outcome.response_status or status.HTTP_201_CREATED,
                content=outcome.response_payload,
                headers={"Idempotent-Replay": "true"},
            )
        if outcome.kind == IdempotencyOutcome.MISMATCH:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error": "Idempotency-Key already used for a different request",
                    "code": "idempotency_key_reuse",
                    "details": "The same key must carry the same request body",
                    "original_fingerprint": outcome.original_fingerprint,
                },
            )
        if outcome.kind == IdempotencyOutcome.IN_FLIGHT:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "A request with this Idempotency-Key is in flight",
                    "code": "request_in_flight",
                    "details": "Retry with the same key to get the stored response",
                    "retry_after_ms": 500,
                },
            )
        reserved = True

    try:
        return _create_and_post_voucher(request, actor, idempotency, idempotency_key)
    except Exception:
        if reserved and idempotency_key:
            idempotency.release(idempotency_key, AGENT_VOUCHER_ENDPOINT)
        raise


def _create_and_post_voucher(
    request: AgentVoucherRequest,
    actor: str,
    idempotency: IdempotencyService,
    idempotency_key: Optional[str],
) -> dict:
    """Call the posting service and map its domain errors to HTTP."""
    posting_request = VoucherPostingRequest(
        date=request.date,
        period_id=request.period_id,
        description=request.description,
        rows=[row.model_dump() for row in request.rows],
        series=request.series,
        reasoning_summary=request.reasoning_summary,
        intake_source_ids=request.intake_source_ids,
        bank_input_ids=request.bank_input_ids,
        bank_transaction_ids=request.bank_transaction_ids,
    )
    try:
        return post_agent_voucher(
            request=posting_request,
            actor=actor,
            idempotency=idempotency,
            idempotency_key=idempotency_key,
            endpoint=AGENT_VOUCHER_ENDPOINT,
        )
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        )


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
        "total": queue["total"]
        + bank_queue["total"]
        + correction_note_repo.count_pending(),
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
    elif exc.code in {
        "intake_not_processable",
        "intake_already_linked",
        "voucher_not_posted",
    }:
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_400_BAD_REQUEST
    return HTTPException(
        status_code=status_code,
        detail={"error": exc.message, "code": exc.code, "details": exc.details},
    )


def _bank_input_http_error(exc: BankInputError) -> HTTPException:
    if exc.code in {
        "bank_input_not_found",
        "bank_connection_not_found",
        "bank_transaction_not_found",
    }:
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


def _run_core_fields(run: AgentRun) -> dict:
    """Fields shared between `current_run` and `last_run` (SPEC §8)."""
    return {
        "id": run.id,
        "started_at": run.started_at.isoformat(),
        "trigger": run.trigger,
        "model": run.model,
        "protocol": run.protocol,
        "items_seen": run.items_seen,
        "items_posted": run.items_posted,
        "items_abstained": run.items_abstained,
    }


@router.get("/status", response_model=AgentStatusResponse)
async def get_agent_status(
    actor: str = Depends(get_current_actor),
):
    """`GET /api/v1/agent/status` (SPEC-agentruntime.md §8).

    Replaces the old `GET /agent/operations/log` stub, which always
    returned an empty list. Read-only aggregation of independent sources --
    no business logic lives here, per AGENTS.md's layering rule:

    - `enabled`/`running` come from `AgentRunner.status()`
      (`services.agent_runtime`) -- whether the background thread is
      enabled/alive, not whether a pass happens to be running right now.
    - `current_run` is `AgentRunRepository.get_current()`'s row (`None` if
      no pass is in progress) plus `current_source_id`/`current_activity`
      from the process-wide `AgentWorker`. That worker tracks exactly which
      source it is on (`current_source_id`), but `current_activity` is
      deliberately coarse -- `"processing"` while a session runs for that
      source, `None` otherwise -- rather than the live tool name SPEC §8's
      example shows (`"las_kontoplan"`): `services.agent_session.
      run_session`'s manual tool-call loop (task A8) has no per-call hook to
      report progress through without touching that loop, which this task's
      instructions call out as a risk to the existing test suite. See
      `AgentWorker.__init__`'s docstring for the same note from the
      producer's side.
    - `last_run` is `AgentRunRepository.get_last_completed_or_failed()`'s
      row (`None` if no run has ever finished).
    - `queue_depth` is `IntakeRepository.count_pending()` -- a plain
      `COUNT(*)`, not `IntakeService().get_pending_queue()`, which would
      materialize every pending row just to report how many there are.
    - `cost_today_ore`/`budget_today_ore` are
      `AgentRunRepository.sum_cost_today_ore()` and
      `settings.agent_daily_budget_ore`.
    - The top-level `last_error` is the runner's own last in-thread failure
      (`AgentRunner.status()["last_error"]`) -- e.g. an `UnknownModelError`
      or `DailyBudgetExhaustedError` raised before a pass could even create
      its `agent_runs` row -- which `last_run.last_error` (that specific
      finished run's own column) cannot show. Both are surfaced: neither is
      dropped in favor of the other.

    SPEC §12.6: the LLM gateway's API key setting is never read anywhere in
    this function or in `AgentStatusResponse`/`AgentCurrentRunResponse`/
    `AgentLastRunResponse` (`api/schemas.py`) -- `TestAgentStatusEndpoint` in
    `tests/test_agent_runtime.py` pins this with a monkeypatched key value
    and asserts it is absent from the serialized response body.
    """
    runner_status = get_runner().status()
    worker = get_worker()

    current_run_row = AgentRunRepository.get_current()
    current_run = None
    if current_run_row is not None:
        current_run = AgentCurrentRunResponse(
            **_run_core_fields(current_run_row),
            current_source_id=worker.current_source_id,
            current_activity=worker.current_activity,
        )

    last_run_row = AgentRunRepository.get_last_completed_or_failed()
    last_run = None
    if last_run_row is not None:
        last_run = AgentLastRunResponse(
            **_run_core_fields(last_run_row),
            finished_at=(
                last_run_row.finished_at.isoformat()
                if last_run_row.finished_at
                else None
            ),
            status=last_run_row.status,
            cost_ore=last_run_row.cost_ore,
            last_error=last_run_row.last_error,
        )

    return AgentStatusResponse(
        enabled=runner_status["enabled"],
        running=runner_status["running"],
        current_run=current_run,
        last_run=last_run,
        queue_depth=IntakeRepository.count_pending(),
        cost_today_ore=AgentRunRepository.sum_cost_today_ore(),
        budget_today_ore=settings.agent_daily_budget_ore,
        last_error=runner_status["last_error"],
    )


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
