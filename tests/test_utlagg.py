"""Utlägg: an underlag in the dropzone's Utlägg/ is booked against 2820, a
foreign amount at Riksbank's rate with the rate in the voucher's comment, and
a purchase that shows up in the company's statements is asked about before
it is booked (migration 045, `services/reimbursement_check.py`)."""

import sqlite3
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from config import settings
from db.database import db
from domain.types import IntakeStatus
from domain.validation import ValidationError
from repositories.account_repo import AccountRepository
from repositories.decision_repo import DecisionRepository
from repositories.intake_repo import IntakeRepository
from repositories.reimbursement_check_repo import ReimbursementCheckRepository
from repositories.thread_repo import ThreadRepository
from repositories.voucher_repo import VoucherRepository
from services.agent_session import build_user_turn
from services.agent_tools import execute_tool
from services.bank_inputs import BankInputService
from services.fiscal_years import FiscalYearService
from services.llm import LLMCapabilities

VOUCHERS_VIEW = "bocker.verifikationer"

_CAPABILITIES = LLMCapabilities(
    cache_breakpoint=True,
    pdf_document_blocks=True,
    refusal_stop_reason=True,
    streaming=False,
)

#: Riksbank's SEKUSDPMI as the fetcher returns it: Wednesday 2026-10-14.
_USD = [{"date": "2026-10-14", "value": 9.45}]


@pytest.fixture
def client(test_db):
    from api.main import app

    return TestClient(app)


@pytest.fixture
def books(test_db, tmp_path, monkeypatch):
    original = (settings.intake_dir, settings.bank_input_dir)
    settings.intake_dir = str(tmp_path / "intake")
    settings.bank_input_dir = str(tmp_path / "bank-inputs")
    calls = []

    def fetch(series, from_date, to_date):
        calls.append(series)
        return _USD

    monkeypatch.setattr("services.exchange_rates._fetch_from_riksbank", fetch)
    year = FiscalYearService().create(
        date(2026, 1, 1), date(2026, 12, 31), actor="test"
    )
    for code, name, kind in [("6540", "IT-tjänster", "expense")]:
        if AccountRepository.get(code) is None:
            AccountRepository.create(code, name, kind)
    yield year, calls
    settings.intake_dir, settings.bank_input_dir = original


def _october(year):
    from repositories.period_repo import PeriodRepository

    return next(
        p for p in PeriodRepository.list_periods(year.id) if p.start_date.month == 10
    )


def _utlagg(name: str = "openai-faktura.pdf", source_type: str = "reimbursement"):
    from services.intake import IntakeService

    return IntakeService().create_source_from_upload_content(
        filename=name,
        content_type="image/png",
        content=uuid.uuid4().bytes,
        explanation=None,
        source_type=source_type,
        actor="dropzone",
    )


def _statement(lines: str):
    service = BankInputService()
    connection_id = service.resolve_connection_reference("account:1930")
    return service.create_from_upload_content(
        filename=f"utdrag-{uuid.uuid4().hex[:6]}.csv",
        content_type="text/csv",
        content=("Datum;Belopp;Text\n" + lines).encode("utf-8"),
        bank_connection_id=connection_id,
        actor="test",
    )


def _tool(name: str, args: dict, thread=None):
    return execute_tool(
        name,
        args,
        actor="agent",
        capabilities=_CAPABILITIES,
        tool_context={"thread": thread} if thread is not None else None,
    )


def _reverse_charge_rows(sek_ore: int, settle: str = "2820") -> list:
    vat = sek_ore // 4
    return [
        {"account": "6540", "debit": sek_ore},
        {"account": settle, "credit": sek_ore},
        {"account": "2645", "debit": vat},
        {"account": "2614", "credit": vat},
        {"account": "4531", "debit": sek_ore},
        {"account": "4598", "credit": sek_ore},
    ]


def _post(year, source_id: str, rows: list, **extra):
    return _tool(
        "posta_verifikation",
        {
            "date": "2026-10-14",
            "period_id": _october(year).id,
            "description": "OpenAI, API-krediter",
            "rows": rows,
            "intake_source_ids": [source_id],
            **extra,
        },
    )


_VALUTA = {"currency": "USD", "amount": "20.00", "rate_date": "2026-10-14"}


# --- the agent sees what the folder says --------------------------------------


def test_the_user_turn_says_it_is_an_utlagg(books):
    source = _utlagg()
    text = build_user_turn(source, {"type": "text", "text": "x"}, date.today(), [])[0][
        "content"
    ][0]["text"]
    assert "- typ: utlägg (Utlägg/)" in text
    assert "2820" in text
    receipt = _utlagg("kvitto.png", source_type="receipt")
    text = build_user_turn(receipt, {"type": "text", "text": "x"}, date.today(), [])[0][
        "content"
    ][0]["text"]
    assert "- typ: kvitto (Kvitton/)" in text


# --- a foreign utlägg, reverse charge, the rate in the comment ----------------


