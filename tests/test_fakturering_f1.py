"""Fakturering F1: agenten och tråden (docs/redesign/SPEC-fakturering-f1.md §13).

Backendens testfall: 1–32 och 39–40. Klientens (33–38) ligger i vitest.
Verktygen körs genom `execute_tool` med en riktig tråd i `tool_context`, som
i `tests/test_flode_verifikationer.py`. Den riktiga LLM:en används aldrig.
"""

import calendar
import re
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from config import settings
from db.database import db
from domain.validation import ValidationError
from repositories.account_repo import AccountRepository
from repositories.invoice_draft_repo import InvoiceDraftRepository
from repositories.invoice_proposal_repo import InvoiceProposalRepository
from repositories.period_repo import PeriodRepository
from repositories.thread_repo import ThreadRepository
from services.agent_tools import (
    AGENT_TOOL_DEFINITIONS,
    ProposalSequence,
    execute_tool,
)
from services.auth import AuthService
from services.customer_article import CustomerService
from services.decision_service import DecisionService
from services.invoice_draft import InvoiceDraftService
from services.llm import LLMCapabilities

_ACCOUNTS = [
    ("1510", "Kundfordringar", "asset"),
    ("1930", "Företagskonto", "asset"),
    ("3010", "Försäljning momsfri", "revenue"),
    ("3011", "Försäljning tjänster 25%", "revenue"),
    ("2610", "Utgående moms 25%", "vat_out"),
]

_COMPANY = {
    "name": "Wikner Konsult AB",
    "org_number": "556677-8899",
    "address": "Storgatan 1",
    "postnr": "411 01",
    "postort": "Göteborg",
    "seat": "Göteborg",
    "vat_number": "SE556677889901",
    "bankgiro": "123-4567",
    "f_skatt": "true",
    "contact_person": "Stefan Wikner",
}

_FIXTURE_FILE = (
    Path(__file__).resolve().parent.parent
    / "frontend-v3"
    / "lib"
    / "chattyta"
    / "__fixtures__"
    / "inlagg.ts"
)

_FIRST_SEVENTEEN = [
    "las_kontoplan",
    "las_perioder",
    "las_verifikationer",
    "las_korrigeringar",
    "las_underlag",
    "hamta_underlagsfil",
    "las_bankhandelser",
    "posta_verifikation",
    "registrera_avstaende",
    "be_om_beslut",
    "foresla_verifikation",
    "tolka_underlag",
    "koppla_underlag",
    "stang_perioder",
    "koppla_bort_underlag",
    "las_okopplade_banktransaktioner",
    "koppla_banktransaktion",
]


# --- helpers ----------------------------------------------------------------


def _set_company_info(values: dict) -> None:
    db.execute("DELETE FROM company_info")
    for key, value in values.items():
        db.execute(
            "INSERT INTO company_info (key, value) VALUES (?, ?)", (key, str(value))
        )
    db.commit()


def _count(table: str) -> int:
    return db.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]


def _capabilities() -> LLMCapabilities:
    return LLMCapabilities(
        cache_breakpoint=False, pdf_document_blocks=False, refusal_stop_reason=False
    )


class Books:
    """Räkenskapsåret 2026, Fakturerings tråd, en kund och en användarpost."""

    def __init__(self, periods, fiscal_year_id, customer):
        self.periods = periods
        self.fiscal_year_id = fiscal_year_id
        self.customer = customer
        self.thread = ThreadRepository.get_or_create(
            view_key="betala.fakturering",
            fiscal_year_id=fiscal_year_id,
            model="opencode/claude-opus-5",
        )
        self.trigger = self.say("Fakturera QRTECH för junikonsultationen")

    def say(self, text: str):
        return ThreadRepository.add_post(
            thread_id=self.thread.id,
            post_type="user_text",
            actor="stefan",
            body={"text": text},
        )

    def context(self, trigger=None, thread=None):
        thread = thread or self.thread
        trigger = trigger or self.trigger
        return {
            "thread": thread,
            "proposals": ProposalSequence(thread.id, trigger.id),
        }

    def tool(self, name: str, args: dict, context=None):
        return execute_tool(
            name,
            args,
            actor="agent",
            capabilities=_capabilities(),
            tool_context=context if context is not None else self.context(),
        )

    def propose(self, context=None, **overrides):
        return self.tool("foresla_faktura", _args(self.customer, **overrides), context)


