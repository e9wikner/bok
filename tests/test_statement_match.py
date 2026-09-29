"""Account statements (CSV) as underlag: matching, coverage and dedupe.

A transaction on an imported statement is the underlag of the posted voucher
it belongs to (services/statement_match.py, domain/statement_coverage.py).
"""

import asyncio
import sqlite3
from datetime import date
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException

from api.routes.bank_inputs import upload_bank_input
from api.routes.vouchers import get_voucher_source_context
from config import settings
from db.database import db
from repositories.account_repo import AccountRepository
from repositories.bank_input_repo import BankInputRepository
from repositories.voucher_repo import VoucherRepository
from services.agent_tools import AGENT_TOOL_DEFINITIONS, execute_tool
from services.bank_inputs import BankInputConflictError, BankInputService
from services.bank_integration import BankIntegrationService
from services.llm import LLMCapabilities
from services.statement_match import StatementMatchService

SKATTEKONTO_HEADER = "Bokföringsdatum;Text;Belopp;Saldo\n"
BANK_HEADER = "Datum;Belopp;Text\n"


@pytest.fixture
def bank_input_dir(tmp_path):
    original = settings.bank_input_dir
    settings.bank_input_dir = str(tmp_path / "bank-inputs")
    yield Path(settings.bank_input_dir)
    settings.bank_input_dir = original


@pytest.fixture
def books(ledger_service, fiscal_year, bank_input_dir):
    """Accounts and every month of 2026."""
    for code, name, kind in [
        ("1630", "Skattekonto", "asset"),
        ("1930", "Företagskonto", "asset"),
        ("2518", "Betald F-skatt", "liability"),
        ("2641", "Ingående moms", "vat_in"),
        ("6212", "Mobiltelefon", "expense"),
        ("6570", "Bankkostnader", "expense"),
    ]:
        if AccountRepository.get(code) is None:
            AccountRepository.create(code, name, kind)
    periods = {}
    for month in range(1, 13):
        end = date(2026, month, 28)
        periods[month] = ledger_service.periods.create_period(
            fiscal_year_id=fiscal_year.id,
            year=2026,
            month=month,
            start_date=date(2026, month, 1),
            end_date=end,
        )
    return ledger_service, periods


def _post(books, day: date, description: str, rows: list[dict]):
    ledger, periods = books
    voucher = ledger.create_voucher(
        series="A",
        date=day,
        period_id=periods[day.month].id,
        description=description,
        rows_data=rows,
        created_by="test",
    )
    return ledger.post_voucher(voucher.id, actor="test")


def _transfer(books, day: date, amount_ore: int):
    """Inbetalning till skattekontot: 1630 debit, 1930 credit."""
    return _post(
        books,
        day,
        "Inbetalning till skattekontot",
        [
            {"account": "1630", "debit": amount_ore, "credit": 0},
            {"account": "1930", "debit": 0, "credit": amount_ore},
        ],
    )


def _import(account: str, csv_text: str, filename: str = "utdrag.csv"):
    service = BankInputService()
    connection_id = service.resolve_connection_reference(f"account:{account}")
    return service.create_from_upload_content(
        filename=filename,
        content_type="text/csv",
        content=csv_text.encode("utf-8"),
        bank_connection_id=connection_id,
        actor="test",
    )


def _voucher(voucher_id: str):
    return VoucherRepository.get(voucher_id)


def _missing_ids() -> set[str]:
    vouchers, _ = VoucherRepository.list_all(status="posted", missing_attachment=True)
    return {v.id for v in vouchers}


# --- coverage ---------------------------------------------------------------


def test_transfer_needs_both_statements(books):
    voucher = _transfer(books, date(2026, 1, 15), 30_000_000)
    assert _voucher(voucher.id).missing_statement_accounts == ["1630", "1930"]

    _import("1930", BANK_HEADER + "2026-01-15;-300000,00;Till skattekonto\n")
    after_bank = _voucher(voucher.id)
    assert after_bank.missing_attachment is True
    assert after_bank.missing_statement_accounts == ["1630"]
    assert voucher.id in _missing_ids()

    _import(
        "1630",
        SKATTEKONTO_HEADER + "2026-01-15;Inbetalning;300000;312000\n",
    )
    after_both = _voucher(voucher.id)
    assert after_both.missing_attachment is False
    assert after_both.missing_statement_accounts == []
    assert voucher.id not in _missing_ids()


def test_statement_imported_before_posting_links_on_posting(books):
    _import(
        "1630",
        SKATTEKONTO_HEADER + "2026-02-12;Debiterad preliminärskatt;-15202;1000\n",
    )
    voucher = _post(
        books,
        date(2026, 2, 12),
        "Debiterad preliminärskatt",
        [
            {"account": "2518", "debit": 1_520_200, "credit": 0},
            {"account": "1630", "debit": 0, "credit": 1_520_200},
        ],
    )
    assert _voucher(voucher.id).missing_attachment is False


