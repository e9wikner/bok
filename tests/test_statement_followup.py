"""Kontoutdragets okopplade rader i intagspasset (migration 049,
`services/statement_followup.py`).

A statement transaction no voucher and no underlag accounts for -- the
payment of a supplier invoice already booked, a transfer, a fee -- used to
wait until a human pointed at it: the pass only took underlag from the
queue. The pass now gives each such transaction one session after the queue,
and does not pay for one it left open again.
"""

import uuid
from datetime import date
from typing import cast

import pytest

from config import settings
from db.database import db
from repositories.account_repo import AccountRepository
from repositories.bank_input_repo import BankInputRepository
from repositories.period_repo import PeriodRepository
from services.agent_tools import execute_tool
from services.bank_inputs import BankInputService
from services.fiscal_years import FiscalYearService
from services.intake import IntakeService
from services.llm import LLMCapabilities, LLMClient, LLMTurn, ToolCall, Usage
from services.statement_followup import StatementFollowupService

FELLO = "Betalning - FELLO"

_CAPABILITIES = LLMCapabilities(
    cache_breakpoint=True,
    pdf_document_blocks=True,
    refusal_stop_reason=True,
    streaming=False,
)


@pytest.fixture
def books(test_db, tmp_path):
    original = (settings.intake_dir, settings.bank_input_dir)
    settings.intake_dir = str(tmp_path / "intake")
    settings.bank_input_dir = str(tmp_path / "bank-inputs")
    year = FiscalYearService().create(
        date(2026, 1, 1), date(2026, 12, 31), actor="test"
    )
    for code, name, kind in [
        ("1630", "Skattekonto", "asset"),
        ("1920", "PlusGiro", "asset"),
        ("2440", "Leverantörsskulder", "liability"),
        ("2640", "Ingående moms", "liability"),
        ("6540", "IT-tjänster", "expense"),
    ]:
        if AccountRepository.get(code) is None:
            AccountRepository.create(code, name, kind)
    yield year
    settings.intake_dir, settings.bank_input_dir = original


# -- helpers -----------------------------------------------------------------


def _statement(lines: list, account: str = "1920"):
    service = BankInputService()
    connection_id = service.resolve_connection_reference(f"account:{account}")
    body = "\n".join(f"{day};{amount};{text}" for day, amount, text in lines)
    service.create_from_upload_content(
        filename=f"{account}-{uuid.uuid4().hex[:6]}.csv",
        content_type="text/csv",
        content=("Datum;Belopp;Text\n" + body).encode("utf-8"),
        bank_connection_id=connection_id,
        actor="test",
    )


def _transaction(text: str) -> dict:
    row = db.execute(
        "SELECT id, transaction_date, amount FROM bank_transactions "
        "WHERE description = ?",
        (text,),
    ).fetchone()
    return dict(row)


def _period_id(day: str) -> str:
    year = FiscalYearService.containing(date.fromisoformat(day))
    assert year is not None
    period = PeriodRepository.get_period_by_date(year.id, date.fromisoformat(day))
    assert period is not None
    return period.id


def _post(day: str, rows: list, description: str):
    """A voucher booked from an underlag of its own, before the statement."""
    source = IntakeService().create_source_from_upload_content(
        filename=f"{description}.png",
        content_type="image/png",
        content=uuid.uuid4().bytes,
        explanation=None,
        source_type="other",
        actor="dropzone",
    )
    return execute_tool(
        "posta_verifikation",
        {
            "date": day,
            "period_id": _period_id(day),
            "description": description,
            "rows": rows,
            "intake_source_ids": [source.id],
        },
        actor="agent",
        capabilities=_CAPABILITIES,
    )


def _fello_invoice():
    """The supplier invoice, booked from its own underlag weeks before."""
    return _post(
        "2026-01-05",
        [
            {"account": "6540", "debit": 22000},
            {"account": "2640", "debit": 5500},
            {"account": "2440", "credit": 27500},
        ],
        "Leverantörsfaktura Fello 11962843",
    )


def _bank_input_ids(transaction_id: str) -> list:
    return BankInputRepository.list_input_ids_for_transaction(transaction_id)[:1]


def _linked_voucher(transaction_id: str):
    row = db.execute(
        "SELECT voucher_id FROM current_voucher_bank_transactions "
        "WHERE bank_transaction_id = ?",
        (transaction_id,),
    ).fetchone()
    return row["voucher_id"] if row else None


