"""The month's salaries created and booked without a card
(`services/payroll_auto.py`, migration 054): on the payment day when a human
has turned it on, and afterwards with a human's press."""

import sqlite3
from datetime import date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from config import settings
from db.database import db
from repositories.period_repo import PeriodRepository
from repositories.voucher_repo import VoucherRepository
from services.auth import AuthService
from services.bank_inputs import BankInputService
from services.fiscal_years import FiscalYearService
from services.payroll import PayrollService
from services.payroll_auto import AUTO_ACTOR, PayrollAutoService


@pytest.fixture
def client(test_db):
    from api.main import app

    return TestClient(app)


@pytest.fixture
def human_headers():
    return {"Authorization": f"Bearer {AuthService().create_jwt('stefan')}"}


@pytest.fixture
def employee(test_db):
    FiscalYearService().create(date(2026, 1, 1), date(2026, 12, 31), actor="t")
    payroll = PayrollService()
    employee = payroll.create_employee("Anna Andersson")
    payroll.set_salary_setting(
        employee.id,
        gross_monthly_salary=5000000,
        preliminary_tax=1500000,
        employer_fee_rate_bp=3142,
        employer_fee_amount=None,
        payment_day=25,
    )
    db.commit()
    return employee


def _record(enabled: bool, on: date) -> None:
    db.execute(
        "INSERT INTO payroll_auto_booking_settings (id, enabled, set_by, created_at) "
        "VALUES (?, ?, 'stefan', ?)",
        (
            f"s-{on.isoformat()}-{enabled}",
            1 if enabled else 0,
            datetime(on.year, on.month, on.day, 9),
        ),
    )
    db.commit()


def _posted_salary_vouchers():
    return db.execute(
        "SELECT * FROM vouchers WHERE status = 'posted' AND description LIKE 'Lön %'"
    ).fetchall()


# -- the choice ------------------------------------------------------------


def test_it_is_off_until_a_human_turns_it_on(client, human_headers, auth_headers):
    assert (
        client.get("/api/v1/payroll/auto-booking", headers=auth_headers).json()[
            "enabled"
        ]
        is False
    )

    refused = client.put(
        "/api/v1/payroll/auto-booking", json={"enabled": True}, headers=auth_headers
    )
    assert refused.status_code == 403
    assert refused.json()["detail"]["code"] == "human_only"

    on = client.put(
        "/api/v1/payroll/auto-booking", json={"enabled": True}, headers=human_headers
    )
    assert on.status_code == 200
    assert on.json()["enabled"] is True
    assert on.json()["set_by"] == "stefan"


def test_the_choice_is_append_only(test_db):
    PayrollAutoService().set_enabled(True, "stefan")
    PayrollAutoService().set_enabled(True, "stefan")
    PayrollAutoService().set_enabled(False, "stefan")
    rows = db.execute("SELECT enabled FROM payroll_auto_booking_settings").fetchall()
    assert [r["enabled"] for r in rows] == [1, 0]
    with pytest.raises(sqlite3.DatabaseError):
        db.execute("UPDATE payroll_auto_booking_settings SET enabled = 1")
    with pytest.raises(sqlite3.DatabaseError):
        db.execute("DELETE FROM payroll_auto_booking_settings")
    db.rollback()


def test_the_next_payment_day_is_shown(employee):
    _record(True, date(2026, 3, 1))
    status = PayrollAutoService().status(today=date(2026, 3, 26))
    assert status["next_payment_date"] == "2026-04-25"
    status = PayrollAutoService().status(today=date(2026, 3, 10))
    assert status["next_payment_date"] == "2026-03-25"


# -- on the payment day ----------------------------------------------------


def test_nothing_happens_while_it_is_off(employee):
    assert PayrollAutoService().run_due(today=date(2026, 3, 25)) is None
    assert PayrollService().runs.list_for_period(2026, 3) == []


def test_nothing_happens_before_the_payment_day(employee):
    _record(True, date(2026, 3, 1))
    assert PayrollAutoService().run_due(today=date(2026, 3, 24)) is None
    assert PayrollService().runs.list_for_period(2026, 3) == []


def test_the_payment_day_creates_and_books_the_salary(employee):
    _record(True, date(2026, 3, 1))

    result = PayrollAutoService().run_due(today=date(2026, 3, 25))

    assert result is not None and result["errors"] == []
    run = result["run"]
    assert run.created_by == AUTO_ACTOR
    assert run.status == "booked"
    payslip = result["payslips"][0]
    assert payslip.voucher_id is not None
    assert payslip.bank_transaction_id is None
    voucher = VoucherRepository.get(payslip.voucher_id)
    assert voucher.status.value == "posted"
    assert voucher.date == date(2026, 3, 25)
    rows = {r.account_code: (r.debit, r.credit) for r in voucher.rows}
    assert rows["7000"] == (5000000, 0)
    assert rows["2710"] == (0, 1500000)
    assert rows["1930"] == (0, payslip.net_salary)
    # The payslip is the voucher's underlag.
    assert payslip.intake_source_id is not None


def test_it_books_once_a_month(employee):
    _record(True, date(2026, 3, 1))
    auto = PayrollAutoService()
    assert auto.run_due(today=date(2026, 3, 25)) is not None
    assert auto.run_due(today=date(2026, 3, 26)) is None
    assert len(_posted_salary_vouchers()) == 1


