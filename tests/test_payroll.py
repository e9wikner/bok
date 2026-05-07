from datetime import date

import pytest

from domain.validation import ValidationError
from services.bank_integration import BankIntegrationService
from services.payroll import PayrollService
from services.pdf_export import CompanyInfo, PDFExportService


def _setup_period(ledger_service):
    fiscal_year = ledger_service.periods.create_fiscal_year(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    return ledger_service.periods.create_period(
        fiscal_year_id=fiscal_year.id,
        year=2026,
        month=3,
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
    )


def _setup_payslip(ledger_service):
    _setup_period(ledger_service)
    payroll = PayrollService()
    employee = payroll.create_employee(
        "Anna Andersson",
        personal_number="19900101-1234",
        email="anna@example.com",
        bank_account="1234-567890",
    )
    payroll.set_salary_setting(
        employee.id,
        gross_monthly_salary=5000000,
        preliminary_tax=1500000,
        employer_fee_rate_bp=3142,
        employer_fee_amount=None,
        payment_day=25,
    )
    run = payroll.create_payroll_run(2026, 3, date(2026, 3, 25))
    payslips = payroll.generate_payslips(run.id)
    return payroll, payslips[0]


def test_generate_payslip_with_employer_fee(ledger_service):
    payroll, payslip = _setup_payslip(ledger_service)

    assert payslip.gross_salary == 5000000
    assert payslip.preliminary_tax == 1500000
    assert payslip.employer_fee == 1571000
    assert payslip.net_salary == 3500000
    assert payslip.total_employer_cost == 6571000

    with pytest.raises(ValidationError, match="payslips_already_generated"):
        payroll.generate_payslips(payslip.payroll_run_id)


def test_book_payslip_creates_balanced_payroll_voucher(ledger_service):
    payroll, payslip = _setup_payslip(ledger_service)
    bank = BankIntegrationService()
    connection = bank.create_connection("manual", "Testbanken")
    imported, skipped = bank.import_transactions(
        connection.id,
        [
            {
                "external_id": "salary-anna-2026-03",
                "date": "2026-03-25",
                "amount": -35000.0,
                "description": "Lön Anna Andersson",
            }
        ],
    )
    assert imported == 1
    assert skipped == 0
    tx = bank.get_transactions(connection_id=connection.id)[0]

    booked = payroll.match_bank_transaction_and_book(payslip.id, tx.id)

    assert booked.voucher_id is not None
    voucher = ledger_service.vouchers.get(booked.voucher_id)
    assert voucher.is_posted()
    rows = {row.account_code: row for row in voucher.rows}
    assert rows["7010"].debit == 5000000
    assert rows["7510"].debit == 1571000
    assert rows["2710"].credit == 1500000
    assert rows["2730"].credit == 1571000
    assert rows["1930"].credit == 3500000
    assert voucher.get_total_debit() == voucher.get_total_credit()

    with pytest.raises(ValidationError, match="payslip_already_booked"):
        payroll.match_bank_transaction_and_book(payslip.id, tx.id)


def test_book_payslip_rejects_wrong_bank_transaction(ledger_service):
    payroll, payslip = _setup_payslip(ledger_service)
    bank = BankIntegrationService()
    connection = bank.create_connection("manual", "Testbanken")
    bank.import_transactions(
        connection.id,
        [
            {
                "external_id": "wrong-salary-anna-2026-03",
                "date": "2026-03-25",
                "amount": -34000.0,
                "description": "Lön Anna Andersson",
            },
            {
                "external_id": "positive-salary-anna-2026-03",
                "date": "2026-03-25",
                "amount": 35000.0,
                "description": "Lön Anna Andersson",
            },
        ],
    )
    txs = bank.get_transactions(connection_id=connection.id)
    wrong_amount = next(tx for tx in txs if tx.external_id == "wrong-salary-anna-2026-03")
    positive = next(tx for tx in txs if tx.external_id == "positive-salary-anna-2026-03")

    with pytest.raises(ValidationError, match="payroll_amount_mismatch"):
        payroll.match_bank_transaction_and_book(payslip.id, wrong_amount.id)

    with pytest.raises(ValidationError, match="invalid_bank_transaction"):
        payroll.match_bank_transaction_and_book(payslip.id, positive.id)


def test_payslip_html_contains_salary_amounts(ledger_service):
    _, payslip = _setup_payslip(ledger_service)
    html = PDFExportService(company=CompanyInfo(name="Test AB")).export_payslip_html(payslip.id)

    assert "Lönespecifikation" in html
    assert "Anna Andersson" in html
    assert "50 000,00" in html
    assert "15 000,00" in html
    assert "35 000,00" in html
    assert "15 710,00" in html
