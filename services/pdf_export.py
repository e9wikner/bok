"""PDF export service for invoices and financial reports.

Uses WeasyPrint + Jinja2 for HTML→PDF rendering with Swedish templates.
Falls back gracefully if WeasyPrint is not available (requires system libraries).
"""

import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup, escape

# WeasyPrint is optional - requires system libraries (pango, etc.)
try:
    from weasyprint import HTML

    WEASYPRINT_AVAILABLE = True
except (ImportError, OSError):
    WEASYPRINT_AVAILABLE = False
    HTML = None  # type: ignore

from domain.validation import ValidationError
from repositories.company_info_repo import CompanyInfoRepository
from repositories.period_repo import PeriodRepository
from services.invoice import InvoiceService
from services.ledger import LedgerService
from services.payroll import PayrollService

# --- Company info dataclass ---


@dataclass
class CompanyInfo:
    """Company information for document headers/footers."""

    name: str = "Mitt Företag AB"
    org_number: str = ""
    vat_number: str = ""
    address: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    logo_url: Optional[str] = None
    bankgiro: str = ""
    plusgiro: str = ""
    swish: str = ""
    iban: str = ""
    bic: str = ""
    f_skatt: bool = True
    contact_person: str = ""
    seat: str = ""
    postnr: str = ""
    postort: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CompanyInfo":
        """Create from dictionary, ignoring unknown keys."""
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})

    @classmethod
    def load(cls) -> "CompanyInfo":
        """Read the seller's details from `company_info`.

        The keys are the field names. `f_skatt` is stored as the string
        `"true"`; anything else, or no key, is False. Older rows name the
        contact person `contact_name` (the company-info route and the SIE
        import write that key); it is used when `contact_person` is absent.
        """
        values = CompanyInfoRepository.get_all()
        data: Dict[str, Any] = {
            name: (values.get(name) or "").strip()
            for name in cls.__dataclass_fields__
            if name not in ("f_skatt", "logo_url")
        }
        if not data["contact_person"]:
            data["contact_person"] = (values.get("contact_name") or "").strip()
        data["logo_url"] = values.get("logo_url") or None
        data["f_skatt"] = _parse_bool(values.get("f_skatt"))
        return cls(**data)

    def missing_for_invoice(self) -> List[str]:
        """The keys an invoice requires that are absent or malformed (§6)."""
        missing = [
            key
            for key in ("name", "address", "org_number", "seat")
            if not (getattr(self, key) or "").strip()
        ]
        if not VAT_NUMBER_RE.fullmatch(self.vat_number or ""):
            missing.append("vat_number")
        if not (self.bankgiro or "").strip() and not (self.plusgiro or "").strip():
            missing.append("bankgiro_or_plusgiro")
        return missing

    def check_complete_for_invoice(self) -> None:
        """Raise `company_info_incomplete` listing every missing key (§6)."""
        missing = self.missing_for_invoice()
        if missing:
            raise ValidationError(
                code="company_info_incomplete",
                message="Company info is incomplete for issuing an invoice",
                details=f"missing: {', '.join(missing)}",
                payload={"missing": missing},
            )


# Momsregistreringsnummer: SE + organisationsnumrets 10 siffror + 01, utan
# bindestreck eller mellanslag.
VAT_NUMBER_RE = re.compile(r"SE\d{10}01")


