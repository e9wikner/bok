"""Business rule validation."""

from typing import Optional
from domain.models import Voucher, Period, FiscalYear


class ValidationError(Exception):
    """Business validation error."""
    def __init__(self, code: str, message: str, details: Optional[str] = None):
        self.code = code
        self.message = message
        self.details = details
        super().__init__(f"{code}: {message}")


class VoucherValidator:
    """Validate voucher business rules (BFL requirements)."""

    @staticmethod
    def validate_balance(voucher: Voucher) -> None:
        """Check that debit = credit (BFL §5 kap 1 - grundbokföring)."""
        total_debit = voucher.get_total_debit()
        total_credit = voucher.get_total_credit()
        if total_debit != total_credit:
            raise ValidationError(
                code="balance_error",
                message=f"Voucher rows do not balance: debit={total_debit} credit={total_credit}",
                details="total debit must equal total credit"
            )

    @staticmethod
    def validate_rows_not_empty(voucher: Voucher) -> None:
        """Check that voucher has at least 2 rows."""
        if len(voucher.rows) < 2:
            raise ValidationError(
                code="insufficient_rows",
                message="Voucher must have at least 2 rows",
                details="minimum 2 accounting rows required"
            )

    @staticmethod
    def validate_accounts_exist(voucher: Voucher, available_accounts: dict) -> None:
        """Check that all accounts in voucher exist."""
        for row in voucher.rows:
            if row.account_code not in available_accounts:
                raise ValidationError(
                    code="account_not_found",
                    message=f"Account {row.account_code} does not exist",
                    details=f"account_code={row.account_code}"
                )

    @staticmethod
    def validate_accounts_active(voucher: Voucher, accounts: dict) -> None:
        """Check that all accounts are active."""
        for row in voucher.rows:
            account = accounts.get(row.account_code)
            if account and not account.active:
                raise ValidationError(
                    code="inactive_account",
                    message=f"Account {row.account_code} is inactive",
                    details=f"account_code={row.account_code}"
                )

    @staticmethod
    def validate_can_post(voucher: Voucher, period: Period) -> None:
        """Check if voucher can be posted to this period."""
        if period.locked:
            raise ValidationError(
                code="period_locked",
                message=f"Period {period.id} is locked - cannot post vouchers",
                details="period is immutable after locking"
            )

        if voucher.posted_at is not None:
            raise ValidationError(
                code="already_posted",
                message="Voucher is already posted (immutable)",
                details="voucher.status is already 'posted'"
            )

    @staticmethod
    def validate_can_edit(voucher: Voucher) -> None:
        """Check if voucher can be edited (must be draft)."""
        if voucher.is_posted():
            raise ValidationError(
                code="immutable_voucher",
                message="Cannot edit posted voucher - must create correction voucher",
                details="voucher.status is 'posted' - use correction voucher (B-series)"
            )

    @staticmethod
    def validate_has_rows(voucher: Voucher) -> None:
        """Check that voucher has rows before posting."""
        if not voucher.rows:
            raise ValidationError(
                code="no_rows",
                message="Voucher has no accounting rows",
                details="add at least 2 rows before posting"
            )


class PeriodValidator:
    """Validate period business rules."""

    @staticmethod
    def validate_can_lock(period: Period) -> None:
        """Check if period can be locked (irreversible)."""
        if period.locked:
            raise ValidationError(
                code="already_locked",
                message="Period is already locked",
                details="period cannot be locked twice"
            )

    @staticmethod
    def validate_period_closed(period: Period) -> None:
        """Check if period is closed and cannot accept new vouchers."""
        if period.locked:
            raise ValidationError(
                code="period_locked",
                message="Period is locked - cannot add vouchers",
                details="period is immutable after locking"
            )


class FiscalYearValidator:
    """Validate fiscal year business rules."""

    @staticmethod
    def validate_can_lock(fiscal_year: FiscalYear) -> None:
        """Check if fiscal year can be locked."""
        if fiscal_year.locked:
            raise ValidationError(
                code="already_locked",
                message="Fiscal year is already locked",
                details="fiscal_year cannot be locked twice"
            )


def validate_complete_voucher(
    voucher: Voucher,
    period: Period,
    accounts: dict,
) -> None:
    """Run complete validation suite for posting a voucher."""
    VoucherValidator.validate_has_rows(voucher)
    VoucherValidator.validate_rows_not_empty(voucher)
    VoucherValidator.validate_balance(voucher)
    VoucherValidator.validate_accounts_exist(voucher, accounts)
    VoucherValidator.validate_accounts_active(voucher, accounts)
    VoucherValidator.validate_can_post(voucher, period)
