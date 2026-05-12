"""Tests for non-calendar and shortened fiscal years."""

from datetime import date

import pytest
from domain.validation import ValidationError
from repositories.account_repo import AccountRepository
from repositories.period_repo import PeriodRepository
from repositories.voucher_repo import VoucherRepository
from services.ledger import LedgerService
from services.sie4_import import SIE4Importer


def _create_basic_accounts():
    accounts = [
        ("1930", "Företagskonto", "asset"),
        ("3010", "Försäljning", "revenue"),
    ]
    for code, name, account_type in accounts:
        if not AccountRepository.exists(code):
            AccountRepository.create(code, name, account_type)


def _create_fiscal_year_with_monthly_periods(
    ledger: LedgerService,
    start_date: date,
    end_date: date,
):
    """Mirror POST /api/v1/fiscal-years period creation for focused testing."""
    from calendar import monthrange
    from datetime import timedelta

    fiscal_year = ledger.periods.create_fiscal_year(
        start_date=start_date,
        end_date=end_date,
    )
    current_start = start_date
    while current_start <= end_date:
        year = current_start.year
        month = current_start.month
        _, last_day = monthrange(year, month)
        period_end = min(date(year, month, last_day), end_date)
        ledger.periods.create_period(
            fiscal_year_id=fiscal_year.id,
            year=year,
            month=month,
            start_date=current_start,
            end_date=period_end,
        )
        current_start = period_end + timedelta(days=1)
    return fiscal_year


def test_fiscal_year_periods_are_clipped_to_actual_start_and_end(test_db):
    ledger = LedgerService()
    fiscal_year = _create_fiscal_year_with_monthly_periods(
        ledger,
        start_date=date(2026, 7, 15),
        end_date=date(2027, 6, 10),
    )

    periods = PeriodRepository.list_periods(fiscal_year.id)

    assert periods[0].start_date == date(2026, 7, 15)
    assert periods[0].end_date == date(2026, 7, 31)
    assert periods[-1].start_date == date(2027, 6, 1)
    assert periods[-1].end_date == date(2027, 6, 10)
    assert len(periods) == 12


def test_voucher_date_must_be_inside_selected_period(test_db):
    _create_basic_accounts()
    ledger = LedgerService()
    fiscal_year = PeriodRepository.create_fiscal_year(
        start_date=date(2026, 7, 15),
        end_date=date(2027, 6, 10),
    )
    july = PeriodRepository.create_period(
        fiscal_year_id=fiscal_year.id,
        year=2026,
        month=7,
        start_date=date(2026, 7, 15),
        end_date=date(2026, 7, 31),
    )

    with pytest.raises(ValidationError) as exc:
        ledger.create_voucher(
            series="A",
            date=date(2026, 7, 10),
            period_id=july.id,
            description="Fel perioddatum",
            rows_data=[
                {"account": "1930", "debit": 10000, "credit": 0},
                {"account": "3010", "debit": 0, "credit": 10000},
            ],
        )

    assert exc.value.code == "voucher_date_outside_period"


def test_income_statement_can_filter_by_broken_fiscal_year(test_db):
    _create_basic_accounts()
    ledger = LedgerService()

    fiscal_year = PeriodRepository.create_fiscal_year(
        start_date=date(2026, 7, 1),
        end_date=date(2027, 6, 30),
    )
    july = PeriodRepository.create_period(
        fiscal_year_id=fiscal_year.id,
        year=2026,
        month=7,
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 31),
    )
    january = PeriodRepository.create_period(
        fiscal_year_id=fiscal_year.id,
        year=2027,
        month=1,
        start_date=date(2027, 1, 1),
        end_date=date(2027, 1, 31),
    )
    other_year = PeriodRepository.create_fiscal_year(
        start_date=date(2027, 7, 1),
        end_date=date(2028, 6, 30),
    )
    next_july = PeriodRepository.create_period(
        fiscal_year_id=other_year.id,
        year=2027,
        month=7,
        start_date=date(2027, 7, 1),
        end_date=date(2027, 7, 31),
    )

    for period, voucher_date, amount in [
        (july, date(2026, 7, 5), 10000),
        (january, date(2027, 1, 5), 20000),
        (next_july, date(2027, 7, 5), 40000),
    ]:
        voucher = ledger.create_voucher(
            series="A",
            date=voucher_date,
            period_id=period.id,
            description="Försäljning",
            rows_data=[
                {"account": "1930", "debit": amount, "credit": 0},
                {"account": "3010", "debit": 0, "credit": amount},
            ],
        )
        ledger.post_voucher(voucher.id)

    from api.routes.reports import get_income_statement

    response = awaitable = get_income_statement(
        fiscal_year_id=fiscal_year.id,
        year=None,
        month=None,
    )
    if hasattr(awaitable, "__await__"):
        import asyncio

        response = asyncio.run(awaitable)

    assert response["revenue"] == 30000


