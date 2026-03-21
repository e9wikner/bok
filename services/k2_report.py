"""K2 Annual Report generation service (Fas 3)."""

from datetime import date, datetime
from typing import Dict, Optional, List
import uuid

from domain.models import FiscalYear
from repositories.voucher_repo import VoucherRepository
from repositories.audit_repo import AuditRepository


class K2ReportService:
    """Generate K2 annual reports (Årsredovisning för små företag)."""
    
    def __init__(self):
        self.vouchers = VoucherRepository()
        self.audit = AuditRepository()
    
    def generate_report(
        self,
        fiscal_year: FiscalYear,
        company_name: str,
        org_number: Optional[str] = None,
        managing_director: Optional[str] = None,
        average_employees: Optional[int] = None,
        significant_events: Optional[str] = None,
    ) -> Dict:
        """
        Generate K2 annual report for fiscal year.
        
        Returns complete financial statements:
        - Income Statement (Resultaträkning)
        - Balance Sheet (Balansräkning)
        - Cash Flow Statement (Kassaflödesanalys)
        """
        
        report_id = str(uuid.uuid4())
        
        # Get all periods in fiscal year
        from repositories.period_repo import PeriodRepository
        periods = PeriodRepository.list_periods(fiscal_year.id)
        period_ids = [p.id for p in periods]
        
        # Calculate financial totals from posted vouchers
        income_stmt = self._calculate_income_statement(period_ids)
        balance_sheet = self._calculate_balance_sheet(period_ids)
        cash_flow = self._calculate_cash_flow(income_stmt, balance_sheet)
        
        # Compile report
        report = {
            "id": report_id,
            "fiscal_year_id": fiscal_year.id,
            "company_name": company_name,
            "org_number": org_number,
            "report_date": datetime.now(),
            "managing_director": managing_director,
            "average_employees": average_employees,
            "significant_events": significant_events,
            "income_statement": income_stmt,
            "balance_sheet": balance_sheet,
            "cash_flow": cash_flow,
            "status": "draft",
        }
        
        # Log
        self.audit.log(
            entity_type="annual_report",
            entity_id=report_id,
            action="created",
            actor="system",
            payload={
                "fiscal_year": fiscal_year.id,
                "company": company_name,
                "report_date": report["report_date"].isoformat()
            }
        )
        
        return report
    
    def _calculate_income_statement(self, period_ids: List[str]) -> Dict:
        """Calculate income statement from vouchers."""
        income_stmt = {
            "revenue_services": 0,
            "revenue_goods": 0,
            "revenue_other": 0,
            "personnel_costs": 0,
            "depreciation": 0,
            "other_operating_costs": 0,
            "financial_costs": 0,
            "tax_expense": 0,
        }
        
        # Revenue accounts (3000-3999)
        revenue_accounts = {
            "3011": "revenue_services",  # Service revenue
            "3010": "revenue_other",     # Other revenue
            "3020": "revenue_other",
            "3030": "revenue_other",
        }
        
        # Expense accounts
        expense_accounts = {
            "4010": "personnel_costs",    # Salaries
            "4020": "other_operating_costs",  # Rent
            "4030": "other_operating_costs",  # Utilities
            "4040": "other_operating_costs",  # Travel
            "5010": "other_operating_costs",  # Supplies
            "8000": "depreciation",       # Depreciation
        }
        
        # Get all posted vouchers
        all_credit = 0
        all_debit = 0
        
        for period_id in period_ids:
            vouchers = self.vouchers.list_for_period(period_id, status="posted")
            for voucher in vouchers:
                for row in voucher.rows:
                    # Revenue (credit entries on revenue accounts)
                    if row.account_code in revenue_accounts and row.credit > 0:
                        category = revenue_accounts[row.account_code]
                        income_stmt[category] += row.credit
                        all_credit += row.credit
                    
                    # Expenses (debit entries on expense accounts)
                    if row.account_code in expense_accounts and row.debit > 0:
                        category = expense_accounts[row.account_code]
                        income_stmt[category] += row.debit
                        all_debit += row.debit
        
        # Calculate totals
        income_stmt["revenue_total"] = (
            income_stmt["revenue_services"] + 
            income_stmt["revenue_goods"] + 
            income_stmt["revenue_other"]
        )
        
        total_expenses = sum([
            income_stmt["personnel_costs"],
            income_stmt["depreciation"],
            income_stmt["other_operating_costs"],
            income_stmt["financial_costs"],
        ])
        
        income_stmt["operating_profit"] = income_stmt["revenue_total"] - total_expenses
        income_stmt["profit_before_tax"] = income_stmt["operating_profit"]
        income_stmt["net_profit_loss"] = income_stmt["profit_before_tax"] - income_stmt["tax_expense"]
        
        return income_stmt
    
    def _calculate_balance_sheet(self, period_ids: List[str]) -> Dict:
        """Calculate balance sheet from vouchers."""
        balance_sheet = {
            # Assets
            "cash_and_equivalents": 0,
            "receivables": 0,
            "inventory": 0,
            "other_current_assets": 0,
            "tangible_assets": 0,
            "intangible_assets": 0,
            "financial_assets": 0,
            # Liabilities
            "short_term_debt": 0,
            "payables": 0,
            "other_current_liabilities": 0,
            "long_term_debt": 0,
            "other_long_term_liabilities": 0,
            # Equity
            "share_capital": 0,
            "retained_earnings": 0,
            "current_year_result": 0,
        }
        
        # Map accounts to balance sheet items
        account_mapping = {
            "1010": ("cash_and_equivalents", "debit"),      # Bank
            "1200": ("receivables", "debit"),               # Receivables
            "1510": ("receivables", "debit"),               # Customer receivables
            "1710": ("tangible_assets", "debit"),           # Fixed assets
            "2000": ("payables", "credit"),                 # Trade payables
            "2100": ("short_term_debt", "credit"),          # Short-term borrowing
            "2900": ("share_capital", "credit"),            # Equity
        }
        
        # Calculate balances
        for period_id in period_ids:
            vouchers = self.vouchers.list_for_period(period_id, status="posted")
            for voucher in vouchers:
                for row in voucher.rows:
                    if row.account_code in account_mapping:
                        item, side = account_mapping[row.account_code]
                        amount = row.debit if side == "debit" else row.credit
                        balance_sheet[item] += amount
        
        # Calculate totals
        balance_sheet["current_assets_total"] = (
            balance_sheet["cash_and_equivalents"] +
            balance_sheet["receivables"] +
            balance_sheet["inventory"] +
            balance_sheet["other_current_assets"]
        )
        
        balance_sheet["fixed_assets_total"] = (
            balance_sheet["tangible_assets"] +
            balance_sheet["intangible_assets"] +
            balance_sheet["financial_assets"]
        )
        
        balance_sheet["assets_total"] = (
            balance_sheet["current_assets_total"] +
            balance_sheet["fixed_assets_total"]
        )
        
        balance_sheet["current_liabilities_total"] = (
            balance_sheet["short_term_debt"] +
            balance_sheet["payables"] +
            balance_sheet["other_current_liabilities"]
        )
        
        balance_sheet["long_term_liabilities_total"] = (
            balance_sheet["long_term_debt"] +
            balance_sheet["other_long_term_liabilities"]
        )
        
        balance_sheet["equity_total"] = (
            balance_sheet["share_capital"] +
            balance_sheet["retained_earnings"] +
            balance_sheet["current_year_result"]
        )
        
        balance_sheet["liabilities_and_equity_total"] = (
            balance_sheet["current_liabilities_total"] +
            balance_sheet["long_term_liabilities_total"] +
            balance_sheet["equity_total"]
        )
        
        return balance_sheet
    
    def _calculate_cash_flow(self, income_stmt: Dict, balance_sheet: Dict) -> Dict:
        """Calculate cash flow statement (simplified)."""
        return {
            "operating_cash_flow": income_stmt.get("net_profit_loss", 0),
            "investing_cash_flow": 0,  # Placeholder
            "financing_cash_flow": 0,  # Placeholder
            "net_change_cash": 0,
            "beginning_cash": 0,
            "ending_cash": balance_sheet.get("cash_and_equivalents", 0),
        }
    
    def generate_k2_pdf(self, report: Dict) -> bytes:
        """Generate K2 annual report as PDF (future feature)."""
        # Placeholder for PDF generation
        # Would use reportlab or similar library
        raise NotImplementedError("PDF generation coming in next phase")
    
    def export_k2_json(self, report: Dict) -> Dict:
        """Export K2 report as JSON for submission."""
        return {
            "version": "1.0",
            "report_date": report["report_date"].isoformat(),
            "company": {
                "name": report["company_name"],
                "org_number": report["org_number"],
                "managing_director": report["managing_director"],
            },
            "financial_statements": {
                "income_statement": report["income_statement"],
                "balance_sheet": report["balance_sheet"],
                "cash_flow": report["cash_flow"],
            },
            "notes": {
                "average_employees": report.get("average_employees"),
                "significant_events": report.get("significant_events"),
            }
        }
