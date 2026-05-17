"""Service for voucher source material intake."""

from pathlib import Path
import hashlib
import sqlite3
import uuid

from config import settings
from db.database import db
from domain.models import IntakeProcessingAttempt, IntakeSource, VoucherIntakeSource
from domain.types import IntakeSourceType, IntakeStatus, VoucherStatus
from repositories.intake_repo import IntakeRepository
from repositories.voucher_repo import VoucherRepository


class IntakeError(Exception):
    """Base error for intake workflow failures."""

    def __init__(self, code: str, message: str, details: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


class DuplicateIntakeSourceError(IntakeError):
    """Raised when uploaded bytes already exist as an intake source."""

    def __init__(self, sha256: str, existing_id: str | None = None):
        details = f"sha256={sha256}"
        if existing_id:
            details += f", existing_id={existing_id}"
        super().__init__("duplicate_intake_source", "This source file was already uploaded", details)
        self.sha256 = sha256
        self.existing_id = existing_id


class IntakeNotFoundError(IntakeError):
    """Raised when an intake source is not found."""

    def __init__(self, source_id: str):
        super().__init__("intake_not_found", "Intake source not found", f"source_id={source_id}")


class IntakeValidationError(IntakeError):
    """Raised when intake input is invalid."""


class IntakeConflictError(IntakeError):
    """Raised when an intake state transition is not allowed."""


class IntakeFileAccessError(IntakeError):
    """Raised when an intake file cannot be safely served."""


class IntakeService:
    """Coordinate source file storage and intake source state."""

    ALLOWED_MIME_TYPES = {
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "application/pdf",
    }
    MAX_FILE_SIZE = 10 * 1024 * 1024

    def __init__(self):
        self.sources = IntakeRepository()
        self.vouchers = VoucherRepository()

    def create_source_from_upload_content(
        self,
        filename: str | None,
        content_type: str | None,
        content: bytes,
        explanation: str | None,
        source_type: str | None,
        actor: str,
    ) -> IntakeSource:
        """Persist uploaded source bytes and create a pending intake source."""
        original_filename = filename or "file"
        mime_type = content_type or ""
        self._validate_upload(mime_type, content, source_type)

        sha256 = hashlib.sha256(content).hexdigest()
        existing = self.sources.get_by_sha256(sha256)
        if existing:
            raise DuplicateIntakeSourceError(sha256, existing.id)

        source_id = str(uuid.uuid4())
        stored_path = self._stored_path_for(source_id, original_filename, mime_type)
        stored_path.parent.mkdir(parents=True, exist_ok=True)
        stored_path.write_bytes(content)

        try:
            return self.sources.create_source(
                source_id=source_id,
                source_type=source_type,
                original_filename=original_filename,
                mime_type=mime_type,
                size_bytes=len(content),
                sha256=sha256,
                stored_path=str(stored_path),
                explanation=explanation,
                uploaded_by=actor,
            )
        except sqlite3.IntegrityError as exc:
            self._cleanup_stored_file(stored_path)
            if "sha256" in str(exc).lower() or "unique" in str(exc).lower():
                existing = self.sources.get_by_sha256(sha256)
                raise DuplicateIntakeSourceError(
                    sha256,
                    existing.id if existing else None,
                ) from exc
            raise

    def get_source(self, source_id: str) -> IntakeSource:
        source = self.sources.get_source(source_id)
        if not source:
            raise IntakeNotFoundError(source_id)
        return source

    def resolve_source_file(self, source: IntakeSource) -> Path:
        """Return a stored file path only if it remains inside the intake root."""
        root = Path(settings.intake_dir).resolve()
        candidate = Path(source.stored_path).resolve()
        if candidate != root and not candidate.is_relative_to(root):
            raise IntakeFileAccessError(
                "intake_file_outside_root",
                "Intake file path is outside configured storage root",
                f"source_id={source.id}",
            )
        if not candidate.exists():
            raise IntakeFileAccessError(
                "intake_file_missing",
                "Intake file missing from storage",
                f"source_id={source.id}",
            )
        return candidate

    def get_pending_queue(self, limit: int = 100, offset: int = 0) -> dict:
        """Return pending intake sources and total count."""
        return {
            "total": self.sources.count_pending(),
            "limit": limit,
            "offset": offset,
            "items": self.sources.list_pending(limit=limit, offset=offset),
        }

    def soft_delete(self, source_id: str, actor: str) -> None:
        """Soft-delete a pending intake source while preserving file and row."""
        source = self.get_source(source_id)
        if source.status != IntakeStatus.PENDING:
            raise IntakeConflictError(
                "intake_not_pending",
                "Only pending intake sources can be deleted",
                f"source_id={source_id}, status={source.status.value}",
            )
        with db.transaction():
            self.sources.update_status(
                source_id,
                IntakeStatus.DELETED.value,
                actor=actor,
                _commit=False,
            )

    def record_processing(
        self,
        source_id: str,
        summary: str,
        actor: str,
        warnings: list[str] | None = None,
    ):
        """Record that the agent started processing while leaving the source pending."""
        self._validate_summary(summary)
        self._ensure_can_record_outcome(source_id)
        return self.sources.record_attempt(
            intake_source_id=source_id,
            status=IntakeStatus.PROCESSING.value,
            summary=summary,
            warnings=warnings,
            actor=actor,
        )

    def record_failed(
        self,
        source_id: str,
        summary: str,
        error_detail: str,
        actor: str,
        warnings: list[str] | None = None,
    ):
        """Record failed agent processing and remove the source from pending work."""
        self._validate_summary(summary)
        if not error_detail or not error_detail.strip():
            raise IntakeValidationError(
                "missing_error_detail",
                "Failed processing requires error detail",
                f"source_id={source_id}",
            )
        self._ensure_can_record_outcome(source_id)
        with db.transaction():
            attempt = self.sources.record_attempt(
                intake_source_id=source_id,
                status=IntakeStatus.FAILED.value,
                summary=summary,
                warnings=warnings,
                error_detail=error_detail,
                actor=actor,
                _commit=False,
            )
            self.sources.update_status(
                source_id,
                IntakeStatus.FAILED.value,
                actor=actor,
                _commit=False,
            )
        return attempt

    def ensure_source_ready_for_voucher_link(self, source_id: str) -> IntakeSource:
        """Validate that a source can be linked to a voucher."""
        return self._ensure_can_record_outcome(source_id)

    def link_existing_voucher(
        self,
        source_id: str,
        voucher_id: str,
        actor: str,
        summary: str,
        warnings: list[str] | None = None,
        link_reason: str | None = None,
        _commit: bool = True,
    ) -> tuple[IntakeProcessingAttempt, VoucherIntakeSource]:
        """Link processable source material to an already posted voucher."""
        self._validate_summary(summary)
        self._ensure_can_record_outcome(source_id)

        voucher = self.vouchers.get(voucher_id)
        if not voucher:
            raise IntakeError(
                "voucher_not_found",
                "Voucher not found",
                f"voucher_id={voucher_id}",
            )
        if voucher.status != VoucherStatus.POSTED:
            raise IntakeConflictError(
                "voucher_not_posted",
                "Only posted vouchers can be linked to intake sources",
                f"voucher_id={voucher_id}, status={voucher.status.value}",
            )

        def persist_link() -> tuple[IntakeProcessingAttempt, VoucherIntakeSource]:
            link = self.sources.create_voucher_link(
                intake_source_id=source_id,
                voucher_id=voucher_id,
                linked_by=actor,
                link_reason=link_reason,
                _commit=False,
            )
            attempt = self.sources.record_attempt(
                intake_source_id=source_id,
                status=IntakeStatus.PROCESSED.value,
                summary=summary,
                warnings=warnings,
                voucher_id=voucher_id,
                actor=actor,
                _commit=False,
            )
            self.sources.update_status(
                source_id,
                IntakeStatus.PROCESSED.value,
                actor=actor,
                _commit=False,
            )
            return attempt, link

        if _commit:
            with db.transaction():
                return persist_link()
        return persist_link()

    def list_links_for_voucher(self, voucher_id: str) -> list[VoucherIntakeSource]:
        """List intake sources linked to a voucher."""
        return self.sources.list_links_for_voucher(voucher_id)

    def list_attempts_for_source(self, source_id: str) -> list[IntakeProcessingAttempt]:
        """List processing attempts recorded for an intake source."""
        return self.sources.list_attempts_for_source(source_id)

    def _ensure_can_record_outcome(self, source_id: str) -> IntakeSource:
        source = self.get_source(source_id)
        if source.status not in (IntakeStatus.PENDING, IntakeStatus.PROCESSING):
            raise IntakeConflictError(
                "intake_not_processable",
                "Intake source cannot be processed in its current status",
                f"source_id={source_id}, status={source.status.value}",
            )
        if self.sources.get_link_by_source_id(source_id):
            raise IntakeConflictError(
                "intake_already_linked",
                "Intake source is already linked to a voucher",
                f"source_id={source_id}",
            )
        return source

    def _validate_summary(self, summary: str) -> None:
        if not summary or not summary.strip():
            raise IntakeValidationError(
                "missing_summary",
                "Processing outcome requires a summary",
            )

    def _validate_upload(
        self,
        mime_type: str,
        content: bytes,
        source_type: str | None,
    ) -> None:
        if mime_type not in self.ALLOWED_MIME_TYPES:
            raise IntakeValidationError(
                "unsupported_mime_type",
                "File type is not allowed",
                f"mime_type={mime_type}",
            )
        if len(content) > self.MAX_FILE_SIZE:
            raise IntakeValidationError(
                "file_too_large",
                "File too large",
                f"max_size={self.MAX_FILE_SIZE}",
            )
        if source_type is not None:
            try:
                IntakeSourceType(source_type)
            except ValueError as exc:
                raise IntakeValidationError(
                    "invalid_source_type",
                    "Invalid intake source type",
                    f"source_type={source_type}",
                ) from exc

    def _stored_path_for(self, source_id: str, filename: str, mime_type: str) -> Path:
        extension = Path(filename).suffix or self._extension_from_mime(mime_type)
        return Path(settings.intake_dir) / source_id / f"{source_id}{extension}"

    def _cleanup_stored_file(self, stored_path: Path) -> None:
        if stored_path.exists():
            stored_path.unlink()
        try:
            stored_path.parent.rmdir()
        except OSError:
            pass

    def _extension_from_mime(self, mime_type: str) -> str:
        return {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "application/pdf": ".pdf",
        }.get(mime_type, ".bin")