def _broken_year_sie4() -> str:
    return """#FLAGGA 0
#FORMAT PC8
#PROGRAM "Test" 1.0
#FNAMN "Test AB"
#FORGN 5566778899
#RAR 0 20101001 20111231
#KONTO 1930 "Företagskonto"
#KONTO 3010 "Försäljning"
#VER A 1 20101015 "Försäljning okt"
{
#TRANS 1930 {} 10000 20101015
#TRANS 3010 {} -10000 20101015
}
"""


def test_sie4_import_auto_creates_matching_broken_fiscal_year(test_db):
    importer = SIE4Importer(api_url="http://test", api_key="test")

    assert importer.import_content(_broken_year_sie4()) is True

    fiscal_years = PeriodRepository.list_fiscal_years()
    assert len(fiscal_years) == 1
    assert fiscal_years[0].start_date == date(2010, 10, 1)
    assert fiscal_years[0].end_date == date(2011, 12, 31)
    assert importer.fiscal_year_resolution == {
        "id": fiscal_years[0].id,
        "resolution": "created",
        "start": "2010-10-01",
        "end": "2011-12-31",
    }

    periods = PeriodRepository.list_periods(fiscal_years[0].id)
    assert periods[0].start_date == date(2010, 10, 1)
    assert periods[-1].end_date == date(2011, 12, 31)
    assert importer.imported["periods_created"] == 15

    vouchers, total = VoucherRepository.list_all(fiscal_year_id=fiscal_years[0].id)
    assert total == 1
    assert vouchers[0].date == date(2010, 10, 15)


def test_sie4_import_rejects_explicit_mismatched_fiscal_year(test_db):
    importer = SIE4Importer(api_url="http://test", api_key="test")
    data = importer.parser.parse_content(_broken_year_sie4())
    calendar_year = PeriodRepository.create_fiscal_year(
        start_date=date(2010, 1, 1),
        end_date=date(2010, 12, 31),
    )

    with pytest.raises(ValidationError) as exc:
        importer.resolve_fiscal_year(data, calendar_year.id)

    assert exc.value.code == "sie4_fiscal_year_mismatch"
    fiscal_years = PeriodRepository.list_fiscal_years()
    assert len(fiscal_years) == 1


def test_sie4_import_reuses_existing_matching_fiscal_year(test_db):
    importer = SIE4Importer(api_url="http://test", api_key="test")
    data = importer.parser.parse_content(_broken_year_sie4())
    fiscal_year = PeriodRepository.create_fiscal_year(
        start_date=date(2010, 10, 1),
        end_date=date(2011, 12, 31),
    )

    resolved_id = importer.resolve_fiscal_year(data)

    assert resolved_id == fiscal_year.id
    assert importer.fiscal_year_resolution == {
        "id": fiscal_year.id,
        "resolution": "matched_existing",
        "start": "2010-10-01",
        "end": "2011-12-31",
    }
    assert len(PeriodRepository.list_fiscal_years()) == 1


def test_sie4_import_requires_rar_zero_interval(test_db):
    importer = SIE4Importer(api_url="http://test", api_key="test")
    data = importer.parser.parse_content(
        """#FLAGGA 0
#FORMAT PC8
#PROGRAM "Test" 1.0
#FNAMN "Test AB"
#KONTO 1930 "Företagskonto"
"""
    )

    with pytest.raises(ValidationError) as exc:
        importer.resolve_fiscal_year(data)

    assert exc.value.code == "sie4_fiscal_year_missing"
