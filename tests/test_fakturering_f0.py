"""Fakturering F0: utfärda en faktura från ett utkast (SPEC-fakturering.md §9).

Testfall 1–15 ur §9. Varje fall är märkt med den uppgift i
`tasks/fakturering/todo.md` som gör det grönt.

Gränssnitt som testerna förutsätter där specen inte namnger dem:

- `services.invoice_issue.InvoiceIssueService().issue(draft_id, actor=...)`
  returnerar samma fält som 201-svaret i §5 (`invoice_id`, `invoice_number`,
  `voucher_id`, `pdf_url`), som dict eller attribut.
- Fel är `domain.validation.ValidationError` (eller en subklass) med `.code`.
  Fel som bär data (409-fallen i §5 och `company_info_incomplete`) har den i
  `.payload: dict`, med samma nycklar som svaret i §5.
- `company_info` lagras som nyckel/värde. Nycklarna är CompanyInfo-fältens namn
  (`vat_number`, `bankgiro`, `plusgiro`, `contact_person` …) plus `seat` och
  `f_skatt` (§6). `f_skatt` sparas som `"true"`.
- `CompanyInfo.load()` läser `company_info` och `check_complete_for_invoice()`
  kastar `company_info_incomplete` med `payload["missing"]` (uppgift 5).
- PDF:en skrivs under `settings.intake_dir` (datakatalogen) och kopplas som
  underlag till verifikationen. `pdf_path` får vara absolut eller relativ till
  den katalogen eller dess förälder.
- HTTP-fel har formen `detail = {"code": ..., <payload-fält>...}`.

PDF-text läses med pypdf (finns redan som beroende).
"""

import calendar
import hashlib
import io
import re
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from config import settings
from db.database import db
from domain.types import VoucherStatus
from repositories.account_repo import AccountRepository
from repositories.period_repo import PeriodRepository
from repositories.voucher_repo import VoucherRepository
from services.auth import AuthService
from services.customer_article import CustomerService
from services.invoice_draft import InvoiceDraftService

# --- hjälpare ---------------------------------------------------------------

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
    "phone": "031-123 45 67",
    "email": "faktura@wikner.example",
    "contact_person": "Stefan Wikner",
}


def _set_company_info(values: dict) -> None:
    db.execute("DELETE FROM company_info")
    for key, value in values.items():
        db.execute(
            "INSERT INTO company_info (key, value) VALUES (?, ?)", (key, str(value))
        )
    db.commit()


def _count(table: str) -> int:
    return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _snapshot() -> dict:
    return {
        t: _count(t)
        for t in (
            "invoices",
            "invoice_rows",
            "vouchers",
            "intake_sources",
            "voucher_intake_sources",
        )
    }


def _invoice_row(invoice_id: str):
    return db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()


def _field(result, name):
    if isinstance(result, dict):
        return result[name]
    return getattr(result, name)


def _payload(exc) -> dict:
    return getattr(exc, "payload", None) or {}


def _issue(draft_id: str, actor: str = "stefan"):
    from services.invoice_issue import InvoiceIssueService

    return InvoiceIssueService().issue(draft_id, actor=actor)


def _issue_error(draft_id: str):
    from domain.validation import ValidationError

    with pytest.raises(ValidationError) as exc:
        _issue(draft_id)
    return exc.value


def _pdf_file(invoice) -> Path:
    stored = invoice["pdf_path"]
    assert stored, "pdf_path saknas"
    base = Path(settings.intake_dir)
    for candidate in (Path(stored), base / stored, base.parent / stored):
        if candidate.is_file():
            return candidate
    raise AssertionError(f"PDF-filen {stored} finns inte")