def _args(customer, **overrides) -> dict:
    """Ett förslag som går att utfärda: 28 h à 800 kr, 25 %, en period."""
    row = {
        "description": "Konsulttjänster",
        "quantity": "28",
        "unit": "h",
        "unit_price": 80000,
        "vat_code": "MP1",
        "revenue_account": "3011",
        "delivery_from": "2026-06-29",
        "delivery_to": "2026-07-02",
    }
    row.update(overrides.pop("row", {}))
    args = {
        "invoice_number": "2026-1",
        "invoice_date": "2026-07-31",
        "customer_id": customer.id,
        "reference": "Anna Andersson",
        "rows": [row],
        "footnote": "Timmarna ur ditt meddelande",
    }
    args.update(overrides)
    return args


@pytest.fixture
def books(test_db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "intake_dir", str(tmp_path / "intake"))
    for code, name, kind in _ACCOUNTS:
        if not AccountRepository.exists(code):
            AccountRepository.create(code, name, kind)
    fy = PeriodRepository.create_fiscal_year(
        start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)
    )
    periods = {}
    for month in range(1, 13):
        last = calendar.monthrange(2026, month)[1]
        periods[month] = PeriodRepository.create_period(
            fiscal_year_id=fy.id,
            year=2026,
            month=month,
            start_date=date(2026, month, 1),
            end_date=date(2026, month, last),
        )
    _set_company_info(_COMPANY)
    customer = CustomerService().create_customer(
        name="QRTECH Aktiebolag",
        org_number="556000-0001",
        email="faktura@qrtech.example",
        address="Box 100\n412 50 Göteborg",
        payment_terms_days=30,
    )
    return Books(periods, fy.id, customer)


@pytest.fixture
def client(test_db):
    from api.main import app

    return TestClient(app)


@pytest.fixture
def human():
    return {"Authorization": f"Bearer {AuthService().create_jwt('stefan')}"}


def _issue(client, human, draft_id):
    return client.post(f"/api/v1/invoice-drafts/{draft_id}/issue", headers=human)


def _posts(books, post_type):
    return [
        p for p in ThreadRepository.list_posts(books.thread.id) if p.type == post_type
    ]


def _refused(books, name, args, context=None) -> ValidationError:
    with pytest.raises(ValidationError) as exc:
        books.tool(name, args, context)
    return exc.value


def _fixture_keys(name: str) -> tuple:
    source = _FIXTURE_FILE.read_text(encoding="utf-8")
    start = source.index(f"export const {name}")
    block = source[start : source.index("\n};", start)]
    body = block[block.index("body: {") :]
    body_keys = set(re.findall(r"^    (\w+):", body, flags=re.MULTILINE))
    first_row = re.search(r"\{ (text:[^}]*)\}", body)
    row_keys = set(re.findall(r"(\w+):", first_row.group(1))) if first_row else set()
    return body_keys, row_keys


# --- 13.1 Verktygen ---------------------------------------------------------


def test_01_the_four_tools_come_last_and_do_not_issue():
    names = [t["name"] for t in AGENT_TOOL_DEFINITIONS]
    assert names[:17] == _FIRST_SEVENTEEN
    assert names[17:] == [
        "las_kunder",
        "las_fakturor",
        "foresla_faktura",
        "andra_fakturautkast",
    ]
    for tool in AGENT_TOOL_DEFINITIONS[17:]:
        text = tool["description"].lower()
        assert "utfärdar fakturan" not in text
        assert "huvudboken" not in text
    for tool in AGENT_TOOL_DEFINITIONS[17:19]:
        assert "skrivskyddat" in tool["description"].lower()


def test_02_las_kunder_searches_and_lists_articles(books):
    from services.customer_article import ArticleService

    ArticleService().create_article(
        article_number="KONS",
        name="Konsultation",
        unit="h",
        unit_price=115000,
        vat_code="MP1",
        revenue_account="3011",
    )
    CustomerService().create_customer(name="Ateljé Vind AB", org_number="556999-0002")
    result = books.tool("las_kunder", {"query": "556000"})
    assert [c["name"] for c in result["customers"]] == ["QRTECH Aktiebolag"]
    assert result["customers"][0]["last_invoice"] is None
    assert result["customers"][0]["address"] == "Box 100\n412 50 Göteborg"
    assert [a["article_number"] for a in result["articles"]] == ["KONS"]
    assert result["articles"][0]["unit_price"] == 115000


