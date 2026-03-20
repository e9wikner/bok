"""Seed test data for demo/testing."""

import sys
from datetime import date
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.ledger import LedgerService
from repositories.account_repo import AccountRepository
from repositories.period_repo import PeriodRepository


def seed_test_company():
    """Create test company with sample data."""
    print("\n📊 Seeding test data for TestCorp AB...")
    
    ledger = LedgerService()
    
    # Create fiscal year 2026
    print("\n1️⃣  Creating fiscal year 2026...")
    fy = ledger.periods.create_fiscal_year(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31)
    )
    print(f"   ✓ Fiscal year created: {fy.id}")
    
    # Create monthly periods (Jan-Mar for demo)
    print("\n2️⃣  Creating periods...")
    from calendar import monthrange
    periods = {}
    for month in range(1, 4):  # Jan, Feb, Mar
        _, last_day = monthrange(2026, month)
        period = ledger.periods.create_period(
            fiscal_year_id=fy.id,
            year=2026,
            month=month,
            start_date=date(2026, month, 1),
            end_date=date(2026, month, last_day)
        )
        periods[month] = period
        print(f"   ✓ {period.start_date} → {period.end_date}")
    
    # Get March period for transactions
    march_period = periods[3]
    
    # Create sample transactions
    print("\n3️⃣  Creating sample vouchers...")
    
    # Transaction 1: Invoice to customer (consulting services)
    print("\n   📄 Transaction 1: Invoice for consulting services")
    v1 = ledger.create_voucher(
        series="A",
        date=date(2026, 3, 5),
        period_id=march_period.id,
        description="Invoice #001 - Consulting services for Acme Corp",
        rows_data=[
            {
                "account": "1510",  # Kundfordringar
                "debit": 15000000,   # 150,000 kr
                "credit": 0,
                "description": "Customer invoice"
            },
            {
                "account": "3011",   # Försäljning tjänster 25%
                "debit": 0,
                "credit": 12000000,  # 120,000 kr
                "description": "Revenue"
            },
            {
                "account": "2610",   # Utgående moms 25%
                "debit": 0,
                "credit": 3000000,   # 30,000 kr
                "description": "VAT 25%"
            },
        ],
        created_by="test-seed"
    )
    ledger.post_voucher(v1.id, actor="test-seed")
    print(f"      ✓ Voucher A000001 posted (150,000 kr)")
    
    # Transaction 2: Rent expense
    print("\n   📄 Transaction 2: Office rent payment")
    v2 = ledger.create_voucher(
        series="A",
        date=date(2026, 3, 1),
        period_id=march_period.id,
        description="Office rent - March 2026",
        rows_data=[
            {
                "account": "4020",   # Hyra kontorslokal
                "debit": 50000,      # 500 kr
                "credit": 0,
                "description": "Rent expense"
            },
            {
                "account": "1010",   # PlusGiro
                "debit": 0,
                "credit": 50000,
                "description": "Bank transfer"
            },
        ],
        created_by="test-seed"
    )
    ledger.post_voucher(v2.id, actor="test-seed")
    print(f"      ✓ Voucher A000002 posted (500 kr)")
    
    # Transaction 3: Another invoice
    print("\n   📄 Transaction 3: Another consulting invoice")
    v3 = ledger.create_voucher(
        series="A",
        date=date(2026, 3, 15),
        period_id=march_period.id,
        description="Invoice #002 - Consulting services for TechCorp",
        rows_data=[
            {
                "account": "1510",
                "debit": 20000000,   # 200,000 kr
                "credit": 0,
                "description": "Invoice TechCorp"
            },
            {
                "account": "3011",
                "debit": 0,
                "credit": 16000000,  # 160,000 kr
                "description": "Revenue"
            },
            {
                "account": "2610",
                "debit": 0,
                "credit": 4000000,   # 40,000 kr
                "description": "VAT 25%"
            },
        ],
        created_by="test-seed"
    )
    ledger.post_voucher(v3.id, actor="test-seed")
    print(f"      ✓ Voucher A000003 posted (200,000 kr)")
    
    # Transaction 4: Expense reimbursement
    print("\n   📄 Transaction 4: Travel expenses")
    v4 = ledger.create_voucher(
        series="A",
        date=date(2026, 3, 20),
        period_id=march_period.id,
        description="Travel expenses - Stockholm to Gothenburg",
        rows_data=[
            {
                "account": "4040",   # Resor
                "debit": 300000,     # 3,000 kr
                "credit": 0,
                "description": "Train + hotel"
            },
            {
                "account": "1010",
                "debit": 0,
                "credit": 300000,
                "description": "Reimbursed from bank"
            },
        ],
        created_by="test-seed"
    )
    ledger.post_voucher(v4.id, actor="test-seed")
    print(f"      ✓ Voucher A000004 posted (3,000 kr)")
    
    # Get trial balance
    print("\n4️⃣  Calculating trial balance...")
    balances = ledger.get_trial_balance(march_period.id)
    
    print(f"\n   Trial Balance as of 2026-03-31:")
    total_debit = 0
    total_credit = 0
    for account_code in sorted(balances.keys()):
        balance = balances[account_code]
        debit = balance["debit"] / 100  # Convert from öre
        credit = balance["credit"] / 100
        total_debit += debit
        total_credit += credit
        account = AccountRepository.get(account_code)
        print(f"      {account_code} {account.name:30} | Debit: {debit:>12,.2f} | Credit: {credit:>12,.2f}")
    
    print(f"\n      {'':40} | Total:  {total_debit:>12,.2f} | {total_credit:>12,.2f}")
    
    # Lock period
    print("\n5️⃣  Locking period...")
    ledger.lock_period(march_period.id, actor="test-seed")
    print(f"   ✓ Period March 2026 locked (immutable)")
    
    print("\n✅ Test data seeded successfully!")
    print(f"\n📊 Summary:")
    print(f"   • Fiscal Year: 2026-01-01 to 2026-12-31")
    print(f"   • Test Company: TestCorp AB")
    print(f"   • Periods Created: 3 (Jan, Feb, Mar)")
    print(f"   • Vouchers Posted: 4")
    print(f"   • Total Debits: {total_debit:,.2f} kr")
    print(f"   • Total Credits: {total_credit:,.2f} kr")
    print(f"   • Status: March period locked ✓")


if __name__ == "__main__":
    seed_test_company()
