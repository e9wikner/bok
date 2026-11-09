"""Avtal och medgivanden (migration 048, `services/agreement_booking.py`).

An autogiro mandate has no date or amount of its own; it is the underlag of
every transaction it covers. The agent asks on a card which transactions
that is, a logged-in human approves -- once, or once and for the coming
transactions of the fiscal year -- and the intake pass books one voucher per
transaction, each with the mandate and its statement row.
"""

import uuid
from datetime import date
from typing import Callable, Optional

import pytest
from fastapi.testclient import TestClient

from config import settings
from db.database import db
from domain.types import IntakeStatus
from domain.validation import ValidationError
from repositories.account_repo import AccountRepository
from repositories.agreement_booking_repo import AgreementBookingRepository
from repositories.decision_repo import DecisionRepository
from repositories.intake_repo import IntakeRepository
from repositories.intake_reuse_repo import ReuseApprovalRepository
from repositories.period_repo import PeriodRepository
from repositories.thread_repo import ThreadRepository
from services.agent_session import build_user_turn
from services.agent_tools import execute_tool
from services.agreement_booking import AgreementBookingService
from services.auth import AuthService
from services.bank_inputs import BankInputService
from services.fiscal_years import FiscalYearService
from services.intake import IntakeService
from services.llm import LLMCapabilities, LLMTurn, ToolCall, Usage

VOUCHERS_VIEW = "bocker.verifikationer"
LYSA = "Autogiro - Lysa Spar"

_CAPABILITIES = LLMCapabilities(
    cache_breakpoint=True,
    pdf_document_blocks=True,
    refusal_stop_reason=True,
    streaming=False,
)


@pytest.fixture
def client(test_db):
    from api.main import app

    return TestClient(app)


@pytest.fixture
def human_headers():
    return {"Authorization": f"Bearer {AuthService().create_jwt('stefan')}"}


@pytest.fixture
def api_key_headers():
    return {"Authorization": f"Bearer {settings.api_key}"}


@pytest.fixture
def books(test_db, tmp_path):
    original = (settings.intake_dir, settings.bank_input_dir)
    settings.intake_dir = str(tmp_path / "intake")
    settings.bank_input_dir = str(tmp_path / "bank-inputs")
    year = FiscalYearService().create(
        date(2026, 1, 1), date(2026, 12, 31), actor="test"
    )
    for code, name, kind in [
        ("1387", "Värde av kapitalförsäkring", "asset"),
        ("1920", "PlusGiro", "asset"),
    ]:
        if AccountRepository.get(code) is None:
            AccountRepository.create(code, name, kind)
    yield year
    settings.intake_dir, settings.bank_input_dir = original


# -- helpers -----------------------------------------------------------------


def _mandate(name: str = "Lysa autogiro medgivande.pdf"):
    return IntakeService().create_source_from_upload_content(
        filename=name,
        content_type="image/png",
        content=uuid.uuid4().bytes,
        explanation=None,
        source_type="other",
        actor="dropzone",
    )


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


def _transactions(text: str = LYSA) -> list:
    rows = db.execute(
        """
        SELECT id, transaction_date, amount FROM bank_transactions
        WHERE description = ? ORDER BY transaction_date
        """,
        (text,),
    ).fetchall()
    return [dict(r) for r in rows]


def _monthly(months=(1, 2, 3)) -> list:
    _statement([(f"2026-{m:02d}-28", "-10000,00", LYSA) for m in months])
    return _transactions()


def _tool(name: str, args: dict, thread=None):
    return execute_tool(
        name,
        args,
        actor="agent",
        capabilities=_CAPABILITIES,
        tool_context={"thread": thread} if thread is not None else None,
    )


def _propose(source_id: str, transaction_ids: list, counter: str = "1387"):
    return _tool(
        "foresla_avtalsbokforing",
        {
            "source_id": source_id,
            "bank_transaction_ids": transaction_ids,
            "counter_account": counter,
            "reason": "Medgivandet gäller Lysas månadssparande.",
        },
    )


def _answer(client, headers, decision_id: str, option_index: int):
    decision = DecisionRepository.get(decision_id)
    return client.post(
        f"/api/v1/decisions/{decision_id}/answer",
        json={"option_id": decision.options[option_index].id},
        headers=headers,
    )