def test_03_las_fakturor_latest_numbers_and_one_invoice(books, client, human):
    first = books.propose()
    assert _issue(client, human, first["draft_id"]).status_code == 201
    second = books.propose(
        context=books.context(books.say("en till")), invoice_number="2026-2"
    )
    assert _issue(client, human, second["draft_id"]).status_code == 201

    listed = books.tool("las_fakturor", {"status": "unpaid"})
    assert listed["latest_numbers"][:2] == ["2026-2", "2026-1"]
    assert {i["invoice_number"] for i in listed["invoices"]} == {"2026-1", "2026-2"}
    assert all(
        i["voucher"] and i["voucher"].startswith("A-") for i in listed["invoices"]
    )

    one = books.tool("las_fakturor", {"invoice_id": listed["invoices"][0]["id"]})
    row = one["invoice"]["rows"][0]
    assert row["quantity"] == "28" and row["unit"] == "h"
    assert row["delivery"] == "2026-06-29 --> 2026-07-02"


def test_04_las_fakturor_drafts_show_the_pending_card(books):
    proposed = books.propose()
    InvoiceDraftService().create_draft(
        invoice_date=date(2026, 7, 1),
        customer_id=books.customer.id,
        rows_data=[{"description": "Annat", "quantity": 1, "unit_price": 100}],
    )
    result = books.tool("las_fakturor", {"drafts": True})
    by_id = {d["id"]: d for d in result["drafts"]}
    assert by_id[proposed["draft_id"]]["pending_post_id"] == proposed["post_id"]
    assert len(by_id) == 2
    assert [d for d in by_id.values() if d["id"] != proposed["draft_id"]][0][
        "pending_post_id"
    ] is None


def test_05_proposal_writes_draft_card_and_row(books):
    result = books.propose()
    draft = InvoiceDraftRepository.get(result["draft_id"])
    assert draft.status == "needs_review" and draft.created_by == "agent"
    [post] = _posts(books, "draft")
    assert post.id == result["post_id"]
    assert post.body["kind"] == "invoice" and post.body["draft_id"] == draft.id
    proposal = InvoiceProposalRepository.get(draft.id)
    assert proposal.status == "pending" and proposal.post_id == post.id

    body_keys, row_keys = _fixture_keys("FIXTUR_FAKTURA_DRAFT")
    assert set(post.body) == body_keys
    assert set(post.body["rows"][0]) == row_keys


def test_06_the_card_body(books):
    body = books.propose(
        rows=[
            {
                "description": "Konsulttjänster",
                "quantity": "7.5",
                "unit": "h",
                "unit_price": 115000,
                "vat_code": "MP1",
                "revenue_account": "3011",
                "delivery_month": "2026-07",
            },
            {
                "description": "Utlägg",
                "quantity": "1",
                "unit_price": 50000,
                "vat_code": "MF",
                "revenue_account": "3010",
                "delivery_from": "2026-07-15",
            },
        ]
    )
    post = ThreadRepository.get_post(body["post_id"]).body
    assert post["title"] == "Faktura 2026-1 · QRTECH Aktiebolag"
    assert post["meta"] == "förslag · fakturadatum 2026-07-31"
    assert post["recipient"] == {
        "name": "QRTECH Aktiebolag",
        "address": "Box 100\n412 50 Göteborg",
        "reference": "Anna Andersson",
    }
    first, second = post["rows"]
    assert first["quantity_centi"] == 750 and first["amount_ore"] == 862500
    assert first["delivery"] == "juli 2026"
    assert second["delivery"] == "2026-07-15"
    assert post["totals"] == [
        {"key": "net", "text": "Netto", "amount_ore": 912500},
        {"key": "vat", "text": "Moms 25 %", "amount_ore": 215625},
        {"key": "vat_free", "text": "Momsfritt", "amount_ore": 50000},
        {"key": "total", "text": "Att betala senast 2026-08-30", "amount_ore": 1128125},
    ]
    assert post["terms"] == "30 dagar"
    assert post["consequence"].startswith(
        "Utfärdas och bokförs i ett steg · 1510 mot 3011, 2610 och 3010 · "
        "period juli 2026 öppen\n"
    )
    assert post["footnote"] == "Timmarna ur ditt meddelande"


