"""API routes for voucher source intake."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi import status as http_status
from fastapi.responses import FileResponse

from api.deps import get_current_actor
from domain.models import BankInput, IntakeProcessingAttempt, IntakeSource, VoucherIntakeSource
from domain.types import BankInputStatus, IntakeStatus
from repositories.bank_input_repo import BankInputRepository
from repositories.intake_repo import IntakeRepository
from services.intake import (
    DuplicateIntakeSourceError,
    IntakeConflictError,
    IntakeError,
    IntakeFileAccessError,
    IntakeNotFoundError,
    IntakeService,
    IntakeValidationError,
)

router = APIRouter(prefix="/api/v1/intake", tags=["intake"])
VALID_WORKSPACE_KINDS = {"voucher_source", "bank_input"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@router.post("", response_model=dict, status_code=http_status.HTTP_201_CREATED)
async def upload_intake_source(
    file: UploadFile = File(...),
    explanation: str | None = Form(None),
    source_type: str | None = Form(None),
    actor: str = Depends(get_current_actor),
):
    """Upload voucher source material before a voucher exists."""
    content = await _read_limited_upload(file)
    try:
        source = IntakeService().create_source_from_upload_content(
            filename=file.filename,
            content_type=file.content_type,
            content=content,
            explanation=explanation,
            source_type=source_type,
            actor=actor,
        )
        return _source_to_dict(source)
    except IntakeError as exc:
        raise _http_error(exc) from exc


@router.get("/workspace", response_model=dict)
async def list_intake_workspace(
    status: str | None = None,
    kind: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    actor: str = Depends(get_current_actor),
):
    """List voucher sources and bank inputs for human intake review."""
    _validate_workspace_filters(status=status, kind=kind)
    intake_repo = IntakeService().sources
    bank_repo = BankInputRepository()

    include_sources = kind in (None, "voucher_source")
    include_bank_inputs = kind in (None, "bank_input")
    items = []
    total = 0

    if include_sources:
        source_limit = limit if kind == "voucher_source" else limit + offset
        source_offset = offset if kind == "voucher_source" else 0
        sources = intake_repo.list_by_status(
            status=status,
            limit=source_limit,
            offset=source_offset,
        )
        total += intake_repo.count_by_status(status=status)
        items.extend(_workspace_source_item(source, intake_repo) for source in sources)

    if include_bank_inputs:
        bank_limit = limit if kind == "bank_input" else limit + offset
        bank_offset = offset if kind == "bank_input" else 0
        bank_inputs = bank_repo.list_by_status(
            status=status,
            limit=bank_limit,
            offset=bank_offset,
        )
        total += bank_repo.count_by_status(status=status)
        items.extend(_workspace_bank_item(bank_input, bank_repo) for bank_input in bank_inputs)

    items.sort(key=lambda item: item["uploaded_at"])
    page_items = items if kind is not None else items[offset : offset + limit]
    return {
        "items": page_items[:limit],
        "total": total,
        "limit": limit,
        "offset": offset,
        "status_counts": _workspace_status_counts(
            include_sources=include_sources,
            include_bank_inputs=include_bank_inputs,
            intake_repo=intake_repo,
            bank_repo=bank_repo,
        ),
    }


@router.get("/workspace/{kind}/{item_id}", response_model=dict)
async def get_intake_workspace_detail(
    kind: str,
    item_id: str,
    actor: str = Depends(get_current_actor),
):
    """Get full intake detail for a voucher source or bank input."""
    if kind not in VALID_WORKSPACE_KINDS:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail={"error": "Unsupported intake workspace item kind", "code": "intake_kind_not_found"},
        )

    if kind == "voucher_source":
        service = IntakeService()
        try:
            source = service.get_source(item_id)
        except IntakeError as exc:
            raise _http_error(exc) from exc
        return {
            **_workspace_source_item(source, service.sources),
            "processing_attempts": [
                _attempt_to_dict(attempt)
                for attempt in service.list_attempts_for_source(source.id)
            ],
            "voucher_links": [
                _voucher_source_link_to_dict(link)
                for link in service.sources.list_links_for_source(source.id)
            ],
            "deleted_at": source.deleted_at.isoformat() if source.deleted_at else None,
            "deleted_by": source.deleted_by,
        }

    bank_repo = BankInputRepository()
    bank_input = bank_repo.get_bank_input(item_id)
    if not bank_input:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail={"error": "Bank input not found", "code": "bank_input_not_found"},
        )
    return {
        **_workspace_bank_item(bank_input, bank_repo),
        "processed_at": bank_input.processed_at.isoformat() if bank_input.processed_at else None,
        "voucher_links": [
            _bank_input_link_to_dict(link)
            for link in bank_repo.list_voucher_links_for_input(bank_input.id)
        ],
        "transactions": bank_repo.list_transaction_signals_for_input(bank_input.id),
    }


@router.get("/{source_id}", response_model=dict)
async def get_intake_source(
    source_id: str,
    actor: str = Depends(get_current_actor),
):
    """Get intake source metadata."""
    try:
        return _source_to_dict(IntakeService().get_source(source_id))
    except IntakeError as exc:
        raise _http_error(exc) from exc


@router.get("/{source_id}/file")
async def get_intake_source_file(
    source_id: str,
    actor: str = Depends(get_current_actor),
):
    """Download the original intake source file."""
    service = IntakeService()
    try:
        source = service.get_source(source_id)
        stored_path = service.resolve_source_file(source)
        return FileResponse(
            path=str(stored_path),
            media_type=source.mime_type,
            filename=source.original_filename,
        )
    except IntakeError as exc:
        raise _http_error(exc) from exc


@router.delete("/{source_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_intake_source(
    source_id: str,
    actor: str = Depends(get_current_actor),
):
    """Soft-delete an intake source that has not been processed."""
    try:
        IntakeService().soft_delete(source_id, actor)
    except IntakeError as exc:
        raise _http_error(exc) from exc


def _source_to_dict(source: IntakeSource) -> dict:
    return {
        "id": source.id,
        "source_type": source.source_type.value if source.source_type else None,
        "status": source.status.value,
        "original_filename": source.original_filename,
        "mime_type": source.mime_type,
        "size_bytes": source.size_bytes,
        "sha256": source.sha256,
        "explanation": source.explanation,
        "uploaded_by": source.uploaded_by,
        "uploaded_at": source.uploaded_at.isoformat(),
        "deleted_at": source.deleted_at.isoformat() if source.deleted_at else None,
        "deleted_by": source.deleted_by,
    }


def _validate_workspace_filters(status: str | None, kind: str | None) -> None:
    if kind is not None and kind not in VALID_WORKSPACE_KINDS:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={"error": "Invalid intake kind", "code": "invalid_intake_kind"},
        )
    if status is None:
        return
    valid_statuses = {status.value for status in IntakeStatus} | {
        status.value for status in BankInputStatus
    }
    if status not in valid_statuses:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={"error": "Invalid intake status", "code": "invalid_intake_status"},
        )


async def _read_limited_upload(file: UploadFile) -> bytes:
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={"error": "File too large", "code": "file_too_large"},
        )
    return content


def _workspace_source_item(source: IntakeSource, repo: IntakeRepository) -> dict:
    attempts = repo.list_attempts_for_source(source.id)
    latest_attempt = attempts[-1] if attempts else None
    links = repo.list_links_for_source(source.id)
    return {
        "kind": "voucher_source",
        "id": source.id,
        "source_type": source.source_type.value if source.source_type else None,
        "status": source.status.value,
        "original_filename": source.original_filename,
        "mime_type": source.mime_type,
        "size_bytes": source.size_bytes,
        "sha256": source.sha256,
        "explanation": source.explanation,
        "uploaded_by": source.uploaded_by,
        "uploaded_at": source.uploaded_at.isoformat(),
        "download_url": f"/api/v1/intake/{source.id}/file",
        "latest_processing_summary": latest_attempt.summary if latest_attempt else None,
        "latest_error_detail": latest_attempt.error_detail if latest_attempt else None,
        "linked_voucher_ids": [link.voucher_id for link in links],
    }


def _workspace_bank_item(bank_input: BankInput, repo: BankInputRepository) -> dict:
    transaction_ids = repo.list_transaction_ids_for_input(bank_input.id)
    links = repo.list_voucher_links_for_input(bank_input.id)
    return {
        "kind": "bank_input",
        "id": bank_input.id,
        "bank_connection_id": bank_input.bank_connection_id,
        "status": bank_input.status.value,
        "original_filename": bank_input.original_filename,
        "mime_type": bank_input.mime_type,
        "size_bytes": bank_input.size_bytes,
        "sha256": bank_input.sha256,
        "uploaded_by": bank_input.uploaded_by,
        "uploaded_at": bank_input.uploaded_at.isoformat(),
        "download_url": f"/api/v1/bank-inputs/{bank_input.id}/file",
        "imported_count": bank_input.imported_count,
        "skipped_count": bank_input.skipped_count,
        "detected_format": bank_input.detected_format,
        "parse_error": bank_input.parse_error,
        "transaction_ids": transaction_ids,
        "transaction_count": len(transaction_ids),
        "match_signals": repo.list_transaction_signals_for_input(bank_input.id),
        "linked_voucher_ids": [link.voucher_id for link in links],
    }


def _workspace_status_counts(
    include_sources: bool,
    include_bank_inputs: bool,
    intake_repo: IntakeRepository,
    bank_repo: BankInputRepository,
) -> dict[str, int]:
    statuses = sorted(
        {status.value for status in IntakeStatus}
        | {status.value for status in BankInputStatus}
    )
    counts = {}
    for status in statuses:
        count = 0
        if include_sources:
            count += intake_repo.count_by_status(status)
        if include_bank_inputs:
            count += bank_repo.count_by_status(status)
        counts[status] = count
    return counts


def _attempt_to_dict(attempt: IntakeProcessingAttempt) -> dict:
    return {
        "id": attempt.id,
        "intake_source_id": attempt.intake_source_id,
        "status": attempt.status.value,
        "summary": attempt.summary,
        "warnings": attempt.warnings or [],
        "error_detail": attempt.error_detail,
        "voucher_id": attempt.voucher_id,
        "actor": attempt.actor,
        "created_at": attempt.created_at.isoformat(),
    }


def _voucher_source_link_to_dict(link: VoucherIntakeSource) -> dict:
    return {
        "id": link.id,
        "voucher_id": link.voucher_id,
        "intake_source_id": link.intake_source_id,
        "linked_by": link.linked_by,
        "linked_at": link.linked_at.isoformat(),
        "link_reason": link.link_reason,
    }


def _bank_input_link_to_dict(link) -> dict:
    return {
        "id": link.id,
        "voucher_id": link.voucher_id,
        "bank_input_id": link.bank_input_id,
        "linked_by": link.linked_by,
        "linked_at": link.linked_at.isoformat(),
    }


def _http_error(exc: IntakeError) -> HTTPException:
    status_code = http_status.HTTP_400_BAD_REQUEST
    if isinstance(exc, DuplicateIntakeSourceError):
        status_code = http_status.HTTP_409_CONFLICT
    elif isinstance(exc, IntakeNotFoundError):
        status_code = http_status.HTTP_404_NOT_FOUND
    elif isinstance(exc, IntakeConflictError):
        status_code = http_status.HTTP_409_CONFLICT
    elif isinstance(exc, IntakeFileAccessError):
        status_code = (
            http_status.HTTP_404_NOT_FOUND
            if exc.code == "intake_file_missing"
            else http_status.HTTP_403_FORBIDDEN
        )
    elif isinstance(exc, IntakeValidationError):
        status_code = http_status.HTTP_400_BAD_REQUEST

    return HTTPException(
        status_code=status_code,
        detail={"error": exc.message, "code": exc.code, "details": exc.details},
    )
