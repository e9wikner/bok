"""Lönebeskedet som underlag (migration 050, services/payslip_underlag.py).

The payslip supports the salary voucher's gross and tax; the bank row only
the net. Its PDF is stored when it is generated, linked when the salary is
booked, and can be linked afterwards to a voucher that already books it.
"""

import hashlib
import sqlite3
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from config import settings
from db.database import db
from domain.validation import ValidationError
from repositories.intake_repo import IntakeRepository
from services.auth import AuthService
from services.bank_integration import BankIntegrationService
from services.ledger import LedgerService
from services.payroll import PayrollService
from services.payslip_underlag import PayslipUnderlagService


@pytest.fixture
def payroll(ledger_service):
    fiscal_year = ledger_service.periods.create_fiscal_year(
        start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)
    )
    ledger_service.periods.create_period(
        fiscal_year_id=fiscal_year.id,
        year=2026,
        month=3,
        start_date=date(2026, 3, 1),
        end_date=date(2026, 3, 31),
    )
    service = PayrollService()
    service._ensure_payroll_accounts()
    employee = service.create_employee("Anna Andersson")
    service.set_salary_setting(
        employee.id,
        gross_monthly_salary=5000000,
        preliminary_tax=1500000,
        employer_fee_rate_bp=3142,
        employer_fee_amount=None,
        payment_day=25,
    )
    return service


def _generate(payroll):
    run = payroll.create_payroll_run(2026, 3, date(2026, 3, 25))
    return payroll.generate_payslips(run.id)[0]


def _bank_payment(amount_ore: int) -> str:
    bank = BankIntegrationService()
    connection = bank.create_connection("manual", "Testbanken")
    bank.import_transactions(
        connection.id,
        [
            {
                "external_id": "salary-2026-03",
                "date": "2026-03-25",
                "amount": -amount_ore / 100,
                "description": "Lön Anna Andersson",
            }
        ],
    )
    return bank.get_transactions(connection_id=connection.id)[0].id


def _voucher_from_the_statement(payslip, net=None) -> str:
    """A salary booked from the bank row, outside the payroll module. With
    *net*, one whose net (and so tax) is not the payslip's."""
    if net is None:
        rows = [
            {"account": "7000", "debit": payslip.gross_salary, "credit": 0},
            {"account": "7510", "debit": payslip.employer_fee, "credit": 0},
            {"account": "2710", "debit": 0, "credit": payslip.preliminary_tax},
            {"account": "2730", "debit": 0, "credit": payslip.employer_fee},
            {"account": "1930", "debit": 0, "credit": payslip.net_salary},
        ]
    else:
        rows = [
            {"account": "7000", "debit": payslip.gross_salary, "credit": 0},
            {"account": "2710", "debit": 0, "credit": payslip.gross_salary - net},
            {"account": "1930", "debit": 0, "credit": net},
        ]
    ledger = LedgerService()
    period = PayrollService()._find_period_for_date(payslip.payment_date)
    voucher = ledger.create_voucher(
        series="A",
        date=payslip.payment_date,
        period_id=period.id,
        description="Lön mars",
        rows_data=rows,
        created_by="t",
    )
    return ledger.post_voucher(voucher.id, actor="t").id


def _rows(voucher_id: str):
    voucher = LedgerService().vouchers.get(voucher_id)
    return [(r.account_code, r.debit, r.credit) for r in voucher.rows]


def test_generating_a_payslip_stores_its_pdf_but_links_nothing(payroll):
    payslip = _generate(payroll)

    assert payslip.pdf_path and payslip.pdf_sha256
    stored = Path(settings.intake_dir) / payslip.pdf_path
    assert stored.is_file()
    assert hashlib.sha256(stored.read_bytes()).hexdigest() == payslip.pdf_sha256
    # No intake source until it is linked: a pending one would land in the
    # intake pass's queue.
    assert payslip.intake_source_id is None
    assert IntakeRepository.get_by_sha256(payslip.pdf_sha256) is None

    name, content = PayslipUnderlagService().stored_pdf(payslip.id)
    assert content == stored.read_bytes()
    assert name.endswith(".pdf")


def test_storing_again_keeps_the_first_bytes(payroll, monkeypatch):
    payslip = _generate(payroll)
    monkeypatch.setattr(
        PayslipUnderlagService, "_render", staticmethod(lambda _id: b"%PDF other")
    )

    again = PayslipUnderlagService().store(payslip.id)

    assert again.pdf_sha256 == payslip.pdf_sha256


def test_the_stored_pdf_is_written_once(payroll):
    payslip = _generate(payroll)

    with pytest.raises(sqlite3.IntegrityError, match="payslip_pdf_immutable"):
        db.execute("UPDATE payslips SET pdf_sha256 = 'x' WHERE id = ?", (payslip.id,))
    db.rollback()


def test_a_payslip_whose_pdf_fails_is_still_generated(payroll, monkeypatch):
    def fail(_id):
        raise RuntimeError("no renderer")

    monkeypatch.setattr(PayslipUnderlagService, "_render", staticmethod(fail))

    payslip = _generate(payroll)

    assert payslip.pdf_sha256 is None
    with pytest.raises(ValidationError, match="pdf_not_stored"):
        PayslipUnderlagService().stored_pdf(payslip.id)


