"""Ledger service - core accounting logic."""

import logging
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from domain.models import Period, Voucher, VoucherRow
from domain.types import AuditAction, VoucherSeries, VoucherStatus
from domain.validation import (
    PeriodValidator,
    ValidationError,
    VoucherValidator,
    validate_complete_voucher,
)
from repositories.account_repo import AccountRepository
from repositories.audit_repo import AuditRepository
from repositories.period_repo import PeriodRepository
from repositories.voucher_repo import VoucherRepository

logger = logging.getLogger(__name__)


def _today() -> date:
    """The server's date, for where a correction is booked
    (SPEC-flode-verifikationer §7.2). A function so tests can fix it."""
    return date.today()


class LedgerService:
    """Core accounting service (Bokföringssystem)."""

    def __init__(self):
        self.vouchers = VoucherRepository()
        self.periods = PeriodRepository()
        self.accounts = AccountRepository()
        self.audit = AuditRepository()

    def create_voucher(
        self,
        series: str,
        date: date,
        period_id: str,
        description: str,
        rows_data: List[Dict],
        created_by: str = "system",
        _commit: bool = True,
    ) -> Voucher:
        """Create new draft voucher with rows.

        Validates all business rules before persisting to ensure
        no invalid data is written to the database.

        A draft has no number; `post_voucher` sets it (SPEC
        flode-verifikationer §4.3). An explicit number, as in the SIE4
        import, is passed to `post_voucher`.
        """
        # Get period to verify it's open
        period = self.periods.get_period(period_id)
        if not period:
            raise ValidationError(
                "period_not_found", "Period not found", f"period_id={period_id}"
            )

        PeriodValidator.validate_period_closed(period)

        # Get all accounts for validation
        all_accounts = self.accounts.get_all_as_dict()

        # Build in-memory voucher for validation BEFORE persisting
        temp_voucher = Voucher(
            id="temp",
            series=VoucherSeries(series),
            number=None,
            date=date,
            period_id=period_id,
            description=description,
            status=VoucherStatus.DRAFT,
            created_by=created_by,
        )
        for row_data in rows_data:
            temp_voucher.rows.append(
                VoucherRow(
                    id="temp",
                    voucher_id="temp",
                    account_code=row_data["account"],
                    debit=row_data.get("debit", 0),
                    credit=row_data.get("credit", 0),
                    description=row_data.get("description"),
                )
            )

        # Validate BEFORE writing to database
        validate_complete_voucher(temp_voucher, period, all_accounts)

        def persist_voucher() -> Voucher:
            voucher = self.vouchers.create(
                series=series,
                date=date,
                period_id=period_id,
                description=description,
                fiscal_year_id=period.fiscal_year_id,
                created_by=created_by,
                _commit=False,
            )
            for row_data in rows_data:
                row = self.vouchers.add_row(
                    voucher_id=voucher.id,
                    account_code=row_data["account"],
                    debit=row_data.get("debit", 0),
                    credit=row_data.get("credit", 0),
                    description=row_data.get("description"),
                    _commit=False,
                )
                voucher.rows.append(row)
            return voucher

        if _commit:
            from db.database import db

            with db.transaction():
                voucher = persist_voucher()
        else:
            voucher = persist_voucher()

        # Log
        self.audit.log(
            entity_type="voucher",
            entity_id=voucher.id,
            action=AuditAction.CREATED.value,
            actor=created_by,
            payload={
                "series": voucher.series.value,
                "number": voucher.number,
                "date": voucher.date.isoformat(),
                "rows_count": len(voucher.rows),
            },
            _commit=_commit,
        )

        return voucher

    def post_voucher(
        self,
        voucher_id: str,
        auto_post: bool = False,
        actor: str = "system",
        _commit: bool = True,
        update_opening_balance: bool = True,
        number: int | None = None,
    ) -> Voucher:
        """Post voucher (make immutable - BFL varaktighet requirement).

        The voucher gets its number here, in the same UPDATE as the status
        change: *number* if given (SIE4 import keeps the file's numbers),
        otherwise the next among posted vouchers in the series and fiscal
        year.
        """
        voucher = self.vouchers.get(voucher_id)
        if not voucher:
            raise ValidationError(
                "voucher_not_found", "Voucher not found", f"voucher_id={voucher_id}"
            )

        # Get period
        period = self.periods.get_period(voucher.period_id)
        if not period:
            raise ValidationError(
                "period_not_found", "Period not found", f"period_id={voucher.period_id}"
            )

        # Validate can post
        VoucherValidator.validate_can_post(voucher, period)

        # Store fiscal year ID for IB update trigger
        fiscal_year_id = period.fiscal_year_id

        # Post (make immutable) and number it
        voucher.number = self.vouchers.post(voucher.id, number=number, _commit=_commit)

        # Log
        self.audit.log(
            entity_type="voucher",
            entity_id=voucher.id,
            action=AuditAction.POSTED.value,
            actor=actor,
            payload={
                "series": voucher.series.value,
                "number": voucher.number,
                "total_debit": voucher.get_total_debit(),
                "total_credit": voucher.get_total_credit(),
            },
            _commit=_commit,
        )

        # Trigger IB update for next fiscal year (if this is a regular voucher, not IB)
        if _commit and update_opening_balance and voucher.series != VoucherSeries.IB:
            try:
                from services.opening_balance import OpeningBalanceService

                ob_service = OpeningBalanceService()
                # This will update the next year's IB if it exists and is not locked
                ob_service.update_opening_balances_for_next_year(fiscal_year_id, actor)
            except Exception:
                # IB update is best-effort, don't fail the posting if it fails
                pass

        # Reload to get updated status
        return self.vouchers.get(voucher.id)

    def create_correction(
        self,
        original_voucher_id: str,
        correction_rows: List[Dict],
        actor: str = "system",
        _commit: bool = True,
        voucher_date: Optional[date] = None,
        description: Optional[str] = None,
    ) -> Voucher:
        """Create correction voucher (B-series) for an original voucher.

        Booked where SPEC-flode-verifikationer §7.2 says: the original's
        period if open, otherwise the latest open period in the same fiscal
        year. `voucher_date` defaults to the date `correction_target` derives
        for today -- never the original's date, which lies outside the target
        period when the original's is locked (F12) -- and `description` to
        `Correction of voucher …`. A thread proposal passes its own date
        (the same rule, its own clock) and the agent's description, which the
        human sees on the card before posting.

        `ValidationError(no_open_period)` when no date is given and the
        fiscal year has no open period.
        """
        original = self.vouchers.get(original_voucher_id)
        if not original:
            raise ValidationError("voucher_not_found", "Original voucher not found")

        if not original.is_posted():
            raise ValidationError(
                "not_posted",
                "Can only correct posted vouchers",
                "original voucher must be in 'posted' status",
            )

        # Find an unlocked period for the correction.
        # If the original period is locked, use the latest unlocked period
        # in the same fiscal year (BFL: corrections go in current period).
        if voucher_date is None:
            target, voucher_date = self.correction_target(original, _today())
        else:
            target = self._target_correction_period(original)
        target_period_id = target.id if target else original.period_id

        # Create B-series correction voucher
        correction = self.vouchers.create_correction(
            original_voucher_id=original.id,
            series="B",
            created_by=actor,
            period_id_override=target_period_id,
            _commit=_commit,
            voucher_date=voucher_date,
            description=description,
        )

        # Get period and accounts for validation
        period = self.periods.get_period(target_period_id)
        all_accounts = self.accounts.get_all_as_dict()

        # Add correction rows (typically reversal + corrected entries)
        for row_data in correction_rows:
            row = self.vouchers.add_row(
                voucher_id=correction.id,
                account_code=row_data["account"],
                debit=row_data.get("debit", 0),
                credit=row_data.get("credit", 0),
                description=row_data.get("description", "Correction"),
                _commit=_commit,
            )
            correction.rows.append(row)

        # Validate
        validate_complete_voucher(correction, period, all_accounts)

        # Log
        self.audit.log(
            entity_type="voucher",
            entity_id=correction.id,
            action=AuditAction.CORRECTED.value,
            actor=actor,
            payload={
                "correcting": original.id,
                "original_series": original.series.value,
                "original_number": original.number,
            },
            _commit=_commit,
        )

        return correction

    def create_posted_correction(
        self,
        original_voucher_id: str,
        corrected_rows: List[Dict],
        reason: str | None = None,
        actor: str = "system",
        _commit: bool = True,
    ) -> Voucher:
        """Create and post a B-series correction for a posted voucher.

        The posted correction contains reversal rows for the original voucher
        followed by the corrected rows supplied by the caller, dated and
        booked by `correction_target` (SPEC-flode-verifikationer §7.2).

        The voucher, its number and the correction history are one unit: a
        failure writing the history rolls the correction back (F12). With
        `_commit=False` the caller's transaction is that unit; by default
        this method opens one of its own.
        """
        if _commit:
            from db.database import db

            with db.transaction():
                correction = self.create_posted_correction(
                    original_voucher_id,
                    corrected_rows,
                    reason=reason,
                    actor=actor,
                    _commit=False,
                )
            # Skipped by `post_voucher(_commit=False)`; best-effort, as in
            # `api/routes/vouchers.py`.
            try:
                from services.opening_balance import OpeningBalanceService

                period = self.periods.get_period(correction.period_id)
                if period is not None:
                    OpeningBalanceService().update_opening_balances_for_next_year(
                        period.fiscal_year_id, actor
                    )
            except Exception:
                pass
            return correction

        original = self.vouchers.get(original_voucher_id)
        if not original:
            raise ValidationError("voucher_not_found", "Original voucher not found")
        if not original.is_posted():
            raise ValidationError(
                "not_posted",
                "Can only correct posted vouchers",
                "original voucher must be in 'posted' status",
            )

        target_period, voucher_date = self.correction_target(original, _today())
        correction_rows = self.reversal_rows(original) + corrected_rows

        self._validate_correction_rows(
            original, target_period, voucher_date, correction_rows
        )
        correction = self.create_correction(
            original_voucher_id=original.id,
            correction_rows=correction_rows,
            actor=actor,
            _commit=_commit,
            voucher_date=voucher_date,
        )
        correction = self.post_voucher(correction.id, actor=actor, _commit=_commit)

        self.record_correction_history(
            original=original,
            correction=correction,
            corrected_rows=corrected_rows,
            reason=reason,
            actor=actor,
            _commit=_commit,
        )
        return correction

    def update_voucher(
        self,
        voucher_id: str,
        rows_data: List[Dict],
        description: str | None = None,
        reason: str | None = None,
        actor: str = "system",
    ) -> Voucher:
        """Update a voucher's rows (and optionally description) in-place.

        Records old and new state in the audit log so changes are fully
        traceable.  Works for both draft and posted vouchers.
        """
        voucher = self.vouchers.get(voucher_id)
        if not voucher:
            raise ValidationError("voucher_not_found", "Voucher not found")

        VoucherValidator.validate_can_edit(voucher)

        # Snapshot old state for audit
        old_rows = [
            {"account": r.account_code, "debit": r.debit, "credit": r.credit}
            for r in voucher.rows
        ]
        old_description = voucher.description

        # Validate new rows against accounts + period
        period = self.periods.get_period(voucher.period_id)
        all_accounts = self.accounts.get_all_as_dict()

        new_description = (
            description if description is not None else voucher.description
        )

        # Build temp voucher for validation
        temp = Voucher(
            id=voucher.id,
            series=voucher.series,
            number=voucher.number,
            date=voucher.date,
            period_id=voucher.period_id,
            description=new_description,
            status=voucher.status,
            created_by=voucher.created_by,
        )
        for rd in rows_data:
            temp.rows.append(
                VoucherRow(
                    id="temp",
                    voucher_id=voucher.id,
                    account_code=rd["account"],
                    debit=rd.get("debit", 0),
                    credit=rd.get("credit", 0),
                )
            )

        validate_complete_voucher(temp, period, all_accounts)

        # Persist
        from db.database import db

        with db.transaction():
            if description is not None and description != old_description:
                self.vouchers.update_description(voucher_id, description, _commit=False)
            self.vouchers.replace_rows(voucher_id, rows_data, _commit=False)

        # Audit log with before/after
        new_rows = [
            {
                "account": rd["account"],
                "debit": rd.get("debit", 0),
                "credit": rd.get("credit", 0),
            }
            for rd in rows_data
        ]
        self.audit.log(
            entity_type="voucher",
            entity_id=voucher_id,
            action=AuditAction.CORRECTED.value,
            actor=actor,
            payload={
                "reason": reason or "Korrigering",
                "old_description": old_description,
                "new_description": new_description,
                "old_rows": old_rows,
                "new_rows": new_rows,
            },
        )

        return self.vouchers.get(voucher_id)

    @staticmethod
    def reversal_rows(original: Voucher) -> List[Dict]:
        """The reversal of `original`: each of its rows, debit and credit
        swapped. Mechanical, so that it cannot be wrong because a model
        counted (SPEC-flode-verifikationer §7.1); `/correct` and a thread's
        correction proposal both build it here."""
        return [
            {
                "account": row.account_code,
                "debit": row.credit,
                "credit": row.debit,
                "description": f"Återföring {original.series.value}{original.number}",
            }
            for row in original.rows
        ]

    def correction_target(self, original: Voucher, today: date) -> Tuple[Period, date]:
        """Where a correction of `original` is booked, and on which date
        (SPEC-flode-verifikationer §7.2): the original's period if open,
        otherwise the latest open period in the same fiscal year; `today` if
        it lies in that period, otherwise its last day.

        `ValidationError(no_open_period)` when the fiscal year has no open
        period -- a correction across the year end is out of scope."""
        period = self._target_correction_period(original)
        if period is None or period.locked:
            raise ValidationError(
                "no_open_period",
                "No open period in the original voucher's fiscal year",
                details=f"voucher_id={original.id}, period_id={original.period_id}",
            )
        if period.start_date <= today <= period.end_date:
            return period, today
        return period, period.end_date

    def _target_correction_period(self, original: Voucher) -> Period:
        original_period = self.periods.get_period(original.period_id)
        if original_period and original_period.locked:
            unlocked = self._find_unlocked_period(original.period_id)
            return unlocked if unlocked else original_period
        return original_period

    def _validate_correction_rows(
        self,
        original: Voucher,
        period: Period,
        voucher_date: date,
        correction_rows: List[Dict],
    ) -> None:
        all_accounts = self.accounts.get_all_as_dict()
        temp = Voucher(
            id="temp",
            series=VoucherSeries.B,
            number=None,
            date=voucher_date,
            period_id=period.id,
            description=f"Correction of voucher {original.series.value}{original.number:06d}",
            status=VoucherStatus.DRAFT,
            created_by="system",
            correction_of=original.id,
        )
        for row_data in correction_rows:
            temp.rows.append(
                VoucherRow(
                    id="temp",
                    voucher_id="temp",
                    account_code=row_data["account"],
                    debit=row_data.get("debit", 0),
                    credit=row_data.get("credit", 0),
                    description=row_data.get("description"),
                )
            )
        validate_complete_voucher(temp, period, all_accounts)

    def record_correction_history(
        self,
        original: Voucher,
        correction: Voucher,
        corrected_rows: List[Dict],
        reason: str | None,
        actor: str,
        _commit: bool = True,
    ) -> None:
        """The `correction_history` row for a posted correction: the
        original as it was (`original_data`) and as it should have been
        (`corrected_data`: the original's description with the corrected
        rows -- never the reversal).

        Raises on failure. It used to swallow every exception, which let a
        correction be posted without its history; the posting's transaction
        now rolls back instead (SPEC-flode-verifikationer §8.1, F12).
        """
        from repositories.accounting_correction_repo import (
            AccountingCorrectionRepository,
        )

        AccountingCorrectionRepository.create(
            original_voucher_id=original.id,
            corrected_voucher_id=correction.id,
            original_data=self._voucher_snapshot(original),
            corrected_data={
                "description": original.description,
                "rows": [
                    {
                        "account_code": row["account"],
                        "debit": row.get("debit", 0),
                        "credit": row.get("credit", 0),
                        "description": row.get("description"),
                    }
                    for row in corrected_rows
                ],
                "correction_voucher_id": correction.id,
            },
            change_type="multiple",
            corrected_by=actor,
            correction_reason=reason,
            _commit=_commit,
        )

    def _voucher_snapshot(self, voucher: Voucher) -> Dict:
        return {
            "id": voucher.id,
            "series": voucher.series.value,
            "number": voucher.number,
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

    def _find_unlocked_period(self, original_period_id: str):
        """Find the latest unlocked period in the same fiscal year."""
        original_period = self.periods.get_period(original_period_id)
        if not original_period:
            return None
        periods = self.periods.list_periods(original_period.fiscal_year_id)
        # Return the latest unlocked period
        unlocked = [p for p in periods if not p.locked]
        return unlocked[-1] if unlocked else None

    def lock_period(self, period_id: str, actor: str = "system") -> Period:
        """Lock period (irreversible - BFL varaktighet requirement)."""
        period = self.periods.get_period(period_id)
        if not period:
            raise ValidationError("period_not_found", "Period not found")

        PeriodValidator.validate_can_lock(period)

        # Deferred import (AGENTS.md: service-to-service imports wait until
        # the method runs).
        from db.database import db
        from repositories.thread_draft_repo import ThreadDraftRepository
        from services.draft_service import DraftService

        drafts_service = DraftService()
        with db.transaction():
            # Lock first, recording who did it (SPEC-idempotens §5): the
            # write lock is then held, so the drafts read below are the ones
            # the lock applies to.
            self.periods.lock_period(period_id, actor=actor, _commit=False)

            # A pending thread proposal does not stop the lock: it is marked
            # `period_locked` instead (flode-verifikationer F16, beslut
            # 2026-09-24). Every other draft still does.
            proposals = {
                d.voucher_id for d in ThreadDraftRepository.pending_in_period(period_id)
            }
            drafts = [
                d
                for d in self.vouchers.list_for_period(period_id, status="draft")
                if d.id not in proposals
            ]
            if drafts:
                raise ValidationError(
                    "draft_vouchers_exist",
                    f"Cannot lock period - {len(drafts)} draft vouchers exist",
                    "all vouchers must be posted or deleted before locking",
                )
            marked = drafts_service.mark_period_locked(period_id)

            self.audit.log(
                entity_type="period",
                entity_id=period_id,
                action=AuditAction.LOCKED.value,
                actor=actor,
                payload={
                    "period": f"{period.year}-{period.month:02d}",
                    "locked_at": datetime.now().isoformat(),
                    "drafts_marked": [d.voucher_id for d in marked],
                },
                _commit=False,
            )

        # After the commit: the thread's side. It must never undo the lock.
        if marked:
            try:
                drafts_service.on_period_locked(period_id, marked, actor=actor)
            except Exception:
                logger.exception("Thread posts for locked period %s failed", period_id)

        return self.periods.get_period(period_id)

    def get_trial_balance(self, period_id: str) -> Dict[str, Dict]:
        """Get trial balance (råbalans) for a period."""
        # Get all vouchers posted up to and including this period
        period = self.periods.get_period(period_id)
        if not period:
            raise ValidationError("period_not_found", "Period not found")

        # Get all periods up to and including this one in same fiscal year
        all_periods = self.periods.list_periods(period.fiscal_year_id)
        relevant_periods = [
            p.id
            for p in all_periods
            if (
                p.year < period.year
                or (p.year == period.year and p.month <= period.month)
            )
        ]

        balances = {}

        for period_id_item in relevant_periods:
            vouchers = self.vouchers.list_for_period(period_id_item, status="posted")

            for voucher in vouchers:
                for row in voucher.rows:
                    if row.account_code not in balances:
                        balances[row.account_code] = {"debit": 0, "credit": 0}

                    balances[row.account_code]["debit"] += row.debit
                    balances[row.account_code]["credit"] += row.credit

        return balances

    def get_account_ledger(self, account_code: str, period_id: str) -> List[Dict]:
        """Get account ledger (huvudbok) for a specific account."""
        period = self.periods.get_period(period_id)
        if not period:
            raise ValidationError("period_not_found", "Period not found")

        # Get all periods up to and including this one
        all_periods = self.periods.list_periods(period.fiscal_year_id)
        relevant_periods = [
            p.id
            for p in all_periods
            if (
                p.year < period.year
                or (p.year == period.year and p.month <= period.month)
            )
        ]

        ledger_rows = []
        running_balance = 0

        for period_id_item in relevant_periods:
            vouchers = self.vouchers.list_for_period(period_id_item, status="posted")

            for voucher in vouchers:
                for row in voucher.rows:
                    if row.account_code == account_code:
                        debit = row.debit
                        credit = row.credit
                        running_balance += debit - credit

                        ledger_rows.append(
                            {
                                "date": voucher.date.isoformat(),
                                "voucher_series": voucher.series.value,
                                "voucher_number": f"{voucher.number:06d}",
                                "description": voucher.description,
                                "debit": debit,
                                "credit": credit,
                                "balance": running_balance,
                            }
                        )

        return ledger_rows

    def get_audit_history(self, entity_type: str, entity_id: str) -> List[Dict]:
        """Get audit trail for an entity."""
        entries = self.audit.get_history(entity_type, entity_id)
        return [
            {
                "timestamp": entry.timestamp.isoformat(),
                "action": entry.action.value,
                "actor": entry.actor,
                "payload": entry.payload,
            }
            for entry in entries
        ]
