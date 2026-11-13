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


def _links(voucher_id: str) -> dict:
    """{account: linked_by} for the statement links of a voucher."""
    return {
        link["account_code"]: link["linked_by"]
        for link in BankInputRepository.list_statement_links_for_voucher(voucher_id)
    }


def _basis(voucher_id: str, account_code: str) -> str:
    import json

    rows = db.execute(
        "SELECT payload FROM audit_log WHERE entity_id = ? AND action = ?",
        (voucher_id, "statement_linked"),
    ).fetchall()
    for row in rows:
        payload = json.loads(row["payload"])
        if payload["account_code"] == account_code:
            return payload["basis"]
    raise AssertionError(f"no link on {account_code}")


def test_the_later_side_of_a_transfer_is_linked_once_the_first_is(books):
    """A-15: Skatteverket books the payment two days after the bank."""
    voucher = _transfer(books, date(2026, 2, 2), 1_000_000)
    _import("1930", BANK_HEADER + "2026-02-02;-10000,00;Till skattekonto\n")
    _import(
        "1630",
        SKATTEKONTO_HEADER + "2026-02-04;Inbetalning bokförd 260203;10000;10000\n",
    )

    assert set(_links(voucher.id)) == {"1630", "1930"}
    assert _voucher(voucher.id).missing_attachment is False
    assert _basis(voucher.id, "1630") == "transfer_counterpart"
    assert StatementMatchService().open_transactions() == []


def test_the_later_side_waits_for_the_first_whichever_comes_first(books):
    voucher = _transfer(books, date(2026, 2, 2), 1_000_000)
    _import(
        "1630",
        SKATTEKONTO_HEADER + "2026-02-04;Inbetalning bokförd 260203;10000;10000\n",
    )
    assert _links(voucher.id) == {}

    _import("1930", BANK_HEADER + "2026-02-02;-10000,00;Till skattekonto\n")
    assert set(_links(voucher.id)) == {"1630", "1930"}


def test_a_rival_transaction_keeps_the_later_side_a_candidate(books):
    voucher = _transfer(books, date(2026, 2, 2), 1_000_000)
    _import("1930", BANK_HEADER + "2026-02-02;-10000,00;Till skattekonto\n")
    _import(
        "1630",
        SKATTEKONTO_HEADER
        + "2026-02-04;Inbetalning bokförd 260203;10000;10000\n"
        + "2026-02-05;Inbetalning bokförd 260204;10000;20000\n",
    )

    assert set(_links(voucher.id)) == {"1930"}
    assert {m.kind for m in StatementMatchService().open_transactions()} == {
        "candidates"
    }


def test_a_voucher_that_is_not_a_transfer_is_not_linked_days_apart(books):
    voucher = _post(
        books,
        date(2026, 2, 12),
        "Debiterad preliminärskatt",
        [
            {"account": "2518", "debit": 1_520_200, "credit": 0},
            {"account": "1630", "debit": 0, "credit": 1_520_200},
        ],
    )
    _import(
        "1630",
        SKATTEKONTO_HEADER + "2026-02-14;Debiterad preliminärskatt;-15202;1000\n",
    )
    assert _links(voucher.id) == {}


def test_an_unlinked_later_side_is_never_linked_again(books):
    voucher = _transfer(books, date(2026, 2, 2), 1_000_000)
    _import("1930", BANK_HEADER + "2026-02-02;-10000,00;Till skattekonto\n")
    _import(
        "1630",
        SKATTEKONTO_HEADER + "2026-02-04;Inbetalning bokförd 260203;10000;10000\n",
    )
    [tx_id] = [
        link["bank_transaction_id"]
        for link in BankInputRepository.list_statement_links_for_voucher(voucher.id)
        if link["account_code"] == "1630"
    ]
    StatementMatchService().unlink(tx_id, reason="Fel överföring", actor="test")

    StatementMatchService().run()
    assert set(_links(voucher.id)) == {"1930"}


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


def _agi(books, day: date):
    """One AGI voucher: 1630 credited once per part, as the tax account
    debits them."""
    for code, name in [("2710", "Personalskatt"), ("2730", "Arbetsgivaravgifter")]:
        if AccountRepository.get(code) is None:
            AccountRepository.create(code, name, "liability")
    return _post(
        books,
        day,
        "Arbetsgivardeklaration",
        [
            {"account": "2710", "debit": 1_500_000, "credit": 0},
            {"account": "2730", "debit": 1_571_000, "credit": 0},
            {"account": "1630", "debit": 0, "credit": 1_500_000},
            {"account": "1630", "debit": 0, "credit": 1_571_000},
        ],
    )