def test_07_needs_a_thread_and_fakturering(books):
    before = _count("invoice_drafts")
    error = _refused(books, "foresla_faktura", _args(books.customer), context={})
    assert error.code == "draft_requires_thread"
    other = ThreadRepository.get_or_create(
        view_key="bocker.verifikationer",
        fiscal_year_id=books.fiscal_year_id,
        model="opencode/claude-opus-5",
    )
    trigger = ThreadRepository.add_post(
        thread_id=other.id, post_type="user_text", actor="stefan", body={"text": "x"}
    )
    error = _refused(
        books,
        "foresla_faktura",
        _args(books.customer),
        context=books.context(trigger, thread=other),
    )
    assert error.code == "wrong_view"
    assert _count("invoice_drafts") == before


@pytest.mark.parametrize(
    "number, code",
    [("20260929", "number_is_date"), ("2026-09-29", "number_is_date")],
)
def test_08_number_is_a_date(books, number, code):
    before = _count("invoice_drafts")
    assert (
        _refused(
            books, "foresla_faktura", _args(books.customer, invoice_number=number)
        ).code
        == code
    )
    assert _count("invoice_drafts") == before


def test_08_number_taken_or_missing(books, client, human):
    issued = books.propose()
    assert _issue(client, human, issued["draft_id"]).status_code == 201
    before = _count("invoice_drafts")
    error = _refused(
        books,
        "foresla_faktura",
        _args(books.customer),
        context=books.context(books.say("igen")),
    )
    assert error.code == "number_taken"
    assert error.payload["invoice_id"]
    error = _refused(
        books,
        "foresla_faktura",
        _args(books.customer, invoice_number=""),
        context=books.context(books.say("utan nummer")),
    )
    assert error.code in ("invoice_number_missing", "invalid_invoice_number")
    assert _count("invoice_drafts") == before


def test_09_address_delivery_company_and_period(books):
    before = (_count("invoice_drafts"), _count("thread_posts"))
    no_address = CustomerService().create_customer(name="Utan Adress AB")
    assert (
        _refused(books, "foresla_faktura", _args(no_address)).code
        == "customer_address_missing"
    )
    assert (
        _refused(
            books,
            "foresla_faktura",
            _args(books.customer, row={"delivery_from": None, "delivery_to": None}),
        ).code
        == "delivery_date_missing"
    )
    _set_company_info({k: v for k, v in _COMPANY.items() if k != "seat"})
    error = _refused(books, "foresla_faktura", _args(books.customer))
    assert error.code == "company_info_incomplete"
    assert error.payload["missing"] == ["seat"]
    _set_company_info(_COMPANY)
    from services.ledger import LedgerService

    LedgerService().lock_period(books.periods[7].id, actor="stefan")
    assert _refused(books, "foresla_faktura", _args(books.customer)).code == (
        "period_locked"
    )
    assert (_count("invoice_drafts"), _count("thread_posts")) == before


def test_10_the_same_turn_twice_gives_the_same_draft(books):
    first = books.propose()
    again = books.propose()  # a fresh sequence for the same trigger: n = 1 again
    assert again["draft_id"] == first["draft_id"]
    assert again.get("idempotent_replay") is True
    assert _count("invoice_drafts") == 1
    assert len(_posts(books, "draft")) == 1


def test_11_an_invoice_and_a_voucher_in_one_turn_do_not_collide(books):
    context = books.context()
    invoice = books.tool("foresla_faktura", _args(books.customer), context)
    assert context["proposals"].n == 2
    voucher = books.tool(
        "foresla_verifikation",
        {
            "description": "Bankavgift",
            "date": "2026-07-31",
            "period_id": books.periods[7].id,
            "rows": [
                {"account": "3010", "debit": 100},
                {"account": "1930", "credit": 100},
            ],
        },
        context,
    )
    assert voucher["draft_id"] != invoice["draft_id"]
    assert context["proposals"].n == 3


def test_12_possible_duplicates(books, client, human):
    issued = books.propose()
    assert _issue(client, human, issued["draft_id"]).status_code == 201
    again = books.propose(
        context=books.context(books.say("en till")),
        invoice_number="2026-2",
        row={"delivery_from": "2026-07-01", "delivery_to": "2026-07-05"},
    )
    [duplicate] = again["possible_duplicates"]
    assert duplicate["invoice_number"] == "2026-1"
    assert duplicate["delivery"] == "2026-06-29 --> 2026-07-02"
    assert InvoiceDraftRepository.get(again["draft_id"]) is not None