def _parse_bool(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in ("true", "1", "yes", "ja")


# --- Template filters ---

VAT_LABELS = {
    "MP1": "25%",
    "MP2": "12%",
    "MP3": "6%",
    "MF": "0%",
}


def format_sek(value_ore: int) -> str:
    """Format öre amount as SEK string (e.g., 150000 → '1 500,00')."""
    if value_ore is None:
        return "0,00"
    negative = value_ore < 0
    value_ore = abs(value_ore)
    kr = value_ore // 100
    ore = value_ore % 100
    # Thousands separator
    kr_str = f"{kr:,}".replace(",", " ")
    result = f"{kr_str},{ore:02d}"
    if negative:
        result = f"-{result}"
    return result


def vat_label(code: str) -> str:
    """Convert VAT code to human label."""
    return VAT_LABELS.get(code, code)


# --- Invoice template ---

# A no-break space, so "22 400,00 kr" never wraps. Courier Prime has U+00A0
# but no narrow no-break space.
NBSP = "\u00a0"

VAT_RATES = {"MP1": 25, "MP2": 12, "MP3": 6, "MF": 0}

MONTHS_SV = [
    "januari",
    "februari",
    "mars",
    "april",
    "maj",
    "juni",
    "juli",
    "augusti",
    "september",
    "oktober",
    "november",
    "december",
]


def format_kr(value_ore: Optional[int]) -> str:
    """Öre as an invoice amount: 2240000 → '22 400,00 kr', unbreakable."""
    return format_sek(value_ore or 0).replace(" ", NBSP) + NBSP + "kr"


def format_quantity(quantity_centi: Optional[int], unit: Optional[str]) -> str:
    """Quantity times 100 with its unit: (750, 'h') → '7,5 h', (2800, 'h') → '28 h'."""
    if quantity_centi is None:
        return ""
    whole, fraction = divmod(abs(quantity_centi), 100)
    text = f"{whole:,}".replace(",", NBSP)
    if fraction:
        text += f",{fraction:02d}".rstrip("0")
    if quantity_centi < 0:
        text = "-" + text
    return f"{text}{NBSP}{unit}" if unit else text


def format_delivery(
    delivery_from: Optional[date],
    delivery_to: Optional[date],
    delivery_month: Optional[str],
) -> Markup:
    """The KOMMENTAR column: a period over three lines, one date, or a month
    ('2026-07' → 'juli 2026'). Empty when there is no delivery."""
    if delivery_from or delivery_to:
        start, end = delivery_from or delivery_to, delivery_to or delivery_from
        if start == end:
            return Markup(escape(_iso_date(start)))
        return Markup("{}<br>--&gt;<br>{}").format(_iso_date(start), _iso_date(end))
    if delivery_month:
        match = re.fullmatch(r"(\d{4})-(\d{2})", delivery_month.strip())
        if match and 1 <= int(match.group(2)) <= 12:
            return Markup(
                escape(f"{MONTHS_SV[int(match.group(2)) - 1]} {match.group(1)}")
            )
        return Markup(escape(delivery_month))
    return Markup("")


def delivery_text(
    delivery_from: Optional[date],
    delivery_to: Optional[date],
    delivery_month: Optional[str],
) -> str:
    """`format_delivery` as plain text on one line (`2026-06-29 --> 2026-07-02`,
    `2026-07-01`, `juli 2026`), for the invoice proposal card:
    the same words the PDF will print."""
    return str(format_delivery(delivery_from, delivery_to, delivery_month)).replace(
        "<br>--&gt;<br>", " --> "
    )


def _iso_date(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]


def _lines(text: Optional[str]) -> List[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


# --- PDF Engine ---


class PDFEngine:
    """Jinja2 + WeasyPrint PDF rendering engine.

    Falls back to HTML output if WeasyPrint is not available.
    """

    def __init__(self, template_dir: Optional[str] = None):
        if template_dir is None:
            template_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "templates", "pdf"
            )
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=True,
        )
        # Register custom filters
        self.env.filters["format_sek"] = format_sek
        self.env.filters["vat_label"] = vat_label
        self.env.filters["kr"] = format_kr
        self.env.filters["iso_date"] = _iso_date
        # Relative URLs in templates (the invoice's embedded fonts in
        # templates/pdf/fonts/) resolve against the template directory.
        self.base_url = template_dir

    def render_pdf(self, template_name: str, context: Dict[str, Any]) -> bytes:
        """Render a template to PDF bytes."""
        if not WEASYPRINT_AVAILABLE:
            raise RuntimeError(
                "PDF export requires WeasyPrint which is not installed or missing system dependencies. "
                "Install: brew install pango libffi (macOS) or apt-get install libpango-1.0-0 (Ubuntu). "
                "Use the HTML endpoint to get raw HTML output instead."
            )
        template = self.env.get_template(template_name)
        html_str = template.render(**context)
        pdf_bytes = HTML(string=html_str, base_url=self.base_url).write_pdf()
        return pdf_bytes

    def render_html(self, template_name: str, context: Dict[str, Any]) -> str:
        """Render a template to HTML string (for debugging)."""
        template = self.env.get_template(template_name)
        return template.render(**context)


