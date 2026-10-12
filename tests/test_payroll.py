from datetime import date

import pytest

from domain.payroll_models import (
    Payslip,
    agi_due_date,
    declared_employer_fee,
    employer_fee_rate_bp,
    whole_kronor,
)
from domain.validation import ValidationError
from repositories.account_repo import AccountRepository
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


def _setup_payslip(ledger_service, gross=5000000, tax=1500000):
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
        gross_monthly_salary=gross,
        preliminary_tax=tax,
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


def test_create_payroll_run_validates_settings_and_duplicates(ledger_service):
    _setup_period(ledger_service)
    payroll = PayrollService()

    with pytest.raises(ValidationError, match="no_active_salary_settings"):
        payroll.create_payroll_run(2026, 3, date(2026, 3, 25))

    employee = payroll.create_employee("Anna Andersson")
    payroll.set_salary_setting(
        employee.id,
        gross_monthly_salary=5000000,
        preliminary_tax=1500000,
        employer_fee_amount=1571000,
        payment_day=25,
    )
    run = payroll.create_payroll_run(2026, 3, date(2026, 3, 25))

    validation = payroll.validate_payroll_run(run.id)
    assert validation["valid"] is True
    assert validation["employee_count"] == 1

    with pytest.raises(ValidationError, match="payroll_run_already_exists"):
        payroll.create_payroll_run(2026, 3, date(2026, 3, 26))

    with pytest.raises(ValidationError, match="invalid_payment_date"):
        payroll.create_payroll_run(2026, 4, date(2026, 5, 25))


def test_delete_unbooked_payroll_run(ledger_service):
    payroll, payslip = _setup_payslip(ledger_service)

    payroll.delete_payroll_run(payslip.payroll_run_id)

    assert payroll.runs.get(payslip.payroll_run_id) is None
    assert payroll.payslips.get(payslip.id) is None


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
    assert rows["7000"].debit == 5000000
    assert rows["7510"].debit == 1571000
    assert rows["2710"].credit == 1500000
    assert rows["2730"].credit == 1571000
    assert rows["1930"].credit == 3500000
    assert voucher.get_total_debit() == voucher.get_total_credit()

    with pytest.raises(ValidationError, match="payslip_already_booked"):
        payroll.match_bank_transaction_and_book(payslip.id, tx.id)

    with pytest.raises(ValidationError, match="payroll_run_has_booked_payslips"):
        payroll.delete_payroll_run(payslip.payroll_run_id)


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
    wrong_amount = next(
        tx for tx in txs if tx.external_id == "wrong-salary-anna-2026-03"
    )
    positive = next(
        tx for tx in txs if tx.external_id == "positive-salary-anna-2026-03"
    )

    with pytest.raises(ValidationError, match="payroll_amount_mismatch"):
        payroll.match_bank_transaction_and_book(payslip.id, wrong_amount.id)

    with pytest.raises(ValidationError, match="invalid_bank_transaction"):
        payroll.match_bank_transaction_and_book(payslip.id, positive.id)


def test_payslip_html_contains_salary_amounts(ledger_service):
    _, payslip = _setup_payslip(ledger_service)
    html = PDFExportService(company=CompanyInfo(name="Test AB")).export_payslip_html(
        payslip.id
    )

    assert "Lönespecifikation" in html
    assert "Anna Andersson" in html
    assert "50 000,00" in html
    assert "15 000,00" in html
    assert "35 000,00" in html
    assert "15 710,00" in html
    assert "Skatteavdrag (30,0 %)" in html
    assert "Insättning på bankkonto 1234-567890" in html