def test_purchase_with_input_vat_is_never_covered(books):
    voucher = _post(
        books,
        date(2026, 1, 20),
        "Telefon",
        [
            {"account": "6212", "debit": 22_000, "credit": 0},
            {"account": "2641", "debit": 5_500, "credit": 0},
            {"account": "1930", "debit": 0, "credit": 27_500},
        ],
    )
    _import("1930", BANK_HEADER + "2026-01-20;-275,00;Fello\n")
    after = _voucher(voucher.id)
    assert after.missing_attachment is True
    # A receipt is what is missing, not a statement.
    assert after.missing_statement_accounts == []
    assert BankInputRepository.list_statement_links_for_voucher(voucher.id) == []


# --- matching ---------------------------------------------------------------


def test_date_off_by_days_is_a_candidate_not_a_link(books):
    voucher = _transfer(books, date(2026, 3, 10), 10_000_000)
    _import("1930", BANK_HEADER + "2026-03-12;-100000,00;Till skattekonto\n")
    assert BankInputRepository.list_statement_links_for_voucher(voucher.id) == []

    [open_tx] = StatementMatchService().open_transactions()
    assert open_tx.kind == "candidates"
    assert [c.voucher_id for c in open_tx.candidates] == [voucher.id]
    assert open_tx.candidates[0].date_diff_days == 2


def test_two_vouchers_same_day_same_amount_are_candidates(books):
    first = _post(
        books,
        date(2026, 4, 25),
        "Lysa",
        [
            {"account": "6570", "debit": 1_000_000, "credit": 0},
            {"account": "1930", "debit": 0, "credit": 1_000_000},
        ],
    )
    second = _post(
        books,
        date(2026, 4, 25),
        "Lysa igen",
        [
            {"account": "6570", "debit": 1_000_000, "credit": 0},
            {"account": "1930", "debit": 0, "credit": 1_000_000},
        ],
    )
    _import("1930", BANK_HEADER + "2026-04-25;-10000,00;Lysa\n")
    [open_tx] = StatementMatchService().open_transactions()
    assert open_tx.kind == "candidates"
    assert {c.voucher_id for c in open_tx.candidates} == {first.id, second.id}


def test_wrong_sign_does_not_match(books):
    voucher = _transfer(books, date(2026, 5, 5), 5_000_000)
    _import("1930", BANK_HEADER + "2026-05-05;50000,00;Insättning\n")
    assert BankInputRepository.list_statement_links_for_voucher(voucher.id) == []


def test_manual_link_after_decision(books):
    voucher = _transfer(books, date(2026, 3, 10), 10_000_000)
    _import("1930", BANK_HEADER + "2026-03-12;-100000,00;Till skattekonto\n")
    [open_tx] = StatementMatchService().open_transactions()

    result = StatementMatchService().link(
        open_tx.bank_transaction_id, voucher.id, actor="agent"
    )
    assert result["voucher_number"] == f"A-{voucher.number}"
    assert result["missing_statement_accounts"] == ["1630"]
    assert result["replayed"] is False

    again = StatementMatchService().link(
        open_tx.bank_transaction_id, voucher.id, actor="agent"
    )
    assert again["replayed"] is True


def test_manual_link_refuses_purchase_and_amount_mismatch(books):
    purchase = _post(
        books,
        date(2026, 6, 1),
        "Telefon",
        [
            {"account": "6212", "debit": 8_000, "credit": 0},
            {"account": "2641", "debit": 2_000, "credit": 0},
            {"account": "1930", "debit": 0, "credit": 10_000},
        ],
    )
    other = _transfer(books, date(2026, 6, 1), 20_000)
    _import("1930", BANK_HEADER + "2026-06-01;-100,00;Fello\n")
    [open_tx] = StatementMatchService().open_transactions()

    with pytest.raises(BankInputConflictError) as purchase_error:
        StatementMatchService().link(
            open_tx.bank_transaction_id, purchase.id, actor="agent"
        )
    assert purchase_error.value.code == "statement_not_underlag_for_purchase"

    with pytest.raises(BankInputConflictError) as amount_error:
        StatementMatchService().link(
            open_tx.bank_transaction_id, other.id, actor="agent"
        )
    assert amount_error.value.code == "amount_mismatch"


def test_links_are_append_only(books):
    voucher = _transfer(books, date(2026, 1, 15), 30_000_000)
    _import("1930", BANK_HEADER + "2026-01-15;-300000,00;Till skattekonto\n")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "DELETE FROM voucher_bank_transactions WHERE voucher_id = ?",
            (voucher.id,),
        )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "UPDATE voucher_bank_inputs SET linked_by = 'x' WHERE voucher_id = ?",
            (voucher.id,),
        )


