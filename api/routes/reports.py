"""Reports endpoints (income statement, balance sheet, trial balance)"""

from fastapi import APIRouter, Depends, Query
from typing import Optional
from datetime import datetime

from repositories.voucher_repo import VoucherRepository
from repositories.account_repo import AccountRepository

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


@router.get("/income-statement")
async def get_income_statement(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
):
    """Get income statement (resultaträkning) for a specific period"""
    vouchers = VoucherRepository.list_by_status("posted")
    
    # Filter by year/month if provided
    if year:
        vouchers = [v for v in vouchers if v.voucher_date.year == year]
        if month:
            vouchers = [v for v in vouchers if v.voucher_date.month == month]
    
    # Revenue accounts (3000-3999)
    revenue = 0
    # Cost accounts (4000-4999, 5000-5999, 6000-6999)
    costs = 0
    
    for voucher in vouchers:
        for row in voucher.rows:
            account = int(row.account_code) if row.account_code.isdigit() else 0
            amount = (row.debit or 0) - (row.credit or 0)
            
            if 3000 <= account <= 3999:
                revenue += amount
            elif 4000 <= account <= 6999:
                costs += amount
    
    profit = revenue - costs
    
    return {
        "revenue": revenue,
        "costs": costs,
        "profit": profit,
        "period": f"{year}-{month:02d}" if year and month else str(year) if year else "all",
    }


@router.get("/balance-sheet")
async def get_balance_sheet(
    year: Optional[int] = Query(None),
    as_of_date: Optional[str] = Query(None),
):
    """Get balance sheet (balansräkning)"""
    vouchers = VoucherRepository.list_by_status("posted")
    
    # Filter by date
    if as_of_date:
        cutoff = datetime.fromisoformat(as_of_date)
        vouchers = [v for v in vouchers if v.voucher_date <= cutoff]
    elif year:
        vouchers = [v for v in vouchers if v.voucher_date.year == year]
    
    # Assets (1000-1999)
    current_assets = 0  # 1000-1499
    fixed_assets = 0    # 1500-1999
    
    # Liabilities (2000-2999)
    current_liabilities = 0  # 2000-2499
    long_term_liabilities = 0  # 2500-2999
    
    # Equity (2700-2799)
    equity = 0
    
    for voucher in vouchers:
        for row in voucher.rows:
            account = int(row.account_code) if row.account_code.isdigit() else 0
            amount = (row.debit or 0) - (row.credit or 0)
            
            if 1000 <= account <= 1499:
                current_assets += amount
            elif 1500 <= account <= 1999:
                fixed_assets += amount
            elif 2000 <= account <= 2499:
                current_liabilities += amount
            elif 2500 <= account <= 2699:
                long_term_liabilities += amount
            elif 2700 <= account <= 2799:
                equity += amount
    
    total_assets = current_assets + fixed_assets
    total_liabilities = current_liabilities + long_term_liabilities + equity
    
    return {
        "current_assets": current_assets,
        "fixed_assets": fixed_assets,
        "total_assets": total_assets,
        "current_liabilities": current_liabilities,
        "long_term_liabilities": long_term_liabilities,
        "equity": equity,
        "total_liabilities": total_liabilities,
        "period": as_of_date or str(year) if year else "all",
    }


@router.get("/trial-balance")
async def get_trial_balance(
    year: Optional[int] = Query(None),
    period: Optional[int] = Query(None),
):
    """Get trial balance (råbalans) showing debit/credit for all accounts"""
    vouchers = VoucherRepository.list_by_status("posted")
    
    if year:
        vouchers = [v for v in vouchers if v.voucher_date.year == year]
        if period:
            vouchers = [v for v in vouchers if v.voucher_date.month == period]
    
    accounts = {}  # account_code -> {debit, credit}
    
    for voucher in vouchers:
        for row in voucher.rows:
            if row.account_code not in accounts:
                accounts[row.account_code] = {"debit": 0, "credit": 0, "name": row.account_name or ""}
            
            accounts[row.account_code]["debit"] += row.debit or 0
            accounts[row.account_code]["credit"] += row.credit or 0
    
    # Calculate totals
    total_debit = sum(a["debit"] for a in accounts.values())
    total_credit = sum(a["credit"] for a in accounts.values())
    
    # Format accounts list
    accounts_list = [
        {
            "code": code,
            "name": data["name"],
            "debit": data["debit"],
            "credit": data["credit"],
        }
        for code, data in sorted(accounts.items())
    ]
    
    return {
        "accounts": accounts_list,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "balanced": abs(total_debit - total_credit) < 1,  # Allow 1 öre rounding
        "period": f"{year}-{period:02d}" if year and period else str(year) if year else "all",
    }
