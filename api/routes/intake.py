"""API routes for voucher source intake."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi import status as http_status
from fastapi.responses import FileResponse

from api.deps import get_current_actor
from domain.models import IntakeSource
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


@router.post("", response_model=dict, status_code=http_status.HTTP_201_CREATED)
async def upload_intake_source(
    file: UploadFile = File(...),
    explanation: str | None = Form(None),
    source_type: str | None = Form(None),
    actor: str = Depends(get_current_actor),
):
    """Upload voucher source material before a voucher exists."""
    content = file.file.read()
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
    """Soft-delete a pending intake source."""
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
