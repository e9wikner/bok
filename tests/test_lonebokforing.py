"""`foresla_lonebokforing` and `foresla_agi_bokforing`: a payslip's or an AGI
month's booking proposed as a decision card (migration 043,
`services/payroll_proposal.py`). The agent proposes; a logged-in human's
press books."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from db.database import db
from domain.validation import ValidationError
from repositories.decision_repo import DecisionRepository
from repositories.payroll_booking_proposal_repo import (
    PayrollBookingProposalRepository,
)
from repositories.period_repo import PeriodRepository
from repositories.thread_repo import ThreadRepository
from services.agent_tools import execute_tool
from services.auth import AuthService
from services.bank_integration import BankIntegrationService
from services.fiscal_years import FiscalYearService
from services.llm import LLMCapabilities
from services.payroll import PayrollService

_CAPABILITIES = LLMCapabilities(
    cache_breakpoint=False, pdf_document_blocks=False, refusal_stop_reason=False
)


@pytest.fixture
def client(test_db):
    from api.main import app

    return TestClient(app)


@pytest.fixture
def human_headers():
    return {"Authorization": f"Bearer {AuthService().create_jwt('stefan')}"}


@pytest.fixture
def thread(test_db):
    year = FiscalYearService().create(date(2026, 1, 1), date(2026, 12, 31), actor="t")
    return ThreadRepository.get_or_create(
        view_key="betala.loner", fiscal_year_id=year.id, model="test-model"
    )


@pytest.fixture
def payslip(thread):
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
    run = payroll.create_payroll_run(2026, 3, date(2026, 3, 25))
    payslip = payroll.generate_payslips(run.id)[0]
    db.commit()
    return payslip


def _payment(amount_ore: int, on: date = date(2026, 3, 25), ref: str = "1") -> str:
    bank = BankIntegrationService()
    connection = bank.create_connection("manual", f"Testbanken {ref}")
    bank.import_transactions(
        connection.id,
        [
            {
                "external_id": f"salary-{ref}",
                "date": on.isoformat(),
                "amount": -amount_ore / 100,
                "description": "LÖN ANNA",
            }
        ],
    )
    db.commit()
    return bank.get_transactions(connection_id=connection.id)[0].id


def _tool(name: str, thread, **arguments) -> dict:
    return execute_tool(
        name,
        arguments,
        actor="agent",
        capabilities=_CAPABILITIES,
        tool_context={"thread": thread} if thread is not None else None,
    )


def _answer(client, headers, decision_id: str, option_index: int):
    decision = DecisionRepository.get(decision_id)
    return client.post(
        f"/api/v1/decisions/{decision_id}/answer",
        json={"option_id": decision.options[option_index].id},
        headers=headers,
    )


def _voucher_count() -> int:
    return db.execute("SELECT COUNT(*) FROM vouchers").fetchone()[0]


# -- the payslip card -------------------------------------------------------


def test_proposing_finds_the_payment_and_books_nothing(thread, payslip):
    tx_id = _payment(payslip.net_salary)

    result = _tool("foresla_lonebokforing", thread, payslip_id=payslip.id)

    assert result["status"] == "pending"
    assert result["bank_transaction_id"] == tx_id
    assert _voucher_count() == 0
    decision = DecisionRepository.get(result["decision_id"])
    assert decision.thread_id == thread.id
    assert decision.view_key == "betala.loner"
    assert decision.kind == "approval"
    assert decision.amount_ore == payslip.net_salary
    assert decision.title == "Bokför lön mars 2026 · Anna Andersson"
    assert [o.title for o in decision.options] == ["Bokför lönen", "Inte nu"]
    assert "35 000 kr" in decision.reason
    # The voucher is shown as rows on the card, as a voucher proposal shows it.
    [card] = [
        p
        for p in ThreadRepository.list_posts(thread.id)
        if p.type == "decision" and p.body["decision_id"] == decision.id
    ]
    assert card.body["rows"][0] == {
        "account": "7000",
        "name": "Löner",
        "debit_ore": 5000000,
        "credit_ore": None,
    }
    assert {r["account"] for r in card.body["rows"]} == {
        "7000",
        "7510",
        "2710",
        "2730",
        "1930",
    }


def test_no_payment_or_several_is_refused_with_the_candidates(thread, payslip):
    with pytest.raises(ValidationError) as none:
        _tool("foresla_lonebokforing", thread, payslip_id=payslip.id)
    assert none.value.code == "payroll_payment_not_found"
    assert none.value.payload["candidates"] == []

    first = _payment(payslip.net_salary, date(2026, 3, 25), ref="1")
    second = _payment(payslip.net_salary, date(2026, 3, 27), ref="2")
    _payment(payslip.net_salary, date(2026, 5, 25), ref="3")  # outside the window
    with pytest.raises(ValidationError) as several:
        _tool("foresla_lonebokforing", thread, payslip_id=payslip.id)
    assert several.value.code == "payroll_payment_ambiguous"
    assert [c["bank_transaction_id"] for c in several.value.payload["candidates"]] == [
        first,
        second,
    ]

    result = _tool(
        "foresla_lonebokforing",
        thread,
        payslip_id=payslip.id,
        bank_transaction_id=second,
    )
    assert result["bank_transaction_id"] == second


def test_a_payment_of_another_amount_is_refused(thread, payslip):
    tx_id = _payment(payslip.net_salary + 100)
    with pytest.raises(ValidationError) as error:
        _tool(
            "foresla_lonebokforing",
            thread,
            payslip_id=payslip.id,
            bank_transaction_id=tx_id,
        )
    assert error.value.code == "payroll_amount_mismatch"


def test_it_refuses_outside_a_thread(thread, payslip):
    _payment(payslip.net_salary)
    with pytest.raises(ValidationError) as error:
        _tool("foresla_lonebokforing", None, payslip_id=payslip.id)
    assert error.value.code == "payroll_requires_thread"


def test_a_locked_period_is_refused_before_the_card(thread, payslip):
    _payment(payslip.net_salary)
    year = PeriodRepository.list_fiscal_years()[0]
    march = PeriodRepository.get_period_by_date(year.id, date(2026, 3, 25))
    PeriodRepository.lock_period(march.id, "stefan")
    db.commit()

    with pytest.raises(ValidationError) as error:
        _tool("foresla_lonebokforing", thread, payslip_id=payslip.id)
    assert error.value.code == "period_locked"
    assert db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 0


def test_the_same_card_is_joined_and_another_supersedes_it(thread, payslip):
    first_tx = _payment(payslip.net_salary, ref="1")
    first = _tool(
        "foresla_lonebokforing",
        thread,
        payslip_id=payslip.id,
        bank_transaction_id=first_tx,
    )
    again = _tool(
        "foresla_lonebokforing",
        thread,
        payslip_id=payslip.id,
        bank_transaction_id=first_tx,
    )
    assert again["existing_card"] is True
    assert again["decision_id"] == first["decision_id"]

    other_tx = _payment(payslip.net_salary, date(2026, 3, 26), ref="2")
    other = _tool(
        "foresla_lonebokforing",
        thread,
        payslip_id=payslip.id,
        bank_transaction_id=other_tx,
    )
    assert other["decision_id"] != first["decision_id"]
    assert DecisionRepository.get(first["decision_id"]).status == "superseded"
    assert PayrollBookingProposalRepository.get(first["proposal_id"]).status == (
        "superseded"
    )


def test_the_api_key_cannot_press_it(client, auth_headers, thread, payslip):
    _payment(payslip.net_salary)
    result = _tool("foresla_lonebokforing", thread, payslip_id=payslip.id)

    response = _answer(client, auth_headers, result["decision_id"], 0)

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "human_only"
    assert DecisionRepository.get(result["decision_id"]).status == "open"
    assert _voucher_count() == 0


def test_the_human_press_books_the_salary_and_writes_a_receipt(
    client, human_headers, thread, payslip
):
    tx_id = _payment(payslip.net_salary)
    result = _tool("foresla_lonebokforing", thread, payslip_id=payslip.id)

    response = _answer(client, human_headers, result["decision_id"], 0)

    assert response.status_code == 202
    booked = PayrollService().payslips.get(payslip.id)
    assert booked.voucher_id is not None
    assert booked.bank_transaction_id == tx_id
    assert (
        PayrollBookingProposalRepository.get(result["proposal_id"]).status == "booked"
    )
    receipt = ThreadRepository.list_posts(thread.id)[-1]
    assert receipt.type == "receipt"
    assert receipt.body["voucher_id"] == booked.voucher_id
    assert receipt.body["title"].endswith("postad · Lön Anna Andersson 2026-03")
    assert {row["key"] for row in receipt.body["rows"]} == {
        "7000",
        "7510",
        "2710",
        "2730",
        "1930",
    }


def test_declining_books_nothing(client, human_headers, thread, payslip):
    _payment(payslip.net_salary)
    result = _tool("foresla_lonebokforing", thread, payslip_id=payslip.id)

    _answer(client, human_headers, result["decision_id"], 1)

    assert _voucher_count() == 0
    assert PayrollBookingProposalRepository.get(result["proposal_id"]).status == (
        "declined"
    )


def test_a_press_after_the_books_changed_books_nothing(
    client, human_headers, thread, payslip
):
    tx_id = _payment(payslip.net_salary)
    result = _tool("foresla_lonebokforing", thread, payslip_id=payslip.id)
    BankIntegrationService().update_transaction_status(tx_id, status="booked")
    db.commit()

    response = _answer(client, human_headers, result["decision_id"], 0)

    assert response.status_code == 202
    assert _voucher_count() == 0
    assert (
        PayrollBookingProposalRepository.get(result["proposal_id"]).status == "failed"
    )
    error = ThreadRepository.list_posts(thread.id)[-1]
    assert error.type == "error"
    assert error.body["cause"].startswith("Lönen kunde inte bokföras")


# -- the AGI card -----------------------------------------------------------


def test_the_agi_waits_for_the_month_s_salaries(thread, payslip):
    with pytest.raises(ValidationError) as error:
        _tool("foresla_agi_bokforing", thread, year=2026, month=3)
    assert error.value.code == "agi_payslips_not_booked"


def test_the_human_press_books_the_agi_in_two_vouchers(
    client, human_headers, thread, payslip
):
    PayrollService().match_bank_transaction_and_book(
        payslip.id, _payment(payslip.net_salary)
    )
    db.commit()

    result = _tool("foresla_agi_bokforing", thread, year=2026, month=3)
    decision = DecisionRepository.get(result["decision_id"])
    assert decision.title == "Bokför arbetsgivardeklaration mars 2026"
    assert [o.title for o in decision.options] == [
        "Bokför arbetsgivardeklarationen",
        "Inte nu",
    ]
    assert decision.amount_ore == 3071000
    assert "2026-04-13" in decision.consequence
    [card] = [
        p
        for p in ThreadRepository.list_posts(thread.id)
        if p.type == "decision" and p.body["decision_id"] == decision.id
    ]
    debit = {r["account"]: r["debit_ore"] for r in card.body["rows"] if r["debit_ore"]}
    assert set(debit) == {"2710", "2730"}
    assert all(
        r["account"] in {"2710", "2730", "1630", "3740"} for r in card.body["rows"]
    )

    before = _voucher_count()
    response = _answer(client, human_headers, result["decision_id"], 0)

    assert response.status_code == 202
    assert _voucher_count() == before + 2
    assert PayrollService().get_agi(2026, 3).booked is True
    receipts = [
        p for p in ThreadRepository.list_posts(thread.id) if p.type == "receipt"
    ]
    assert len(receipts) == 2
    assert "Arbetsgivardeklaration 2026-03" in receipts[0].body["title"]


def test_the_runs_list_carries_the_month_s_agi(client, human_headers, payslip):
    response = client.get("/api/v1/payroll/runs", headers=human_headers)

    run = response.json()["payroll_runs"][0]
    assert run["agi"]["year"] == 2026
    assert run["agi"]["month"] == 3
    assert run["agi"]["booked"] is False
    assert run["agi"]["unbooked_payslips"] == 1


def test_the_runs_list_points_each_row_at_its_open_card(
    client, human_headers, thread, payslip
):
    def first_run():
        response = client.get("/api/v1/payroll/runs", headers=human_headers)
        return response.json()["payroll_runs"][0]

    assert first_run()["payslips"][0]["pending_decision_id"] is None

    _payment(payslip.net_salary)
    result = _tool("foresla_lonebokforing", thread, payslip_id=payslip.id)
    assert first_run()["payslips"][0]["pending_decision_id"] == result["decision_id"]
    assert first_run()["agi"]["pending_decision_id"] is None

    _answer(client, human_headers, result["decision_id"], 0)
    assert first_run()["payslips"][0]["pending_decision_id"] is None

    agi = _tool("foresla_agi_bokforing", thread, year=2026, month=3)
    assert first_run()["agi"]["pending_decision_id"] == agi["decision_id"]