def _period_id(day: str) -> str:
    year = FiscalYearService.containing(date.fromisoformat(day))
    return PeriodRepository.get_period_by_date(year.id, date.fromisoformat(day)).id


def _post(source_id: str, transaction: dict, rows: Optional[list] = None, thread=None):
    day = str(transaction["transaction_date"])[:10]
    return _tool(
        "posta_verifikation",
        {
            "date": day,
            "period_id": _period_id(day),
            "description": f"Månadssparande Lysa, kontoutdrag 1920 rad {day}",
            "rows": rows
            or [
                {"account": "1387", "debit": 1000000},
                {"account": "1920", "credit": 1000000},
            ],
            "intake_source_ids": [source_id],
            "bank_transaction_ids": [transaction["id"]],
        },
        thread=thread,
    )


def _linked(source_id: str) -> set:
    return {lk.voucher_id for lk in IntakeRepository.list_links_for_source(source_id)}


def _pending_queue_ids() -> set:
    return {s.id for s in IntakeService().get_pending_queue()["items"]}


# -- the card ------------------------------------------------------------------


def test_the_pass_card_goes_in_verifikationer_and_the_underlag_waits(books):
    source = _mandate()
    transactions = _monthly()

    card = _propose(source.id, [tx["id"] for tx in transactions])

    decision = DecisionRepository.get(card["decision_id"])
    assert ThreadRepository.get(decision.thread_id).view_key == VOUCHERS_VIEW
    assert [o.title for o in decision.options] == [
        "Bokför 3 transaktioner",
        "Bokför och godkänn för kommande under 2026",
        "Avstå",
    ]
    assert card["rows"] == [
        {"account": "1387", "debit": 1000000},
        {"account": "1920", "credit": 1000000},
    ]
    assert source.id not in _pending_queue_ids()


@pytest.mark.parametrize(
    "lines, counter, code",
    [
        (
            [("2026-01-28", "-10000,00", LYSA), ("2026-02-28", "-12000,00", LYSA)],
            "1387",
            "agreement_transactions_differ",
        ),
        ([("2026-01-28", "-10000,00", LYSA)], "2640", "agreement_with_vat"),
        ([("2026-01-28", "-10000,00", LYSA)], "1920", "agreement_counter_is_bank"),
    ],
)
def test_a_card_the_server_cannot_book_is_refused(books, lines, counter, code):
    source = _mandate()
    _statement(lines)

    with pytest.raises(ValidationError) as excinfo:
        _propose(source.id, [tx["id"] for tx in _transactions()], counter=counter)
    assert excinfo.value.code == code


def test_a_new_card_supersedes_the_pending_one(books):
    source = _mandate()
    transactions = _monthly()
    first = _propose(source.id, [transactions[0]["id"]])

    second = _propose(source.id, [tx["id"] for tx in transactions])

    assert AgreementBookingRepository.get(first["booking_id"]).status == "superseded"
    assert DecisionRepository.get(first["decision_id"]).status == "superseded"
    assert AgreementBookingRepository.get(second["booking_id"]).status == "pending"


def test_the_api_key_cannot_answer_the_card(books, client, api_key_headers):
    source = _mandate()
    card = _propose(source.id, [tx["id"] for tx in _monthly()])

    response = _answer(client, api_key_headers, card["decision_id"], 0)

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "human_only"


@pytest.mark.parametrize("option_index", [0, 1])
def test_no_second_card_for_transactions_already_approved(
    books, client, human_headers, option_index
):
    # The thread turn that follows the press, before the pass has booked:
    # proposing the same set again would put the underlag back on hold.
    source = _mandate()
    transactions = _monthly()
    card = _propose(source.id, [tx["id"] for tx in transactions])
    _answer(client, human_headers, card["decision_id"], option_index)

    with pytest.raises(ValidationError) as excinfo:
        _propose(source.id, [tx["id"] for tx in transactions])

    assert excinfo.value.code == "agreement_already_approved"
    assert AgreementBookingRepository.pending_for_source(source.id) is None


def test_dismissing_the_card_releases_the_underlag(books, client, human_headers):
    source = _mandate()
    card = _propose(source.id, [tx["id"] for tx in _monthly()])

    response = client.post(
        f"/api/v1/decisions/{card['decision_id']}/dismiss", headers=human_headers
    )

    assert response.status_code in (200, 204)
    assert AgreementBookingRepository.get(card["booking_id"]).status == "superseded"
    assert AgreementBookingRepository.pending_for_source(source.id) is None