def test_a_foreign_utlagg_is_booked_at_riksbanks_rate_with_the_rate_in_the_comment(
    books, client, auth_headers
):
    year, calls = books
    source = _utlagg()
    rate = _tool(
        "hamta_valutakurs", {"currency": "USD", "date": "2026-10-14", "amount": "20"}
    )
    assert rate["sek_ore"] == 18900
    assert rate["rate"] == "9.45"

    result = _post(
        year,
        source.id,
        _reverse_charge_rows(18900),
        valuta=_VALUTA,
        comment="Omvänd skattskyldighet: API-tjänst från säljare i USA, ruta 22.",
    )

    voucher = VoucherRepository.get(result["id"])
    assert voucher.comment.splitlines() == [
        "Omräknat 20,00 USD × 9,45 SEK/USD = 189,00 kr. Riksbankens dagliga "
        "mittkurs (serie SEKUSDPMI) för 2026-10-14, köpdatum. Källa: Sveriges "
        "Riksbank, https://api.riksbank.se/swea/v1/Observations/SEKUSDPMI/"
        "2026-10-14/2026-10-14",
        "Omvänd skattskyldighet: API-tjänst från säljare i USA, ruta 22.",
    ]
    assert result["agent"]["conversion"]["sek_ore"] == 18900
    # One fetch for the tool, none for the posting: the rate is stored.
    assert calls == ["SEKUSDPMI"]

    response = client.get(f"/api/v1/vouchers/{voucher.id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["comment"] == voucher.comment

    # A posted voucher's comment never changes.
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        db.execute("UPDATE vouchers SET comment = 'ändrad' WHERE id = ?", (voucher.id,))


def test_the_agent_cannot_book_its_own_rate(books):
    year, _ = books
    source = _utlagg()
    with pytest.raises(ValidationError) as excinfo:
        # The private card's 192,40 kr, not Riksbank's 189,00.
        _post(year, source.id, _reverse_charge_rows(19240), valuta=_VALUTA)
    assert excinfo.value.code == "fx_amount_mismatch"
    assert excinfo.value.payload["sek_ore"] == 18900
    assert IntakeRepository.get_source(source.id).status == IntakeStatus.PENDING


def test_an_utlagg_is_never_credited_to_the_bank(books):
    year, _ = books
    source = _utlagg()
    with pytest.raises(ValidationError) as excinfo:
        _post(
            year, source.id, _reverse_charge_rows(18900, settle="1930"), valuta=_VALUTA
        )
    assert excinfo.value.code == "reimbursement_requires_2820"


def test_a_receipt_from_kvitton_is_not_checked_as_an_utlagg(books):
    year, _ = books
    _statement("2026-10-15;-189,00;OPENAI\n")
    source = _utlagg("kvitto.png", source_type="receipt")
    result = _post(
        year, source.id, _reverse_charge_rows(18900, settle="1930"), valuta=_VALUTA
    )
    assert result["status"] == "posted"


# --- a statement transaction that looks like the purchase ---------------------


def test_kontrollera_utlagg_finds_the_company_card_within_five_percent(books):
    _statement("2026-10-16;-192,40;OPENAI *CHATGPT\n2026-10-16;-500,00;Annat\n")
    source = _utlagg()
    result = _tool(
        "kontrollera_utlagg",
        {
            "source_id": source.id,
            "amount_ore": 18900,
            "date": "2026-10-14",
            "foreign_currency": True,
        },
    )
    assert [hit["amount_ore"] for hit in result["hits"]] == [19240]
    assert "foresla_utlaggskontroll" in result["next"]

    exact = _tool(
        "kontrollera_utlagg",
        {"source_id": source.id, "amount_ore": 18900, "date": "2026-10-14"},
    )
    assert exact["hits"] == []


def test_a_matching_transaction_stops_the_posting_and_the_card_asks(
    books, client, auth_headers
):
    year, _ = books
    _statement("2026-10-16;-192,40;OPENAI *CHATGPT\n")
    source = _utlagg()

    with pytest.raises(ValidationError) as excinfo:
        _post(year, source.id, _reverse_charge_rows(18900), valuta=_VALUTA)
    assert excinfo.value.code == "reimbursement_matches_statement"
    hit = excinfo.value.payload["hits"][0]

    # The intake pass has no thread: the card goes in Verifikationer.
    card = _tool(
        "foresla_utlaggskontroll",
        {"source_id": source.id, "bank_transaction_id": hit["bank_transaction_id"]},
    )
    decision = DecisionRepository.get(card["decision_id"])
    thread = ThreadRepository.get(decision.thread_id)
    assert thread.view_key == VOUCHERS_VIEW
    assert [o.title for o in decision.options] == [
        "Det är ett privat utlägg",
        "Företaget betalade",
        "Avstå",
    ]
    # The underlag waits out of the pass's queue.
    assert source.id not in {s.id for s in IntakeRepository.list_pending()}
    # Asking again joins the same card.
    again = _tool(
        "foresla_utlaggskontroll",
        {"source_id": source.id, "bank_transaction_id": hit["bank_transaction_id"]},
    )
    assert again["existing_card"] is True
    with pytest.raises(ValidationError) as excinfo:
        _post(year, source.id, _reverse_charge_rows(18900), valuta=_VALUTA)
    assert excinfo.value.code == "reimbursement_check_pending"

    response = client.post(
        f"/api/v1/decisions/{decision.id}/answer",
        json={"option_id": decision.options[0].id},
        headers=auth_headers,
    )
    assert response.status_code == 202, response.text

    # Back in the queue, the pass told what the human said, and it books.
    source = IntakeRepository.get_source(source.id)
    assert source.id in {s.id for s in IntakeRepository.list_pending()}
    text = build_user_turn(source, {"type": "text", "text": "x"}, date.today(), [])[0][
        "content"
    ][0]["text"]
    assert (
        "- utläggskontroll: användaren har svarat att det är ett privat utlägg" in text
    )
    result = _post(year, source.id, _reverse_charge_rows(18900), valuta=_VALUTA)
    assert result["status"] == "posted"


def test_company_paid_is_not_booked_against_2820(books, client, auth_headers):
    year, _ = books
    _statement("2026-10-16;-192,40;OPENAI *CHATGPT\n")
    source = _utlagg()
    hits = _tool(
        "kontrollera_utlagg",
        {
            "source_id": source.id,
            "amount_ore": 18900,
            "date": "2026-10-14",
            "foreign_currency": True,
        },
    )["hits"]
    card = _tool(
        "foresla_utlaggskontroll",
        {"source_id": source.id, "bank_transaction_id": hits[0]["bank_transaction_id"]},
    )
    decision = DecisionRepository.get(card["decision_id"])
    client.post(
        f"/api/v1/decisions/{decision.id}/answer",
        json={"option_id": decision.options[1].id},
        headers=auth_headers,
    )

    check = ReimbursementCheckRepository.get_by_decision(decision.id)
    assert check.status == "company_paid"
    with pytest.raises(ValidationError) as excinfo:
        _post(year, source.id, _reverse_charge_rows(18900), valuta=_VALUTA)
    assert excinfo.value.code == "reimbursement_company_paid"
    assert hits[0]["bank_transaction_id"] in excinfo.value.details


def test_avsta_records_the_underlag_as_failed(books, client, auth_headers):
    _statement("2026-10-14;-189,00;OPENAI\n")
    source = _utlagg()
    hits = _tool(
        "kontrollera_utlagg",
        {"source_id": source.id, "amount_ore": 18900, "date": "2026-10-14"},
    )["hits"]
    card = _tool(
        "foresla_utlaggskontroll",
        {"source_id": source.id, "bank_transaction_id": hits[0]["bank_transaction_id"]},
    )
    decision = DecisionRepository.get(card["decision_id"])
    client.post(
        f"/api/v1/decisions/{decision.id}/answer",
        json={"option_id": decision.options[2].id},
        headers=auth_headers,
    )
    assert IntakeRepository.get_source(source.id).status == IntakeStatus.FAILED


def test_a_reimbursement_payout_is_not_a_hit(books):
    """The payout to the person who paid (debit 2820, credit 1930) has the
    same amount days later. Linked to its voucher, it is not the purchase."""
    year, _ = books
    first = _utlagg()
    _post(year, first.id, _reverse_charge_rows(18900), valuta=_VALUTA)
    _statement("2026-10-20;-189,00;Ersättning utlägg Stefan\n")
    from repositories.bank_input_repo import BankInputRepository
    from services.ledger import LedgerService

    tx = BankInputRepository.find_outgoing_near(
        18900, 18900, "2026-10-01", "2026-10-31"
    )
    assert len(tx) == 1
    ledger = LedgerService()
    payout = ledger.create_voucher(
        series="A",
        date=date(2026, 10, 20),
        period_id=_october(year).id,
        description="Ersättning utlägg",
        rows_data=[
            {"account": "2820", "debit": 18900},
            {"account": "1930", "credit": 18900},
        ],
        created_by="test",
    )
    ledger.post_voucher(payout.id, actor="test")
    from services.statement_match import StatementMatchService

    StatementMatchService().link(tx[0]["id"], payout.id, actor="test")

    assert (
        BankInputRepository.find_outgoing_near(18900, 18900, "2026-10-01", "2026-10-31")
        == []
    )


def test_a_proposal_carries_the_comment_to_the_card_and_the_draft(books):
    year, _ = books
    thread = ThreadRepository.get_or_create(
        view_key=VOUCHERS_VIEW, fiscal_year_id=year.id, model="test-model"
    )
    result = _tool(
        "foresla_verifikation",
        {
            "description": "OpenAI, API-krediter",
            "rows": _reverse_charge_rows(18900),
            "date": "2026-10-14",
            "period_id": _october(year).id,
            "valuta": _VALUTA,
            "comment": "Ruta 22.",
        },
        thread=thread,
    )
    draft = VoucherRepository.get(result["draft_id"])
    assert draft.comment.startswith("Omräknat 20,00 USD × 9,45 SEK/USD = 189,00 kr.")
    assert draft.comment.endswith("\nRuta 22.")
    post = next(
        p for p in ThreadRepository.list_posts(thread.id) if p.id == result["post_id"]
    )
    assert post.body["comment"] == draft.comment