def test_a_late_check_still_books_the_month(employee):
    """The server was down on the 25th: the 27th books March."""
    _record(True, date(2026, 3, 1))
    result = PayrollAutoService().run_due(today=date(2026, 3, 27))
    assert result is not None
    assert result["run"].payment_date == date(2026, 3, 25)


def test_turning_it_on_after_the_payment_day_waits_for_next_month(employee):
    _record(True, date(2026, 3, 26))
    assert PayrollAutoService().run_due(today=date(2026, 3, 27)) is None
    assert PayrollAutoService().run_due(today=date(2026, 4, 25)) is not None


def test_a_month_with_a_run_is_left_alone(employee):
    _record(True, date(2026, 3, 1))
    payroll = PayrollService()
    run = payroll.create_payroll_run(2026, 3, date(2026, 3, 25), actor="stefan")
    payroll.generate_payslips(run.id, actor="stefan")

    assert PayrollAutoService().run_due(today=date(2026, 3, 25)) is None
    assert _posted_salary_vouchers() == []


def test_a_locked_period_leaves_the_payslip_unbooked(employee):
    _record(True, date(2026, 3, 1))
    year = PeriodRepository.list_fiscal_years()[0]
    march = PeriodRepository.get_period_by_date(year.id, date(2026, 3, 25))
    PeriodRepository.lock_period(march.id, "stefan")
    db.commit()

    result = PayrollAutoService().run_due(today=date(2026, 3, 25))

    assert result is not None
    assert [e["code"] for e in result["errors"]] == ["period_locked"]
    assert result["payslips"][0].voucher_id is None
    # Not retried: the month has its run.
    assert PayrollAutoService().run_due(today=date(2026, 3, 26)) is None


# -- the bank statement afterwards -----------------------------------------


@pytest.fixture
def bank_input_dir(tmp_path):
    original = settings.bank_input_dir
    settings.bank_input_dir = str(tmp_path / "bank-inputs")
    yield Path(settings.bank_input_dir)
    settings.bank_input_dir = original


def test_the_payment_on_the_statement_is_linked_to_the_voucher(
    employee, bank_input_dir
):
    _record(True, date(2026, 3, 1))
    result = PayrollAutoService().run_due(today=date(2026, 3, 25))
    payslip = result["payslips"][0]
    net = payslip.net_salary

    service = BankInputService()
    connection_id = service.resolve_connection_reference("account:1930")
    csv = f"Datum;Belopp;Text\n2026-03-25;-{net // 100},{net % 100:02d};LÖN ANNA\n"
    service.create_from_upload_content(
        filename="1930 mars.csv",
        content_type="text/csv",
        content=csv.encode("utf-8"),
        bank_connection_id=connection_id,
        actor="test",
    )

    linked = db.execute(
        "SELECT voucher_id FROM current_voucher_bank_transactions"
    ).fetchall()
    assert [r["voucher_id"] for r in linked] == [payslip.voucher_id]


def test_a_payment_already_on_the_statement_is_booked_against(employee):
    from services.bank_integration import BankIntegrationService

    bank = BankIntegrationService()
    connection = bank.create_connection("manual", "Testbanken")
    net = 5000000 - 1500000
    bank.import_transactions(
        connection.id,
        [
            {
                "external_id": "salary-1",
                "date": "2026-03-24",
                "amount": -net / 100,
                "description": "LÖN ANNA",
            }
        ],
    )
    db.commit()
    tx_id = bank.get_transactions(connection_id=connection.id)[0].id

    result = PayrollAutoService().create_and_book(
        2026, 3, date(2026, 3, 25), actor="stefan"
    )

    payslip = result["payslips"][0]
    assert payslip.bank_transaction_id == tx_id
    assert VoucherRepository.get(payslip.voucher_id).date == date(2026, 3, 24)


# -- the button ------------------------------------------------------------


def test_the_button_books_a_past_month(client, human_headers, employee):
    response = client.post(
        "/api/v1/payroll/runs/book",
        json={"year": 2026, "month": 1, "payment_date": "2026-01-23"},
        headers=human_headers,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["errors"] == []
    assert body["status"] == "booked"
    assert body["payslips"][0]["voucher_id"] is not None


def test_the_api_key_cannot_press_the_button(client, auth_headers, employee):
    response = client.post(
        "/api/v1/payroll/runs/book",
        json={"year": 2026, "month": 1},
        headers=auth_headers,
    )
    assert response.status_code == 403
    assert PayrollService().runs.list_for_period(2026, 1) == []


def test_the_button_refuses_a_locked_month_before_writing(
    client, human_headers, employee
):
    year = PeriodRepository.list_fiscal_years()[0]
    january = PeriodRepository.get_period_by_date(year.id, date(2026, 1, 25))
    PeriodRepository.lock_period(january.id, "stefan")
    db.commit()

    response = client.post(
        "/api/v1/payroll/runs/book",
        json={"year": 2026, "month": 1},
        headers=human_headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "period_locked"
    assert PayrollService().runs.list_for_period(2026, 1) == []


def test_the_button_refuses_a_month_that_has_a_run(client, human_headers, employee):
    PayrollService().create_payroll_run(2026, 1, date(2026, 1, 25), actor="stefan")
    response = client.post(
        "/api/v1/payroll/runs/book",
        json={"year": 2026, "month": 1},
        headers=human_headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "payroll_run_already_exists"