# -- the press and the pass's postings ------------------------------------------


def test_book_approves_the_set_and_the_pass_books_each_transaction(
    books, client, human_headers
):
    source = _mandate()
    transactions = _monthly()
    card = _propose(source.id, [tx["id"] for tx in transactions])

    assert _answer(client, human_headers, card["decision_id"], 0).status_code == 202

    assert source.id in _pending_queue_ids()
    assert ReuseApprovalRepository.active_for(source.id, books.id) is None
    turn = build_user_turn(
        IntakeRepository.get_source(source.id),
        {"type": "text", "text": "pdf"},
        date(2026, 11, 9),
        [],
    )
    text = turn[0]["content"][0]["text"]
    assert "avtalsbokföring: användaren har godkänt" in text
    assert all(tx["id"] in text for tx in transactions)

    results = [_post(source.id, tx) for tx in transactions]

    assert [r["pass_continues"] for r in results] == [True, True, False]
    assert results[-1]["agreement_remaining_transaction_ids"] == []
    assert _linked(source.id) == {r["id"] for r in results}
    assert IntakeRepository.get_source(source.id).status == IntakeStatus.PROCESSED
    assert AgreementBookingService().remaining(source.id) == []


def test_a_posting_is_replayed_not_booked_twice(books, client, human_headers):
    source = _mandate()
    transactions = _monthly()
    card = _propose(source.id, [tx["id"] for tx in transactions])
    _answer(client, human_headers, card["decision_id"], 0)

    first = _post(source.id, transactions[0])
    again = _post(source.id, transactions[0])

    assert again["id"] == first["id"]
    assert again.get("idempotent_replay") is True


def test_the_rows_must_be_the_approved_kontering(books, client, human_headers):
    source = _mandate()
    transactions = _monthly()
    card = _propose(source.id, [tx["id"] for tx in transactions])
    _answer(client, human_headers, card["decision_id"], 0)

    with pytest.raises(ValidationError) as excinfo:
        _post(
            source.id,
            transactions[0],
            rows=[
                {"account": "6500", "debit": 1000000},
                {"account": "1920", "credit": 1000000},
            ],
        )
    assert excinfo.value.code == "agreement_rows_differ"


def test_a_transaction_outside_the_set_is_not_booked_on_the_underlag(
    books, client, human_headers
):
    source = _mandate()
    transactions = _monthly((1, 2, 3))
    card = _propose(source.id, [tx["id"] for tx in transactions[:2]])
    _answer(client, human_headers, card["decision_id"], 0)
    _post(source.id, transactions[0])

    with pytest.raises(Exception) as excinfo:
        _post(source.id, transactions[2])
    assert getattr(excinfo.value, "code", None) == "intake_already_linked"


def test_a_thread_turn_does_not_book_an_approved_agreement(
    books, client, human_headers
):
    source = _mandate()
    transactions = _monthly()
    card = _propose(source.id, [tx["id"] for tx in transactions])
    _answer(client, human_headers, card["decision_id"], 0)
    thread = ThreadRepository.get(DecisionRepository.get(card["decision_id"]).thread_id)

    with pytest.raises(ValidationError) as excinfo:
        _post(source.id, transactions[0], thread=thread)
    assert excinfo.value.code == "agreement_booked_by_pass"


def test_avsta_fails_the_underlag_and_books_nothing(books, client, human_headers):
    source = _mandate()
    transactions = _monthly()
    card = _propose(source.id, [tx["id"] for tx in transactions])

    _answer(client, human_headers, card["decision_id"], 2)

    assert IntakeRepository.get_source(source.id).status == IntakeStatus.FAILED
    assert AgreementBookingService().remaining(source.id) == []
    assert _linked(source.id) == set()


# -- the standing approval -------------------------------------------------------


def _approved_standing(client, human_headers, months=(1, 2)):
    source = _mandate()
    transactions = _monthly(months)
    card = _propose(source.id, [tx["id"] for tx in transactions])
    _answer(client, human_headers, card["decision_id"], 1)
    for tx in transactions:
        _post(source.id, tx)
    return source