def test_booking_links_the_payslip_beside_the_bank_row(payroll):
    payslip = _generate(payroll)
    tx_id = _bank_payment(payslip.net_salary)

    booked = payroll.match_bank_transaction_and_book(payslip.id, tx_id)

    links = IntakeRepository.list_links_for_voucher(booked.voucher_id)
    assert [link.intake_source_id for link in links] == [booked.intake_source_id]
    source = IntakeRepository.get_source(booked.intake_source_id)
    assert source.sha256 == payslip.pdf_sha256
    assert source.status.value == "processed"
    assert Path(source.stored_path) == Path(settings.intake_dir) / payslip.pdf_path
    assert PayslipUnderlagService.is_linked(booked)
    assert LedgerService().vouchers.get(booked.voucher_id).missing_attachment is False


def test_no_booking_without_the_stored_pdf(payroll, monkeypatch):
    def fail(_id):
        raise RuntimeError("no renderer")

    monkeypatch.setattr(PayslipUnderlagService, "_render", staticmethod(fail))
    payslip = _generate(payroll)
    tx_id = _bank_payment(payslip.net_salary)

    with pytest.raises(ValidationError, match="payslip_pdf_failed"):
        payroll.match_bank_transaction_and_book(payslip.id, tx_id)

    assert payroll.payslips.get(payslip.id).voucher_id is None
    count = db.execute("SELECT COUNT(*) FROM vouchers").fetchone()[0]
    assert count == 0


def test_attaching_to_a_voucher_booked_from_the_statement(payroll):
    payslip = _generate(payroll)
    voucher_id = _voucher_from_the_statement(payslip)
    rows_before = _rows(voucher_id)
    service = PayslipUnderlagService()

    assert [v.id for v in service.voucher_candidates(payslip.id)] == [voucher_id]

    attached = service.attach(payslip.id, voucher_id, actor="stefan")

    assert attached.voucher_id == voucher_id
    assert attached.status == "booked"
    assert PayslipUnderlagService.is_linked(attached)
    assert _rows(voucher_id) == rows_before
    assert payroll.runs.get(payslip.payroll_run_id).status == "booked"
    # Booked now: not offered for a second booking.
    assert payslip.id not in [p.id for p in payroll.payslips.list_unbooked()]

    # A replay links nothing more.
    service.attach(payslip.id, voucher_id, actor="stefan")
    assert len(IntakeRepository.list_links_for_voucher(voucher_id)) == 1


def test_attaching_refuses_a_voucher_of_other_amounts(payroll):
    payslip = _generate(payroll)
    voucher_id = _voucher_from_the_statement(payslip, net=3400000)

    assert PayslipUnderlagService().voucher_candidates(payslip.id) == []
    with pytest.raises(ValidationError, match="payroll_amount_mismatch"):
        PayslipUnderlagService().attach(payslip.id, voucher_id, actor="stefan")

    assert payroll.payslips.get(payslip.id).voucher_id is None
    assert IntakeRepository.list_links_for_voucher(voucher_id) == []


def test_attaching_a_payslip_booked_before_its_pdf_was_stored(payroll, monkeypatch):
    """A-11: booked by the payroll module before migration 050, with the
    bank row as its only underlag."""
    original = PayslipUnderlagService.__dict__["_render"]

    def fail(_id):
        raise RuntimeError("no renderer")

    monkeypatch.setattr(PayslipUnderlagService, "_render", staticmethod(fail))
    payslip = _generate(payroll)
    voucher_id = _voucher_from_the_statement(payslip)
    payroll.payslips.link_booking(payslip.id, None, voucher_id)
    monkeypatch.setattr(PayslipUnderlagService, "_render", original)

    service = PayslipUnderlagService()
    assert [v.id for v in service.voucher_candidates(payslip.id)] == [voucher_id]
    attached = service.attach(payslip.id, voucher_id, actor="stefan")

    assert attached.pdf_sha256 is not None
    assert PayslipUnderlagService.is_linked(attached)

    other = _voucher_from_the_statement(payslip)
    with pytest.raises(ValidationError, match="payslip_already_booked"):
        service.attach(payslip.id, other, actor="stefan")


def test_the_api(payroll, auth_headers):
    from api.main import app

    client = TestClient(app)
    human = {"Authorization": f"Bearer {AuthService().create_jwt('stefan')}"}
    payslip = _generate(payroll)
    voucher_id = _voucher_from_the_statement(payslip)
    db.commit()

    pdf = client.get(f"/api/v1/payroll/payslips/{payslip.id}/pdf", headers=auth_headers)
    assert pdf.status_code == 200
    assert hashlib.sha256(pdf.content).hexdigest() == payslip.pdf_sha256

    candidates = client.get(
        f"/api/v1/payroll/payslips/{payslip.id}/voucher-candidates",
        headers=auth_headers,
    ).json()["vouchers"]
    assert [c["id"] for c in candidates] == [voucher_id]

    def row():
        runs = client.get("/api/v1/payroll/runs", headers=auth_headers).json()
        return runs["payroll_runs"][0]["payslips"][0]

    assert row()["attach_voucher"]["id"] == voucher_id

    url = f"/api/v1/payroll/payslips/{payslip.id}/attach"
    body = {"voucher_id": voucher_id}
    refused = client.post(url, json=body, headers=auth_headers)
    assert refused.status_code == 403
    assert refused.json()["detail"]["code"] == "human_only"

    attached = client.post(url, json=body, headers=human)
    assert attached.status_code == 200, attached.text
    assert attached.json()["underlag_linked"] is True
    assert attached.json()["pdf_stored"] is True
    assert row()["attach_voucher"] is None
    assert row()["underlag_linked"] is True
