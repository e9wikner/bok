"""A human approves a posted voucher without underlag (migration 051).

One press takes the voucher out of `Saknar underlag`:

- `later`: the underlag arrives after the posting. The matching still sets
  it against the voucher when it comes (`MISSING_DOCUMENT_SQL` ignores the
  waiver), and the link then documents the voucher as usual.
- `none`: the voucher has no external underlag -- an accrual, a
  depreciation, a reclassification. The voucher and its description are the
  document (BFNAR 2013:2, egenupprättad verifikation).

The voucher is never touched. A waiver is ended by a revocation row; the
voucher is then back in the list unless it has got its underlag meanwhile.
Both are audit-logged on the voucher.
"""

from dataclasses import dataclass
from typing import Optional

from db.database import db
from domain.models import UnderlagWaiver
from domain.types import AuditAction
from repositories.audit_repo import AuditRepository
from repositories.underlag_waiver_repo import UnderlagWaiverRepository
from repositories.voucher_repo import VoucherRepository

REASONS = ("later", "none")
NOTE_MAX = 500


@dataclass
class UnderlagWaiverError(Exception):
    """`code` is the API's error code; `status` the HTTP status it maps to."""

    code: str
    message: str
    status: int = 409

    def __str__(self) -> str:
        return self.message


class UnderlagWaiverService:
    def waive(
        self, voucher_id: str, *, reason: str, note: Optional[str], actor: str
    ) -> UnderlagWaiver:
        """Approve *voucher_id* without underlag. A second press with the same
        reason is a replay and returns the current waiver; another reason is
        a conflict -- revoke first."""
        if reason not in REASONS:
            raise UnderlagWaiverError(
                "invalid_reason", f"reason must be one of {', '.join(REASONS)}", 422
            )
        note = (note or "").strip() or None
        if note is not None and len(note) > NOTE_MAX:
            raise UnderlagWaiverError(
                "note_too_long", f"the note is at most {NOTE_MAX} characters", 422
            )
        voucher = VoucherRepository.get(voucher_id)
        if voucher is None:
            raise UnderlagWaiverError("voucher_not_found", "No such voucher", 404)
        current = UnderlagWaiverRepository.current_for(voucher_id)
        if current is not None:
            if current.reason == reason:
                return current
            raise UnderlagWaiverError(
                "waiver_exists",
                "The voucher is already approved without underlag for another"
                " reason; undo that first",
            )
        if not voucher.is_posted():
            raise UnderlagWaiverError(
                "voucher_not_posted", "Only a posted voucher can be approved"
            )
        if not VoucherRepository.lacks_underlag(voucher_id):
            raise UnderlagWaiverError(
                "not_missing_underlag", "The voucher already has its underlag"
            )
        try:
            waiver = UnderlagWaiverRepository.create(
                voucher_id=voucher_id,
                reason=reason,
                note=note,
                waived_by=actor,
                _commit=False,
            )
            AuditRepository.log(
                "voucher",
                voucher_id,
                AuditAction.UNDERLAG_WAIVED.value,
                actor=actor,
                payload={"waiver_id": waiver.id, "reason": reason, "note": note},
                _commit=False,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        return waiver

    def revoke(self, voucher_id: str, *, actor: str) -> Optional[UnderlagWaiver]:
        """End the voucher's current waiver. `None` when there is none -- a
        replay of an undo is not an error."""
        current = UnderlagWaiverRepository.current_for(voucher_id)
        if current is None:
            if VoucherRepository.get(voucher_id) is None:
                raise UnderlagWaiverError("voucher_not_found", "No such voucher", 404)
            return None
        try:
            UnderlagWaiverRepository.revoke(current.id, revoked_by=actor, _commit=False)
            AuditRepository.log(
                "voucher",
                voucher_id,
                AuditAction.UNDERLAG_WAIVER_REVOKED.value,
                actor=actor,
                payload={"waiver_id": current.id, "reason": current.reason},
                _commit=False,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        return UnderlagWaiverRepository.get(current.id)
