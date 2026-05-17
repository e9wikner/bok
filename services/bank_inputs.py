"""Service for uploaded bank input source material."""

from pathlib import Path
import hashlib
import sqlite3
import uuid

from config import settings
from db.database import db
from domain.models import BankInput
from domain.types import BankInputStatus
from domain.validation import ValidationError
from repositories.bank_input_repo import BankInputRepository
from services.bank_integration import BankIntegrationService


class BankInputError(Exception):
    """Base error for bank input workflow failures."""

    def __init__(self, code: str, message: str, details: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


class DuplicateBankInputError(BankInputError):
    """Raised when uploaded bank input bytes already exist."""

    def __init__(self, sha256: str, existing_id: str | None = None):
        details = f"sha256={sha256}"
        if existing_id:
            details += f", existing_id={existing_id}"
        super().__init__("duplicate_bank_input", "This bank input was already uploaded", details)
        self.sha256 = sha256
        self.existing_id = existing_id


class BankInputNotFoundError(BankInputError):
    """Raised when a bank input cannot be found."""

    def __init__(self, bank_input_id: str):
        super().__init__("bank_input_not_found", "Bank input not found", f"bank_input_id={bank_input_id}")


class BankConnectionNotFoundError(BankInputError):
    """Raised when a selected bank connection cannot be found."""

    def __init__(self, bank_connection_id: str):
        super().__init__(
            "bank_connection_not_found",
            "Bank connection not found",
            f"bank_connection_id={bank_connection_id}",
        )


class BankTransactionNotFoundError(BankInputError):
    """Raised when a selected bank transaction cannot be found."""

    def __init__(self, bank_transaction_id: str):
        super().__init__(
            "bank_transaction_not_found",
            "Bank transaction not found",
            f"bank_transaction_id={bank_transaction_id}",
        )


class BankInputValidationError(BankInputError):
    """Raised when bank input data is invalid."""


class BankInputConflictError(BankInputError):
    """Raised when bank input state conflicts with the requested action."""


class BankInputFileAccessError(BankInputError):
    """Raised when a bank input file cannot be safely served."""


class BankInputService:
    """Coordinate bank CSV storage and bank-input lifecycle."""

    ALLOWED_MIME_TYPES = {
        "text/csv",
        "application/csv",
        "application/vnd.ms-excel",
    }
    MAX_FILE_SIZE = 10 * 1024 * 1024

    def __init__(self):
        self.inputs = BankInputRepository()
        self.bank = BankIntegrationService()

    def create_from_upload_content(
        self,
        filename: str | None,
        content_type: str | None,
        content: bytes,
        bank_connection_id: str,
        actor: str,
    ) -> BankInput:
        """Persist uploaded CSV bytes and create a pending bank input."""
        original_filename = filename or "bank-input.csv"
        mime_type = content_type or ""
        self._validate_upload(original_filename, mime_type, content)
        self._validate_active_connection(bank_connection_id)

        sha256 = hashlib.sha256(content).hexdigest()
        existing = self.inputs.get_by_sha256(sha256)
        if existing:
            raise DuplicateBankInputError(sha256, existing.id)

        bank_input_id = str(uuid.uuid4())
        stored_path = self._stored_path_for(bank_input_id, original_filename)
        stored_path.parent.mkdir(parents=True, exist_ok=True)
        stored_path.write_bytes(content)
        bank_input_created = False

        try:
            with db.transaction():
                bank_input = self.inputs.create_bank_input(
                    bank_input_id=bank_input_id,
                    bank_connection_id=bank_connection_id,
                    original_filename=original_filename,
                    mime_type=mime_type,
                    size_bytes=len(content),
                    sha256=sha256,
                    stored_path=str(stored_path),
                    uploaded_by=actor,
                    status=BankInputStatus.PENDING.value,
                    _commit=False,
                )
                bank_input_created = True
            return self._process_persisted_input(bank_input, content)
        except sqlite3.IntegrityError as exc:
            self._cleanup_stored_file(stored_path)
            if "sha256" in str(exc).lower() or "unique" in str(exc).lower():
                existing = self.inputs.get_by_sha256(sha256)
                raise DuplicateBankInputError(sha256, existing.id if existing else None) from exc
            raise
        except Exception:
            if not bank_input_created:
                self._cleanup_stored_file(stored_path)
            raise

    def get_bank_input(self, bank_input_id: str) -> BankInput:
        bank_input = self.inputs.get_bank_input(bank_input_id)
        if not bank_input:
            raise BankInputNotFoundError(bank_input_id)
        return bank_input

    def resolve_input_file(self, bank_input: BankInput) -> Path:
        """Return a stored file path only if it remains inside the bank-input root."""
        root = Path(settings.bank_input_dir).resolve()
        candidate = Path(bank_input.stored_path).resolve()
        if candidate != root and not candidate.is_relative_to(root):
            raise BankInputFileAccessError(
                "bank_input_file_outside_root",
                "Bank input file path is outside configured storage root",
                f"bank_input_id={bank_input.id}",
            )
        if not candidate.exists():
            raise BankInputFileAccessError(
                "bank_input_file_missing",
                "Bank input file missing from storage",
                f"bank_input_id={bank_input.id}",
            )
        return candidate

    def list_agent_relevant(self, limit: int = 100, offset: int = 0) -> dict:
        """Return bank inputs relevant to the agent intake queue."""
        return {
            "total": self.inputs.count_agent_relevant(),
            "limit": limit,
            "offset": offset,
            "items": self.inputs.list_by_status(status=None, limit=limit, offset=offset),
        }

    def agent_queue_items(self, limit: int = 100, offset: int = 0) -> dict:
        """Return compact bank input items for the agent intake queue."""
        queue = self.list_agent_relevant(limit=limit, offset=offset)
        items = []
        for bank_input in queue["items"]:
            transaction_ids = self.inputs.list_transaction_ids_for_input(bank_input.id)
            items.append(
                {
                    "kind": "bank_input",
                    "id": bank_input.id,
                    "status": bank_input.status.value,
                    "bank_connection_id": bank_input.bank_connection_id,
                    "original_filename": bank_input.original_filename,
                    "mime_type": bank_input.mime_type,
                    "size_bytes": bank_input.size_bytes,
                    "sha256": bank_input.sha256,
                    "uploaded_at": bank_input.uploaded_at.isoformat(),
                    "uploaded_by": bank_input.uploaded_by,
                    "download_url": f"/api/v1/bank-inputs/{bank_input.id}/file",
                    "imported_count": bank_input.imported_count,
                    "skipped_count": bank_input.skipped_count,
                    "detected_format": bank_input.detected_format,
                    "parse_error": bank_input.parse_error,
                    "transaction_ids": transaction_ids,
                    "transaction_count": len(transaction_ids),
                    "match_signals": self.inputs.list_transaction_signals_for_input(bank_input.id),
                }
            )
        return {**queue, "items": items}

    def ensure_transactions_available(
        self,
        bank_input_ids: list[str],
        bank_transaction_ids: list[str],
    ) -> None:
        """Validate bank inputs and linked transactions before voucher creation."""
        bank_input_ids = _unique_preserve_order(bank_input_ids)
        bank_transaction_ids = _unique_preserve_order(bank_transaction_ids)
        if bank_transaction_ids and not bank_input_ids:
            raise BankInputValidationError(
                "missing_bank_input_traceability",
                "Bank transaction IDs require at least one bank input ID",
            )

        input_id_set = set(bank_input_ids)
        for bank_input_id in bank_input_ids:
            bank_input = self.get_bank_input(bank_input_id)
            if bank_input.status != BankInputStatus.PROCESSED:
                raise BankInputConflictError(
                    "bank_input_not_processed",
                    "Only processed bank inputs can be used for posting",
                    f"bank_input_id={bank_input_id}, status={bank_input.status.value}",
                )

        for transaction_id in bank_transaction_ids:
            transaction = self.bank.get_transaction(transaction_id)
            if not transaction:
                raise BankTransactionNotFoundError(transaction_id)
            linked_input_ids = set(self.inputs.list_input_ids_for_transaction(transaction_id))
            if not linked_input_ids.intersection(input_id_set):
                raise BankInputConflictError(
                    "bank_transaction_not_linked",
                    "Bank transaction is not linked to the supplied bank input",
                    f"bank_transaction_id={transaction_id}",
                )
            if transaction.status == "booked":
                raise BankInputConflictError(
                    "bank_transaction_already_booked",
                    "Bank transaction is already booked",
                    f"bank_transaction_id={transaction_id}",
                )
            if transaction.matched_voucher_id is not None:
                raise BankInputConflictError(
                    "bank_transaction_already_matched",
                    "Bank transaction is already matched to a voucher",
                    f"bank_transaction_id={transaction_id}, voucher_id={transaction.matched_voucher_id}",
                )

    def link_posted_voucher(
        self,
        voucher_id: str,
        bank_input_ids: list[str],
        bank_transaction_ids: list[str],
        actor: str,
        _commit: bool = True,
    ) -> dict:
        """Persist bank traceability and mark used transactions booked."""
        bank_input_ids = _unique_preserve_order(bank_input_ids)
        bank_transaction_ids = _unique_preserve_order(bank_transaction_ids)
        if not bank_input_ids and not bank_transaction_ids:
            return {
                "bank_input_link_count": 0,
                "bank_transaction_link_count": 0,
                "booked_transaction_count": 0,
            }

        self.ensure_transactions_available(bank_input_ids, bank_transaction_ids)

        def persist_links() -> None:
            for bank_input_id in bank_input_ids:
                self.inputs.create_voucher_bank_input_link(
                    voucher_id=voucher_id,
                    bank_input_id=bank_input_id,
                    linked_by=actor,
                    _commit=False,
                )
            for transaction_id in bank_transaction_ids:
                self.inputs.create_voucher_bank_transaction_link(
                    voucher_id=voucher_id,
                    bank_transaction_id=transaction_id,
                    linked_by=actor,
                    _commit=False,
                )
            self.inputs.mark_transactions_booked(
                bank_transaction_ids,
                voucher_id=voucher_id,
                _commit=False,
            )

        try:
            if _commit:
                with db.transaction():
                    persist_links()
            else:
                persist_links()
        except sqlite3.IntegrityError as exc:
            raise BankInputConflictError(
                "bank_transaction_already_linked",
                "Bank transaction is already linked to a voucher",
                str(exc),
            ) from exc

        return {
            "bank_input_link_count": len(bank_input_ids),
            "bank_transaction_link_count": len(bank_transaction_ids),
            "booked_transaction_count": len(bank_transaction_ids),
        }

    def _process_persisted_input(self, bank_input: BankInput, content: bytes) -> BankInput:
        try:
            csv_content = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            return self.inputs.update_processing_result(
                bank_input.id,
                status="failed",
                imported_count=0,
                skipped_count=0,
                parse_error=f"invalid_bank_csv_encoding: {exc}",
            )

        try:
            result = self.bank.import_csv(bank_input.bank_connection_id, csv_content)
        except ValidationError as exc:
            return self.inputs.update_processing_result(
                bank_input.id,
                status="failed",
                imported_count=0,
                skipped_count=0,
                parse_error=f"{exc.code}: {exc.message}",
            )

        with db.transaction():
            for transaction_id in result.imported_transaction_ids:
                self.inputs.create_transaction_link(
                    bank_input_id=bank_input.id,
                    bank_transaction_id=transaction_id,
                    _commit=False,
                )
            return self.inputs.update_processing_result(
                bank_input.id,
                status="processed",
                detected_format=result.detected_format,
                imported_count=result.imported_count,
                skipped_count=result.skipped_count,
                parse_error=None,
                _commit=False,
            )

    def _validate_upload(self, filename: str, mime_type: str, content: bytes) -> None:
        if not filename.lower().endswith(".csv"):
            raise BankInputValidationError(
                "unsupported_bank_input_file",
                "Bank inputs must be CSV files",
                f"filename={filename}",
            )
        if mime_type not in self.ALLOWED_MIME_TYPES:
            raise BankInputValidationError(
                "unsupported_bank_input_mime_type",
                "Bank input MIME type is not allowed",
                f"mime_type={mime_type}",
            )
        if len(content) > self.MAX_FILE_SIZE:
            raise BankInputValidationError(
                "bank_input_file_too_large",
                "Bank input file too large",
                f"max_size={self.MAX_FILE_SIZE}",
            )

    def _validate_active_connection(self, bank_connection_id: str) -> None:
        if not bank_connection_id or not bank_connection_id.strip():
            raise BankInputValidationError(
                "missing_bank_connection_id",
                "Bank input upload requires a selected bank connection",
            )
        connection = self.bank.get_connection(bank_connection_id)
        if not connection:
            raise BankConnectionNotFoundError(bank_connection_id)
        if connection.status != "active":
            raise BankInputConflictError(
                "inactive_bank_connection",
                "Bank input upload requires an active bank connection",
                f"bank_connection_id={bank_connection_id}, status={connection.status}",
            )

    def _stored_path_for(self, bank_input_id: str, filename: str) -> Path:
        extension = Path(filename).suffix or ".csv"
        return Path(settings.bank_input_dir) / bank_input_id / f"{bank_input_id}{extension}"

    def _cleanup_stored_file(self, stored_path: Path) -> None:
        if stored_path.exists():
            stored_path.unlink()
        try:
            stored_path.parent.rmdir()
        except OSError:
            pass


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values
