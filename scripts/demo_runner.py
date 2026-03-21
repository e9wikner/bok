"""
Demo data generator that uses the API to populate the bookkeeping system.

This container runs once to create realistic accounting data for demonstration.
"""

import os
import sys
import time
import random
from datetime import date, datetime, timedelta
from typing import Optional
import requests

# Configuration
API_URL = os.getenv("API_URL", "http://bokfoering-api:8000")
API_KEY = os.getenv("API_KEY", "dev-key-change-in-production")
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}


def wait_for_api(timeout: int = 60) -> bool:
    """Wait for API to be ready."""
    print("⏳ Waiting for API to be ready...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"{API_URL}/health", timeout=2)
            if resp.status_code == 200:
                print("✅ API is ready!")
                return True
        except:
            pass
        time.sleep(2)
        print("  ...still waiting")
    print("❌ API timeout")
    return False


def find_existing_fiscal_year() -> Optional[str]:
    """Try to find existing fiscal year by checking common IDs."""
    for fy_id in ["fy-2026", "fy2026", "1", "2026"]:
        resp = requests.get(f"{API_URL}/api/v1/fiscal-years/{fy_id}", headers=HEADERS)
        if resp.status_code == 200:
            return fy_id
    return None


def get_or_create_fiscal_year() -> str:
    """Get or create fiscal year 2026."""
    # Try to find existing fiscal year first
    existing_fy = find_existing_fiscal_year()
    if existing_fy:
        # Check if periods exist for this fiscal year
        resp = requests.get(
            f"{API_URL}/api/v1/periods",
            headers=HEADERS,
            params={"fiscal_year_id": existing_fy}
        )
        if resp.status_code == 200:
            periods = resp.json().get("periods", [])
            if periods:
                print(f"✅ Found {len(periods)} existing periods")
                return existing_fy
            else:
                print(f"ℹ️ Fiscal year exists but no periods found")
                return existing_fy
    
    # Try to create fiscal year via API
    print("📅 Creating fiscal year 2026...")
    resp = requests.post(
        f"{API_URL}/api/v1/fiscal-years",
        headers=HEADERS,
        params={
            "start_date": "2026-01-01",
            "end_date": "2026-12-31"
        }
    )
    if resp.status_code == 201:
        data = resp.json()
        print(f"  ✓ Created fiscal year: {data.get('id', 'unknown')}")
        return data.get("id", "fy-2026")
    elif resp.status_code == 500 and "UNIQUE constraint failed" in resp.text:
        # Already exists, find it
        existing_fy = find_existing_fiscal_year()
        if existing_fy:
            print(f"  ✓ Found existing fiscal year: {existing_fy}")
            return existing_fy
        print("  ⚠️ Could not find existing fiscal year, assuming fy-2026")
        return "fy-2026"
    else:
        print(f"  ⚠ Failed to create fiscal year: {resp.status_code} - {resp.text}")
        return ""


def get_period_id(fiscal_year_id: str, month: int) -> Optional[str]:
    """Get period ID for a specific month."""
    resp = requests.get(
        f"{API_URL}/api/v1/periods",
        headers=HEADERS,
        params={"fiscal_year_id": fiscal_year_id}
    )
    if resp.status_code == 200:
        for period in resp.json().get("periods", []):
            if period.get("year") == 2026 and period.get("month") == month:
                return period.get("id")
    return None


def create_voucher(description: str, voucher_date: date, period_id: str, rows: list, series: str = "A"):
    """Create a voucher via API."""
    data = {
        "series": series,
        "date": voucher_date.isoformat(),
        "period_id": period_id,
        "description": description,
        "rows": rows,
        "auto_post": True
    }
    
    resp = requests.post(
        f"{API_URL}/api/v1/vouchers",
        headers=HEADERS,
        json=data
    )
    
    if resp.status_code == 201:
        voucher = resp.json()
        total = sum(r.get("debit", 0) for r in rows)
        print(f"  ✓ {voucher['series']}{voucher['number']}: {description} ({total/100:,.0f} kr)")
        return voucher
    else:
        print(f"  ❌ Failed: {description} - {resp.text}")
        return None


def generate_demo_vouchers():
    """Generate 20 realistic vouchers for a small consulting company."""
    
    print("\n" + "="*60)
    print("🎯 GENERATING DEMO VOUCHERS")
    print("="*60)
    
    # First ensure fiscal year exists
    print("\n📅 Checking fiscal year...")
    fy_id = get_or_create_fiscal_year()
    
    if not fy_id:
        print("❌ Could not get or create fiscal year. Aborting.")
        return 0
    
    # Get period IDs
    periods = {}
    for month in range(1, 13):
        periods[month] = get_period_id(fy_id, month)
    
    if not any(periods.values()):
        print(f"❌ No periods found for fiscal year {fy_id}. Cannot create vouchers.")
        return 0
    
    vouchers_created = 0
    
    # === JANUARY - Company Setup ===
    print("\n📅 JANUARY - Company Setup")
    
    # 1. Owner's capital contribution
    if periods[1]:
        create_voucher(
            "Aktieägartillskott - Startkapital",
            date(2026, 1, 15),
            periods[1],
            [
                {"account": "1930", "debit": 20000000, "credit": 0, "description": "Insättning företagskonto"},
                {"account": "2081", "debit": 0, "credit": 20000000, "description": "Aktieägartillskott"},
            ]
        )
        vouchers_created += 1
    
    # 2. Office equipment purchase
    if periods[1]:
        create_voucher(
            "Inköp dator och kontorsutrustning",
            date(2026, 1, 20),
            periods[1],
            [
                {"account": "5410", "debit": 2500000, "credit": 0, "description": "Dator och skärmar"},
                {"account": "2640", "debit": 625000, "credit": 0, "description": "Ingående moms 25%"},
                {"account": "2440", "debit": 0, "credit": 3125000, "description": "Leverantörsskuld - Elgiganten"},
            ]
        )
        vouchers_created += 1
    
    # === FEBRUARY - Operations Begin ===
    print("\n📅 FEBRUARY - Operations")
    
    # 3. Office rent
    if periods[2]:
        create_voucher(
            "Hyra kontor februari",
            date(2026, 2, 1),
            periods[2],
            [
                {"account": "5010", "debit": 1200000, "credit": 0, "description": "Lokalhyra"},
                {"account": "2640", "debit": 300000, "credit": 0, "description": "Ingående moms 25%"},
                {"account": "1930", "debit": 0, "credit": 1500000, "description": "Bankutbetalning"},
            ]
        )
        vouchers_created += 1
    
    # 4. First consulting sale
    if periods[2]:
        create_voucher(
            "Försäljning konsulttjänster - TechStart AB",
            date(2026, 2, 15),
            periods[2],
            [
                {"account": "1510", "debit": 12500000, "credit": 0, "description": "Kundfordran - TechStart AB"},
                {"account": "3041", "debit": 0, "credit": 10000000, "description": "Försäljning tjänster 25%"},
                {"account": "2610", "debit": 0, "credit": 2500000, "description": "Utgående moms 25%"},
            ]
        )
        vouchers_created += 1
    
    # 5. Phone and internet
    if periods[2]:
        create_voucher(
            "Telefon och internet",
            date(2026, 2, 25),
            periods[2],
            [
                {"account": "6210", "debit": 60000, "credit": 0, "description": "Telefon"},
                {"account": "2640", "debit": 15000, "credit": 0, "description": "Ingående moms"},
                {"account": "1930", "debit": 0, "credit": 75000, "description": "Bankutbetalning"},
            ]
        )
        vouchers_created += 1
    
    # === MARCH - More Sales ===
    print("\n📅 MARCH - Sales & Expenses")
    
    # 6. Another consulting project
    if periods[3]:
        create_voucher(
            "Försäljning - Webbapplikation Nordic Cloud",
            date(2026, 3, 10),
            periods[3],
            [
                {"account": "1510", "debit": 18750000, "credit": 0, "description": "Kundfordran - Nordic Cloud"},
                {"account": "3041", "debit": 0, "credit": 15000000, "description": "Försäljning tjänster 25%"},
                {"account": "2610", "debit": 0, "credit": 3750000, "description": "Utgående moms 25%"},
            ]
        )
        vouchers_created += 1
    
    # 7. Received payment from TechStart
    if periods[3]:
        create_voucher(
            "Inbetalning från TechStart AB",
            date(2026, 3, 20),
            periods[3],
            [
                {"account": "1930", "debit": 12500000, "credit": 0, "description": "Inbetalning kund"},
                {"account": "1510", "debit": 0, "credit": 12500000, "description": "Kundfordran TechStart"},
            ]
        )
        vouchers_created += 1
    
    # 8. Accounting software subscription
    if periods[3]:
        create_voucher(
            "Programvaror - Bokföringssystem",
            date(2026, 3, 25),
            periods[3],
            [
                {"account": "6540", "debit": 50000, "credit": 0, "description": "Programvaror"},
                {"account": "2640", "debit": 12500, "credit": 0, "description": "Ingående moms"},
                {"account": "1930", "debit": 0, "credit": 62500, "description": "Bankutbetalning"},
            ]
        )
        vouchers_created += 1
    
    # === APRIL - Salary & More Sales ===
    print("\n📅 APRIL - Salary & Growth")
    
    # 9. Salary payment
    if periods[4]:
        create_voucher(
            "Lön april - Stefan Wikner",
            date(2026, 4, 25),
            periods[4],
            [
                {"account": "7010", "debit": 5000000, "credit": 0, "description": "Lön tjänstemän"},
                {"account": "2710", "debit": 0, "credit": 1500000, "description": "Avräkning skatter"},
                {"account": "2730", "debit": 0, "credit": 1400000, "description": "Arbetsgivaravgifter"},
                {"account": "1930", "debit": 0, "credit": 2100000, "description": "Nettolön utbetald"},
            ]
        )
        vouchers_created += 1
    
    # 10. Sale with 12% VAT (food-related service)
    if periods[4]:
        create_voucher(
            "Försäljning - Matkassar system (12% moms)",
            date(2026, 4, 12),
            periods[4],
            [
                {"account": "1510", "debit": 1120000, "credit": 0, "description": "Kundfordran - FoodTech AB"},
                {"account": "3042", "debit": 0, "credit": 1000000, "description": "Försäljning tjänster 12%"},
                {"account": "2620", "debit": 0, "credit": 120000, "description": "Utgående moms 12%"},
            ]
        )
        vouchers_created += 1
    
    # 11. Marketing expenses
    if periods[4]:
        create_voucher(
            "Marknadsföring - Google Ads",
            date(2026, 4, 15),
            periods[4],
            [
                {"account": "5910", "debit": 400000, "credit": 0, "description": "Reklam och marknadsföring"},
                {"account": "2640", "debit": 100000, "credit": 0, "description": "Ingående moms 25%"},
                {"account": "1930", "debit": 0, "credit": 500000, "description": "Bankutbetalning"},
            ]
        )
        vouchers_created += 1
    
    # === MAY - Travel & Conferences ===
    print("\n📅 MAY - Travel & Professional Development")
    
    # 12. Conference travel
    if periods[5]:
        create_voucher(
            "Konferensresa - PyCon Stockholm",
            date(2026, 5, 10),
            periods[5],
            [
                {"account": "5800", "debit": 800000, "credit": 0, "description": "Resekostnader"},
                {"account": "6110", "debit": 400000, "credit": 0, "description": "Konferensavgift"},
                {"account": "2640", "debit": 300000, "credit": 0, "description": "Ingående moms"},
                {"account": "1930", "debit": 0, "credit": 1500000, "description": "Bankutbetalning"},
            ]
        )
        vouchers_created += 1
    
    # 13. Large consulting project
    if periods[5]:
        create_voucher(
            "Försäljning - Systemintegration Enterprise AB",
            date(2026, 5, 20),
            periods[5],
            [
                {"account": "1510", "debit": 37500000, "credit": 0, "description": "Kundfordran - Enterprise AB"},
                {"account": "3041", "debit": 0, "credit": 30000000, "description": "Försäljning tjänster 25%"},
                {"account": "2610", "debit": 0, "credit": 7500000, "description": "Utgående moms 25%"},
            ]
        )
        vouchers_created += 1
    
    # === JUNE - Mid-year VAT Reporting ===
    print("\n📅 JUNE - VAT Reporting")
    
    # 14. VAT payment to Skatteverket
    if periods[6]:
        create_voucher(
            "Momsinbetalning Q2 till Skatteverket",
            date(2026, 6, 12),
            periods[6],
            [
                {"account": "2650", "debit": 9230000, "credit": 0, "description": "Moms att betala"},
                {"account": "1930", "debit": 0, "credit": 9230000, "description": "Bankutbetalning Skatteverket"},
            ]
        )
        vouchers_created += 1
    
    # 15. Office supplies
    if periods[6]:
        create_voucher(
            "Kontorsmaterial",
            date(2026, 6, 18),
            periods[6],
            [
                {"account": "6180", "debit": 20000, "credit": 0, "description": "Kontorsmaterial"},
                {"account": "2640", "debit": 5000, "credit": 0, "description": "Ingående moms"},
                {"account": "1930", "debit": 0, "credit": 25000, "description": "Kontantutbetalning"},
            ]
        )
        vouchers_created += 1
    
    # === SEPTEMBER - More Activity ===
    print("\n📅 SEPTEMBER - Continued Operations")
    
    # 16. Insurance payment
    if periods[9]:
        create_voucher(
            "Försäkringar - Företagsförsäkring",
            date(2026, 9, 1),
            periods[9],
            [
                {"account": "6310", "debit": 600000, "credit": 0, "description": "Försäkringspremier"},
                {"account": "1930", "debit": 0, "credit": 600000, "description": "Bankutbetalning"},
            ]
        )
        vouchers_created += 1
    
    # 17. Rent again
    if periods[9]:
        create_voucher(
            "Hyra kontor september",
            date(2026, 9, 1),
            periods[9],
            [
                {"account": "5010", "debit": 1200000, "credit": 0, "description": "Lokalhyra"},
                {"account": "2640", "debit": 300000, "credit": 0, "description": "Ingående moms"},
                {"account": "1930", "debit": 0, "credit": 1500000, "description": "Bankutbetalning"},
            ]
        )
        vouchers_created += 1
    
    # 18. Payment received from Nordic Cloud
    if periods[9]:
        create_voucher(
            "Inbetalning från Nordic Cloud",
            date(2026, 9, 15),
            periods[9],
            [
                {"account": "1930", "debit": 18750000, "credit": 0, "description": "Inbetalning kund"},
                {"account": "1510", "debit": 0, "credit": 18750000, "description": "Kundfordran Nordic Cloud"},
            ]
        )
        vouchers_created += 1
    
    # === NOVEMBER - Year-end Preparations ===
    print("\n📅 NOVEMBER - Preparing for Year-end")
    
    # 19. Accountant fees
    if periods[11]:
        create_voucher(
            "Revisorskostnader - Årsbokslut",
            date(2026, 11, 15),
            periods[11],
            [
                {"account": "6991", "debit": 1500000, "credit": 0, "description": "Revisorskostnader"},
                {"account": "2640", "debit": 375000, "credit": 0, "description": "Ingående moms"},
                {"account": "1930", "debit": 0, "credit": 1875000, "description": "Bankutbetalning"},
            ]
        )
        vouchers_created += 1
    
    # 20. Final quarterly VAT
    if periods[11]:
        create_voucher(
            "Momsinbetalning Q4 till Skatteverket",
            date(2026, 11, 12),
            periods[11],
            [
                {"account": "2650", "debit": 4500000, "credit": 0, "description": "Moms att betala Q4"},
                {"account": "1930", "debit": 0, "credit": 4500000, "description": "Bankutbetalning Skatteverket"},
            ]
        )
        vouchers_created += 1
    
    # === DECEMBER - Year-end ===
    print("\n📅 DECEMBER - Year-end")
    
    # 21. Depreciation
    if periods[12]:
        create_voucher(
            "Årets avskrivningar - Inventarier",
            date(2026, 12, 31),
            periods[12],
            [
                {"account": "7830", "debit": 500000, "credit": 0, "description": "Avskrivningar inventarier"},
                {"account": "1220", "debit": 0, "credit": 500000, "description": "Ack avskrivningar"},
            ]
        )
        vouchers_created += 1
    
    # 22. Owner's withdrawal
    if periods[12]:
        create_voucher(
            "Eget uttag - Stefan Wikner",
            date(2026, 12, 28),
            periods[12],
            [
                {"account": "2013", "debit": 2000000, "credit": 0, "description": "Eget uttag"},
                {"account": "1930", "debit": 0, "credit": 2000000, "description": "Bankutbetalning"},
            ]
        )
        vouchers_created += 1
    
    # Summary
    print("\n" + "="*60)
    print("✅ DEMO DATA GENERATION COMPLETE")
    print("="*60)
    print(f"\n📊 Created {vouchers_created} vouchers")
    print(f"📅 Period: January - December 2026")
    print(f"\n💰 Key transactions:")
    print(f"   • Revenue: ~600,000 kr")
    print(f"   • Expenses: ~200,000 kr")
    print(f"   • VAT reported: ~180,000 kr")
    print("\n🌐 View in frontend: http://localhost:8501")
    print("="*60)
    
    return vouchers_created


def main():
    """Main entry point."""
    print("="*60)
    print("🚀 DEMO DATA GENERATOR")
    print("="*60)
    print(f"API URL: {API_URL}")
    
    # Wait for API
    if not wait_for_api():
        sys.exit(1)
    
    # Generate data
    count = generate_demo_vouchers()
    
    if count > 0:
        print("\n✨ Success! Refresh your browser to see the data.")
        sys.exit(0)
    else:
        print("\n⚠️ No vouchers created.")
        sys.exit(1)


if __name__ == "__main__":
    main()
