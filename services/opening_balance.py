"""Opening balance service - manages IB (ingående balans) vouchers."""

from datetime import date
from typing import Optional, Dict, List

from domain.models import Voucher, Period, FiscalYear
from domain.types import VoucherSeries, VoucherStatus
from domain.validation import ValidationError
from repositories.voucher_repo import VoucherRepository
from repositories.period_repo import PeriodRepository
from repositories.fiscal_year_repo import FiscalYearRepository
from repositories.audit_repo import AuditRepository
from services.ledger import LedgerService


class OpeningBalanceService:
    """Manages opening balance (IB) vouchers.

    IB vouchers are special vouchers with series "IB" that represent
    the opening balances for a fiscal year.
    """

    def __init__(self):
        self.vouchers = VoucherRepository()
        self.periods = PeriodRepository()
        self.fiscal_years = FiscalYearRepository()
        self.audit = AuditRepository()
        self.ledger = LedgerService()

    def update_opening_balances(
        self, fiscal_year_id: str, actor: str = "system"
    ) -> Optional[Voucher]:
        """Update or create IB voucher for a fiscal year."""
        fy = self.fiscal_years.get_fiscal_year(fiscal_year_id)
        if not fy:
            raise ValidationError("fiscal_year_not_found", "Fiscal year not found")

        prev_fy = self._get_previous_fiscal_year(fy)
        if not prev_fy:
            return None

        opening_balances = self._calculate_prior_year_balances(prev_fy.id)
        if not opening_balances:
            return None

        ib_voucher = self._find_ib_voucher(fiscal_year_id)
        first_period = self._get_first_period(fiscal_year_id)
        if not first_period:
            raise ValidationError("period_not_found", "No period found for fiscal year")

        rows_data = []
        for account_code, balance in opening_balances.items():
            if balance == 0:
                continue
            if balance > 0:
                rows_data.append(
                    {
                        "account": account_code,
                        "debit": balance,
                        "credit": 0,
                        "description": "Ingående balans",
                    }
                )
            else:
                rows_data.append(
                    {
                        "account": account_code,
                        "debit": 0,
                        "credit": abs(balance),
                        "description": "Ingående balans",
                    }
                )

        if not rows_data:
            return None

        if ib_voucher:
            return self._update_ib_voucher(
                ib_voucher, rows_data, fy.start_date.year, actor
            )
        else:
            return self._create_ib_voucher(
                fiscal_year_id, first_period.id, fy.start_date, rows_data, actor
            )

    def _find_ib_voucher(self, fiscal_year_id: str) -> Optional[Voucher]:
        vouchers, _ = self.vouchers.list_all(fiscal_year_id=fiscal_year_id)
        for voucher in vouchers:
            if voucher.series == VoucherSeries.IB:
                return voucher
        return None

    def _get_first_period(self, fiscal_year_id: str) -> Optional[Period]:
        periods = self.periods.list_periods(fiscal_year_id)
        if not periods:
            return None
        return min(periods, key=lambda p: (p.year, p.month))

    def _get_previous_fiscal_year(self, fy: FiscalYear) -> Optional[FiscalYear]:
        all_years = self.fiscal_years.list_fiscal_years()
        prev_year = None
        for year in all_years:
            if year.end_date < fy.start_date:
                if prev_year is None or year.end_date > prev_year.end_date:
                    prev_year = year
        return prev_year

    def _calculate_prior_year_balances(
        self, prev_fiscal_year_id: str
    ) -> Dict[str, int]:
        vouchers, _ = self.vouchers.list_all(
            fiscal_year_id=prev_fiscal_year_id, status="posted"
        )

        balances = {}
        for voucher in vouchers:
            for row in voucher.rows:
                code = row.account_code
                if not code or len(code) < 1 or code[0] not in ("1", "2"):
                    continue

                if code not in balances:
                    balances[code] = 0

                if code[0] == "1":
                    balances[code] += (row.debit or 0) - (row.credit or 0)
                else:
                    balances[code] += (row.credit or 0) - (row.debit or 0)

        return balances

    def _create_ib_voucher(
        self,
        fiscal_year_id: str,
        period_id: str,
        voucher_date: date,
        rows_data: List[Dict],
        actor: str,
    ) -> Voucher:
        year = voucher_date.year

        voucher = self.ledger.create_voucher(
            series=VoucherSeries.IB.value,
            date=voucher_date,
            period_id=period_id,
            description=f"Ingående balans {year}",
            rows_data=rows_data,
            created_by=actor,
        )

        voucher = self.ledger.post_voucher(voucher.id, actor=actor)

        self.audit.log(
            entity_type="opening_balance",
            entity_id=voucher.id,
            action="created",
            actor=actor,
            payload={
                "fiscal_year_id": fiscal_year_id,
                "year": year,
                "accounts_count": len(rows_data),
            },
        )

        return voucher

    def _update_ib_voucher(
        self, ib_voucher: Voucher, rows_data: List[Dict], year: int, actor: str
    ) -> Voucher:
        old_rows = [
            {"account": r.account_code, "debit": r.debit, "credit": r.credit}
            for r in ib_voucher.rows
        ]

        if ib_voucher.status == VoucherStatus.DRAFT:
            self.vouchers.delete_draft(ib_voucher.id)
        else:
            raise ValidationError(
                "ib_voucher_posted",
                "Cannot update posted IB voucher",
                "IB vouchers should not be posted before update",
            )

        fiscal_year_id = ib_voucher.fiscal_year_id
        period_id = ib_voucher.period_id

        new_voucher = self.ledger.create_voucher(
            series=VoucherSeries.IB.value,
            date=ib_voucher.date,
            period_id=period_id,
            description=f"Ingående balans {year}",
            rows_data=rows_data,
            created_by=actor,
        )

        new_voucher = self.ledger.post_voucher(new_voucher.id, actor=actor)

        self.audit.log(
            entity_type="opening_balance",
            entity_id=new_voucher.id,
            action="updated",
            actor=actor,
            payload={
                "fiscal_year_id": fiscal_year_id,
                "year": year,
                "accounts_count": len(rows_data),
                "previous_accounts_count": len(old_rows),
            },
        )

        return new_voucher

    def update_opening_balances_for_next_year(
        self, current_fiscal_year_id: str, actor: str = "system"
    ) -> Optional[Voucher]:
        """Update IB for the next fiscal year when current year changes.

        This should be called after posting a voucher in the current year
        to ensure the next year's IB is up to date.

        Args:
            current_fiscal_year_id: The fiscal year that had changes
            actor: Who triggered the update

        Returns:
            The updated IB voucher for the next year, or None
        """
        # Get current fiscal year
        fy = self.fiscal_years.get_fiscal_year(current_fiscal_year_id)
        if not fy:
            return None

        # Find next fiscal year
        next_fy = self._get_next_fiscal_year(fy)
        if not next_fy:
            return None

        # Check if next year has IB voucher
        existing_ib = self._find_ib_voucher(next_fy.id)

        # Only update if IB exists (don't create new one automatically)
        # This prevents creating IB vouchers unexpectedly
        if existing_ib:
            return self.update_opening_balances(next_fy.id, actor)

        return None

    def _get_next_fiscal_year(self, fy: FiscalYear) -> Optional[FiscalYear]:
        """Get the fiscal year immediately after the given one."""
        all_years = self.fiscal_years.list_fiscal_years()
        next_year = None
        for year in all_years:
            if year.start_date > fy.end_date:
                if next_year is None or year.start_date < next_year.start_date:
                    next_year = year
        return next_year