class _FakeClient:
    def __init__(self, turns: list):
        self._turns = list(turns)
        self.capabilities = _CAPABILITIES
        self.calls: list = []
        self.tools: list = []

    def run_turn(self, system, messages, tools, model, max_tokens, **_hooks):
        self.calls.append(messages)
        self.tools.append([tool["name"] for tool in tools])
        return self._turns.pop(0) if len(self._turns) > 1 else self._turns[0]


def _usage() -> Usage:
    return Usage(input_tokens=10, output_tokens=5, cache_read_input_tokens=0)


def _payment_turn(transaction: dict) -> LLMTurn:
    day = str(transaction["transaction_date"])[:10]
    return LLMTurn(
        text="",
        tool_calls=[
            ToolCall(
                id="call-0",
                name="posta_verifikation",
                arguments={
                    "date": day,
                    "period_id": _period_id(day),
                    "description": (
                        "Betalning leverantörsfaktura Fello 11962843, se "
                        f"kontoutdrag 1920 jan 2026, rad {day}, 275 kr"
                    ),
                    "rows": [
                        {"account": "2440", "debit": 27500},
                        {"account": "1920", "credit": 27500},
                    ],
                    "bank_transaction_ids": [transaction["id"]],
                    "bank_input_ids": _bank_input_ids(transaction["id"]),
                },
            )
        ],
        stop="tool_calls",
        usage=_usage(),
    )


_GIVING_UP = LLMTurn(
    text="Ett kortköp: kvittot behövs, raden står kvar.",
    tool_calls=[],
    stop="end",
    usage=_usage(),
)


def _run_pass(turns: list):
    from services.agent_runtime import AgentWorker

    fake = _FakeClient(turns)
    run = AgentWorker().run_pass_once(
        client_factory=lambda model: cast(LLMClient, fake)
    )
    return run, fake


# -- which transactions ------------------------------------------------------


def test_a_payment_of_a_booked_invoice_waits_for_the_pass(books):
    _fello_invoice()
    _statement([("2026-01-30", "-275,00", FELLO)])
    payment = _transaction(FELLO)

    [item] = StatementFollowupService().followups()

    assert item["id"] == payment["id"]
    assert item["period_id"] == _period_id("2026-01-30")
    assert item["bank_input_ids"] == _bank_input_ids(payment["id"]) != []


def test_a_purchase_booked_from_its_receipt_is_not_taken_up(books):
    _post(
        "2026-01-12",
        [
            {"account": "6540", "debit": 8000},
            {"account": "2640", "debit": 2000},
            {"account": "1920", "credit": 10000},
        ],
        "Kortköp, kvitto",
    )
    _statement([("2026-01-12", "-100,00", "Kortköp")])

    assert StatementFollowupService().followups() == []


def test_a_transaction_a_voucher_may_be_is_left_for_a_human(books):
    _post(
        "2026-01-10",
        [
            {"account": "2440", "debit": 50000},
            {"account": "1920", "credit": 50000},
        ],
        "Betalning, tre dagar före raden",
    )
    _statement([("2026-01-13", "-500,00", "Betalning")])

    assert StatementFollowupService().followups() == []


def test_a_transaction_in_a_locked_period_is_not_taken_up(books):
    _statement([("2026-01-30", "-275,00", FELLO)])
    db.execute(
        "UPDATE periods SET locked = 1 WHERE id = ?", (_period_id("2026-01-30"),)
    )
    db.commit()

    assert StatementFollowupService().followups() == []


# -- the intake pass ---------------------------------------------------------


def test_the_pass_books_the_payment_against_the_statement_row(books):
    _fello_invoice()
    _statement([("2026-01-30", "-275,00", FELLO)])
    payment = _transaction(FELLO)

    run, fake = _run_pass([_payment_turn(payment)])

    assert run is not None and run.status == "completed"
    turn_text = fake.calls[0][0]["content"][0]["text"]
    assert payment["id"] in turn_text and "sok_verifikationer" in turn_text
    assert "posta_verifikation" in fake.tools[0]
    assert "registrera_avstaende" not in fake.tools[0]
    assert "be_om_beslut" not in fake.tools[0]
    assert _linked_voucher(payment["id"]) is not None
    assert StatementFollowupService().followups() == []