def test_13_a_change_is_a_new_draft_that_replaces_the_old(books):
    old = books.propose()
    changed = books.tool(
        "andra_fakturautkast",
        {
            "draft_id": old["draft_id"],
            "rows": [
                {
                    "description": "Konsulttjänster",
                    "quantity": "26",
                    "unit": "h",
                    "unit_price": 80000,
                    "vat_code": "MP1",
                    "revenue_account": "3011",
                    "delivery_from": "2026-06-29",
                    "delivery_to": "2026-07-02",
                }
            ],
        },
        books.context(books.say("det var 26 timmar")),
    )
    assert changed["draft_id"] != old["draft_id"]
    assert changed["replaced_draft_id"] == old["draft_id"]
    new = InvoiceDraftRepository.get(changed["draft_id"])
    assert new.customer_address == "Box 100\n412 50 Göteborg"
    assert new.reference == "Anna Andersson"
    assert new.rows[0].quantity_centi == 2600
    stale = InvoiceDraftRepository.get(old["draft_id"])
    assert stale.status == "rejected" and stale.rows[0].quantity_centi == 2800
    row = InvoiceProposalRepository.get(old["draft_id"])
    assert row.status == "superseded" and row.replaced_by == new.id
    posts = _posts(books, "draft")
    assert len(posts) == 2 and posts[1].body["meta"].startswith("nytt förslag")


def test_14_change_refused(books, client, human):
    context = books.context
    assert (
        _refused(
            books, "andra_fakturautkast", {"draft_id": "nope", "reference": "x"}
        ).code
        == "draft_not_found"
    )
    old = books.propose()
    books.tool(
        "andra_fakturautkast",
        {"draft_id": old["draft_id"], "reference": "Bo"},
        context(books.say("Bo")),
    )
    error = _refused(
        books,
        "andra_fakturautkast",
        {"draft_id": old["draft_id"], "reference": "Cilla"},
        context(books.say("Cilla")),
    )
    assert error.code == "draft_superseded"

    rejected = books.propose(context=context(books.say("ny")), invoice_number="2026-5")
    books.tool(
        "andra_fakturautkast",
        {"draft_id": rejected["draft_id"], "reject_reason": "fel kund"},
        context(books.say("släng")),
    )
    assert (
        _refused(
            books,
            "andra_fakturautkast",
            {"draft_id": rejected["draft_id"], "reference": "x"},
            context(books.say("x")),
        ).code
        == "draft_rejected"
    )

    issued = books.propose(context=context(books.say("tre")), invoice_number="2026-9")
    assert _issue(client, human, issued["draft_id"]).status_code == 201
    error = _refused(
        books,
        "andra_fakturautkast",
        {"draft_id": issued["draft_id"], "reference": "x"},
        context(books.say("y")),
    )
    assert error.code == "draft_already_issued" and error.payload["invoice_id"]


def test_15_reject_reason(books):
    old = books.propose()
    error = _refused(
        books,
        "andra_fakturautkast",
        {"draft_id": old["draft_id"], "reject_reason": "x", "reference": "y"},
        books.context(books.say("a")),
    )
    assert error.code == "reject_is_exclusive"
    drafts = _count("invoice_drafts")
    result = books.tool(
        "andra_fakturautkast",
        {"draft_id": old["draft_id"], "reject_reason": "Kunden ångrade sig"},
        books.context(books.say("b")),
    )
    assert result == {"draft_id": old["draft_id"], "status": "rejected"}
    assert InvoiceDraftRepository.get(old["draft_id"]).status == "rejected"
    assert InvoiceProposalRepository.get(old["draft_id"]).status == "rejected"
    assert _count("invoice_drafts") == drafts
    assert len(_posts(books, "draft")) == 1


def test_16_nothing_changed(books):
    old = books.propose()
    before = _count("invoice_drafts")
    error = _refused(
        books,
        "andra_fakturautkast",
        {"draft_id": old["draft_id"], "reference": "Anna Andersson"},
        books.context(books.say("samma")),
    )
    assert error.code == "nothing_changed"
    assert _count("invoice_drafts") == before


def test_17_a_replayed_change_makes_one_new_draft(books):
    old = books.propose()
    trigger = books.say("Er referens är Bo")
    args = {"draft_id": old["draft_id"], "reference": "Bo"}
    first = books.tool("andra_fakturautkast", args, books.context(trigger))
    again = books.tool("andra_fakturautkast", args, books.context(trigger))
    assert again["draft_id"] == first["draft_id"]
    assert again["idempotent_replay"] is True
    assert _count("invoice_drafts") == 2