def _pdf_text(pdf_bytes: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    text = text.replace("\xa0", " ").replace(" ", " ")
    return re.sub(r"\s+", " ", text)


def _pdf_fonts(pdf_bytes: bytes) -> list:
    """(BaseFont, embedded) för varje typsnitt i PDF:en."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    fonts = []
    for page in reader.pages:
        resources = page.get("/Resources") or {}
        for font in (resources.get("/Font") or {}).values():
            font = font.get_object()
            descriptor = font.get("/FontDescriptor")
            if descriptor is None and "/DescendantFonts" in font:
                descendant = font["/DescendantFonts"][0].get_object()
                descriptor = descendant.get("/FontDescriptor")
            descriptor = descriptor.get_object() if descriptor else {}
            embedded = any(
                k in descriptor for k in ("/FontFile", "/FontFile2", "/FontFile3")
            )
            fonts.append((str(font.get("/BaseFont", "")), embedded))
    return fonts


@pytest.fixture
def books(test_db, tmp_path, monkeypatch):
    """Konton, räkenskapsåret 2026 med tolv perioder, fullständig
    `company_info` och en isolerad datakatalog."""
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
    return periods


@pytest.fixture
def customer(books):
    return CustomerService().create_customer(
        name="QRTECH Aktiebolag",
        org_number="556000-0001",
        email="faktura@qrtech.example",
        address="Box 100\n412 50 Göteborg",
        payment_terms_days=65,
    )


def _draft(customer, **overrides):
    """Ett utkast som går att utfärda: 28 h à 800 kr, 25 %, period."""
    row = {
        "description": "Konsulttjänster",
        "quantity": 28,
        "unit": "h",
        "unit_price": 80000,
        "vat_code": "MP1",
        "revenue_account": "3011",
        "delivery_from": date(2026, 6, 29),
        "delivery_to": date(2026, 7, 2),
    }
    row.update(overrides.pop("row", {}))
    kwargs = dict(
        customer_id=customer.id if customer else None,
        invoice_date=date(2026, 7, 31),
        invoice_number="2026-1",
        reference="Anna Andersson",
        rows_data=[row],
        created_by="agent",
    )
    kwargs.update(overrides)
    return InvoiceDraftService().create_draft(**kwargs)


@pytest.fixture
def client(test_db):
    from api.main import app

    return TestClient(app)


@pytest.fixture
def human_headers():
    return {"Authorization": f"Bearer {AuthService().create_jwt('stefan')}"}


def _insert_issued_invoice(number: str = "101282", rows=None) -> str:
    """En utfärdad faktura skriven direkt i databasen (kolumnerna i §4), så
    triggers och mall kan testas utan utfärdandetjänsten."""
    rows = rows or [
        {
            "description": "Konsulttjänster enligt avtal",
            "quantity_centi": 2800,
            "unit": "h",
            "unit_price": 80000,
            "vat_code": "MP1",
            "revenue_account": "3011",
            "amount_ex_vat": 2240000,
            "vat_amount": 560000,
            "delivery_from": "2026-06-29",
            "delivery_to": "2026-07-02",
            "delivery_month": None,
        }
    ]
    ex_vat = sum(r["amount_ex_vat"] for r in rows)
    vat = sum(r["vat_amount"] for r in rows)
    invoice_id = str(uuid.uuid4())
    db.execute(
        """
        INSERT INTO invoices (
            id, invoice_number, customer_name, customer_org_number,
            customer_address, customer_reference, payment_terms_days,
            invoice_date, due_date, status, amount_ex_vat, vat_amount,
            amount_inc_vat, paid_amount, issued_at, issued_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'sent', ?, ?, ?, 0, ?, ?)
        """,
        (
            invoice_id,
            number,
            "QRTECH Aktiebolag",
            "556000-0001",
            "Box 100\n412 50 Göteborg",
            "Anna Andersson",
            65,
            "2026-07-31",
            (date(2026, 7, 31) + timedelta(days=65)).isoformat(),
            ex_vat,
            vat,
            ex_vat + vat,
            datetime(2026, 7, 31, 12, 0).isoformat(),
            "stefan",
        ),
    )
    for r in rows:
        db.execute(
            """
            INSERT INTO invoice_rows (
                id, invoice_id, description, quantity, quantity_centi, unit,
                unit_price, vat_code, revenue_account, amount_ex_vat, vat_amount,
                amount_inc_vat, delivery_from, delivery_to, delivery_month
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                invoice_id,
                r["description"],
                max(1, r["quantity_centi"] // 100),
                r["quantity_centi"],
                r["unit"],
                r["unit_price"],
                r["vat_code"],
                r["revenue_account"],
                r["amount_ex_vat"],
                r["vat_amount"],
                r["amount_ex_vat"] + r["vat_amount"],
                r["delivery_from"],
                r["delivery_to"],
                r["delivery_month"],
            ),
        )
    db.commit()
    return invoice_id


def _render_invoice_pdf(invoice_id: str) -> bytes:
    from services.pdf_export import CompanyInfo, PDFExportService

    company = CompanyInfo.from_dict({**_COMPANY, "f_skatt": True})
    return PDFExportService(company=company).export_invoice(invoice_id)


# --- 1–7: utfärdandetjänsten (uppgift 7) ------------------------------------


@pytest.mark.xfail(strict=True, reason="F0 uppgift 7")
def test_01_issue_creates_invoice_posted_voucher_and_stored_pdf(customer):
    draft = _draft(customer)

    result = _issue(draft.id)

    invoice = _invoice_row(_field(result, "invoice_id"))
    assert _field(result, "invoice_number") == "2026-1"
    assert invoice["invoice_number"] == "2026-1"
    assert invoice["source_draft_id"] == draft.id
    assert invoice["issued_at"] is not None
    assert invoice["issued_by"] == "stefan"
    assert invoice["customer_address"] == "Box 100\n412 50 Göteborg"
    assert invoice["customer_reference"] == "Anna Andersson"
    assert invoice["payment_terms_days"] == 65
    assert invoice["amount_inc_vat"] == 2800000

    voucher = VoucherRepository.get(_field(result, "voucher_id"))
    assert invoice["voucher_id"] == voucher.id
    assert voucher.status == VoucherStatus.POSTED
    assert voucher.series == "A" or getattr(voucher.series, "value", None) == "A"
    assert voucher.date == date(2026, 7, 31)
    assert voucher.description == "Faktura 2026-1 QRTECH Aktiebolag"
    lines = sorted((r.account_code, r.debit, r.credit) for r in voucher.rows)
    assert lines == [
        ("1510", 2800000, 0),
        ("2610", 0, 560000),
        ("3011", 0, 2240000),
    ]

    pdf = _pdf_file(invoice).read_bytes()
    assert pdf.startswith(b"%PDF")
    assert hashlib.sha256(pdf).hexdigest() == invoice["pdf_sha256"]
    linked = db.execute(
        """
        SELECT s.sha256 FROM voucher_intake_sources l
        JOIN intake_sources s ON s.id = l.intake_source_id
        WHERE l.voucher_id = ?
        """,
        (voucher.id,),
    ).fetchall()
    assert [row["sha256"] for row in linked] == [invoice["pdf_sha256"]]

    assert InvoiceDraftService().get_draft(draft.id).status == "issued"
    assert _field(result, "pdf_url") == f"/api/v1/invoices/{invoice['id']}/pdf"


@pytest.mark.xfail(strict=True, reason="F0 uppgift 7")
def test_02_same_number_on_two_drafts_gives_number_taken(customer):
    first = _draft(customer)
    second = _draft(customer)
    issued = _issue(first.id)
    before = _snapshot()

    err = _issue_error(second.id)

    assert err.code == "number_taken"
    assert _payload(err)["invoice_number"] == "2026-1"
    assert _payload(err)["invoice_id"] == _field(issued, "invoice_id")
    assert _snapshot() == before
    assert InvoiceDraftService().get_draft(second.id).status == "needs_review"


@pytest.mark.xfail(strict=True, reason="F0 uppgift 7")
def test_03_failure_after_posting_rolls_everything_back(customer, monkeypatch):
    from services.pdf_export import PDFEngine

    draft = _draft(customer)
    before = _snapshot()

    def broken(self, template_name, context):
        raise RuntimeError("PDF-renderingen fallerade")

    with monkeypatch.context() as patch:
        patch.setattr(PDFEngine, "render_pdf", broken)
        with pytest.raises(RuntimeError):
            _issue(draft.id)

    assert _snapshot() == before
    assert _count("invoices") == 0 and _count("vouchers") == 0
    untouched = InvoiceDraftService().get_draft(draft.id)
    assert untouched.status == "needs_review"
    assert untouched.invoice_number == "2026-1"

    # Numret är fortfarande ledigt: samma utkast går att utfärda nu.
    result = _issue(draft.id)
    assert _field(result, "invoice_number") == "2026-1"


def test_03_prerequisite_the_issue_path_leaves_commit_to_the_caller(books, customer):
    """Förutsättningen i §5 (uppgift 3): repona och `InvoiceService` committar
    inte själva på utfärdandevägen. En rollback efter dem lämnar databasen
    som den var."""
    from repositories.invoice_draft_repo import InvoiceDraftRepository
    from services.invoice import InvoiceService

    draft = InvoiceDraftService().create_draft(
        customer_id=customer.id,
        invoice_date=date(2026, 7, 31),
        rows_data=[
            {
                "description": "Konsulttjänster",
                "quantity": 28,
                "unit_price": 80000,
                "vat_code": "MP1",
                "revenue_account": "3011",
            }
        ],
        created_by="agent",
    )

    def state() -> dict:
        return {
            **_snapshot(),
            "voucher_rows": _count("voucher_rows"),
            "audit_log": _count("audit_log"),
        }

    before = state()

    service = InvoiceService()
    invoice = service.create_invoice(
        customer_name=draft.customer_name,
        invoice_date=draft.invoice_date,
        due_date=draft.due_date,
        rows_data=[
            {
                "description": row.description,
                "quantity": row.quantity,
                "unit_price": row.unit_price,
                "vat_code": row.vat_code,
                "revenue_account": row.revenue_account,
            }
            for row in draft.rows
        ],
        created_by="stefan",
        _commit=False,
    )
    voucher_id = service.create_booking_for_invoice(
        invoice.id, books[7].id, actor="stefan", _commit=False
    )
    InvoiceDraftRepository.update_status(draft.id, "issued")

    # Skrivet på anslutningen, men inte committat.
    written = state()
    assert written["invoices"] == before["invoices"] + 1
    assert written["vouchers"] == before["vouchers"] + 1
    assert _invoice_row(invoice.id)["voucher_id"] == voucher_id

    db.rollback()

    assert state() == before
    assert _invoice_row(invoice.id) is None
    assert InvoiceDraftService().get_draft(draft.id).status == "needs_review"


@pytest.mark.xfail(strict=True, reason="F0 uppgift 7")
def test_04_issuing_the_same_draft_twice_gives_one_invoice(customer):
    draft = _draft(customer)
    first = _issue(draft.id)

    err = _issue_error(draft.id)

    assert err.code == "draft_already_issued"
    assert _payload(err)["invoice_id"] == _field(first, "invoice_id")
    assert _count("invoices") == 1
    assert _count("vouchers") == 1


@pytest.mark.xfail(strict=True, reason="F0 uppgift 7")
def test_05_locked_period_gives_period_locked(books, customer):
    from services.ledger import LedgerService

    LedgerService().lock_period(books[7].id, actor="test")
    draft = _draft(customer)
    before = _snapshot()

    err = _issue_error(draft.id)

    assert err.code == "period_locked"
    assert _payload(err)["locked_by"] == "test"
    assert _payload(err)["locked_at"]
    assert _snapshot() == before
    assert InvoiceDraftService().get_draft(draft.id).status == "needs_review"


@pytest.mark.xfail(strict=True, reason="F0 uppgift 7")
def test_06_invoice_number_missing_or_a_date(customer):
    from domain.validation import ValidationError

    missing = _draft(customer, invoice_number=None)
    assert _issue_error(missing.id).code == "invoice_number_missing"

    # Ett datum som nummer får avvisas redan när utkastet sparas eller först
    # vid utfärdandet; båda håller specen.
    for number in ("20260929", "2026-09-29"):
        with pytest.raises(ValidationError) as exc:
            _issue(_draft(customer, invoice_number=number).id)
        assert exc.value.code == "number_is_date"

    assert _count("invoices") == 0 and _count("vouchers") == 0


@pytest.mark.xfail(strict=True, reason="F0 uppgift 7")
def test_07_customer_address_and_delivery_date_are_required(books, customer):
    no_address = CustomerService().create_customer(
        name="Adresslös Aktiebolag", payment_terms_days=30
    )
    draft = _draft(no_address, invoice_number="2026-2")
    assert _issue_error(draft.id).code == "customer_address_missing"

    no_delivery = _draft(customer, row={"delivery_from": None, "delivery_to": None})
    assert _issue_error(no_delivery.id).code == "delivery_date_missing"

    assert _count("invoices") == 0 and _count("vouchers") == 0


@pytest.mark.xfail(strict=True, reason="F0 uppgift 7")
def test_07b_delivery_on_the_draft_covers_rows_without_one(customer):
    draft = _draft(
        customer,
        delivery_month="2026-07",
        row={"delivery_from": None, "delivery_to": None},
    )

    result = _issue(draft.id)

    row = db.execute(
        "SELECT * FROM invoice_rows WHERE invoice_id = ?",
        (_field(result, "invoice_id"),),
    ).fetchone()
    assert row["delivery_month"] == "2026-07"


@pytest.mark.xfail(strict=True, reason="F0 uppgift 7")
def test_11b_issue_refuses_incomplete_company_info(customer):
    _set_company_info(
        {
            k: v
            for k, v in _COMPANY.items()
            if k not in ("vat_number", "seat", "bankgiro")
        }
    )
    draft = _draft(customer)

    err = _issue_error(draft.id)

    assert err.code == "company_info_incomplete"
    assert {"vat_number", "seat"} <= set(_payload(err)["missing"])
    assert _count("invoices") == 0 and _count("vouchers") == 0


# --- 8: triggers (uppgift 2) ------------------------------------------------


def test_08_issued_invoice_is_append_only_in_the_database(test_db):
    invoice_id = _insert_issued_invoice()
    row_id = db.execute(
        "SELECT id FROM invoice_rows WHERE invoice_id = ?", (invoice_id,)
    ).fetchone()["id"]

    refused = [
        ("UPDATE invoices SET amount_inc_vat = 1 WHERE id = ?", invoice_id),
        ("UPDATE invoices SET invoice_number = 'X-1' WHERE id = ?", invoice_id),
        ("UPDATE invoice_rows SET unit_price = 1 WHERE id = ?", row_id),
        ("DELETE FROM invoice_rows WHERE id = ?", row_id),
        ("DELETE FROM invoices WHERE id = ?", invoice_id),
    ]
    for sql, key in refused:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(sql, (key,))
        db.rollback()

    db.execute(
        "UPDATE invoices SET paid_amount = 100000, status = 'partially_paid' "
        "WHERE id = ?",
        (invoice_id,),
    )
    db.commit()
    invoice = _invoice_row(invoice_id)
    assert invoice["paid_amount"] == 100000
    assert invoice["status"] == "partially_paid"
    assert invoice["amount_inc_vat"] == 2800000
    assert invoice["invoice_number"] == "101282"


# --- 9, 10, 14: routes (uppgift 8) ------------------------------------------


@pytest.mark.xfail(strict=True, reason="F0 uppgift 8")
def test_09_the_api_key_may_not_issue(client, customer, auth_headers):
    draft = _draft(customer)
    before = _snapshot()

    refused = client.post(
        f"/api/v1/invoice-drafts/{draft.id}/issue", headers=auth_headers
    )

    assert refused.status_code == 403
    assert refused.json()["detail"]["code"] == "human_only"
    assert _snapshot() == before


@pytest.mark.xfail(strict=True, reason="F0 uppgift 8")
def test_09b_issue_route_status_codes(client, customer, human_headers):
    unnumbered = _draft(customer, invoice_number=None)
    missing = client.post(
        f"/api/v1/invoice-drafts/{unnumbered.id}/issue", headers=human_headers
    )
    assert missing.status_code == 422
    assert missing.json()["detail"]["code"] == "invoice_number_missing"

    draft = _draft(customer)
    created = client.post(
        f"/api/v1/invoice-drafts/{draft.id}/issue", headers=human_headers
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["invoice_number"] == "2026-1"
    assert body["voucher_id"]
    assert body["pdf_url"] == f"/api/v1/invoices/{body['invoice_id']}/pdf"

    again = client.post(
        f"/api/v1/invoice-drafts/{draft.id}/issue", headers=human_headers
    )
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "draft_already_issued"
    assert again.json()["detail"]["invoice_id"] == body["invoice_id"]

    taken = client.post(
        f"/api/v1/invoice-drafts/{_draft(customer).id}/issue", headers=human_headers
    )
    assert taken.status_code == 409
    assert taken.json()["detail"]["code"] == "number_taken"
    assert taken.json()["detail"]["invoice_id"] == body["invoice_id"]


@pytest.mark.xfail(strict=True, reason="F0 uppgift 8")
def test_10_pdf_download_is_the_stored_file(
    client, customer, human_headers, auth_headers, monkeypatch
):
    from services.pdf_export import PDFEngine

    draft = _draft(customer)
    created = client.post(
        f"/api/v1/invoice-drafts/{draft.id}/issue", headers=human_headers
    )
    assert created.status_code == 201, created.text
    url = created.json()["pdf_url"]

    first = client.get(url, headers=auth_headers)
    # Nedladdningen renderar aldrig på nytt.
    monkeypatch.setattr(
        PDFEngine,
        "render_pdf",
        lambda self, *a, **k: (_ for _ in ()).throw(AssertionError("rendering")),
    )
    second = client.get(url, headers=auth_headers)

    assert first.status_code == 200 and second.status_code == 200
    assert first.headers["content-type"].startswith("application/pdf")
    assert first.content == second.content
    invoice = _invoice_row(created.json()["invoice_id"])
    assert hashlib.sha256(first.content).hexdigest() == invoice["pdf_sha256"]


def _insert_old_invoice() -> str:
    """En faktura från före F0: inget utfärdande, ingen sparad PDF."""
    invoice_id = str(uuid.uuid4())
    db.execute(
        """
        INSERT INTO invoices (
            id, invoice_number, customer_name, invoice_date, due_date, status,
            amount_ex_vat, vat_amount, amount_inc_vat
        ) VALUES (?, '20260301001', 'Gammal Kund AB', '2026-03-01', '2026-03-31',
                  'sent', 100000, 25000, 125000)
        """,
        (invoice_id,),
    )
    db.execute(
        """
        INSERT INTO invoice_rows (
            id, invoice_id, description, quantity, unit_price, vat_code,
            amount_ex_vat, vat_amount, amount_inc_vat
        ) VALUES (?, ?, 'Konsulttimme', 1, 100000, 'MP1', 100000, 25000, 125000)
        """,
        (str(uuid.uuid4()), invoice_id),
    )
    db.commit()
    return invoice_id


def test_14_old_invoices_keep_their_numbers_and_can_be_read_and_paid(
    client, books, auth_headers
):
    invoice_id = _insert_old_invoice()

    read = client.get(f"/api/v1/invoices/{invoice_id}", headers=auth_headers)
    assert read.status_code == 200
    assert read.json()["invoice_number"] == "20260301001"

    paid = client.post(
        f"/api/v1/invoices/{invoice_id}/payment",
        headers=auth_headers,
        json={
            "amount": 125000,
            "payment_date": "2026-03-20",
            "payment_method": "bank_transfer",
        },
    )
    assert paid.status_code == 200, paid.text
    assert paid.json()["invoice_status"] == "paid"
    assert paid.json()["remaining_amount"] == 0

    pdf = client.get(f"/api/v1/export/pdf/invoice/{invoice_id}", headers=auth_headers)
    assert pdf.status_code == 200, pdf.text
    assert pdf.content.startswith(b"%PDF")


@pytest.mark.xfail(strict=True, reason="F0 uppgift 8")
def test_14b_the_old_invoice_routes_are_gone(client, books, customer, auth_headers):
    invoice_id = _insert_old_invoice()
    draft = _draft(customer)

    calls = [
        ("/api/v1/invoices", {}),
        (f"/api/v1/invoices/{invoice_id}/send", {}),
        (f"/api/v1/invoices/{invoice_id}/book", {"period_id": books[3].id}),
        (f"/api/v1/invoice-drafts/{draft.id}/send", {}),
    ]
    for url, body in calls:
        response = client.post(url, headers=auth_headers, json=body)
        assert response.status_code in (404, 405), url
    assert _count("vouchers") == 0


# --- 11: säljarens uppgifter (uppgift 5) ------------------------------------


@pytest.mark.xfail(strict=True, reason="F0 uppgift 5")
def test_11_incomplete_company_info_lists_everything_missing(test_db):
    from domain.validation import ValidationError
    from services.pdf_export import CompanyInfo

    _set_company_info(
        {
            k: v
            for k, v in _COMPANY.items()
            if k not in ("vat_number", "seat", "bankgiro")
        }
    )

    company = CompanyInfo.load()
    assert company.name == _COMPANY["name"]
    assert company.f_skatt is True
    with pytest.raises(ValidationError) as exc:
        company.check_complete_for_invoice()

    assert exc.value.code == "company_info_incomplete"
    missing = _payload(exc.value)["missing"]
    assert "vat_number" in missing
    assert "seat" in missing
    assert any("giro" in item for item in missing)

    _set_company_info(_COMPANY)
    CompanyInfo.load().check_complete_for_invoice()


@pytest.mark.xfail(strict=True, reason="F0 uppgift 5")
def test_11c_vat_number_format_is_checked(test_db):
    from domain.validation import ValidationError
    from services.pdf_export import CompanyInfo

    _set_company_info({**_COMPANY, "vat_number": "SE 556677-8899 01"})

    with pytest.raises(ValidationError) as exc:
        CompanyInfo.load().check_complete_for_invoice()

    assert exc.value.code == "company_info_incomplete"
    assert "vat_number" in _payload(exc.value)["missing"]


# --- 12: decimalt antal och enhet (uppgift 4) -------------------------------


def test_12_decimal_quantity_in_draft_and_preview(books, client, auth_headers):
    draft = InvoiceDraftService().create_draft(
        customer_name="Decimal Aktiebolag",
        invoice_date=date(2026, 7, 31),
        rows_data=[
            {
                "description": "Konsulttjänster",
                "quantity": 7.5,
                "unit": "h",
                "unit_price": 115000,
                "vat_code": "MP1",
                "revenue_account": "3011",
            }
        ],
        created_by="agent",
    )
    assert draft.amount_ex_vat == 862500
    assert draft.vat_amount == 215625
    assert draft.rows[0].quantity_centi == 750
    assert draft.rows[0].unit == "h"

    created = client.post(
        "/api/v1/invoice-drafts",
        headers=auth_headers,
        json={
            "customer_name": "Decimal Aktiebolag",
            "invoice_date": "2026-07-31",
            "rows": [
                {
                    "description": "Konsulttjänster",
                    "quantity": 7.5,
                    "unit": "h",
                    "unit_price": 115000,
                    "vat_code": "MP1",
                    "revenue_account": "3011",
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["amount_ex_vat"] == 862500
    assert created.json()["vat_amount"] == 215625

    preview = client.post(
        "/api/v1/invoices/preview",
        headers=auth_headers,
        json={
            "rows": [
                {
                    "description": "Konsulttjänster",
                    "quantity": 7.5,
                    "unit_price": 115000,
                    "vat_code": "MP1",
                },
                # round_half_even: 0,5 × 1,01 kr = 50,5 öre → 50 öre,
                # 0,5 × 1,03 kr = 51,5 öre → 52 öre.
                {
                    "description": "Avrundning ned",
                    "quantity": 0.5,
                    "unit_price": 101,
                    "vat_code": "MF",
                },
                {
                    "description": "Avrundning upp",
                    "quantity": 0.5,
                    "unit_price": 103,
                    "vat_code": "MF",
                },
            ]
        },
    )
    assert preview.status_code == 200, preview.text
    rows = preview.json()["rows"]
    assert rows[0]["amount_ex_vat"] == 862500
    assert rows[0]["vat_amount"] == 215625
    assert rows[1]["amount_ex_vat"] == 50
    assert rows[2]["amount_ex_vat"] == 52


# --- 13, 15: PDF:ens innehåll (uppgift 6) -----------------------------------


@pytest.mark.xfail(strict=True, reason="F0 uppgift 6")
def test_13_pdf_has_every_required_detail(test_db):
    _set_company_info(_COMPANY)
    invoice_id = _insert_issued_invoice(
        rows=[
            {
                "description": "Konsulttjänster enligt avtal",
                "quantity_centi": 2800,
                "unit": "h",
                "unit_price": 80000,
                "vat_code": "MP1",
                "revenue_account": "3011",
                "amount_ex_vat": 2240000,
                "vat_amount": 560000,
                "delivery_from": "2026-06-29",
                "delivery_to": "2026-07-02",
                "delivery_month": None,
            },
            {
                "description": "Kurslitteratur",
                "quantity_centi": 100,
                "unit": "st",
                "unit_price": 50000,
                "vat_code": "MF",
                "revenue_account": "3010",
                "amount_ex_vat": 50000,
                "vat_amount": 0,
                "delivery_from": None,
                "delivery_to": None,
                "delivery_month": "2026-07",
            },
        ]
    )

    pdf = _render_invoice_pdf(invoice_id)
    text = _pdf_text(pdf)

    required = [
        # Säljaren
        "Wikner Konsult AB",
        "Storgatan 1",
        "556677-8899",
        "Göteborg",
        "SE556677889901",
        "123-4567",
        "Godkänd för F-skatt",
        "031-123 45 67",
        "faktura@wikner.example",
        "Stefan Wikner",
        # Fakturan och kunden
        "FAKTURA",
        "101282",
        "2026-07-31",
        "QRTECH Aktiebolag",
        "Box 100",
        "412 50 Göteborg",
        "Anna Andersson",
        "65 dagar",
        (date(2026, 7, 31) + timedelta(days=65)).isoformat(),
        # Raderna
        "Konsulttjänster enligt avtal",
        "2026-06-29 --> 2026-07-02",
        "28 h",
        "800,00",
        "Kurslitteratur",
        "juli 2026",
        # Summering
        "Summa att betala",
        "Momsgrundande belopp",
        "25 %: 22 400,00 kr",
        "Momsfritt",
        "5 600,00 kr",
        "28 500,00 kr",
    ]
    for item in required:
        assert item in text, f"{item!r} saknas i PDF:en"
    for header in ("MOTTAGARE", "ART.NR.", "BESKRIVNING", "KOMMENTAR", "ANTAL"):
        assert header in text, header
    for label in ("Säte", "VAT-nr", "Org.nr", "Bankgiro"):
        assert label in text, label
    lowered = text.lower()
    assert "ränta" not in lowered and "dröjsmål" not in lowered

    fonts = _pdf_fonts(pdf)
    courier = [
        (name, embedded)
        for name, embedded in fonts
        if "courierprime" in name.lower().replace(" ", "").replace("-", "")
    ]
    assert courier, fonts
    assert all(embedded for _, embedded in courier)


@pytest.mark.xfail(strict=True, reason="F0 uppgift 6")
def test_15_the_model_invoice_recreated(test_db):
    """Förlagan nr 101282: QRTECH, 28 h à 800 kr, 25 %. Den visuella
    jämförelsen mot förlagan görs för hand och sparas inte i repot."""
    _set_company_info(_COMPANY)
    invoice_id = _insert_issued_invoice()

    text = _pdf_text(_render_invoice_pdf(invoice_id))

    assert re.search(r"Netto[^0-9]{0,20}22 400,00 kr", text), text
    assert re.search(r"Moms[^0-9]{0,20}5 600,00 kr", text), text
    assert re.search(r"Totalt[^0-9]{0,20}28 000,00 kr", text), text
    assert re.search(r"Summa att betala[^0-9]{0,20}28 000,00 kr", text), text
    assert "À PRIS" in text and "NETTO" in text
    assert "28 h" in text
