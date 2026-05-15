"""API routes for bank input source material."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi import status as http_status
from fastapi.responses import FileResponse

from api.deps import get_current_actor
from domain.models import BankInput
from services.bank_inputs import (
    BankConnectionNotFoundError,
    BankInputConflictError,
    BankInputError,
    BankInputFileAccessError,
    BankInputNotFoundError,
    BankInputService,
    BankInputValidationError,
    DuplicateBankInputError,
)

router = APIRouter(prefix="/api/v1/bank-inputs", tags=["bank-inputs"])


@router.post("", response_model=dict, status_code=http_status.HTTP_201_CREATED)
async def upload_bank_input(
    file: UploadFile = File(...),
    bank_connection_id: str = Form(...),
    actor: str = Depends(get_current_actor),
):
    """Upload bank CSV source material before agent voucher posting."""
    content = file.file.read()
    try:
        bank_input = BankInputService().create_from_upload_content(
            filename=file.filename,
            content_type=file.content_type,
            content=content,
            bank_connection_id=bank_connection_id,
            actor=actor,
        )
        return _bank_input_to_dict(bank_input)
    except BankInputError as exc:
        raise _http_error(exc) from exc


@router.get("/{bank_input_id}", response_model=dict)
async def get_bank_input(
    bank_input_id: str,
    actor: str = Depends(get_current_actor),
):
    """Get bank input metadata."""
    try:
        return _bank_input_to_dict(BankInputService().get_bank_input(bank_input_id))
    except BankInputError as exc:
        raise _http_error(exc) from exc


@router.get("/{bank_input_id}/file")
async def get_bank_input_file(
    bank_input_id: str,
    actor: str = Depends(get_current_actor),
):
    """Download the original bank CSV file."""
    service = BankInputService()
    try:
        bank_input = service.get_bank_input(bank_input_id)
        stored_path = service.resolve_input_file(bank_input)
        return FileResponse(
            path=str(stored_path),
            media_type=bank_input.mime_type,
            filename=bank_input.original_filename,
        )
    except BankInputError as exc:
        raise _http_error(exc) from exc


def _bank_input_to_dict(bank_input: BankInput) -> dict:
    return {
        "id": bank_input.id,
        "bank_connection_id": bank_input.bank_connection_id,
        "status": bank_input.status.value,
        "original_filename": bank_input.original_filename,
        "mime_type": bank_input.mime_type,
        "size_bytes": bank_input.size_bytes,
        "sha256": bank_input.sha256,
        "uploaded_by": bank_input.uploaded_by,
        "uploaded_at": bank_input.uploaded_at.isoformat(),
        "detected_format": bank_input.detected_format,
        "imported_count": bank_input.imported_count,
        "skipped_count": bank_input.skipped_count,
        "parse_error": bank_input.parse_error,
        "processed_at": bank_input.processed_at.isoformat() if bank_input.processed_at else None,
    }


def _http_error(exc: BankInputError) -> HTTPException:
    status_code = http_status.HTTP_400_BAD_REQUEST
    if isinstance(exc, DuplicateBankInputError):
        status_code = http_status.HTTP_409_CONFLICT
    elif isinstance(exc, (BankInputNotFoundError, BankConnectionNotFoundError)):
        status_code = http_status.HTTP_404_NOT_FOUND
    elif isinstance(exc, BankInputConflictError):
        status_code = http_status.HTTP_409_CONFLICT
    elif isinstance(exc, BankInputFileAccessError):
        status_code = (
            http_status.HTTP_404_NOT_FOUND
            if exc.code == "bank_input_file_missing"
            else http_status.HTTP_403_FORBIDDEN
        )
    elif isinstance(exc, BankInputValidationError):
        status_code = http_status.HTTP_400_BAD_REQUEST

    return HTTPException(
        status_code=status_code,
        detail={"error": exc.message, "code": exc.code, "details": exc.details},
    )
