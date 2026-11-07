"""API routes for bank input source material."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi import status as http_status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api.deps import get_current_actor
from domain.models import BankInput
from repositories.bank_input_repo import BankInputRepository
from services.bank_inputs import (
    AUTO_CONNECTION_REFERENCE,
    BankConnectionNotFoundError,
    BankInputConflictError,
    BankInputError,
    BankInputFileAccessError,
    BankInputNotFoundError,
    BankInputService,
    BankInputValidationError,
    BankTransactionNotFoundError,
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
    """Upload a bank CSV (an account statement).

    `bank_connection_id` is a connection id, `account:<kontokod>`, or `auto`
    -- the account is then read from the file name's leading account code,
    or is 1630 for Skatteverket's tax-account export (the chat's upload).
    Imported transactions that are the underlag of already posted vouchers
    are linked to them at once; the answer says how many vouchers that is
    (`linked_voucher_count`) and which account (`account_code`)."""
    content = await _read_limited_upload(file)
    service = BankInputService()
    try:
        reference = bank_connection_id
        if reference == AUTO_CONNECTION_REFERENCE:
            reference = service.resolve_auto_reference(file.filename, content)
        connection_id = service.resolve_connection_reference(reference)
        bank_input = service.create_from_upload_content(
            filename=file.filename,
            content_type=file.content_type,
            content=content,
            bank_connection_id=connection_id,
            actor=actor,
        )
        connection = BankIntegrationService().get_connection(connection_id)
        return {
            **_bank_input_to_dict(bank_input),
            "account_code": connection.account_number if connection else None,
            "linked_voucher_count": len(
                BankInputRepository.list_voucher_links_for_input(bank_input.id)
            ),
        }
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


class UnlinkBankTransactionRequest(BaseModel):
    reason: str = Field(..., description="Why the link is wrong; kept in the trace")


@router.post("/transactions/{bank_transaction_id}/unlink", response_model=dict)
async def unlink_bank_transaction(
    bank_transaction_id: str,
    request: UnlinkBankTransactionRequest,
    actor: str = Depends(get_current_actor),
):
    """Undo a statement transaction's link to a posted voucher
    (`services/statement_match.py`, migration 040). The link row stays and a
    `voucher_bank_transaction_unlinks` row says it no longer holds; the
    voucher is not touched. The transaction is never again linked
    automatically -- only by `koppla_banktransaktion`.

    - `400 unlink_reason_required`
    - `404 bank_transaction_not_found`
    - `409 bank_transaction_not_linked`
    """
    from services.statement_match import StatementMatchService

    try:
        return StatementMatchService().unlink(
            bank_transaction_id, reason=request.reason, actor=actor
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
        "processed_at": (
            bank_input.processed_at.isoformat() if bank_input.processed_at else None
        ),
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
    elif isinstance(
        exc,
        (
            BankInputNotFoundError,
            BankConnectionNotFoundError,
            BankTransactionNotFoundError,
        ),
    ):
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


def _merge_manual_account_options(
    connections: list[BankConnection],
) -> list[BankConnection]:
    """Add chart-of-accounts options without duplicating live connections."""
    seen_account_numbers = {
        conn.account_number for conn in connections if conn.account_number
    }
    connections.extend(
        manual_connection
        for manual_connection in _manual_account_connections()
        if manual_connection.account_number not in seen_account_numbers
    )
    return connections


def _manual_account_connections() -> list[BankConnection]:
    return BankInputService().statement_account_connections()
