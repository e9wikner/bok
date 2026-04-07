"""Reports endpoints (income statement, balance sheet, trial balance)"""

from fastapi import APIRouter, Query
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
    vouchers, _ = VoucherRepository.list_all(status="posted")

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


# New balance sheet function with 3 columns
# This will be inserted into api/routes/reports.py


@router.get("/balance-sheet")
async def get_balance_sheet(
    year: Optional[int] = Query(None),
    as_of_date: Optional[str] = Query(None),
):
    """Get balance sheet (balansräkning) with 3 columns: IB, Förändring, UB.

    Assets (tillgångar) = debit - credit on accounts 1000-1999
    Liabilities (skulder) = credit - debit on accounts 2000-2999
    Equity (eget kapital) = subset of 2000-2999

    Returns data in 3 columns:
    - opening_balance (IB): Balance at start of year
    - change: Sum of year's transactions
    - closing_balance (UB): IB + change

    All amounts in ören.
    """
    vouchers, _ = VoucherRepository.list_all(status="posted")
    target_year = year
    if as_of_date and not year:
        target_year = date_type.fromisoformat(as_of_date).year

    # Separate IB vouchers from regular vouchers for the target year
    ib_vouchers = []
    regular_vouchers = []
    prior_vouchers = []

    for voucher in vouchers:
        voucher_date = _parse_voucher_date(voucher)
        if voucher_date.year == target_year:
            if voucher.series.value == "IB":
                ib_vouchers.append(voucher)
            else:
                regular_vouchers.append(voucher)
        elif voucher_date.year < target_year:
            prior_vouchers.append(voucher)

    all_accounts = AccountRepository.get_all_as_dict()

    # Calculate opening balances from IB vouchers, or from prior year totals
    opening_balances = {}
    source_vouchers = ib_vouchers if ib_vouchers else prior_vouchers

    for voucher in source_vouchers:
        for row in voucher.rows:
            code = row.account_code
            if code not in opening_balances:
                opening_balances[code] = {"debit": 0, "credit": 0}
            opening_balances[code]["debit"] += row.debit or 0
            opening_balances[code]["credit"] += row.credit or 0

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
    asset_ranges = [
        (1000, 1199),
        (1200, 1299),
        (1300, 1399),
        (1400, 1599),
        (1600, 1899),
        (1900, 1999),
    ]
    liability_ranges = [(2000, 2299), (2300, 2499), (2500, 2999)]

    # Calculate totals
    opening_assets = _calc_category(opening_balances, asset_ranges, False)
    opening_liabilities = _calc_category(opening_balances, liability_ranges, True)
    change_assets = _calc_category(change_balances, asset_ranges, False)
    change_liabilities = _calc_category(change_balances, liability_ranges, True)
    closing_assets = opening_assets + change_assets
    closing_liabilities = opening_liabilities + change_liabilities

    # Build account details with 3 columns
    all_codes = set(opening_balances.keys()) | set(change_balances.keys())

    def _build_details(codes, ranges, is_liability=False):
        """Build account details with opening, change, and closing balances."""
        details = []
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
                details.append(
                    {
                        "code": code,
                        "name": acct.name if acct else code,
                        "opening_balance": opening,
                        "change": change,
                        "closing_balance": closing,
                    }
                )
        return details

    # Calculate sub-categories for assets
    opening_current_assets = _calc_category(
        opening_balances, [(1000, 1199), (1300, 1399), (1600, 1899)], False
    )
    opening_receivables = _calc_category(opening_balances, [(1400, 1599)], False)
    opening_fixed_assets = _calc_category(opening_balances, [(1200, 1299)], False)
    opening_bank = _calc_category(opening_balances, [(1900, 1999)], False)

    change_current_assets = _calc_category(
        change_balances, [(1000, 1199), (1300, 1399), (1600, 1899)], False
    )
    change_receivables = _calc_category(change_balances, [(1400, 1599)], False)
    change_fixed_assets = _calc_category(change_balances, [(1200, 1299)], False)
    change_bank = _calc_category(change_balances, [(1900, 1999)], False)

    # Calculate sub-categories for liabilities/equity
    opening_equity = _calc_category(opening_balances, [(2000, 2299)], True)
    opening_long_term = _calc_category(opening_balances, [(2300, 2499)], True)
    opening_current_liab = _calc_category(opening_balances, [(2500, 2999)], True)

    change_equity = _calc_category(change_balances, [(2000, 2299)], True)
    change_long_term = _calc_category(change_balances, [(2300, 2499)], True)
    change_current_liab = _calc_category(change_balances, [(2500, 2999)], True)

    return {
        # Summary totals with 3 columns
        "opening_assets": opening_assets,
        "opening_equity_liabilities": opening_liabilities,
        "change_assets": change_assets,
        "change_equity_liabilities": change_liabilities,
        "closing_assets": closing_assets,
        "closing_equity_liabilities": closing_liabilities,
        "balanced": abs(closing_assets - closing_liabilities) < 100,
        "period": as_of_date or str(year) if year else "all",
        "has_ib_vouchers": len(ib_vouchers) > 0,
        # Asset categories with 3 columns
        "opening_current_assets": opening_current_assets,
        "opening_receivables": opening_receivables,
        "opening_fixed_assets": opening_fixed_assets,
        "opening_bank_and_cash": opening_bank,
        "change_current_assets": change_current_assets,
        "change_receivables": change_receivables,
        "change_fixed_assets": change_fixed_assets,
        "change_bank_and_cash": change_bank,
        "closing_current_assets": opening_current_assets + change_current_assets,
        "closing_receivables": opening_receivables + change_receivables,
        "closing_fixed_assets": opening_fixed_assets + change_fixed_assets,
        "closing_bank_and_cash": opening_bank + change_bank,
        # Liability/equity categories with 3 columns
        "opening_equity": opening_equity,
        "opening_long_term_liabilities": opening_long_term,
        "opening_current_liabilities": opening_current_liab,
        "change_equity": change_equity,
        "change_long_term_liabilities": change_long_term,
        "change_current_liabilities": change_current_liab,
        "closing_equity": opening_equity + change_equity,
        "closing_long_term_liabilities": opening_long_term + change_long_term,
        "closing_current_liabilities": opening_current_liab + change_current_liab,
        # Per-account details with 3 columns
        "fixed_assets_details": _build_details(all_codes, [(1200, 1299)], False),
        "receivables_details": _build_details(all_codes, [(1400, 1599)], False),
        "bank_and_cash_details": _build_details(all_codes, [(1900, 1999)], False),
        "current_assets_details": _build_details(
            all_codes, [(1000, 1199), (1300, 1399), (1600, 1899)], False
        ),
        "equity_details": _build_details(all_codes, [(2000, 2299)], True),
        "long_term_liabilities_details": _build_details(
            all_codes, [(2300, 2499)], True
        ),
        "current_liabilities_details": _build_details(all_codes, [(2500, 2999)], True),
        # Backward compatibility
        "total_assets": closing_assets,
        "total_equity_liabilities": closing_liabilities,
        "current_assets": opening_current_assets + change_current_assets,
        "fixed_assets": opening_fixed_assets + change_fixed_assets,
        "receivables": opening_receivables + change_receivables,
        "bank_and_cash": opening_bank + change_bank,
        "equity": opening_equity + change_equity,
        "long_term_liabilities": opening_long_term + change_long_term,
        "current_liabilities": opening_current_liab + change_current_liab,
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
    vouchers, _ = VoucherRepository.list_all(status="posted")
    
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
    vouchers, _ = VoucherRepository.list_all(status="posted")

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
