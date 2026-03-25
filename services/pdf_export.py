"""PDF export service for invoices and financial reports.

Uses WeasyPrint + Jinja2 for HTML→PDF rendering with Swedish templates.
Falls back gracefully if WeasyPrint is not available (requires system libraries).
"""

import io
import os
import base64
from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass

import qrcode
from jinja2 import Environment, FileSystemLoader

# WeasyPrint is optional - requires system libraries (pango, etc.)
try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except (ImportError, OSError):
    WEASYPRINT_AVAILABLE = False
    HTML = None  # type: ignore

from services.ledger import LedgerService
from services.invoice import InvoiceService
from services.k2_report import K2ReportService
from repositories.period_repo import PeriodRepository


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

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CompanyInfo":
        """Create from dictionary, ignoring unknown keys."""
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


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
                os.path.dirname(os.path.dirname(__file__)),
                "templates", "pdf"
            )
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=True,
        )
        # Register custom filters
        self.env.filters["format_sek"] = format_sek
        self.env.filters["vat_label"] = vat_label
    
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
        pdf_bytes = HTML(string=html_str).write_pdf()
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
        self.period_repo = PeriodRepository()
    
    # ---- Invoice PDF ----
    
    def export_invoice(self, invoice_id: str) -> bytes:
        """Generate PDF for a single invoice."""
        invoice = self.invoice_service.invoices.get(invoice_id)
        if not invoice:
            raise ValueError(f"Faktura {invoice_id} hittades inte")
        
        # Calculate VAT summary by code
        vat_summary: Dict[str, int] = {}
        for row in invoice.rows:
            code = row.vat_code
            vat_summary[code] = vat_summary.get(code, 0) + row.vat_amount
        
        # Generate QR code for Swish payment if available
        qr_code_data = None
        if self.company.swish:
            qr_code_data = generate_swish_qr(
                payee=self.company.swish,
                amount_ore=invoice.amount_inc_vat,
                message=invoice.invoice_number,
            )
        
        context = {
            "company": self.company,
            "invoice": invoice,
            "vat_summary": vat_summary,
            "qr_code_data": qr_code_data,
        }
        return self.engine.render_pdf("invoice.html", context)
    
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
            rows.append({
                "account_code": code,
                "account_name": account_name,
                "debit": bal["debit"],
                "credit": bal["credit"],
                "balance": bal["debit"] - bal["credit"],
            })
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
        """Generate balance sheet (balansräkning) PDF."""
        period = self.period_repo.get_period(period_id)
        if not period:
            raise ValueError(f"Period {period_id} hittades inte")
        
        balances = self.ledger.get_trial_balance(period_id)
        all_accounts = self.ledger.accounts.get_all_as_dict()
        
        fixed_asset_rows = []
        current_asset_rows = []
        equity_rows = []
        liability_rows = []
        
        total_fixed = total_current = total_equity = total_liabilities = 0
        
        for code in sorted(balances.keys()):
            account = all_accounts.get(code)
            if not account:
                continue
            bal = balances[code]
            
            row_data = {
                "account_code": code,
                "account_name": account.name,
            }
            
            # BAS classification
            if code.startswith("1"):  # Tillgångar
                debit_balance = bal["debit"] - bal["credit"]
                row_data["amount"] = debit_balance
                if code < "1300":  # Anläggningstillgångar (10xx-12xx)
                    fixed_asset_rows.append(row_data)
                    total_fixed += debit_balance
                else:  # Omsättningstillgångar (13xx+)
                    current_asset_rows.append(row_data)
                    total_current += debit_balance
            elif code.startswith("2"):  # Skulder & Eget kapital
                credit_balance = bal["credit"] - bal["debit"]
                row_data["amount"] = credit_balance
                if code < "2100":  # Eget kapital (20xx)
                    equity_rows.append(row_data)
                    total_equity += credit_balance
                else:  # Skulder (21xx+)
                    liability_rows.append(row_data)
                    total_liabilities += credit_balance
        
        total_assets = total_fixed + total_current
        total_eq_liab = total_equity + total_liabilities
        
        context = {
            "company": self.company,
            "balance_date": period.end_date.isoformat(),
            "fixed_asset_rows": fixed_asset_rows,
            "current_asset_rows": current_asset_rows,
            "equity_rows": equity_rows,
            "liability_rows": liability_rows,
            "total_fixed_assets": total_fixed,
            "total_current_assets": total_current,
            "total_assets": total_assets,
            "total_equity": total_equity,
            "total_liabilities": total_liabilities,
            "total_equity_and_liabilities": total_eq_liab,
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
                rev_rows.append({"label": item.get("name", ""), "amount": item.get("amount", 0)})
            income_statement_sections.append({
                "title": "Rörelseintäkter",
                "rows": rev_rows,
                "total": is_data.get("total_revenue", 0),
                "total_label": "Summa rörelseintäkter",
            })
            # Expense section
            exp_rows = []
            for item in is_data.get("expense_items", []):
                exp_rows.append({"label": item.get("name", ""), "amount": item.get("amount", 0)})
            income_statement_sections.append({
                "title": "Rörelsekostnader",
                "rows": exp_rows,
                "total": is_data.get("total_expenses", 0),
                "total_label": "Summa rörelsekostnader",
            })
        
        if "balance_sheet" in report:
            bs_data = report["balance_sheet"]
            for section_name in ["assets", "equity_and_liabilities"]:
                section_data = bs_data.get(section_name, {})
                rows = []
                for item in section_data.get("items", []):
                    rows.append({"label": item.get("name", ""), "amount": item.get("amount", 0)})
                title = "Tillgångar" if section_name == "assets" else "Eget kapital och skulder"
                balance_sheet_sections.append({
                    "title": title,
                    "rows": rows,
                    "total": section_data.get("total", 0),
                    "total_label": f"Summa {title.lower()}",
                })
        
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
        invoice = self.invoice_service.invoices.get(invoice_id)
        if not invoice:
            raise ValueError(f"Faktura {invoice_id} hittades inte")
        
        vat_summary: Dict[str, int] = {}
        for row in invoice.rows:
            code = row.vat_code
            vat_summary[code] = vat_summary.get(code, 0) + row.vat_amount
        
        qr_code_data = None
        if self.company.swish:
            qr_code_data = generate_swish_qr(
                payee=self.company.swish,
                amount_ore=invoice.amount_inc_vat,
                message=invoice.invoice_number,
            )
        
        context = {
            "company": self.company,
            "invoice": invoice,
            "vat_summary": vat_summary,
            "qr_code_data": qr_code_data,
        }
        return self.engine.render_html("invoice.html", context)

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
            rows.append({
                "account_code": code,
                "account_name": account_name,
                "debit": bal["debit"],
                "credit": bal["credit"],
                "balance": bal["debit"] - bal["credit"],
            })
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
