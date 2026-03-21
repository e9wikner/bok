"""Generate comprehensive demo data for presentations.

Usage:
    python scripts/generate_demo_data.py
"""

import sys
sys.path.insert(0, '.')

from datetime import date, datetime, timedelta
import random
from db.database import db
from repositories.account_repo import AccountRepository
from repositories.period_repo import PeriodRepository
from services.ledger import LedgerService
from services.invoice import InvoiceService
from domain.types import AccountType


def create_fiscal_year_2026():
    """Create fiscal year 2026 with periods."""
    # Check if exists
    existing = PeriodRepository.get_all_periods()
    if existing:
        print("✓ Fiscal year already exists")
        return existing[0].fiscal_year_id
    
    # Create fiscal year
    fy = PeriodRepository.create_fiscal_year(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31)
    )
    print(f"✓ Created fiscal year 2026: {fy.id}")
    
    # Create all 12 months
    for month in range(1, 13):
        start = date(2026, month, 1)
        # Calculate end of month
        if month == 12:
            end = date(2026, 12, 31)
        else:
            end = date(2026, month + 1, 1) - timedelta(days=1)
        
        PeriodRepository.create_period(
            fiscal_year_id=fy.id,
            year=2026,
            month=month,
            start_date=start,
            end_date=end
        )
    print(f"✓ Created 12 periods")
    
    return fy.id


def create_sample_vouchers(ledger: LedgerService, period_id: str):
    """Create realistic sample vouchers."""
    vouchers = []
    
    # January - Company setup
    v1 = ledger.create_voucher(
        series="A",
        date=date(2026, 1, 15),
        period_id=period_id,
        description="Aktieägartillskott - Startkapital",
        rows_data=[
            {"account_code": "1930", "debit": 10000000, "credit": 0, "description": "Insättning bankkonto"},
            {"account_code": "2081", "debit": 0, "credit": 10000000, "description": "Aktieägartillskott"},
        ],
        created_by="demo"
    )
    ledger.post_voucher(v1.id)
    vouchers.append(v1)
    print("  ✓ Voucher: Startkapital 100,000 kr")
    
    # February - Office rent
    v2 = ledger.create_voucher(
        series="A",
        date=date(2026, 2, 1),
        period_id=period_id,
        description="Hyra kontor februari",
        rows_data=[
            {"account_code": "5010", "debit": 850000, "credit": 0, "description": "Lokalhyra"},
            {"account_code": "2640", "debit": 212500, "credit": 0, "description": "Ingående moms 25%"},
            {"account_code": "2440", "debit": 0, "credit": 1062500, "description": "Leverantörsskuld"},
        ],
        created_by="demo"
    )
    ledger.post_voucher(v2.id)
    vouchers.append(v2)
    print("  ✓ Voucher: Hyra 10,625 kr")
    
    # March - Sales
    v3 = ledger.create_voucher(
        series="A",
        date=date(2026, 3, 15),
        period_id=period_id,
        description="Försäljning konsulttjänster",
        rows_data=[
            {"account_code": "1510", "debit": 12500000, "credit": 0, "description": "Kundfordran - TechStart AB"},
            {"account_code": "3041", "debit": 0, "credit": 10000000, "description": "Försäljning tjänster 25%"},
            {"account_code": "2610", "debit": 0, "credit": 2500000, "description": "Utgående moms 25%"},
        ],
        created_by="demo"
    )
    ledger.post_voucher(v3.id)
    vouchers.append(v3)
    print("  ✓ Voucher: Försäljning 125,000 kr")
    
    # April - Salary
    v4 = ledger.create_voucher(
        series="A",
        date=date(2026, 4, 25),
        period_id=period_id,
        description="Lön april",
        rows_data=[
            {"account_code": "7010", "debit": 4500000, "credit": 0, "description": "Lön tjänstemän"},
            {"account_code": "2710", "debit": 0, "credit": 1350000, "description": "Avräkning för skatter"},
            {"account_code": "2730", "debit": 0, "credit": 1200000, "description": "Avräkning för arbetsgivaravgifter"},
            {"account_code": "1930", "debit": 0, "credit": 1950000, "description": "Nettolön utbetald"},
        ],
        created_by="demo"
    )
    ledger.post_voucher(v4.id)
    vouchers.append(v4)
    print("  ✓ Voucher: Lön 45,000 kr brutto")
    
    return vouchers