def test_18_a_draft_from_an_old_page_is_replaced_through_the_tool(books):
    legacy = InvoiceDraftService().create_draft(
        invoice_date=date(2026, 7, 31),
        customer_id=books.customer.id,
        invoice_number="2026-3",
        rows_data=[
            {
                "description": "Konsulttjänster",
                "quantity": 2,
                "unit_price": 100000,
                "vat_code": "MP1",
                "revenue_account": "3011",
                "delivery_month": "2026-07",
            }
        ],
    )
    changed = books.tool(
        "andra_fakturautkast", {"draft_id": legacy.id, "reference": "Bo"}
    )
    assert InvoiceProposalRepository.get(changed["draft_id"]).status == "pending"
    assert InvoiceDraftRepository.get(legacy.id).status == "rejected"
    assert InvoiceProposalRepository.get(legacy.id) is None


# --- 13.2 Utfärdandet -------------------------------------------------------


def test_19_issue_a_pending_proposal(books, client, human, monkeypatch):
    published = []
    from services import thread_stream

    broker = thread_stream.get_broker()
    monkeypatch.setattr(
        broker,
        "publish",
        lambda thread_id, event, data: published.append((event, data)),
    )
    proposed = books.propose()
    response = _issue(client, human, proposed["draft_id"])
    assert response.status_code == 201, response.text
    invoice_id = response.json()["invoice_id"]

    row = InvoiceProposalRepository.get(proposed["draft_id"])
    assert row.status == "issued" and row.invoice_id == invoice_id
    [receipt] = _posts(books, "receipt")
    assert row.receipt_post_id == receipt.id
    assert receipt.actor == "stefan"
    body = receipt.body
    assert body["title"].startswith("Faktura 2026-1 utfärdad · A-")
    assert body["invoice_id"] == invoice_id
    assert body["pdf_url"] == f"/api/v1/invoices/{invoice_id}/pdf"
    assert [r["key"] for r in body["rows"]] == ["1510", "3011", "2610"]
    assert body["rows"][0] == {
        "key": "1510",
        "text": "Kundfordringar",
        "left_ore": 0,
        "right_ore": 2800000,
    }
    assert [t["tool"] for t in receipt.traces] == [
        "utfarda_faktura",
        "posta_utkast",
        "pdf",
        "forfallodag",
        "vantar",
    ]
    assert receipt.traces[-1]["label"] == "0 kvar"
    changed = [data for event, data in published if event == "view.changed"]
    assert changed[-1]["changed"]["kind"] == "invoice_issued"
    assert changed[-1]["view_key"] == "betala.fakturering"


def test_20_two_presses_one_invoice_one_receipt(books, client, human):
    proposed = books.propose()
    first = _issue(client, human, proposed["draft_id"])
    second = _issue(client, human, proposed["draft_id"])
    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "draft_already_issued"
    assert second.json()["detail"]["invoice_id"] == first.json()["invoice_id"]
    assert _count("invoices") == 1
    assert len(_posts(books, "receipt")) == 1


def test_21_a_missing_receipt_is_written_by_the_next_press(
    books, client, human, monkeypatch
):
    from services.invoice_proposal import InvoiceProposalService

    proposed = books.propose()
    original = InvoiceProposalService.on_issued

    def _boom(self, draft_id, *, actor):
        raise RuntimeError("thread layer down")

    monkeypatch.setattr(InvoiceProposalService, "on_issued", _boom)
    assert _issue(client, human, proposed["draft_id"]).status_code == 201
    assert _posts(books, "receipt") == []
    monkeypatch.setattr(InvoiceProposalService, "on_issued", original)
    assert _issue(client, human, proposed["draft_id"]).status_code == 409
    assert len(_posts(books, "receipt")) == 1


def test_22_issuing_a_replaced_proposal(books, client, human):
    old = books.propose()
    books.tool(
        "andra_fakturautkast",
        {"draft_id": old["draft_id"], "reference": "Bo"},
        books.context(books.say("Bo")),
    )
    before = (_count("invoices"), _count("thread_posts"))
    response = _issue(client, human, old["draft_id"])
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "draft_rejected"
    assert (_count("invoices"), _count("thread_posts")) == before


