"""Reports endpoints (income statement, balance sheet, trial balance)"""

from fastapi import APIRouter, Depends, Query
from typing import Optional
from datetime import datetime, date as date_type

from repositories.voucher_repo import VoucherRepository
from repositories.account_repo import AccountRepository

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


def _parse_voucher_date(v) -> date_type:
    """Safely extract a date object from a voucher's date field."""
    d = v.date
    if isinstance(d, str):
        return date_type.fromisoformat(d)
    if isinstance(d, datetime):
        return d.date()
    return d  # already a date


def _ören_to_kr(amount: int) -> float:
    """Convert ören to kronor."""
    return round(amount / 100, 2)


@router.get("/income-statement")
async def get_income_statement(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
):
    """Get income statement (resultaträkning) for a specific period.
    
    Revenue (intäkter) = credit - debit on accounts 3000-3999
    Costs (kostnader) = debit - credit on accounts 4000-7999
    Profit = revenue - costs
    
    All amounts returned in ören (divide by 100 for kronor).
    """
    vouchers = VoucherRepository.list_all(status="posted")

    # Filter by year/month
    if year:
        vouchers = [v for v in vouchers if _parse_voucher_date(v).year == year]
        if month:
            vouchers = [v for v in vouchers if _parse_voucher_date(v).month == month]
    
    revenue = 0      # Intäkter (3000-3999) - normally credited
    costs = 0        # Kostnader (4000-7999) - normally debited
    financial = 0    # Finansiella poster (8000-8999)
    
    revenue_details = {}  # Per-account breakdown
    cost_details = {}
    financial_details = {}
    
    for voucher in vouchers:
        for row in voucher.rows:
            account = int(row.account_code) if row.account_code.isdigit() else 0
            debit = row.debit or 0
            credit = row.credit or 0
            
            if 3000 <= account <= 3999:
                # Revenue: credit increases, debit decreases
                amount = credit - debit
                revenue += amount
                key = row.account_code
                revenue_details[key] = revenue_details.get(key, 0) + amount
                
            elif 4000 <= account <= 7999:
                # Costs: debit increases, credit decreases
                amount = debit - credit
                costs += amount
                key = row.account_code
                cost_details[key] = cost_details.get(key, 0) + amount
                
            elif 8000 <= account <= 8999:
                # Financial items
                amount = debit - credit  # expenses positive, income negative
                financial += amount
                key = row.account_code
                financial_details[key] = financial_details.get(key, 0) + amount
    
    # Look up account names
    all_accounts = AccountRepository.get_all_as_dict()
    
    def _format_details(details):
        return [
            {
                "code": code,
                "name": all_accounts[code].name if code in all_accounts else code,
                "amount": amount,
            }
            for code, amount in sorted(details.items())
            if amount != 0
        ]
    
    operating_profit = revenue - costs
    profit_before_tax = operating_profit - financial
    
    return {
        "revenue": revenue,
        "costs": costs,
        "financial": financial,
        "operating_profit": operating_profit,
        "profit": profit_before_tax,
        "revenue_details": _format_details(revenue_details),
        "cost_details": _format_details(cost_details),
        "financial_details": _format_details(financial_details),
        "period": f"{year}-{month:02d}" if year and month else str(year) if year else "all",
        "voucher_count": len(vouchers),
    }