def create_sample_invoices(invoice_service: InvoiceService):
    """Create sample invoices with various states."""
    invoices = []
    
    # Invoice 1: Draft
    inv1 = invoice_service.create_invoice(
        customer_name="TechStart AB",
        invoice_date=date(2026, 3, 1),
        due_date=date(2026, 3, 31),
        rows_data=[
            {"description": "Konsultation systemarkitektur", "quantity": 40, "unit_price": 150000, "vat_code": "MP1"},
            {"description": "Utveckling webbapplikation", "quantity": 80, "unit_price": 125000, "vat_code": "MP1"},
        ],
        customer_email="faktura@techstart.se",
        customer_address="Storgatan 1, 111 22 Stockholm",
        customer_org_number="559123-4567"
    )
    invoices.append((inv1, "draft"))
    print("  ✓ Invoice: Draft - TechStart AB (87,500 kr)")
    
    # Invoice 2: Sent
    inv2 = invoice_service.create_invoice(
        customer_name="DataFlow Solutions",
        invoice_date=date(2026, 2, 15),
        due_date=date(2026, 3, 15),
        rows_data=[
            {"description": "IT-support månadsabonnemang", "quantity": 1, "unit_price": 2500000, "vat_code": "MP1"},
        ],
        customer_email="billing@dataflow.io",
        customer_address="Kungsgatan 42, 411 15 Göteborg",
        customer_org_number="556789-0123"
    )
    invoice_service.send_invoice(inv2.id)
    invoices.append((inv2, "sent"))
    print("  ✓ Invoice: Sent - DataFlow (25,000 kr)")
    
    # Invoice 3: Partially paid
    inv3 = invoice_service.create_invoice(
        customer_name="Nordic Cloud AB",
        invoice_date=date(2026, 1, 20),
        due_date=date(2026, 2, 20),
        rows_data=[
            {"description": "Serverhosting Q1", "quantity": 3, "unit_price": 500000, "vat_code": "MP1"},
            {"description": "Backup-tjänst", "quantity": 3, "unit_price": 200000, "vat_code": "MP1"},
        ],
        customer_email="economy@nordiccloud.se",
        customer_address="Malmövägen 10, 211 20 Malmö",
        customer_org_number="559456-7890"
    )
    invoice_service.send_invoice(inv3.id)
    invoice_service.register_payment(inv3.id, 1312500, date(2026, 2, 15), "bank_transfer")
    invoices.append((inv3, "partially_paid"))
    print("  ✓ Invoice: Partially paid - Nordic Cloud (26,250 kr, betalat 13,125 kr)")
    
    # Invoice 4: Paid
    inv4 = invoice_service.create_invoice(
        customer_name="Smart Systems",
        invoice_date=date(2026, 1, 10),
        due_date=date(2026, 2, 10),
        rows_data=[
            {"description": "Projekt 'Digitalisering'", "quantity": 120, "unit_price": 95000, "vat_code": "MP1"},
        ],
        customer_email="finance@smartsystems.nu",
        customer_address="Uppsalagatan 5, 753 20 Uppsala",
        customer_org_number="556123-9876"
    )
    invoice_service.send_invoice(inv4.id)
    invoice_service.register_payment(inv4.id, 14250000, date(2026, 2, 5), "bank_transfer")
    invoices.append((inv4, "paid"))
    print("  ✓ Invoice: Paid - Smart Systems (142,500 kr)")
    
    return invoices


def generate_demo_data():
    """Generate complete demo dataset."""
    print("="*60)
    print("🎯 GENERERAR DEMO-DATA")
    print("="*60)
    
    # Initialize database
    db.init_db()
    print("\n📊 Steg 1: Databas initialiserad")
    
    # Create fiscal year
    print("\n📅 Steg 2: Skapar räkenskapsår...")
    fy_id = create_fiscal_year_2026()
    
    # Get first period for vouchers
    periods = PeriodRepository.get_all_periods()
    period_3 = next((p for p in periods if p.month == 3), periods[0])
    
    # Create vouchers
    print("\n📝 Steg 3: Skapar verifikationer...")
    ledger = LedgerService()
    vouchers = create_sample_vouchers(ledger, period_3.id)
    
    # Create invoices
    print("\n📄 Steg 4: Skapar fakturor...")
    invoice_service = InvoiceService()
    invoices = create_sample_invoices(invoice_service)
    
    # Summary
    print("\n" + "="*60)
    print("✅ DEMO-DATA KLAR")
    print("="*60)
    print(f"\n📊 Sammanfattning:")
    print(f"  • {len(vouchers)} verifikationer")
    print(f"  • {len(invoices)} fakturor")
    print(f"\n🔑 API-nyckel: dev-key-change-in-production")
    print(f"\n🌐 Åtkomst:")
    print(f"  • API: http://localhost:8000/docs")
    print(f"  • Frontend: http://localhost:8501")
    print("="*60)


if __name__ == "__main__":
    generate_demo_data()
