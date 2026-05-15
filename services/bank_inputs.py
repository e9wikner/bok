"""Service for uploaded bank input source material."""

from pathlib import Path
import hashlib
import sqlite3
import uuid

from config import settings
from db.database import db
from domain.models import BankInput
from domain.types import BankInputStatus
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

        try:
            with db.transaction():
                return self.inputs.create_bank_input(
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
        except sqlite3.IntegrityError as exc:
            self._cleanup_stored_file(stored_path)
            if "sha256" in str(exc).lower() or "unique" in str(exc).lower():
                existing = self.inputs.get_by_sha256(sha256)
                raise DuplicateBankInputError(sha256, existing.id if existing else None) from exc
            raise
        except Exception:
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