def test_book_payslip_credits_the_statements_bank_account(ledger_service):
    payroll, payslip = _setup_payslip(ledger_service)
    if not AccountRepository.exists("1920"):
        AccountRepository.create("1920", "Plusgiro", "asset")
    bank = BankIntegrationService()
    connection = bank.create_connection("csv", "Företagskonto", account_number="1920")
    bank.import_transactions(
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
    tx = bank.get_transactions(connection_id=connection.id)[0]

    booked = payroll.match_bank_transaction_and_book(payslip.id, tx.id)

    voucher = ledger_service.vouchers.get(booked.voucher_id)
    rows = {row.account_code: row for row in voucher.rows}
    assert rows["1920"].credit == 3500000
    assert "1930" not in rows


def _book_salary(payroll, payslip):
    bank = BankIntegrationService()
    connection = bank.create_connection("manual", "Testbanken")
    bank.import_transactions(
        connection.id,
        [
            {
                "external_id": f"salary-{payslip.id}",
                "date": payslip.payment_date.isoformat(),
                "amount": -payslip.net_salary / 100,
                "description": "Lön",
            }
        ],
    )
    tx = bank.get_transactions(connection_id=connection.id)[0]
    return payroll.match_bank_transaction_and_book(payslip.id, tx.id)


def _april_period(ledger_service):
    fiscal_year = ledger_service.periods.list_fiscal_years()[0]
    return ledger_service.periods.create_period(
        fiscal_year_id=fiscal_year.id,
        year=2026,
        month=4,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
    )


def test_agi_due_date():
    assert agi_due_date(2026, 3) == date(2026, 4, 13)  # the 12th is a Sunday
    assert agi_due_date(2025, 12) == date(2026, 1, 19)  # the 17th, a Saturday
    assert agi_due_date(2026, 7) == date(2026, 8, 17)
    assert agi_due_date(2026, 9) == date(2026, 10, 12)


def test_agi_sums_the_payslips_paid_in_the_month(ledger_service):
    payroll, payslip = _setup_payslip(ledger_service)

    agi = payroll.get_agi(2026, 3)

    assert [i.name for i in agi.individuals] == ["Anna Andersson"]
    assert agi.individuals[0].personal_number == "19900101-1234"
    assert agi.total_gross_salary == 5000000
    assert agi.total_preliminary_tax == 1500000
    assert agi.total_employer_fee == 1571000
    assert agi.total_to_pay == 3071000
    assert agi.unbooked_payslips == 1
    assert agi.voucher_ids == {}
    assert agi.booked is False
    assert payroll.get_agi(2026, 4).individuals == []


def _rows(ledger_service, voucher_id):
    voucher = ledger_service.vouchers.get(voucher_id)
    assert voucher.is_posted()
    assert voucher.get_total_debit() == voucher.get_total_credit()
    return voucher, {r.account_code: (r.debit, r.credit) for r in voucher.rows}


def test_book_agi_as_one_voucher_per_tax_account_transaction(ledger_service):
    payroll, payslip = _setup_payslip(ledger_service)
    _april_period(ledger_service)

    with pytest.raises(ValidationError, match="agi_payslips_not_booked"):
        payroll.book_agi(2026, 3)

    _book_salary(payroll, payslip)
    agi = payroll.book_agi(2026, 3)

    assert agi.booked is True
    tax, tax_rows = _rows(ledger_service, agi.voucher_ids["tax"])
    fee, fee_rows = _rows(ledger_service, agi.voucher_ids["employer_fee"])
    assert tax.date == fee.date == date(2026, 4, 13)
    assert tax.description == "Arbetsgivardeklaration 2026-03, avdragen skatt"
    assert fee.description == "Arbetsgivardeklaration 2026-03, arbetsgivaravgifter"
    assert tax_rows == {"2710": (1500000, 0), "1630": (0, 1500000)}
    assert fee_rows == {"2730": (1571000, 0), "1630": (0, 1571000)}

    with pytest.raises(ValidationError, match="agi_already_booked"):
        payroll.book_agi(2026, 3)


def test_agi_vouchers_match_the_two_tax_account_transactions(ledger_service):
    from services.statement_match import StatementMatchService

    payroll, payslip = _setup_payslip(ledger_service)
    _april_period(ledger_service)
    _book_salary(payroll, payslip)
    agi = payroll.book_agi(2026, 3)

    bank = BankIntegrationService()
    skattekonto = bank.create_connection("csv", "Skattekonto", account_number="1630")
    bank.import_transactions(
        skattekonto.id,
        [
            {
                "external_id": "agi-avgift-202603",
                "date": "2026-04-13",
                "amount": -15710.0,
                "description": "Arbetsgivaravgift 202603",
            },
            {
                "external_id": "agi-skatt-202603",
                "date": "2026-04-13",
                "amount": -15000.0,
                "description": "Avdragen skatt 202603",
            },
        ],
    )

    linked = StatementMatchService().run()["linked"]

    assert {link["voucher_id"] for link in linked} == set(agi.voucher_ids.values())


def test_book_agi_again_after_a_part_is_reversed(ledger_service):
    payroll, payslip = _setup_payslip(ledger_service)
    _april_period(ledger_service)
    _book_salary(payroll, payslip)
    first = payroll.book_agi(2026, 3, voucher_date=date(2026, 4, 14))
    original = ledger_service.vouchers.get(first.voucher_ids["tax"])
    assert original.date == date(2026, 4, 14)

    correction = ledger_service.create_correction(
        original.id,
        [
            {
                "account": r.account_code,
                "debit": r.credit,
                "credit": r.debit,
                "description": r.description,
            }
            for r in original.rows
        ],
        voucher_date=date(2026, 4, 20),
    )
    ledger_service.post_voucher(correction.id)
    assert payroll.get_agi(2026, 3).unbooked_parts == ["tax"]

    second = payroll.book_agi(2026, 3)
    assert second.voucher_ids["tax"] != first.voucher_ids["tax"]
    assert second.voucher_ids["employer_fee"] == first.voucher_ids["employer_fee"]


def test_whole_kronor_drops_the_ore():
    assert whole_kronor(1047399) == 1047300
    assert whole_kronor(100) == 100
    assert whole_kronor(99) == 0
    assert whole_kronor(-150) == -100


def test_employer_fee_rate_is_read_back_from_the_payslip():
    assert employer_fee_rate_bp(3333333, 1047333) == 3142
    assert employer_fee_rate_bp(1000000, 102100) == 1021
    assert employer_fee_rate_bp(1000000, 12345) is None  # set as an amount
    assert employer_fee_rate_bp(1000000, 0) is None


def _payslip(employee_id, gross, fee):
    return Payslip(
        id=employee_id,
        payroll_run_id="run",
        employee_id=employee_id,
        period_year=2026,
        period_month=3,
        payment_date=date(2026, 3, 25),
        gross_salary=gross,
        preliminary_tax=0,
        employer_fee=fee,
        net_salary=gross,
        total_employer_cost=gross + fee,
    )


def test_declared_employer_fee_per_rate_with_ore_dropped():
    """SKV 401: the fee per rate on the reported whole kronor, öre dropped
    after each rate, then summed. 2 x 10 003 kr at 31,42 % is 6 285,88 kr
    together -- 6 285 kr, not the 2 x 3 142 kr of dropping öre per person."""
    payslips = [
        _payslip("a", 1000300, 314294),
        _payslip("b", 1000300, 314294),
        _payslip("c", 1000000, 102100),  # 10,21 %
        _payslip("d", 1000000, 12345),  # an amount, not a rate
    ]
    assert declared_employer_fee(payslips) == 628500 + 102100 + 12300


def test_book_agi_in_whole_kronor_with_ore_to_rounding(ledger_service):
    """33 333,33 kr gross and 10 000,50 kr tax: the AGI declares 33 333 and
    10 000 kr; the liability is cleared in öre and the rest is 3740."""
    payroll, payslip = _setup_payslip(ledger_service, gross=3333333, tax=1000050)
    assert payslip.employer_fee == 1047333
    _april_period(ledger_service)
    _book_salary(payroll, payslip)

    agi = payroll.get_agi(2026, 3)
    assert agi.individuals[0].gross_salary == 3333300
    assert agi.individuals[0].preliminary_tax == 1000000
    assert agi.total_preliminary_tax == 1000000
    assert agi.total_employer_fee == 1047300  # 33 333 kr x 31,42 % = 10 473,22
    assert agi.total_to_pay == 2047300

    agi = payroll.book_agi(2026, 3)
    _, tax_rows = _rows(ledger_service, agi.voucher_ids["tax"])
    _, fee_rows = _rows(ledger_service, agi.voucher_ids["employer_fee"])
    assert tax_rows == {"2710": (1000050, 0), "1630": (0, 1000000), "3740": (0, 50)}
    assert fee_rows == {
        "2730": (1047333, 0),
        "1630": (0, 1047300),
        "3740": (0, 33),
    }


def test_book_agi_writes_nothing_when_a_part_fails(ledger_service, monkeypatch):
    from db.database import db
    from repositories.payroll_repo import AgiBookingRepository

    payroll, payslip = _setup_payslip(ledger_service)
    _april_period(ledger_service)
    _book_salary(payroll, payslip)

    create = AgiBookingRepository.create
    calls = []

    def fail_second(*args, **kwargs):
        calls.append(args)
        if len(calls) == 2:
            raise RuntimeError("disk full")
        return create(*args, **kwargs)

    monkeypatch.setattr(AgiBookingRepository, "create", staticmethod(fail_second))
    with pytest.raises(RuntimeError, match="disk full"):
        payroll.book_agi(2026, 3)

    count = db.execute(
        "SELECT COUNT(*) FROM vouchers WHERE description LIKE 'Arbetsgivardeklaration%'"
    ).fetchone()[0]
    assert count == 0
    assert payroll.get_agi(2026, 3).voucher_ids == {}

    monkeypatch.setattr(AgiBookingRepository, "create", staticmethod(create))
    agi = payroll.book_agi(2026, 3)
    assert set(agi.voucher_ids) == {"tax", "employer_fee"}


def test_book_agi_without_payslips(ledger_service):
    _setup_period(ledger_service)
    with pytest.raises(ValidationError, match="agi_no_payslips"):
        PayrollService().book_agi(2026, 3)


def test_agi_api(ledger_service, auth_headers):
    from fastapi.testclient import TestClient

    from api.main import app

    payroll, payslip = _setup_payslip(ledger_service)
    _april_period(ledger_service)
    _book_salary(payroll, payslip)
    client = TestClient(app)

    response = client.get("/api/v1/payroll/agi/2026/3", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["due_date"] == "2026-04-13"
    assert body["total_to_pay"] == 3071000
    assert body["individuals"][0]["gross_salary"] == 5000000

    response = client.post(
        "/api/v1/payroll/agi/2026/3/book", json={}, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["booked"] is True
    assert set(response.json()["voucher_ids"]) == {"tax", "employer_fee"}

    response = client.post(
        "/api/v1/payroll/agi/2026/3/book", json={}, headers=auth_headers
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "agi_already_booked"
