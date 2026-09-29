"""PDF export service for invoices and financial reports.

Uses WeasyPrint + Jinja2 for HTML→PDF rendering with Swedish templates.
Falls back gracefully if WeasyPrint is not available (requires system libraries).
"""

import base64
import io
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import qrcode
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
from services.k2_report import K2ReportService
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
        """Read the seller's details from `company_info` (SPEC-fakturering.md §6).

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
# bindestreck eller mellanslag (SPEC-fakturering.md §6).
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


# --- Invoice template (SPEC-fakturering.md §6.1) ---

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


def _iso_date(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]


def _lines(text: Optional[str]) -> List[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


# --- QR code generation ---


def generate_swish_qr(
    payee: str,
    amount_ore: int,
    message: str = "",
) -> str:
    """Generate Swish-compatible QR code as base64 PNG.

    Uses the Swish C2B format.
    """
    amount_kr = amount_ore / 100
    # Swish QR payload format
    payload = f"C{payee};{amount_kr:.2f};{message}"

    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(payload)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


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
        """What `invoice.html` shows (SPEC-fakturering.md §6.1).

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

    # ---- Trial Balance PDF ----

    def export_trial_balance(self, period_id: str) -> bytes:
        """Generate trial balance (råbalans) PDF."""
        period = self.period_repo.get_period(period_id)
        if not period:
            raise ValueError(f"Period {period_id} hittades inte")

        balances = self.ledger.get_trial_balance(period_id)
        all_accounts = self.ledger.accounts.get_all_as_dict()

        rows = []
        total_debit = 0
        total_credit = 0

        for code in sorted(balances.keys()):
            bal = balances[code]
            account = all_accounts.get(code)
            account_name = account.name if account else code
            rows.append(
                {
                    "account_code": code,
                    "account_name": account_name,
                    "debit": bal["debit"],
                    "credit": bal["credit"],
                    "balance": bal["debit"] - bal["credit"],
                }
            )
            total_debit += bal["debit"]
            total_credit += bal["credit"]

        context = {
            "company": self.company,
            "period": f"{period.year}-{period.month:02d}",
            "rows": rows,
            "total_debit": total_debit,
            "total_credit": total_credit,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        return self.engine.render_pdf("trial_balance.html", context)

    # ---- Account Ledger (Huvudbok) PDF ----

    def export_general_ledger(self, account_code: str, period_id: str) -> bytes:
        """Generate general ledger (huvudbok) PDF for one account."""
        account = self.ledger.accounts.get(account_code)
        if not account:
            raise ValueError(f"Konto {account_code} hittades inte")

        period = self.period_repo.get_period(period_id)
        if not period:
            raise ValueError(f"Period {period_id} hittades inte")

        ledger_rows = self.ledger.get_account_ledger(account_code, period_id)
        ending_balance = ledger_rows[-1]["balance"] if ledger_rows else 0

        context = {
            "company": self.company,
            "account_code": account_code,
            "account_name": account.name,
            "period": f"{period.year}-{period.month:02d}",
            "rows": ledger_rows,
            "ending_balance": ending_balance,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        return self.engine.render_pdf("general_ledger.html", context)

    # ---- Income Statement (Resultaträkning) PDF ----

    def export_income_statement(self, period_id: str) -> bytes:
        """Generate income statement (resultaträkning) PDF."""
        period = self.period_repo.get_period(period_id)
        if not period:
            raise ValueError(f"Period {period_id} hittades inte")

        balances = self.ledger.get_trial_balance(period_id)
        all_accounts = self.ledger.accounts.get_all_as_dict()

        revenue_rows = []
        expense_rows = []
        financial_income_rows = []
        financial_expense_rows = []
        total_revenue = 0
        total_expenses = 0
        total_fin_income = 0
        total_fin_expense = 0

        for code in sorted(balances.keys()):
            account = all_accounts.get(code)
            if not account:
                continue
            bal = balances[code]
            net = bal["credit"] - bal["debit"]  # Revenue is credit-positive

            row_data = {
                "account_code": code,
                "account_name": account.name,
                "amount": net,
            }

            # BAS plan classification
            if code.startswith("3"):  # Intäkter (3xxx)
                revenue_rows.append(row_data)
                total_revenue += net
            elif code.startswith(("4", "5", "6", "7")):  # Kostnader
                # Expenses: debit-positive, negate for display
                row_data["amount"] = bal["debit"] - bal["credit"]
                expense_rows.append(row_data)
                total_expenses += row_data["amount"]
            elif code.startswith("8"):  # Finansiella poster
                if code < "8400":
                    financial_income_rows.append(row_data)
                    total_fin_income += net
                else:
                    row_data["amount"] = bal["debit"] - bal["credit"]
                    financial_expense_rows.append(row_data)
                    total_fin_expense += row_data["amount"]

        operating_result = total_revenue - total_expenses
        result_after_financial = operating_result + total_fin_income - total_fin_expense

        context = {
            "company": self.company,
            "period_start": period.start_date.isoformat(),
            "period_end": period.end_date.isoformat(),
            "revenue_rows": revenue_rows,
            "expense_rows": expense_rows,
            "financial_income_rows": financial_income_rows,
            "financial_expense_rows": financial_expense_rows,
            "total_revenue": total_revenue,
            "total_expenses": total_expenses,
            "operating_result": operating_result,
            "result_after_financial": result_after_financial,
            "net_result": result_after_financial,
            "compare_period": None,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        return self.engine.render_pdf("income_statement.html", context)

    # ---- Balance Sheet (Balansräkning) PDF ----

    def export_balance_sheet(self, period_id: str) -> bytes:
        """Generate balance sheet (balansräkning) PDF with 3 columns: IB, Förändring, UB."""
        from repositories.account_repo import AccountRepository
        from repositories.voucher_repo import VoucherRepository

        period = self.period_repo.get_period(period_id)
        if not period:
            raise ValueError(f"Period {period_id} hittades inte")

        target_year = period.year

        from services.opening_balance import OpeningBalanceService

        # The period's fiscal year: its IB (services/opening_balance.py) and
        # its posted vouchers. A posted `IB`-series voucher predates
        # migration 033 -- opening state, never a movement.
        vouchers, _ = VoucherRepository.list_all(
            fiscal_year_id=period.fiscal_year_id, status="posted"
        )
        regular_vouchers = [v for v in vouchers if v.series.value != "IB"]

        all_accounts = AccountRepository.get_all_as_dict()

        opening = OpeningBalanceService().get(period.fiscal_year_id)
        opening_balances = {
            code: {"debit": max(amount, 0), "credit": max(-amount, 0)}
            for code, amount in opening.balances.items()
        }

        # Calculate changes from regular vouchers
        change_balances = {}
        for voucher in regular_vouchers:
            for row in voucher.rows:
                code = row.account_code
                if code not in change_balances:
                    change_balances[code] = {"debit": 0, "credit": 0}
                change_balances[code]["debit"] += row.debit or 0
                change_balances[code]["credit"] += row.credit or 0

        # Helper functions
        def _get_net(balances, code, is_liability=False):
            """Get net balance for an account."""
            if code not in balances:
                return 0
            bal = balances[code]
            net = bal["debit"] - bal["credit"]
            return -net if is_liability else net

        def _calc_category(balances, ranges, is_liability=False):
            """Calculate total for a category range."""
            total = 0
            for code, bal in balances.items():
                try:
                    num = int(code)
                    for min_r, max_r in ranges:
                        if min_r <= num <= max_r:
                            net = bal["debit"] - bal["credit"]
                            total += -net if is_liability else net
                            break
                except ValueError:
                    continue
            return total

        # Category ranges
        fixed_asset_ranges = [(1200, 1299)]
        current_asset_ranges = [(1000, 1199), (1300, 1999)]
        equity_ranges = [(2000, 2099)]
        long_term_liability_ranges = [(2100, 2199)]
        current_liability_ranges = [(2200, 2999)]

        # Build account rows with 3 columns
        all_codes = set(opening_balances.keys()) | set(change_balances.keys())

        def _build_rows(codes, ranges, is_liability=False):
            """Build account rows with opening, change, and closing balances."""
            rows = []
            for code in sorted(codes):
                try:
                    num = int(code)
                    if not any(min_r <= num <= max_r for min_r, max_r in ranges):
                        continue
                except ValueError:
                    continue

                opening = _get_net(opening_balances, code, is_liability)
                change = _get_net(change_balances, code, is_liability)
                closing = opening + change

                if opening != 0 or change != 0 or closing != 0:
                    acct = all_accounts.get(code)
                    rows.append(
                        {
                            "account_code": code,
                            "account_name": acct.name if acct else code,
                            "opening_balance": opening,
                            "change": change,
                            "closing_balance": closing,
                        }
                    )
            return rows

        # Build category rows
        fixed_asset_rows = _build_rows(all_codes, fixed_asset_ranges, False)
        current_asset_rows = _build_rows(all_codes, current_asset_ranges, False)
        equity_rows = _build_rows(all_codes, equity_ranges, True)
        liability_rows = _build_rows(
            all_codes, long_term_liability_ranges + current_liability_ranges, True
        )

        # Calculate totals
        total_fixed_opening = _calc_category(
            opening_balances, fixed_asset_ranges, False
        )
        total_fixed_change = _calc_category(change_balances, fixed_asset_ranges, False)
        total_fixed_closing = total_fixed_opening + total_fixed_change

        total_current_opening = _calc_category(
            opening_balances, current_asset_ranges, False
        )
        total_current_change = _calc_category(
            change_balances, current_asset_ranges, False
        )
        total_current_closing = total_current_opening + total_current_change

        total_assets_opening = total_fixed_opening + total_current_opening
        total_assets_change = total_fixed_change + total_current_change
        total_assets_closing = total_assets_opening + total_assets_change

        total_equity_opening = _calc_category(opening_balances, equity_ranges, True)
        total_equity_change = _calc_category(change_balances, equity_ranges, True)
        total_equity_closing = total_equity_opening + total_equity_change

        total_liab_opening = _calc_category(
            opening_balances,
            long_term_liability_ranges + current_liability_ranges,
            True,
        )
        total_liab_change = _calc_category(
            change_balances, long_term_liability_ranges + current_liability_ranges, True
        )
        total_liab_closing = total_liab_opening + total_liab_change

        total_eq_liab_opening = total_equity_opening + total_liab_opening
        total_eq_liab_change = total_equity_change + total_liab_change
        total_eq_liab_closing = total_eq_liab_opening + total_eq_liab_change

        context = {
            "company": self.company,
            "balance_date": period.end_date.isoformat(),
            "period_year": target_year,
            # Asset rows
            "fixed_asset_rows": fixed_asset_rows,
            "current_asset_rows": current_asset_rows,
            # Liability/equity rows
            "equity_rows": equity_rows,
            "liability_rows": liability_rows,
            # Asset totals with 3 columns
            "total_fixed_assets_opening": total_fixed_opening,
            "total_fixed_assets_change": total_fixed_change,
            "total_fixed_assets_closing": total_fixed_closing,
            "total_current_assets_opening": total_current_opening,
            "total_current_assets_change": total_current_change,
            "total_current_assets_closing": total_current_closing,
            "total_assets_opening": total_assets_opening,
            "total_assets_change": total_assets_change,
            "total_assets_closing": total_assets_closing,
            # Liability/equity totals with 3 columns
            "total_equity_opening": total_equity_opening,
            "total_equity_change": total_equity_change,
            "total_equity_closing": total_equity_closing,
            "total_liabilities_opening": total_liab_opening,
            "total_liabilities_change": total_liab_change,
            "total_liabilities_closing": total_liab_closing,
            "total_equity_and_liabilities_opening": total_eq_liab_opening,
            "total_equity_and_liabilities_change": total_eq_liab_change,
            "total_equity_and_liabilities_closing": total_eq_liab_closing,
            "balanced": abs(total_assets_closing - total_eq_liab_closing) < 100,
            "opening_balance_source": opening.source,
            "compare_period": None,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        return self.engine.render_pdf("balance_sheet.html", context)

    # ---- K2 Report PDF ----

    def export_k2_report(
        self,
        fiscal_year_id: str,
        company_name: str,
        org_number: str = "",
        managing_director: str = "",
        average_employees: Optional[int] = None,
        significant_events: str = "",
    ) -> bytes:
        """Generate K2 annual report PDF."""
        fy = self.period_repo.get_fiscal_year(fiscal_year_id)
        if not fy:
            raise ValueError(f"Räkenskapsår {fiscal_year_id} hittades inte")

        # Generate K2 data via existing service
        k2_service = K2ReportService()
        report = k2_service.generate_report(
            fiscal_year=fy,
            company_name=company_name,
            org_number=org_number,
            managing_director=managing_director,
            average_employees=average_employees,
            significant_events=significant_events,
        )

        # Build sections for template
        income_statement_sections = []
        balance_sheet_sections = []

        if "income_statement" in report:
            is_data = report["income_statement"]
            # Revenue section
            rev_rows = []
            for item in is_data.get("revenue_items", []):
                rev_rows.append(
                    {"label": item.get("name", ""), "amount": item.get("amount", 0)}
                )
            income_statement_sections.append(
                {
                    "title": "Rörelseintäkter",
                    "rows": rev_rows,
                    "total": is_data.get("total_revenue", 0),
                    "total_label": "Summa rörelseintäkter",
                }
            )
            # Expense section
            exp_rows = []
            for item in is_data.get("expense_items", []):
                exp_rows.append(
                    {"label": item.get("name", ""), "amount": item.get("amount", 0)}
                )
            income_statement_sections.append(
                {
                    "title": "Rörelsekostnader",
                    "rows": exp_rows,
                    "total": is_data.get("total_expenses", 0),
                    "total_label": "Summa rörelsekostnader",
                }
            )

        if "balance_sheet" in report:
            bs_data = report["balance_sheet"]
            for section_name in ["assets", "equity_and_liabilities"]:
                section_data = bs_data.get(section_name, {})
                rows = []
                for item in section_data.get("items", []):
                    rows.append(
                        {"label": item.get("name", ""), "amount": item.get("amount", 0)}
                    )
                title = (
                    "Tillgångar"
                    if section_name == "assets"
                    else "Eget kapital och skulder"
                )
                balance_sheet_sections.append(
                    {
                        "title": title,
                        "rows": rows,
                        "total": section_data.get("total", 0),
                        "total_label": f"Summa {title.lower()}",
                    }
                )

        context = {
            "company": CompanyInfo(name=company_name, org_number=org_number),
            "fiscal_year_start": fy.start_date.isoformat(),
            "fiscal_year_end": fy.end_date.isoformat(),
            "fiscal_year_label": f"{fy.start_date.year}",
            "managing_director": managing_director,
            "average_employees": average_employees,
            "significant_events": significant_events,
            "income_statement_sections": income_statement_sections,
            "balance_sheet_sections": balance_sheet_sections,
            "net_result": report.get("income_statement", {}).get("net_result", 0),
            "compare_year": None,
            "notes": report.get("notes", []),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        return self.engine.render_pdf("k2_report.html", context)

    # ---- HTML Export Methods (Fallback) ----

    def export_invoice_html(self, invoice_id: str) -> str:
        """Generate HTML for an invoice (fallback for PDF)."""
        return self.engine.render_html(
            "invoice.html", self._invoice_context(invoice_id)
        )

    def export_trial_balance_html(self, period_id: str) -> str:
        """Generate HTML for trial balance (fallback for PDF)."""
        period = self.period_repo.get_period(period_id)
        if not period:
            raise ValueError(f"Period {period_id} hittades inte")

        balances = self.ledger.get_trial_balance(period_id)
        all_accounts = self.ledger.accounts.get_all_as_dict()

        rows = []
        total_debit = 0
        total_credit = 0

        for code in sorted(balances.keys()):
            bal = balances[code]
            account = all_accounts.get(code)
            account_name = account.name if account else code
            rows.append(
                {
                    "account_code": code,
                    "account_name": account_name,
                    "debit": bal["debit"],
                    "credit": bal["credit"],
                    "balance": bal["debit"] - bal["credit"],
                }
            )
            total_debit += bal["debit"]
            total_credit += bal["credit"]

        context = {
            "company": self.company,
            "period": f"{period.year}-{period.month:02d}",
            "rows": rows,
            "total_debit": total_debit,
            "total_credit": total_credit,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        return self.engine.render_html("trial_balance.html", context)