def test_a_voucher_with_a_row_per_debit_is_covered_by_both(books):
    voucher = _agi(books, date(2026, 4, 13))
    _import(
        "1630",
        SKATTEKONTO_HEADER + "2026-04-13;Avdragen skatt 202603;-15000;1000\n",
    )
    [link] = BankInputRepository.list_statement_links_for_voucher(voucher.id)
    assert link["amount"] == -1_500_000
    # Half the tax account's amount is not underlag for all of it.
    assert _voucher(voucher.id).missing_statement_accounts == ["1630"]

    _import(
        "1630",
        SKATTEKONTO_HEADER + "2026-04-13;Arbetsgivaravgift 202603;-15710;-14710\n",
        filename="utdrag-2.csv",
    )
    links = BankInputRepository.list_statement_links_for_voucher(voucher.id)
    assert sorted(link["amount"] for link in links) == [-1_571_000, -1_500_000]
    assert _voucher(voucher.id).missing_attachment is False


def test_the_whole_amount_still_covers_a_voucher_with_several_rows(books):
    voucher = _agi(books, date(2026, 4, 13))
    _import("1630", SKATTEKONTO_HEADER + "2026-04-13;AGI 202603;-30710;1000\n")
    [link] = BankInputRepository.list_statement_links_for_voucher(voucher.id)
    assert link["amount"] == -3_071_000
    assert _voucher(voucher.id).missing_attachment is False


def test_a_row_amount_is_refused_once_the_rest_is_less(books):
    voucher = _agi(books, date(2026, 4, 13))
    _import(
        "1630",
        SKATTEKONTO_HEADER
        + "2026-04-13;Arbetsgivaravgift 202603;-15710;1000\n"
        + "2026-04-14;Arbetsgivaravgift igen;-15710;-14710\n",
    )
    [linked] = BankInputRepository.list_statement_links_for_voucher(voucher.id)
    assert linked["amount"] == -1_571_000
    [open_tx] = StatementMatchService().open_transactions()
    assert open_tx.kind == "none"

    with pytest.raises(BankInputConflictError) as error:
        StatementMatchService().link(
            open_tx.bank_transaction_id, voucher.id, actor="agent"
        )
    assert error.value.code == "amount_mismatch"


def test_a_covered_account_refuses_another_transaction(books):
    voucher = _transfer(books, date(2026, 7, 1), 50_000)
    _import(
        "1930",
        BANK_HEADER + "2026-07-01;-500,00;Till skattekonto\n"
        "2026-07-02;-500,00;Till skattekonto\n",
    )
    [open_tx] = StatementMatchService().open_transactions()
    with pytest.raises(BankInputConflictError) as error:
        StatementMatchService().link(
            open_tx.bank_transaction_id, voucher.id, actor="agent"
        )
    assert error.value.code == "voucher_account_already_covered"


def test_covers():
    from domain.statement_coverage import covers

    assert covers(-100, -100, [-100])
    assert covers(-60, -100, [-60, -40])
    assert covers(-40, -40, [-60, -40])
    assert not covers(-60, -40, [-60, -40])  # more than is left
    assert not covers(60, -100, [60, -160])  # the other way
    assert not covers(-60, -100, [-100])  # one row: all of it or nothing
    assert not covers(-50, -100, [-60, -40])  # no such row
    assert not covers(0, 0, [100, -100])


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
    context = asyncio.run(get_voucher_source_context(voucher.id, actor="test"))
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


def test_koppla_banktransaktion_is_the_seventeenth_tool():
    # Fakturering F1 appended four after it.
    assert AGENT_TOOL_DEFINITIONS[16]["name"] == "koppla_banktransaktion"


def test_the_statement_unlink_tool_comes_before_the_payroll_tools():
    names = [t["name"] for t in AGENT_TOOL_DEFINITIONS]
    assert names[21:23] == ["koppla_bort_banktransaktion", "las_loner"]


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


# --- undoing a link (migration 040) -----------------------------------------


def _tool(name: str, arguments: dict):
    capabilities = LLMCapabilities(
        cache_breakpoint=False, pdf_document_blocks=False, refusal_stop_reason=False
    )
    return execute_tool(name, arguments, actor="agent", capabilities=capabilities)


def _only_transaction_id() -> str:
    [row] = db.execute("SELECT id FROM bank_transactions").fetchall()
    return row["id"]


