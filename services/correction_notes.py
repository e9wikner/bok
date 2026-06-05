"""Lifecycle service for voucher correction notes."""

from typing import Dict, List, Optional

from db.database import db
from domain.models import CorrectionNote, Voucher, VoucherRow
from domain.validation import ValidationError, validate_complete_voucher
from repositories.accounting_correction_repo import AccountingCorrectionRepository
from repositories.correction_note_repo import CorrectionNoteRepository
from services.ledger import LedgerService


class CorrectionNoteError(Exception):
    """Typed correction-note lifecycle error for API mapping."""

    def __init__(self, code: str, message: str, details: Optional[str] = None):
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)


class CorrectionNoteService:
    """Orchestrate correction notes, draft suggestions, and terminal history."""

    def __init__(self):
        self.notes = CorrectionNoteRepository()
        self.history = AccountingCorrectionRepository()
        self.ledger = LedgerService()

    def list_for_voucher(self, voucher_id: str) -> List[CorrectionNote]:
        self._require_voucher(voucher_id)
        return self.notes.list_for_voucher(voucher_id)

    def create_note(
        self,
        voucher_id: str,
        note_text: str,
        actor: str = "system",
    ) -> CorrectionNote:
        original = self._require_voucher(voucher_id)
        if not original.is_posted():
            raise CorrectionNoteError(
                "voucher_not_posted",
                "Correction notes can only be created for posted vouchers",
            )
        if self.notes.get_active_for_voucher(voucher_id):
            raise CorrectionNoteError(
                "correction_note_active_exists",
                "An active correction note already exists for this voucher",
            )
        if not note_text.strip():
            raise CorrectionNoteError("validation_error", "Correction note text is required")
        return self.notes.create(voucher_id, note_text.strip(), actor)

    def create_draft(
        self,
        voucher_id: str,
        correction_rows: List[Dict],
        actor: str = "system",
    ) -> Voucher:
        return self.ledger.create_correction(
            original_voucher_id=voucher_id,
            correction_rows=correction_rows,
            actor=actor,
        )

    def suggest(
        self,
        voucher_id: str,
        note_id: str,
        correction_rows: List[Dict],
        actor: str = "agent",
    ) -> tuple[CorrectionNote, Voucher]:
        note = self._require_note_for_voucher(note_id, voucher_id)
        if note.status != "pending":
            raise CorrectionNoteError(
                "invalid_lifecycle_transition",
                "Only pending correction notes can be suggested",
            )
        draft = LedgerService().create_correction(
            original_voucher_id=voucher_id,
            correction_rows=correction_rows,
            actor=actor,
        )
        suggested = self.notes.set_suggested(note.id, draft.id)
        return suggested, draft

    def approve(
        self,
        voucher_id: str,
        note_id: str,
        rows_data: Optional[List[Dict]] = None,
        actor: str = "system",
    ) -> Voucher:
        note = self._require_note_for_voucher(note_id, voucher_id)
        if note.status != "suggested" or not note.suggested_voucher_id:
            raise CorrectionNoteError(
                "invalid_lifecycle_transition",
                "Only suggested correction notes can be approved",
            )
        draft = self._require_draft(note.suggested_voucher_id)
        if draft.correction_of != voucher_id:
            raise CorrectionNoteError(
                "validation_error",
                "Suggested draft does not belong to this voucher",
            )
        if rows_data is not None:
            self._replace_draft_rows(draft, rows_data)

        with db.transaction():
            posted = self.ledger.post_voucher(
                draft.id,
                actor=actor,
                _commit=False,
            )
            applied = self.notes.set_applied(note.id, _commit=False)
            if applied.status != "applied":
                raise CorrectionNoteError(
                    "invalid_lifecycle_transition",
                    "Correction note could not be marked applied",
                )
        return posted

    def dismiss(
        self,
        voucher_id: str,
        note_id: str,
        reason: Optional[str] = None,
        actor: str = "system",
    ) -> CorrectionNote:
        note = self._require_note_for_voucher(note_id, voucher_id)
        if note.status not in {"pending", "suggested"}:
            raise CorrectionNoteError(
                "invalid_lifecycle_transition",
                "Only pending or suggested correction notes can be dismissed",
            )
        draft_snapshot = None
        if note.suggested_voucher_id:
            draft = self.ledger.vouchers.get(note.suggested_voucher_id)
            if draft and draft.is_draft():
                draft_snapshot = self._voucher_snapshot(draft)
                self.ledger.vouchers.delete_draft(draft.id)

        original = self._require_voucher(voucher_id)
        with db.transaction():
            self.history.create(
                original_voucher_id=voucher_id,
                corrected_voucher_id=None,
                original_data=self._voucher_snapshot(original),
                corrected_data=draft_snapshot,
                change_type="suggestion_dismissed",
                was_successful=False,
                corrected_by=actor,
                correction_reason=reason or note.note_text,
                _commit=False,
            )
            dismissed = self.notes.set_dismissed(note.id, _commit=False)
            if dismissed.status != "dismissed":
                raise CorrectionNoteError(
                    "invalid_lifecycle_transition",
                    "Correction note could not be dismissed",
                )
        return dismissed

    def reject(
        self,
        voucher_id: str,
        note_id: str,
        rejection_reason: str,
        actor: str = "agent",
    ) -> CorrectionNote:
        note = self._require_note_for_voucher(note_id, voucher_id)
        if note.status not in {"pending", "suggested"}:
            raise CorrectionNoteError(
                "invalid_lifecycle_transition",
                "Only pending or suggested correction notes can be rejected",
            )
        draft_snapshot = None
        if note.suggested_voucher_id:
            draft = self.ledger.vouchers.get(note.suggested_voucher_id)
            if draft:
                draft_snapshot = self._voucher_snapshot(draft)
        failure_context = draft_snapshot or {"rejection_reason": rejection_reason}
        original = self._require_voucher(voucher_id)
        with db.transaction():
            self.history.create(
                original_voucher_id=voucher_id,
                corrected_voucher_id=None,
                original_data=self._voucher_snapshot(original),
                corrected_data=failure_context,
                change_type="suggestion_rejected",
                was_successful=False,
                corrected_by=actor,
                correction_reason=rejection_reason,
                _commit=False,
            )
            rejected = self.notes.set_rejected(note.id, rejection_reason, _commit=False)
            if rejected.status != "rejected":
                raise CorrectionNoteError(
                    "invalid_lifecycle_transition",
                    "Correction note could not be rejected",
                )
        return rejected

    def _require_voucher(self, voucher_id: str) -> Voucher:
        voucher = self.ledger.vouchers.get(voucher_id)
        if not voucher:
            raise CorrectionNoteError("voucher_not_found", "Voucher not found")
        return voucher

    def _require_note_for_voucher(self, note_id: str, voucher_id: str) -> CorrectionNote:
        note = self.notes.get(note_id)
        if not note or note.voucher_id != voucher_id:
            raise CorrectionNoteError("correction_note_not_found", "Correction note not found")
        return note

    def _require_draft(self, voucher_id: str) -> Voucher:
        draft = self.ledger.vouchers.get(voucher_id)
        if not draft:
            raise CorrectionNoteError("voucher_not_found", "Suggested draft not found")
        if not draft.is_draft():
            raise CorrectionNoteError(
                "invalid_lifecycle_transition",
                "Suggested correction voucher is no longer a draft",
            )
        return draft

    def _replace_draft_rows(self, draft: Voucher, rows_data: List[Dict]) -> None:
        period = self.ledger.periods.get_period(draft.period_id)
        all_accounts = self.ledger.accounts.get_all_as_dict()
        temp = Voucher(
            id=draft.id,
            series=draft.series,
            number=draft.number,
            date=draft.date,
            period_id=draft.period_id,
            description=draft.description,
            status=draft.status,
            correction_of=draft.correction_of,
            created_by=draft.created_by,
        )
        for row_data in rows_data:
            temp.rows.append(
                VoucherRow(
                    id="temp",
                    voucher_id=draft.id,
                    account_code=row_data["account"],
                    debit=row_data.get("debit", 0),
                    credit=row_data.get("credit", 0),
                    description=row_data.get("description"),
                )
            )
        try:
            validate_complete_voucher(temp, period, all_accounts)
        except ValidationError as exc:
            raise CorrectionNoteError(exc.code, exc.message, exc.details) from exc
        self.ledger.vouchers.replace_rows(draft.id, rows_data)

    def _voucher_snapshot(self, voucher: Voucher) -> dict:
        return {
            "id": voucher.id,
            "series": voucher.series.value,
            "number": voucher.number,
            "status": voucher.status.value,
            "description": voucher.description,
            "rows": [
                {
                    "account_code": row.account_code,
                    "debit": row.debit,
                    "credit": row.credit,
                    "description": row.description,
                }
                for row in voucher.rows
            ],
        }