def test_source_context_lists_statement_links(books):
    voucher = _transfer(books, date(2026, 1, 15), 30_000_000)
    _import(
        "1930",
        BANK_HEADER + "2026-01-15;-300000,00;Till skattekonto\n",
        filename="1930 jan.csv",
    )
    context = asyncio.run(
        get_voucher_source_context(voucher.id, ledger=books[0], actor="test")
    )
    [link] = context["statement_links"]
    assert link["account_code"] == "1930"
    assert link["date"] == "2026-01-15"
    assert link["amount_ore"] == -30_000_000
    assert link["original_filename"] == "1930 jan.csv"


# --- overlapping exports and duplicates -------------------------------------


def test_overlapping_exports_keep_one_transaction_per_row(books):
    jan_mar = SKATTEKONTO_HEADER + (
        "2026-01-12;Debiterad preliminärskatt;-15202;1000\n"
        "2026-02-12;Debiterad preliminärskatt;-15202;2000\n"
        "2026-03-12;Debiterad preliminärskatt;-15202;3000\n"
    )
    jan_apr = jan_mar + "2026-04-12;Debiterad preliminärskatt;-15202;4000\n"
    first = _import("1630", jan_mar, filename="jan-mar.csv")
    second = _import("1630", jan_apr, filename="jan-apr.csv")
    assert first.imported_count == 3
    assert second.imported_count == 1
    assert second.skipped_count == 3

    rows = db.execute(
        "SELECT COUNT(*) AS n FROM bank_transactions bt"
        " JOIN bank_connections bc ON bc.id = bt.bank_connection_id"
        " WHERE bc.account_number = '1630'"
    ).fetchone()
    assert rows["n"] == 4


def test_identical_rows_on_one_day_are_two_transactions(books):
    content = BANK_HEADER + (
        "2026-07-25;-10000,00;Lysa\n" "2026-07-25;-10000,00;Lysa\n"
    )
    first = _import("1930", content, filename="a.csv")
    assert first.imported_count == 2
    # A later, overlapping export finds the same two again.
    second = _import("1930", content + "2026-07-26;-5,00;Avgift\n", filename="b.csv")
    assert second.imported_count == 1
    assert second.skipped_count == 2


def test_amounts_are_rounded_to_the_ore():
    service = BankIntegrationService()
    assert service._normalize_amount("1,15") == "1.15"
    assert int(round(float("1.15") * 100)) == 115


# --- chat upload (auto account) -----------------------------------------------


class _UploadFile:
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self.content_type = "text/csv"
        self.file = BytesIO(content)

    async def read(self, size: int = -1) -> bytes:
        return self.file.read(size)


def test_auto_account_from_skatteverket_format(books):
    voucher = _transfer(books, date(2026, 1, 15), 30_000_000)
    answer = asyncio.run(
        upload_bank_input(
            file=_UploadFile(
                "skattekonto.csv",
                (SKATTEKONTO_HEADER + "2026-01-15;Inbetalning;300000;1\n").encode(),
            ),
            bank_connection_id="auto",
            actor="test",
        )
    )
    assert answer["account_code"] == "1630"
    assert answer["linked_voucher_count"] == 1
    assert _voucher(voucher.id).missing_statement_accounts == ["1930"]


def test_auto_account_from_file_name(books):
    answer = asyncio.run(
        upload_bank_input(
            file=_UploadFile(
                "1930 september.csv",
                (BANK_HEADER + "2026-09-12;-5,00;Avgift\n").encode(),
            ),
            bank_connection_id="auto",
            actor="test",
        )
    )
    assert answer["account_code"] == "1930"


def test_auto_account_unknown_is_refused(books):
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            upload_bank_input(
                file=_UploadFile(
                    "utdrag.csv", (BANK_HEADER + "2026-09-12;-5,00;Avgift\n").encode()
                ),
                bank_connection_id="auto",
                actor="test",
            )
        )
    assert error.value.detail["code"] == "statement_account_unknown"


# --- agent tools ------------------------------------------------------------


def test_koppla_banktransaktion_is_the_last_tool():
    assert AGENT_TOOL_DEFINITIONS[-1]["name"] == "koppla_banktransaktion"


def test_agent_reads_open_transactions_and_links(books):
    voucher = _transfer(books, date(2026, 3, 10), 10_000_000)
    _import("1930", BANK_HEADER + "2026-03-12;-100000,00;Till skattekonto\n")
    capabilities = LLMCapabilities(
        cache_breakpoint=False, pdf_document_blocks=False, refusal_stop_reason=False
    )
    listed = execute_tool(
        "las_okopplade_banktransaktioner",
        {},
        actor="agent",
        capabilities=capabilities,
    )
    [item] = listed["items"]
    assert item["match"] == "candidates"
    assert item["candidates"][0]["voucher_id"] == voucher.id

    linked = execute_tool(
        "koppla_banktransaktion",
        {"bank_transaction_id": item["bank_transaction_id"], "voucher_id": voucher.id},
        actor="agent",
        capabilities=capabilities,
    )
    assert linked["missing_statement_accounts"] == ["1630"]