def test_a_wrong_automatic_link_is_undone_and_linked_right(books):
    """Two transfers of 1 000 kr: the statement arrives when only the wrong
    one is posted, same day, so the server links it. The user says it is
    wrong; the link is undone, stays as a trace, and the server does not
    link it back. The right voucher is linked by decision."""
    wrong = _transfer(books, date(2026, 3, 10), 100_000)
    _import("1930", BANK_HEADER + "2026-03-10;-1000,00;Till skattekonto\n")
    tx_id = _only_transaction_id()
    assert _voucher(wrong.id).missing_statement_accounts == ["1630"]
    right = _transfer(books, date(2026, 3, 12), 100_000)

    result = _tool(
        "koppla_bort_banktransaktion",
        {"bank_transaction_id": tx_id, "reason": "Betalningen gällde den 12:e"},
    )

    assert result["unlinked"] is True
    assert result["voucher_id"] == wrong.id
    assert _voucher(wrong.id).missing_statement_accounts == ["1630", "1930"]
    assert BankInputRepository.current_transaction_link(tx_id) is None
    released = db.execute(
        "SELECT status, matched_voucher_id FROM bank_transactions WHERE id = ?",
        (tx_id,),
    ).fetchone()
    assert (released["status"], released["matched_voucher_id"]) == ("pending", None)

    # Never linked back on its own -- not to the wrong voucher, and since a
    # human has looked at it, not to the right one either.
    assert StatementMatchService().run()["linked"] == []
    [match] = StatementMatchService().open_transactions()
    assert match.kind == "candidates"
    assert [c.voucher_id for c in match.candidates] == [right.id]

    _tool(
        "koppla_banktransaktion",
        {"bank_transaction_id": tx_id, "voucher_id": right.id},
    )
    assert _voucher(right.id).missing_statement_accounts == ["1630"]
    assert _voucher(wrong.id).missing_statement_accounts == ["1630", "1930"]
    history = db.execute(
        "SELECT voucher_id FROM voucher_bank_transactions"
        " WHERE bank_transaction_id = ? ORDER BY linked_at",
        (tx_id,),
    ).fetchall()
    assert [r["voucher_id"] for r in history] == [wrong.id, right.id]
    wrong_context = asyncio.run(get_voucher_source_context(wrong.id, actor="test"))
    assert wrong_context["statement_links"] == []
    assert BankInputRepository.list_inputs_for_voucher(wrong.id) == []
    assert len(BankInputRepository.list_inputs_for_voucher(right.id)) == 1


def test_unlink_needs_a_reason_and_a_link(books):
    from services.bank_inputs import BankInputValidationError

    _transfer(books, date(2026, 3, 10), 100_000)
    _import("1930", BANK_HEADER + "2026-03-10;-1000,00;Till skattekonto\n")
    tx_id = _only_transaction_id()
    service = StatementMatchService()

    with pytest.raises(BankInputValidationError) as reason:
        service.unlink(tx_id, reason="  ", actor="test")
    assert reason.value.code == "unlink_reason_required"

    service.unlink(tx_id, reason="Fel verifikation", actor="test")
    with pytest.raises(BankInputConflictError) as again:
        service.unlink(tx_id, reason="Fel verifikation", actor="test")
    assert again.value.code == "bank_transaction_not_linked"