def test_standing_approval_books_the_coming_transactions(books, client, human_headers):
    source = _approved_standing(client, human_headers)
    assert ReuseApprovalRepository.active_for(source.id, books.id) is not None
    assert AgreementBookingService().followups() == []

    _statement(
        [
            ("2026-03-27", "-10000,00", LYSA),
            ("2026-03-28", "-15000,00", LYSA),  # another amount: not it
            ("2026-03-29", "-10000,00", "Autogiro - Annat"),  # another text
        ]
    )

    [item] = AgreementBookingService().followups()
    assert item["source"].id == source.id
    [march] = item["book"]
    assert str(march["transaction_date"])[:10] == "2026-03-27"
    assert item["ask"] == []
    text = AgreementBookingService().followup_turn(item)
    assert march["id"] in text and "registrera_avstaende" in text

    result = _post(source.id, march)

    assert result["pass_continues"] is False
    assert result["id"] in _linked(source.id)
    assert AgreementBookingService().followups() == []


def test_a_revoked_approval_books_nothing_more(books, client, human_headers):
    from services.intake_reuse import IntakeReuseService

    source = _approved_standing(client, human_headers)
    approval = ReuseApprovalRepository.active_for(source.id, books.id)
    IntakeReuseService().revoke(
        source.id, approval.id, reason="Sparandet är avslutat", actor="stefan"
    )
    _statement([("2026-03-27", "-10000,00", LYSA)])

    assert AgreementBookingService().followups() == []


def test_a_locked_period_is_left_for_a_human(books, client, human_headers):
    source = _approved_standing(client, human_headers)
    _statement([("2026-03-27", "-10000,00", LYSA)])
    PeriodRepository.lock_period(_period_id("2026-03-27"))

    assert AgreementBookingService().followups() == []
    assert source.id  # the approval stands; only the period is closed


def test_a_later_fiscal_year_asks_for_a_new_card(books, client, human_headers):
    source = _approved_standing(client, human_headers)
    FiscalYearService().create(date(2027, 1, 1), date(2027, 12, 31), actor="test")
    _statement([("2027-01-28", "-10000,00", LYSA)])

    [item] = AgreementBookingService().followups()
    assert item["book"] == []
    [january] = item["ask"]
    assert "foresla_avtalsbokforing" in AgreementBookingService().followup_turn(item)

    # The pass raises the card for 2027; while it waits, nothing is asked.
    _propose(source.id, [january["id"]])
    assert AgreementBookingService().followups() == []


def test_a_followup_the_pass_gave_up_on_is_not_tried_again(
    books, client, human_headers
):
    source = _approved_standing(client, human_headers)
    _statement([("2026-03-27", "-10000,00", LYSA)])
    [item] = AgreementBookingService().followups()

    AgreementBookingService().record_followup_outcome(
        source.id,
        [tx["id"] for tx in item["book"]],
        agent_run_id=None,
        reason="agent_no_outcome",
    )

    assert AgreementBookingService().followups() == []


# -- the intake pass -------------------------------------------------------------


class _FakeClient:
    """Pre-programmed turns, as in `tests/test_agent_runtime.py`."""

    def __init__(self, turns: list):
        self._turns = list(turns)
        self.capabilities = _CAPABILITIES
        self.calls: list = []

    def run_turn(self, system, messages, tools, model, max_tokens, **_hooks):
        self.calls.append(messages)
        return self._turns.pop(0) if len(self._turns) > 1 else self._turns[0]


def _posting_turn(source_id: str, transaction: dict, n: int) -> LLMTurn:
    day = str(transaction["transaction_date"])[:10]
    return LLMTurn(
        text="",
        tool_calls=[
            ToolCall(
                id=f"call-{n}",
                name="posta_verifikation",
                arguments={
                    "date": day,
                    "period_id": _period_id(day),
                    "description": f"Månadssparande Lysa {day}",
                    "rows": [
                        {"account": "1387", "debit": 1000000},
                        {"account": "1920", "credit": 1000000},
                    ],
                    "intake_source_ids": [source_id],
                    "bank_transaction_ids": [transaction["id"]],
                },
            )
        ],
        stop="tool_calls",
        usage=Usage(input_tokens=10, output_tokens=5, cache_read_input_tokens=0),
    )