def test_a_transaction_the_pass_left_open_is_not_paid_for_again(books):
    _statement([("2026-01-21", "-89,00", "Kortköp Kjell")])
    purchase = _transaction("Kortköp Kjell")

    run, _fake = _run_pass([_GIVING_UP])

    assert run is not None and run.status == "completed"
    assert _linked_voucher(purchase["id"]) is None
    reason = db.execute(
        "SELECT reason FROM statement_followup_attempts "
        "WHERE bank_transaction_id = ?",
        (purchase["id"],),
    ).fetchone()["reason"]
    assert "kvittot" in reason
    assert StatementFollowupService().followups() == []
    assert _run_pass([_GIVING_UP])[0] is None  # nothing to do


# -- a transfer between own accounts ------------------------------------------

TILL_SKATTEKONTO = "Betalning - SKATTEVERKET"
INBETALNING = "Inbetalning bokförd 260831"


def _transfer_statements():
    """2026-08-29 out of 1920, 2026-09-01 into 1630: one transfer, two months."""
    _statement([("2026-08-29", "-300000,00", TILL_SKATTEKONTO)])
    _statement([("2026-09-01", "300000,00", INBETALNING)], account="1630")
    return _transaction(TILL_SKATTEKONTO), _transaction(INBETALNING)


def _transfer_turn(out: dict, into: dict) -> LLMTurn:
    return LLMTurn(
        text="",
        tool_calls=[
            ToolCall(
                id="call-0",
                name="posta_verifikation",
                arguments={
                    "date": "2026-08-29",
                    "period_id": _period_id("2026-08-29"),
                    "description": "Överföring till skattekontot, se "
                    "kontoutdrag 1920 2026-08-29 och 1630 2026-09-01",
                    "rows": [
                        {"account": "1630", "debit": 30_000_000},
                        {"account": "1920", "credit": 30_000_000},
                    ],
                    "bank_transaction_ids": [out["id"], into["id"]],
                    "bank_input_ids": _bank_input_ids(out["id"])
                    + _bank_input_ids(into["id"]),
                },
            )
        ],
        stop="tool_calls",
        usage=_usage(),
    )


def test_a_transfer_comes_with_its_other_side(books):
    out, into = _transfer_statements()

    items = {item["id"]: item for item in StatementFollowupService().followups()}

    other = items[out["id"]]["counterpart"]
    assert other["id"] == into["id"]
    assert other["bank_input_ids"] == _bank_input_ids(into["id"]) != []
    # Dated on the side the money left, whichever row the session is about.
    assert other["voucher_date"] == "2026-08-29"
    assert other["voucher_period_id"] == _period_id("2026-08-29")
    assert items[into["id"]]["counterpart"]["voucher_period_id"] == _period_id(
        "2026-08-29"
    )
    turn = StatementFollowupService.followup_turn(items[out["id"]])
    assert into["id"] in turn and "en gång per rad" in turn


def test_the_pass_books_a_transfer_once(books):
    out, into = _transfer_statements()

    run, fake = _run_pass([_transfer_turn(out, into)])

    assert run is not None and run.status == "completed"
    voucher_id = _linked_voucher(out["id"])
    assert voucher_id is not None and _linked_voucher(into["id"]) == voucher_id
    # One session, ended by its posting: the second row was booked by the
    # first, so it gets none.
    assert len(fake.calls) == 1
    assert (
        db.execute(
            "SELECT COUNT(*) AS n FROM vouchers WHERE status = 'posted'"
        ).fetchone()["n"]
        == 1
    )


def test_a_booked_row_is_no_longer_refreshed(books):
    out, into = _transfer_statements()
    [first, _second] = StatementFollowupService().followups()
    assert StatementFollowupService().refreshed(first["id"]) is not None

    execute_tool(
        "posta_verifikation",
        _transfer_turn(out, into).tool_calls[0].arguments,
        actor="agent",
        capabilities=_CAPABILITIES,
    )

    assert StatementFollowupService().refreshed(out["id"]) is None
    assert StatementFollowupService().refreshed(into["id"]) is None


def test_migration_049_attempts_are_append_only(books):
    _statement([("2026-01-21", "-89,00", "Kortköp Kjell")])
    _run_pass([_GIVING_UP])

    with pytest.raises(Exception):
        db.execute("DELETE FROM statement_followup_attempts")