def test_unlink_route(books, auth_headers):
    from fastapi.testclient import TestClient

    from api.main import app

    _transfer(books, date(2026, 3, 10), 100_000)
    _import("1930", BANK_HEADER + "2026-03-10;-1000,00;Till skattekonto\n")
    tx_id = _only_transaction_id()
    client = TestClient(app)
    url = f"/api/v1/bank-inputs/transactions/{tx_id}/unlink"

    response = client.post(url, json={"reason": "Fel dag"}, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["unlinked"] is True

    response = client.post(url, json={"reason": "Fel dag"}, headers=auth_headers)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "bank_transaction_not_linked"

    response = client.post(
        "/api/v1/bank-inputs/transactions/nope/unlink",
        json={"reason": "Fel dag"},
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_one_current_link_per_transaction_and_unlinks_are_append_only(books):
    voucher = _transfer(books, date(2026, 3, 10), 100_000)
    _import("1930", BANK_HEADER + "2026-03-10;-1000,00;Till skattekonto\n")
    tx_id = _only_transaction_id()

    with pytest.raises(sqlite3.IntegrityError, match="already linked"):
        BankInputRepository.create_voucher_bank_transaction_link(
            voucher_id=voucher.id, bank_transaction_id=tx_id, linked_by="test"
        )
    db.rollback()

    StatementMatchService().unlink(tx_id, reason="Fel", actor="test")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute("DELETE FROM voucher_bank_transaction_unlinks")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute("DELETE FROM voucher_bank_transactions")


# --- unaccounted transactions (GET /bank-inputs/transactions/open) ----------


def _open_route(fiscal_year_id: str):
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app, headers={"Authorization": f"Bearer {settings.api_key}"})
    return client.get(
        "/api/v1/bank-inputs/transactions/open",
        params={"fiscal_year_id": fiscal_year_id},
    )


def test_unbooked_transaction_is_listed_for_its_year(books, fiscal_year):
    _import(
        "1930",
        BANK_HEADER + "2026-03-10;-500,00;Årsavgift\n2025-12-30;-100,00;Förra året\n",
    )
    response = _open_route(fiscal_year.id)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    [item] = body["items"]
    assert (item["date"], item["amount_ore"], item["match"]) == (
        "2026-03-10",
        -50000,
        "none",
    )
    assert item["account_code"] == "1930"


def test_purchase_booked_from_receipt_is_accounted_for(books, fiscal_year):
    _post(
        books,
        date(2026, 1, 20),
        "Telefon",
        [
            {"account": "6212", "debit": 22_000, "credit": 0},
            {"account": "2641", "debit": 5_500, "credit": 0},
            {"account": "1930", "debit": 0, "credit": 27_500},
        ],
    )
    _import(
        "1930", BANK_HEADER + "2026-01-22;-275,00;Fello\n2026-02-20;-275,00;Fello\n"
    )
    [left] = _open_route(fiscal_year.id).json()["items"]
    # January's is the receipt-booked purchase; February's has no voucher.
    assert left["date"] == "2026-02-20"


def test_candidate_is_listed_with_the_voucher(books, fiscal_year):
    voucher = _transfer(books, date(2026, 3, 10), 10_000_000)
    _import("1930", BANK_HEADER + "2026-03-12;-100000,00;Till skattekonto\n")
    [item] = _open_route(fiscal_year.id).json()["items"]
    assert item["match"] == "candidates"
    assert item["candidates"][0]["voucher_id"] == voucher.id


def test_open_route_unknown_year_is_404(books):
    response = _open_route("no-such-year")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "fiscal_year_not_found"


def test_agent_tool_names_the_purchase_that_covers_a_transaction(books):
    """The agent sees that a card payment is booked from its receipt, so it
    does not book it again (`covered_by_purchase`)."""
    purchase = _post(
        books,
        date(2026, 1, 20),
        "Telefon",
        [
            {"account": "6212", "debit": 22_000, "credit": 0},
            {"account": "2641", "debit": 5_500, "credit": 0},
            {"account": "1930", "debit": 0, "credit": 27_500},
        ],
    )
    _import("1930", BANK_HEADER + "2026-01-22;-275,00;Fello\n")
    result = execute_tool(
        "las_okopplade_banktransaktioner",
        {},
        actor="agent",
        capabilities=LLMCapabilities(
            cache_breakpoint=False, pdf_document_blocks=False, refusal_stop_reason=False
        ),
    )
    [item] = result["items"]
    assert item["match"] == "none"
    assert item["covered_by_purchase"] == [f"A-{purchase.number}"]


# --- a document that arrives after the statement ------------------------------


def test_a_document_after_the_statement_links_without_a_decision(books):
    """A customer payment covered by its statement row still lacks a
    document of its own: a deposit slip read afterwards matches it exactly
    and links without a decision. The statement documents the payment, the
    slip the business event; neither stops the other."""
    from tests.test_flode_underlag import interpret, link, make_source

    if AccountRepository.get("1510") is None:
        AccountRepository.create("1510", "Kundfordringar", "asset")
    payment = _post(
        books,
        date(2026, 4, 8),
        "Inbetalning faktura #101276",
        [
            {"account": "1930", "debit": 9_200_000, "credit": 0},
            {"account": "1510", "debit": 0, "credit": 9_200_000},
        ],
    )
    _import("1930", BANK_HEADER + "2026-04-08;92000,00;QRTECH AKTIEBOLAG\n")
    assert _voucher(payment.id).missing_attachment is False

    source_id = make_source()
    result = interpret(
        source_id,
        vendor="QRTECH AKTIEBOLAG",
        document_date="2026-04-08",
        total_ore=9_200_000,
        vat_ore=0,
        lines=[{"text": "Faktura #101276", "amount_ore": 9_200_000, "vat_rate": 0}],
    )
    assert result["match"]["voucher_id"] == payment.id
    assert result["match"]["kind"] == "exact"

    assert link(source_id, payment.id).basis == "exact_match"
    assert VoucherRepository.match_still_open(payment.id, make_source()) is False
