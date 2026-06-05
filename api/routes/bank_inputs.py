"""API routes for bank input source material."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi import status as http_status
from fastapi.responses import FileResponse

from api.deps import get_current_actor
from domain.models import BankInput
from repositories.account_repo import AccountRepository
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
from services.bank_integration import BankConnection, BankIntegrationService

router = APIRouter(prefix="/api/v1/bank-inputs", tags=["bank-inputs"])
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@router.post("", response_model=dict, status_code=http_status.HTTP_201_CREATED)
async def upload_bank_input(
    file: UploadFile = File(...),
    bank_connection_id: str = Form(...),
    actor: str = Depends(get_current_actor),
):
    """Upload bank CSV source material before agent voucher posting."""
    content = await _read_limited_upload(file)
    resolved_bank_connection_id = _resolve_bank_connection_reference(bank_connection_id)
    try:
        bank_input = BankInputService().create_from_upload_content(
            filename=file.filename,
            content_type=file.content_type,
            content=content,
            bank_connection_id=resolved_bank_connection_id,
            actor=actor,
        )
        return _bank_input_to_dict(bank_input)
    except BankInputError as exc:
        raise _http_error(exc) from exc


@router.get("/connections", response_model=dict)
async def list_bank_input_connections(
    include_inactive: bool = False,
    actor: str = Depends(get_current_actor),
):
    """List bank account options for bank CSV upload."""
    connections = BankIntegrationService().get_connections()
    if not include_inactive:
        connections = [conn for conn in connections if conn.status == "active"]

    connections = _merge_manual_account_options(connections)

    return {
        "items": [
            {
                "id": conn.id,
                "provider": conn.provider,
                "bank_name": conn.bank_name,
                "display_name": _connection_display_name(conn),
                "account_number": conn.account_number,
                "iban": conn.iban,
                "currency": conn.currency,
                "status": conn.status,
            }
            for conn in connections
        ]
    }


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


@router.delete("/{bank_input_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_bank_input(
    bank_input_id: str,
    actor: str = Depends(get_current_actor),
):
    """Delete a bank input that has not been successfully processed."""
    try:
        BankInputService().delete_unprocessed(bank_input_id)
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


async def _read_limited_upload(file: UploadFile) -> bytes:
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={"error": "File too large", "code": "file_too_large"},
        )
    return content


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


def _connection_display_name(conn) -> str:
    identifier = conn.account_number or conn.iban
    if identifier:
        return f"{identifier} - {conn.bank_name}"
    return conn.bank_name


def _merge_manual_account_options(connections: list[BankConnection]) -> list[BankConnection]:
    """Add chart-of-accounts options without duplicating live connections."""
    seen_account_numbers = {conn.account_number for conn in connections if conn.account_number}
    connections.extend(
        manual_connection
        for manual_connection in _manual_account_connections()
        if manual_connection.account_number not in seen_account_numbers
    )
    return connections


def _manual_account_connections() -> list[BankConnection]:
    manual_connections = []
    for account in AccountRepository.list_all(active_only=True):
        manual_connections.append(
            BankConnection(
                id=f"account:{account.code}",
                provider="manual",
                bank_name=account.name,
                account_number=account.code,
                currency="SEK",
                status="active",
            )
        )
    return manual_connections


def _resolve_bank_connection_reference(bank_connection_id: str) -> str:
    if not bank_connection_id.startswith("account:"):
        return bank_connection_id

    account_code = bank_connection_id.split(":", 1)[1]
    if not account_code:
        return bank_connection_id

    service = BankIntegrationService()
    for connection in service.get_connections():
        if connection.account_number == account_code and connection.status == "active":
            return connection.id

    account = AccountRepository.get(account_code)
    if not account or not account.active:
        return bank_connection_id

    connection = service.create_connection(
        provider="manual",
        bank_name=account.name,
        account_number=account.code,
        currency="SEK",
    )
    return connection.id