def test_23_put_and_reject_are_refused_while_a_card_waits(
    books, client, human, auth_headers
):
    proposed = books.propose()
    draft_id = proposed["draft_id"]
    payload = {
        "customer_id": books.customer.id,
        "invoice_date": "2026-07-31",
        "invoice_number": "2026-1",
        "rows": [
            {
                "description": "Annat",
                "quantity": 1,
                "unit_price": 1,
                "delivery_month": "2026-07",
            }
        ],
    }
    put = client.put(f"/api/v1/invoice-drafts/{draft_id}", json=payload, headers=human)
    assert put.status_code == 409
    assert put.json()["detail"]["code"] == "draft_in_thread"
    assert put.json()["detail"]["post_id"] == proposed["post_id"]
    reject = client.post(
        f"/api/v1/invoice-drafts/{draft_id}/reject", headers=auth_headers
    )
    assert reject.status_code == 409
    assert InvoiceDraftRepository.get(draft_id).rows[0].description == "Konsulttjänster"

    # Replaced: the old draft is rejected and behaves as today.
    changed = books.tool(
        "andra_fakturautkast",
        {"draft_id": draft_id, "reference": "Bo"},
        books.context(books.say("Bo")),
    )
    old_put = client.put(
        f"/api/v1/invoice-drafts/{draft_id}", json=payload, headers=human
    )
    assert old_put.status_code == 400
    assert old_put.json()["detail"]["code"] == "draft_rejected"
    assert changed["draft_id"]


def test_24_issued_from_an_old_page_gets_its_receipt(books, client, human):
    proposed = books.propose()
    from services.invoice_issue import InvoiceIssueService

    # The old pages call the same route; the service alone marks the row.
    InvoiceIssueService().issue(proposed["draft_id"], actor="stefan")
    assert InvoiceProposalRepository.get(proposed["draft_id"]).status == "issued"
    # The route's resume path writes the receipt.
    assert _issue(client, human, proposed["draft_id"]).status_code == 409
    assert len(_posts(books, "receipt")) == 1


def test_25_number_taken_between_proposal_and_press(books, client, human):
    first = books.propose()
    second = books.propose(context=books.context(books.say("en till")))
    assert _issue(client, human, first["draft_id"]).status_code == 201
    response = _issue(client, human, second["draft_id"])
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "number_taken"
    [error] = _posts(books, "error")
    assert "2026-1" in error.body["cause"]
    assert error.body["consequence"].startswith(
        "Ingenting har bokförts och ingen faktura är utfärdad."
    )
    assert error.body["retry_draft_id"] is None
    row = InvoiceProposalRepository.get(second["draft_id"])
    assert row.status == "pending" and row.last_error_code == "number_taken"
    assert row.last_error_post_id == error.id


def test_26_period_locked_then_unlocked(books, client, human):
    from services.ledger import LedgerService

    proposed = books.propose()
    ledger = LedgerService()
    ledger.lock_period(books.periods[7].id, actor="stefan")
    response = _issue(client, human, proposed["draft_id"])
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "period_locked"
    [error] = _posts(books, "error")
    assert error.body["cause"].startswith("Perioden juli 2026 låstes")
    assert "av stefan" in error.body["cause"]
    assert _count("invoices") == 0
    ledger.unlock_period(books.periods[7].id, actor="stefan")
    assert _issue(client, human, proposed["draft_id"]).status_code == 201


def test_27_company_info_emptied_in_between(books, client, human):
    proposed = books.propose()
    _set_company_info(
        {k: v for k, v in _COMPANY.items() if k not in ("seat", "vat_number")}
    )
    response = _issue(client, human, proposed["draft_id"])
    assert response.status_code == 422
    [error] = _posts(books, "error")
    assert error.body["cause"] == (
        "Företagsuppgifter saknas: säte, momsregistreringsnummer."
    )
    assert InvoiceProposalRepository.get(proposed["draft_id"]).status == "pending"
    _set_company_info(_COMPANY)
    assert _issue(client, human, proposed["draft_id"]).status_code == 201


def test_28_the_same_error_three_times_is_one_post(books, client, human):
    from services.ledger import LedgerService

    proposed = books.propose()
    LedgerService().lock_period(books.periods[7].id, actor="stefan")
    for _ in range(3):
        assert _issue(client, human, proposed["draft_id"]).status_code == 409
    assert len(_posts(books, "error")) == 1


