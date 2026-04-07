"""Ledger service - core accounting logic."""

from datetime import datetime, date
from typing import List, Dict

from domain.models import Voucher, VoucherRow, Period
from domain.types import VoucherStatus, VoucherSeries, AuditAction
from domain.validation import (
    validate_complete_voucher,
    VoucherValidator,
    PeriodValidator,
    ValidationError,
)
from repositories.voucher_repo import VoucherRepository
from repositories.period_repo import PeriodRepository
from repositories.account_repo import AccountRepository
from repositories.audit_repo import AuditRepository


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
        number: int | None = None,
    ) -> Voucher:
        """Create new draft voucher with rows.

        Validates all business rules before persisting to ensure
        no invalid data is written to the database.

        If *number* is provided it is used as-is (e.g. SIE4 import);
        otherwise the next sequential number is auto-assigned.
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
        if number is None:
            number = self.vouchers.get_next_number(series, period.fiscal_year_id)
        temp_voucher = Voucher(
            id="temp",
            series=VoucherSeries(series),
            number=number,
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

        # Now persist (validation passed) - use transaction for atomicity
        from db.database import db

        with db.transaction():
            voucher = self.vouchers.create(
                series=series,
                number=number,
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
        )

        return voucher

    def post_voucher(
        self, voucher_id: str, auto_post: bool = False, actor: str = "system"
    ) -> Voucher:
        """Post voucher (make immutable - BFL varaktighet requirement)."""
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

        # Post (make immutable)
        self.vouchers.post(voucher.id)

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
        )

        # Trigger IB update for next fiscal year (if this is a regular voucher, not IB)
        if voucher.series != VoucherSeries.IB:
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
    ) -> Voucher:
        """Create correction voucher (B-series) for an original voucher."""
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
        original_period = self.periods.get_period(original.period_id)
        if original_period and original_period.locked:
            unlocked = self._find_unlocked_period(original.period_id)
            target_period_id = unlocked.id if unlocked else original.period_id
        else:
            target_period_id = original.period_id

        # Create B-series correction voucher
        correction = self.vouchers.create_correction(
            original_voucher_id=original.id,
            series="B",
            created_by=actor,
            period_id_override=target_period_id,
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

        # Check that no draft vouchers exist in period
        drafts = self.vouchers.list_for_period(period_id, status="draft")
        if drafts:
            raise ValidationError(
                "draft_vouchers_exist",
                f"Cannot lock period - {len(drafts)} draft vouchers exist",
                "all vouchers must be posted or deleted before locking",
            )

        # Lock period
        self.periods.lock_period(period_id)

        # Log
        self.audit.log(
            entity_type="period",
            entity_id=period_id,
            action=AuditAction.LOCKED.value,
            actor=actor,
            payload={
                "period": f"{period.year}-{period.month:02d}",
                "locked_at": datetime.now().isoformat(),
            },
        )

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