# --- PDF Export Service ---


class PDFExportService:
    """High-level PDF export for invoices and reports."""

    def __init__(self, company: Optional[CompanyInfo] = None):
        self.engine = PDFEngine()
        self.company = company or CompanyInfo()
        self.ledger = LedgerService()
        self.invoice_service = InvoiceService()
        self.payroll_service = PayrollService()
        self.period_repo = PeriodRepository()

    # ---- Invoice PDF ----

    def export_invoice(self, invoice_id: str) -> bytes:
        """Generate PDF for a single invoice."""
        return self.engine.render_pdf("invoice.html", self._invoice_context(invoice_id))

    def _invoice_context(self, invoice_id: str) -> Dict[str, Any]:
        """What `invoice.html` shows.

        A row without its own delivery takes the draft's (§4.2). Old invoices
        have neither, and their KOMMENTAR is empty.
        """
        invoice = self.invoice_service.invoices.get(invoice_id)
        if not invoice:
            raise ValueError(f"Faktura {invoice_id} hittades inte")

        default_delivery: Tuple[Optional[date], Optional[date], Optional[str]] = (
            None,
            None,
            None,
        )
        if invoice.source_draft_id:
            from repositories.invoice_draft_repo import InvoiceDraftRepository

            draft = InvoiceDraftRepository.get(invoice.source_draft_id)
            if draft:
                default_delivery = (
                    draft.delivery_from,
                    draft.delivery_to,
                    draft.delivery_month,
                )

        rows = []
        vat_base: Dict[str, int] = {}
        for row in invoice.rows:
            own = (row.delivery_from, row.delivery_to, row.delivery_month)
            delivery = own if any(own) else default_delivery
            quantity_centi = row.quantity_centi
            if quantity_centi is None:
                quantity_centi = row.quantity * 100
            rows.append(
                {
                    "article_number": row.article_number or "",
                    "description": row.description,
                    "delivery": format_delivery(*delivery),
                    "quantity": format_quantity(quantity_centi, row.unit),
                    "unit_price": row.unit_price,
                    "amount_ex_vat": row.amount_ex_vat,
                }
            )
            vat_base[row.vat_code] = vat_base.get(row.vat_code, 0) + row.amount_ex_vat

        vat_exempt = vat_base.pop("MF", None)
        vat_bases = [
            (f"{VAT_RATES[code]} %" if code in VAT_RATES else code, amount)
            for code, amount in sorted(
                vat_base.items(), key=lambda item: -VAT_RATES.get(item[0], 0)
            )
        ]

        company = self.company
        postal = " ".join(p for p in (company.postnr, company.postort) if p)
        return {
            "company": company,
            "company_address": _lines(company.address) + ([postal] if postal else []),
            "invoice": invoice,
            "customer_address": _lines(invoice.customer_address),
            "rows": rows,
            "vat_bases": vat_bases,
            "vat_exempt": vat_exempt,
        }

    def export_payslip(self, payslip_id: str) -> bytes:
        """Generate PDF for a payslip."""
        context = self.payroll_service.get_payslip_context(payslip_id)
        context["company"] = self.company
        return self.engine.render_pdf("payslip.html", context)

    def export_payslip_html(self, payslip_id: str) -> str:
        """Generate payslip HTML for preview/debugging and PDF-light tests."""
        context = self.payroll_service.get_payslip_context(payslip_id)
        context["company"] = self.company
        return self.engine.render_html("payslip.html", context)