def test_29_the_api_key_may_still_not_issue(books, client, auth_headers):
    proposed = books.propose()
    response = client.post(
        f"/api/v1/invoice-drafts/{proposed['draft_id']}/issue", headers=auth_headers
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "human_only"


# Testfall 30 (F0:s testfall 1–15 oförändrade) är tests/test_fakturering_f0.py.


# --- 13.3 Vyn och räknaren --------------------------------------------------


def test_31_get_drafts_has_both_kinds(books, client, human, auth_headers):
    pending = books.propose()
    issued = books.propose(
        context=books.context(books.say("två")), invoice_number="2026-2"
    )
    assert _issue(client, human, issued["draft_id"]).status_code == 201
    response = client.get(
        "/api/v1/drafts",
        params={"view_key": "betala.fakturering"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    rows = {d["draft_id"]: d for d in response.json()["drafts"]}
    assert rows[pending["draft_id"]]["kind"] == "invoice"
    assert rows[pending["draft_id"]]["status"] == "pending"
    assert rows[pending["draft_id"]]["invoice"] is None
    block = rows[issued["draft_id"]]["invoice"]
    assert block["invoice_number"] == "2026-2"
    assert block["voucher"].startswith("A-")
    assert block["pdf_url"].endswith("/pdf")

    only_issued = client.get(
        "/api/v1/drafts",
        params={"view_key": "betala.fakturering", "status": "issued"},
        headers=auth_headers,
    ).json()
    assert [d["draft_id"] for d in only_issued["drafts"]] == [issued["draft_id"]]
    posted = client.get(
        "/api/v1/drafts",
        params={"view_key": "betala.fakturering", "status": "posted"},
        headers=auth_headers,
    ).json()
    assert posted["drafts"] == []


def test_32_count_waiting(books, client, human, auth_headers):
    service = DecisionService()
    assert service.count_waiting("betala.fakturering") == 0
    old = books.propose()
    assert service.count_waiting("betala.fakturering") == 1
    books.tool(
        "andra_fakturautkast",
        {"draft_id": old["draft_id"], "reference": "Bo"},
        books.context(books.say("Bo")),
    )
    assert service.count_waiting("betala.fakturering") == 1
    assert service.count_waiting() == 1
    assert service.count_waiting("bocker.verifikationer") == 0

    overview = client.get("/api/v1/overview", headers=auth_headers).json()
    pages = {p["key"]: p for p in overview["pages"]}
    assert pages["betala"]["counters"]["open_decisions"] == 1
    assert pages["bocker"]["counters"]["open_decisions"] == 1

    current = InvoiceProposalRepository.list(
        view_key="betala.fakturering", status="pending"
    )[0][0]
    assert _issue(client, human, current.draft_id).status_code == 201
    assert service.count_waiting("betala.fakturering") == 0


# --- hela flödet och append-only ---------------------------------------------


def test_39_the_whole_flow(books, client, human):
    customers = books.tool("las_kunder", {"query": "QRTECH"})
    customer_id = customers["customers"][0]["id"]
    invoices = books.tool("las_fakturor", {})
    assert invoices["latest_numbers"] == []
    proposed = books.tool(
        "foresla_faktura", _args(books.customer, customer_id=customer_id)
    )
    changed = books.tool(
        "andra_fakturautkast",
        {
            "draft_id": proposed["draft_id"],
            "rows": [
                {
                    "description": "Konsulttjänster",
                    "quantity": "26",
                    "unit": "h",
                    "unit_price": 80000,
                    "vat_code": "MP1",
                    "revenue_account": "3011",
                    "delivery_month": "2026-07",
                }
            ],
        },
        books.context(books.say("det var 26 timmar")),
    )
    assert _issue(client, human, proposed["draft_id"]).status_code == 422
    response = _issue(client, human, changed["draft_id"])
    assert response.status_code == 201
    assert response.json()["invoice_number"] == "2026-1"
    [receipt] = _posts(books, "receipt")
    assert receipt.body["rows"][0]["right_ore"] == 2600000
    assert books.tool("las_fakturor", {})["latest_numbers"] == ["2026-1"]


def test_40_append_only_is_untouched(books, client, human):
    proposed = books.propose()
    response = _issue(client, human, proposed["draft_id"])
    invoice_id = response.json()["invoice_id"]
    import sqlite3

    with pytest.raises(sqlite3.DatabaseError):
        db.execute("UPDATE invoices SET amount_inc_vat = 1 WHERE id = ?", (invoice_id,))
    with pytest.raises(ValidationError) as exc:
        books.tool(
            "andra_fakturautkast",
            {"draft_id": proposed["draft_id"], "reference": "x"},
            books.context(books.say("ändra den utfärdade")),
        )
    assert exc.value.code == "draft_already_issued"