def _write_file(source):
    path = IntakeService().resolve_source_file(source)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(b"\x89PNG\r\n")


def _run_pass(turns_for: Callable[[], list]):
    from services.agent_runtime import AgentWorker

    fake = _FakeClient(turns_for())
    run = AgentWorker().run_pass_once(client_factory=lambda model: fake)
    return run, fake


def test_the_pass_books_the_whole_approved_set_in_one_session(
    books, client, human_headers
):
    source = _mandate()
    transactions = _monthly()
    card = _propose(source.id, [tx["id"] for tx in transactions])
    _answer(client, human_headers, card["decision_id"], 0)

    run, fake = _run_pass(
        lambda: [_posting_turn(source.id, tx, n) for n, tx in enumerate(transactions)]
    )

    assert run is not None and run.status == "completed"
    assert len(fake.calls) == 3  # one session, three turns
    assert len(_linked(source.id)) == 3
    assert IntakeRepository.get_source(source.id).status == IntakeStatus.PROCESSED


def test_a_statement_import_gives_the_pass_a_followup_session(
    books, client, human_headers
):
    source = _approved_standing(client, human_headers)
    _write_file(IntakeRepository.get_source(source.id))
    _statement([("2026-03-27", "-10000,00", LYSA)])
    [march] = [tx for tx in _transactions() if tx["transaction_date"] == "2026-03-27"]

    run, fake = _run_pass(lambda: [_posting_turn(source.id, march, 0)])

    assert run is not None and run.status == "completed"
    turn_text = fake.calls[0][0]["content"][0]["text"]
    assert "Avtalsbokföring" in turn_text and march["id"] in turn_text
    assert len(_linked(source.id)) == 3
    assert AgreementBookingService().followups() == []


def test_a_followup_session_that_books_nothing_is_not_paid_for_again(
    books, client, human_headers
):
    source = _approved_standing(client, human_headers)
    _write_file(IntakeRepository.get_source(source.id))
    _statement([("2026-03-27", "-10000,00", LYSA)])
    giving_up = LLMTurn(
        text="Kan inte avgöra perioden.",
        tool_calls=[],
        stop="end",
        usage=Usage(input_tokens=10, output_tokens=5, cache_read_input_tokens=0),
    )

    run, _fake = _run_pass(lambda: [giving_up])

    assert run is not None
    assert AgreementBookingService().followups() == []
    assert _run_pass(lambda: [giving_up])[0] is None  # nothing to do


def test_migration_048_tables_are_append_only(books, client, human_headers):
    source = _mandate()
    card = _propose(source.id, [tx["id"] for tx in _monthly()])

    with pytest.raises(Exception):
        db.execute(
            "DELETE FROM agreement_booking_transactions WHERE booking_id = ?",
            (card["booking_id"],),
        )


def test_an_underlag_the_agent_abstained_on_is_back_in_the_queue_on_yes(
    books, client, human_headers
):
    source = _mandate()
    IntakeService().record_failed(
        source.id, summary="Medgivande", error_detail="Inget datum", actor="agent"
    )
    card = _propose(source.id, [tx["id"] for tx in _monthly()])

    _answer(client, human_headers, card["decision_id"], 1)

    assert IntakeRepository.get_source(source.id).status == IntakeStatus.PENDING
    assert source.id in _pending_queue_ids()


def test_a_thread_file_is_booked_by_the_pass_as_a_followup(
    books, client, human_headers
):
    from services.thread_service import ThreadService

    source = _mandate()
    transactions = _monthly()
    card = _propose(source.id, [tx["id"] for tx in transactions])
    thread = ThreadRepository.get(DecisionRepository.get(card["decision_id"]).thread_id)
    ThreadService.record_user_file(
        thread,
        filename=source.original_filename,
        size_bytes=16,
        actor="stefan",
        intake_source_id=source.id,
    )
    _answer(client, human_headers, card["decision_id"], 0)
    assert source.id not in _pending_queue_ids()  # the thread owns it
    _write_file(IntakeRepository.get_source(source.id))

    run, _fake = _run_pass(
        lambda: [_posting_turn(source.id, tx, n) for n, tx in enumerate(transactions)]
    )

    assert run is not None and run.status == "completed"
    assert len(_linked(source.id)) == 3
