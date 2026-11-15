"""Year-to-year SRU mappings: compare against the BAS standard and inherit.

A fiscal year's saved mappings (``account_sru_mappings``) override the BAS
coupling table in ``domain/sru_fields.py``. In practice they come from one SIE4
import, so a new year inherits the previous year's. Field codes and couplings
change between app versions, so before inheriting, the agent compares the
previous year's mapping with today's standard account by account and asks the
user about each row that needs review (issue #47, see
``docs/to_agent/04_sie4_import_och_rakenskapsar.md``).
"""

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

from domain.models import FiscalYear
from domain.sru_fields import (
    DERIVED_RESULT_ACCOUNTS,
    MAPPING_NEEDS_REVIEW,
    mapping_status,
    standard_field_for_account,
)
from repositories.period_repo import PeriodRepository
from repositories.sru_mapping_repo import SruMappingRepository


class SruMappingError(Exception):
    """Base for SRU mapping errors."""


class FiscalYearNotFoundError(SruMappingError):
    """The fiscal year does not exist."""


class NoPreviousFiscalYearError(SruMappingError):
    """There is no earlier fiscal year to inherit from."""


@dataclass(frozen=True)
class SruMappingDiffRow:
    account_code: str
    account_name: Optional[str]
    has_balance: bool
    current_field: Optional[str]
    previous_field: Optional[str]
    standard_field: Optional[str]
    status: str

    def as_dict(self) -> Dict:
        return asdict(self)

    def review_item(self) -> Dict:
        return {
            "account_code": self.account_code,
            "account_name": self.account_name,
            "current_field": self.current_field,
            "previous_field": self.previous_field,
            "standard_field": self.standard_field,
            "status": self.status,
        }


def _is_derived(account_code: str) -> bool:
    try:
        return int(account_code) in DERIVED_RESULT_ACCOUNTS
    except ValueError:
        return False


class SruMappingService:
    """Diff and inheritance of a fiscal year's saved SRU mappings."""

    def _fiscal_year(self, fiscal_year_id: str) -> FiscalYear:
        fiscal_year = PeriodRepository.get_fiscal_year(fiscal_year_id)
        if fiscal_year is None:
            raise FiscalYearNotFoundError(fiscal_year_id)
        return fiscal_year

    @staticmethod
    def previous_fiscal_year(fiscal_year: FiscalYear) -> Optional[FiscalYear]:
        """The closest fiscal year that ends before this one starts."""
        earlier = [
            year
            for year in PeriodRepository.list_fiscal_years()
            if year.end_date < fiscal_year.start_date
        ]
        return max(earlier, key=lambda year: year.end_date) if earlier else None

    def diff(self, fiscal_year_id: str) -> Dict:
        """Compare this year's, the previous year's and the standard mapping.

        One row per account that has a balance, a saved mapping this year, a
        saved mapping the previous year, or a standard mapping (accounts in
        the chart only, for the standard)."""
        fiscal_year = self._fiscal_year(fiscal_year_id)
        previous = self.previous_fiscal_year(fiscal_year)
        previous_mappings = (
            SruMappingRepository.for_year(previous.id) if previous else {}
        )
        rows = self._rows(
            fiscal_year_id,
            SruMappingRepository.for_year(fiscal_year_id),
            previous_mappings,
        )
        return {
            "fiscal_year_id": fiscal_year_id,
            "previous_fiscal_year_id": previous.id if previous else None,
            "rows": [row.as_dict() for row in rows],
        }

    def inherit_previous(self, fiscal_year_id: str, dry_run: bool = False) -> Dict:
        """Replace this year's saved mappings with the previous year's.

        The report's ``needs_review`` is computed as if the inheritance had
        been made, so a dry run shows exactly what a real run would leave to
        review. A dry run writes nothing."""
        from db.database import db

        fiscal_year = self._fiscal_year(fiscal_year_id)
        previous = self.previous_fiscal_year(fiscal_year)
        if previous is None:
            raise NoPreviousFiscalYearError(fiscal_year_id)

        inherited = SruMappingRepository.for_year(previous.id)
        if not dry_run:
            with db.transaction():
                SruMappingRepository.replace(fiscal_year_id, inherited)

        rows = self._rows(fiscal_year_id, dict(inherited), inherited)
        return {
            "fiscal_year_id": fiscal_year_id,
            "source_fiscal_year_id": previous.id,
            "copied": len(inherited),
            "dry_run": dry_run,
            "needs_review": [
                row.review_item() for row in rows if row.status in MAPPING_NEEDS_REVIEW
            ],
        }

    def _rows(
        self,
        fiscal_year_id: str,
        current: Dict[str, str],
        previous: Dict[str, str],
    ) -> List[SruMappingDiffRow]:
        from services.sru_export import SRUExportService

        accounts = SRUExportService().calculate_account_balances(fiscal_year_id)
        codes = set(current) | set(previous)
        codes.update(
            code
            for code, account in accounts.items()
            if account["balance"] != 0 or standard_field_for_account(code)
        )
        year_has_saved_mappings = bool(current)

        rows = []
        for code in sorted(codes):
            account = accounts.get(code)
            has_balance = bool(account and account["balance"] != 0)
            standard = standard_field_for_account(code)
            rows.append(
                SruMappingDiffRow(
                    account_code=code,
                    account_name=account["name"] if account else None,
                    has_balance=has_balance,
                    current_field=current.get(code),
                    previous_field=previous.get(code),
                    standard_field=standard,
                    status=mapping_status(
                        has_balance=has_balance,
                        derived=_is_derived(code),
                        current_field=current.get(code),
                        previous_field=previous.get(code),
                        standard_field=standard,
                        year_has_saved_mappings=year_has_saved_mappings,
                    ),
                )
            )
        return rows
