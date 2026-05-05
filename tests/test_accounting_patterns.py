"""Tests for accounting pattern analysis and backtesting."""

from datetime import date

from repositories.account_repo import AccountRepository
from repositories.period_repo import PeriodRepository
from services.accounting_patterns import AccountingPatternAnalysisService
from services.ledger import LedgerService


def _ensure_accounts():
    accounts = [
        ("1920", "Bankkonto", "asset"),
        ("2640", "Ingående moms", "vat_in"),
        ("6200", "Tele och post", "expense"),
    ]
    for code, name, account_type in accounts:
        if not AccountRepository.exists(code):
            AccountRepository.create(code, name, account_type)


def test_analyze_and_evaluate_suggested_patterns(test_db):
    _ensure_accounts()
    ledger = LedgerService()
    fiscal_year = PeriodRepository.create_fiscal_year(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    period = PeriodRepository.create_period(
        fiscal_year_id=fiscal_year.id,
        year=2026,
        month=3,
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
    )

    for day, gross in [(1, 27500), (26, 27500)]:
        voucher = ledger.create_voucher(
            series="A",
            date=date(2026, 3, day),
            period_id=period.id,
            description="Telefonutgift till Fello",
            rows_data=[
                {"account": "1920", "debit": 0, "credit": gross},
                {"account": "2640", "debit": 5500, "credit": 0},
                {"account": "6200", "debit": 22000, "credit": 0},
            ],
            created_by="test",
        )
        ledger.post_voucher(voucher.id, actor="test")

    service = AccountingPatternAnalysisService()
    analysis = service.analyze(fiscal_year_id=fiscal_year.id, created_by="test")

    assert analysis["vouchers_analyzed"] == 2
    assert analysis["suggested_created_or_updated"] == 1
    pattern = analysis["patterns"][0]
    assert pattern["status"] == "suggested"
    assert pattern["sample_count"] == 2
    assert [row["account"] for row in pattern["voucher_template"]["rows"]] == [
        "1920",
        "2640",
        "6200",
    ]
    assert [row["account_name"] for row in pattern["voucher_template"]["rows"]] == [
        "Bankkonto",
        "Ingående moms",
        "Tele och post",
    ]

    evaluation = service.evaluate(
        name="Test backtest",
        fiscal_year_id=fiscal_year.id,
        include_all_suggested=True,
        created_by="test",
    )

    assert evaluation["summary"]["cases_total"] == 2
    assert evaluation["summary"]["baseline"]["matched"] == 0
    assert evaluation["summary"]["candidate"]["exact"] == 2
    assert evaluation["summary"]["delta"]["average_score"] > 0