@router.get("/balance-sheet")
async def get_balance_sheet(
    year: Optional[int] = Query(None),
    as_of_date: Optional[str] = Query(None),
):
    """Get balance sheet (balansräkning).
    
    Assets (tillgångar) = debit - credit on accounts 1000-1999
    Liabilities (skulder) = credit - debit on accounts 2000-2999
    Equity (eget kapital) = subset of 2000-2999
    
    All amounts in ören.
    """
    vouchers = VoucherRepository.list_all(status="posted")

    # Filter by date
    if as_of_date:
        cutoff = date_type.fromisoformat(as_of_date)
        vouchers = [v for v in vouchers if _parse_voucher_date(v) <= cutoff]
    elif year:
        # Include all vouchers up to end of year
        cutoff = date_type(year, 12, 31)
        vouchers = [v for v in vouchers if _parse_voucher_date(v) <= cutoff]
    
    # Asset categories
    current_assets = 0    # 1000-1399 (Omsättningstillgångar exkl kundfordringar)
    receivables = 0       # 1400-1599 (Kundfordringar)
    fixed_assets = 0      # 1200-1299 (Anläggningstillgångar - inventarier)
    bank_and_cash = 0     # 1900-1999 (Kassa och bank)
    
    # Liability categories
    equity = 0            # 2000-2099 (Eget kapital)
    long_term_debt = 0    # 2300-2499 (Långfristiga skulder)
    short_term_debt = 0   # 2600-2999 (Kortfristiga skulder inkl moms, skatt)
    
    all_accounts = AccountRepository.get_all_as_dict()
    account_balances = {}
    
    for voucher in vouchers:
        for row in voucher.rows:
            account = int(row.account_code) if row.account_code.isdigit() else 0
            debit = row.debit or 0
            credit = row.credit or 0
            
            # Track all balances
            if row.account_code not in account_balances:
                acct = all_accounts.get(row.account_code)
                account_balances[row.account_code] = {
                    "name": acct.name if acct else row.account_code,
                    "debit": 0, "credit": 0,
                }
            account_balances[row.account_code]["debit"] += debit
            account_balances[row.account_code]["credit"] += credit
            
            # Assets (1xxx): debit increases, credit decreases
            if 1000 <= account <= 1199:
                current_assets += (debit - credit)
            elif 1200 <= account <= 1299:
                fixed_assets += (debit - credit)
            elif 1400 <= account <= 1599:
                receivables += (debit - credit)
            elif 1900 <= account <= 1999:
                bank_and_cash += (debit - credit)
            elif 1300 <= account <= 1399:
                current_assets += (debit - credit)
            elif 1600 <= account <= 1899:
                current_assets += (debit - credit)
                
            # Equity & Liabilities (2xxx): credit increases, debit decreases
            elif 2000 <= account <= 2099:
                equity += (credit - debit)
            elif 2300 <= account <= 2499:
                long_term_debt += (credit - debit)
            elif 2100 <= account <= 2299:
                equity += (credit - debit)  # Retained earnings etc
            elif 2500 <= account <= 2999:
                short_term_debt += (credit - debit)
    
    total_assets = current_assets + fixed_assets + receivables + bank_and_cash
    total_equity_liabilities = equity + long_term_debt + short_term_debt
    
    return {
        "current_assets": current_assets,
        "fixed_assets": fixed_assets,
        "receivables": receivables,
        "bank_and_cash": bank_and_cash,
        "total_assets": total_assets,
        "equity": equity,
        "long_term_liabilities": long_term_debt,
        "current_liabilities": short_term_debt,
        "total_equity_liabilities": total_equity_liabilities,
        "balanced": abs(total_assets - total_equity_liabilities) < 100,  # Within 1 kr
        "period": as_of_date or str(year) if year else "all",
        "voucher_count": len(vouchers),
    }


@router.get("/general-ledger/{account_code}")
async def get_general_ledger(
    account_code: str,
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
):
    """Get general ledger (huvudbok) for a specific account.
    
    Returns all transactions for the account with running balance.
    """
    vouchers = VoucherRepository.list_all(status="posted")
    
    if year:
        vouchers = [v for v in vouchers if _parse_voucher_date(v).year == year]
        if month:
            vouchers = [v for v in vouchers if _parse_voucher_date(v).month == month]
    
    # Sort by date
    vouchers.sort(key=lambda v: _parse_voucher_date(v))
    
    # Look up account info
    all_accounts = AccountRepository.get_all_as_dict()
    account = all_accounts.get(account_code)
    account_name = account.name if account else account_code
    
    # Collect transactions for this account
    transactions = []
    running_balance = 0
    
    for voucher in vouchers:
        for row in voucher.rows:
            if row.account_code == account_code:
                debit = row.debit or 0
                credit = row.credit or 0
                running_balance += (debit - credit)
                
                transactions.append({
                    "date": _parse_voucher_date(voucher).isoformat(),
                    "voucher_id": voucher.id,
                    "voucher_number": f"{voucher.series.value}{voucher.number}",
                    "description": row.description or voucher.description,
                    "debit": debit,
                    "credit": credit,
                    "balance": running_balance,
                })
    
    total_debit = sum(t["debit"] for t in transactions)
    total_credit = sum(t["credit"] for t in transactions)
    
    return {
        "account_code": account_code,
        "account_name": account_name,
        "transactions": transactions,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "closing_balance": running_balance,
        "transaction_count": len(transactions),
        "period": f"{year}-{month:02d}" if year and month else str(year) if year else "all",
    }


@router.get("/trial-balance")
async def get_trial_balance(
    year: Optional[int] = Query(None),
    period: Optional[int] = Query(None),
):
    """Get trial balance (råbalans) showing debit/credit for all accounts."""
    vouchers = VoucherRepository.list_all(status="posted")

    if year:
        vouchers = [v for v in vouchers if _parse_voucher_date(v).year == year]
        if period:
            vouchers = [v for v in vouchers if _parse_voucher_date(v).month == period]
    
    all_accounts = AccountRepository.get_all_as_dict()
    accounts = {}

    for voucher in vouchers:
        for row in voucher.rows:
            if row.account_code not in accounts:
                acct = all_accounts.get(row.account_code)
                accounts[row.account_code] = {
                    "debit": 0, "credit": 0,
                    "name": acct.name if acct else "",
                }
            accounts[row.account_code]["debit"] += row.debit or 0
            accounts[row.account_code]["credit"] += row.credit or 0
    
    total_debit = sum(a["debit"] for a in accounts.values())
    total_credit = sum(a["credit"] for a in accounts.values())
    
    accounts_list = [
        {
            "code": code,
            "name": data["name"],
            "debit": data["debit"],
            "credit": data["credit"],
            "balance": data["debit"] - data["credit"],
        }
        for code, data in sorted(accounts.items())
    ]
    
    return {
        "accounts": accounts_list,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "balanced": abs(total_debit - total_credit) < 1,
        "period": f"{year}-{period:02d}" if year and period else str(year) if year else "all",
        "voucher_count": len(vouchers),
    }
