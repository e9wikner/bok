"""
Demo data generator - skapar 3 års realistisk bokföringsdata via API.

Simulerar ett konsultföretag "TechVision AB":
- 2024: Startår, investeringar, lån, ~500k omsättning
- 2025: Tillväxtår, expansion, ~800k omsättning  
- 2026: Stabiliseringsår, ~600k omsättning
"""

import os
import sys
import time
from datetime import date
from typing import Optional
import requests

# Konfiguration
API_URL = os.getenv("API_URL", "http://bokfoering-api:8000")
API_KEY = os.getenv("API_KEY", "dev-key-change-in-production")
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}


def ensure_accounts_exist():
    """Skapa konton som demodatan behöver."""
    required_accounts = [
        # Tillgångar (1xxx)
        ("1220", "Ackumulerade avskrivningar inventarier", "asset"),
        ("1230", "Installationer", "asset"),
        ("1250", "Datorer och IT-utrustning", "asset"),
        ("1510", "Kundfordringar", "asset"),
        ("1580", "Fordringar hos anställda", "asset"),
        ("1910", "Kassa", "asset"),
        ("1930", "Företagskonto / checkräkningskonto", "asset"),
        ("1940", "Sparkonto", "asset"),
        ("5410", "Inventarier", "asset"),
        # Skulder (2xxx)
        ("2081", "Aktieägartillskott", "equity"),
        ("2013", "Eget uttag", "equity"),
        ("2091", "Balanserad vinst/förlust", "equity"),
        ("2350", "Banklån", "liability"),
        ("2440", "Leverantörsskulder", "liability"),
        ("2610", "Utgående moms 25%", "vat_out"),
        ("2620", "Utgående moms 12%", "vat_out"),
        ("2630", "Utgående moms 6%", "vat_out"),
        ("2640", "Ingående moms", "vat_in"),
        ("2650", "Moms att betala", "liability"),
        ("2710", "Avräkning för skatter", "liability"),
        ("2730", "Avräkning för arbetsgivaravgifter", "liability"),
        # Intäkter (3xxx)
        ("3011", "Försäljning konsulttjänster", "revenue"),
        ("3041", "Försäljning tjänster 25% moms", "revenue"),
        ("3042", "Försäljning tjänster 12% moms", "revenue"),
        ("3050", "Försäljning utbildning", "revenue"),
        ("3510", "Fakturerade resekostnader", "revenue"),
        ("3740", "Öres- och kronavrundning", "revenue"),
        ("3900", "Övriga rörelseintäkter", "revenue"),
        # Kostnader (4xxx-7xxx)
        ("4010", "Inköp material", "expense"),
        ("5010", "Lokalhyra", "expense"),
        ("5090", "Övriga lokalkostnader", "expense"),
        ("5410", "Inventarier", "expense"),
        ("5800", "Resekostnader", "expense"),
        ("5910", "Reklam och marknadsföring", "expense"),
        ("6110", "Konsultarvoden", "expense"),
        ("6180", "Kontorsmaterial", "expense"),
        ("6210", "Telefon och post", "expense"),
        ("6310", "Försäkringspremier", "expense"),
        ("6540", "Programvaror och licenser", "expense"),
        ("6570", "Bankkostnader", "expense"),
        ("6991", "Revisorskostnader", "expense"),
        ("7010", "Lön tjänstemän", "expense"),
        ("7210", "Lön övrig personal", "expense"),
        ("7510", "Sociala avgifter", "expense"),
        ("7830", "Avskrivningar inventarier", "expense"),
        ("8310", "Ränteintäkter", "revenue"),
        ("8410", "Räntekostnader", "expense"),
    ]
    
    print("📊 Kontrollerar konton...")
    created = 0
    for code, name, acc_type in required_accounts:
        resp = requests.get(f"{API_URL}/api/v1/accounts/{code}", headers=HEADERS)
        if resp.status_code == 404:
            resp = requests.post(
                f"{API_URL}/api/v1/accounts",
                headers=HEADERS,
                json={"code": code, "name": name, "account_type": acc_type}
            )
            if resp.status_code == 201:
                created += 1
            else:
                print(f"  ⚠ Kunde inte skapa {code}: {resp.text}")
    
    print(f"  ✅ {created} nya konton skapade" if created else "  ✅ Alla konton finns redan")


def wait_for_api(timeout: int = 60) -> bool:
    """Vänta på att API:et är redo."""
    print("⏳ Väntar på API...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"{API_URL}/health", timeout=2)
            if resp.status_code == 200:
                print("✅ API redo!")
                return True
        except:
            pass
        time.sleep(2)
    print("❌ API timeout")
    return False


def find_existing_fiscal_year(year: int) -> Optional[str]:
    """Hitta befintligt räkenskapsår."""
    resp = requests.get(f"{API_URL}/api/v1/fiscal-years", headers=HEADERS)
    if resp.status_code == 200:
        for fy in resp.json().get("fiscal_years", []):
            start = fy.get("start_date", "")
            if start.startswith(str(year)):
                return fy.get("id")
    return None


def get_or_create_fiscal_year(year: int) -> str:
    """Hämta eller skapa räkenskapsår."""
    existing = find_existing_fiscal_year(year)
    if existing:
        print(f"  ✓ Räkenskapsår {year} finns: {existing}")
        return existing
    
    print(f"📅 Skapar räkenskapsår {year}...")
    resp = requests.post(
        f"{API_URL}/api/v1/fiscal-years",
        headers=HEADERS,
        params={
            "start_date": f"{year}-01-01",
            "end_date": f"{year}-12-31"
        }
    )
    if resp.status_code == 201:
        fy_id = resp.json().get("id", f"fy-{year}")
        print(f"  ✓ Skapat: {fy_id}")
        return fy_id
    elif resp.status_code == 500 and "UNIQUE" in resp.text:
        existing = find_existing_fiscal_year(year)
        return existing or f"fy-{year}"
    else:
        print(f"  ⚠ Fel: {resp.status_code} - {resp.text}")
        return ""


def get_period_id(fiscal_year_id: str, year: int, month: int) -> Optional[str]:
    """Hämta period-ID för en specifik månad."""
    resp = requests.get(
        f"{API_URL}/api/v1/periods",
        headers=HEADERS,
        params={"fiscal_year_id": fiscal_year_id}
    )
    if resp.status_code == 200:
        for period in resp.json().get("periods", []):
            if period.get("year") == year and period.get("month") == month:
                if not period.get("locked"):
                    return period.get("id")
                else:
                    print(f"    ℹ️ Period {year}-{month:02d} är låst, hoppar över")
                    return None
    return None


def create_voucher(description, voucher_date, period_id, rows, series="A"):
    """Skapa en verifikation via API."""
    if not period_id:
        return None
    
    data = {
        "series": series,
        "date": voucher_date.isoformat(),
        "period_id": period_id,
        "description": description,
        "rows": rows,
        "auto_post": True
    }
    
    resp = requests.post(f"{API_URL}/api/v1/vouchers", headers=HEADERS, json=data)
    
    if resp.status_code == 201:
        voucher = resp.json()
        total = sum(r.get("debit", 0) for r in rows)
        print(f"    ✓ {voucher['series']}{voucher['number']}: {description} ({total/100:,.0f} kr)")
        return voucher
    else:
        print(f"    ❌ Fel: {description} - {resp.text[:100]}")
        return None


def generate_year_2024(fy_id):
    """2024: Startår - grundande, investeringar, lån, ~500k omsättning."""
    print("\n" + "="*60)
    print("📅 2024 — STARTÅR: Grundande & Investeringar")
    print("="*60)
    
    count = 0
    
    def pid(month):
        return get_period_id(fy_id, 2024, month)
    
    # Januari: Grundande
    p = pid(1)
    if p:
        create_voucher("Aktiekapital vid bolagsbildning", date(2024, 1, 5), p,
            [{"account": "1930", "debit": 5000000, "credit": 0, "description": "Insättning aktiekapital"},
             {"account": "2081", "debit": 0, "credit": 5000000, "description": "Aktiekapital"}])
        count += 1
        
        create_voucher("Banklån för startinvesteringar", date(2024, 1, 10), p,
            [{"account": "1930", "debit": 30000000, "credit": 0, "description": "Låneutbetalning"},
             {"account": "2350", "debit": 0, "credit": 30000000, "description": "Banklån"}])
        count += 1
        
        create_voucher("Inköp kontorsutrustning och möbler", date(2024, 1, 15), p,
            [{"account": "1250", "debit": 8000000, "credit": 0, "description": "Datorer, skärmar, möbler"},
             {"account": "2640", "debit": 2000000, "credit": 0, "description": "Ingående moms 25%"},
             {"account": "1930", "debit": 0, "credit": 10000000, "description": "Bankutbetalning"}])
        count += 1
    
    # Februari: Första hyran + försäkring
    p = pid(2)
    if p:
        create_voucher("Hyra kontor februari", date(2024, 2, 1), p,
            [{"account": "5010", "debit": 1500000, "credit": 0, "description": "Lokalhyra"},
             {"account": "2640", "debit": 375000, "credit": 0, "description": "Ingående moms"},
             {"account": "1930", "debit": 0, "credit": 1875000, "description": "Bankutbetalning"}])
        count += 1
        
        create_voucher("Företagsförsäkring helår", date(2024, 2, 5), p,
            [{"account": "6310", "debit": 1200000, "credit": 0, "description": "Årsförsäkring"},
             {"account": "1930", "debit": 0, "credit": 1200000, "description": "Bankutbetalning"}])
        count += 1
    
    # Mars-Juni: Första kunderna, ~200k intäkter
    for month, customer, amount in [
        (3, "Startup Nordic AB", 6000000),
        (4, "DataDriven Solutions", 8000000),
        (5, "GreenTech Innovation", 5000000),
        (6, "LogistikPartner AB", 7000000),
    ]:
        p = pid(month)
        if p:
            vat = int(amount * 0.25)
            create_voucher(f"Konsulttjänster — {customer}", date(2024, month, 15), p,
                [{"account": "1510", "debit": amount + vat, "credit": 0, "description": f"Kundfordran {customer}"},
                 {"account": "3041", "debit": 0, "credit": amount, "description": "Försäljning tjänster 25%"},
                 {"account": "2610", "debit": 0, "credit": vat, "description": "Utgående moms 25%"}])
            count += 1
    
    # Hyra mars-dec
    for month in range(3, 13):
        p = pid(month)
        if p:
            create_voucher(f"Hyra kontor {month:02d}/2024", date(2024, month, 1), p,
                [{"account": "5010", "debit": 1500000, "credit": 0, "description": "Lokalhyra"},
                 {"account": "2640", "debit": 375000, "credit": 0, "description": "Ingående moms"},
                 {"account": "1930", "debit": 0, "credit": 1875000, "description": "Bankutbetalning"}])
            count += 1
    
    # Juli-Dec: Mer försäljning, ~240k
    for month, customer, amount in [
        (7, "MedTech Sverige AB", 10000000),
        (8, "E-handel Pro", 6000000),
        (9, "FinansData Nordic", 8000000),
        (10, "Byggkonsult AB", 4000000),
        (11, "RetailTech Solutions", 9000000),
        (12, "YearEnd Corp", 7000000),
    ]:
        p = pid(month)
        if p:
            vat = int(amount * 0.25)
            create_voucher(f"Konsulttjänster — {customer}", date(2024, month, 15), p,
                [{"account": "1510", "debit": amount + vat, "credit": 0, "description": f"Kundfordran {customer}"},
                 {"account": "3041", "debit": 0, "credit": amount, "description": "Försäljning tjänster 25%"},
                 {"account": "2610", "debit": 0, "credit": vat, "description": "Utgående moms 25%"}])
            count += 1
    
    # Inbetalningar från kunder (med viss fördröjning)
    for month, amount in [(4, 7500000), (5, 10000000), (7, 6250000), (8, 8750000),
                          (9, 12500000), (10, 7500000), (11, 10000000), (12, 11250000)]:
        p = pid(month)
        if p:
            create_voucher(f"Inbetalning kunder {month:02d}/2024", date(2024, month, 25), p,
                [{"account": "1930", "debit": amount, "credit": 0, "description": "Kundinbetalningar"},
                 {"account": "1510", "debit": 0, "credit": amount, "description": "Kundfordringar"}])
            count += 1
    
    # Löner kvartalsvis (liten personal)
    for month in [3, 6, 9, 12]:
        p = pid(month)
        if p:
            create_voucher(f"Lönekostnader Q{month//3}/2024", date(2024, month, 25), p,
                [{"account": "7010", "debit": 4500000, "credit": 0, "description": "Lön grundare"},
                 {"account": "7510", "debit": 1400000, "credit": 0, "description": "Sociala avgifter"},
                 {"account": "2710", "debit": 0, "credit": 1350000, "description": "Skatt"},
                 {"account": "2730", "debit": 0, "credit": 1400000, "description": "Arbetsgivaravgifter"},
                 {"account": "1930", "debit": 0, "credit": 3150000, "description": "Nettolön"}])
            count += 1
    
    # Programvaror & telefon
    for month in [1, 4, 7, 10]:
        p = pid(month)
        if p:
            create_voucher(f"Programvaror och licenser Q{(month-1)//3+1}", date(2024, month, 10), p,
                [{"account": "6540", "debit": 250000, "credit": 0, "description": "SaaS-licenser"},
                 {"account": "2640", "debit": 62500, "credit": 0, "description": "Ingående moms"},
                 {"account": "1930", "debit": 0, "credit": 312500, "description": "Bankutbetalning"}])
            count += 1
    
    # Ränta på lån
    for month in [6, 12]:
        p = pid(month)
        if p:
            create_voucher(f"Ränta banklån H{month//6}/2024", date(2024, month, 30), p,
                [{"account": "8410", "debit": 450000, "credit": 0, "description": "Räntekostnad"},
                 {"account": "1930", "debit": 0, "credit": 450000, "description": "Bankutbetalning"}])
            count += 1
    
    # Avskrivningar december
    p = pid(12)
    if p:
        create_voucher("Årets avskrivningar inventarier 2024", date(2024, 12, 31), p,
            [{"account": "7830", "debit": 1600000, "credit": 0, "description": "Avskrivning 20%"},
             {"account": "1220", "debit": 0, "credit": 1600000, "description": "Ack avskrivningar"}])
        count += 1
    
    return count


def generate_year_2025(fy_id):
    """2025: Tillväxtår - expansion, anställning, ~800k omsättning."""
    print("\n" + "="*60)
    print("📅 2025 — TILLVÄXTÅR: Expansion & Rekrytering")
    print("="*60)
    
    count = 0
    
    def pid(month):
        return get_period_id(fy_id, 2025, month)
    
    # Januari: Ny anställd, mer utrustning
    p = pid(1)
    if p:
        create_voucher("Inköp utrustning till nyanställd", date(2025, 1, 10), p,
            [{"account": "1250", "debit": 4000000, "credit": 0, "description": "Dator + tillbehör"},
             {"account": "2640", "debit": 1000000, "credit": 0, "description": "Ingående moms"},
             {"account": "1930", "debit": 0, "credit": 5000000, "description": "Bankutbetalning"}])
        count += 1
    
    # Hyra varje månad (större kontor)
    for month in range(1, 13):
        p = pid(month)
        if p:
            create_voucher(f"Hyra kontor {month:02d}/2025", date(2025, month, 1), p,
                [{"account": "5010", "debit": 2000000, "credit": 0, "description": "Lokalhyra (större kontor)"},
                 {"account": "2640", "debit": 500000, "credit": 0, "description": "Ingående moms"},
                 {"account": "1930", "debit": 0, "credit": 2500000, "description": "Bankutbetalning"}])
            count += 1
    
    # Större försäljningsprojekt varje månad
    monthly_sales = [
        (1, "Enterprise Solutions AB", 6000000),
        (2, "Nordic AI Labs", 8000000),
        (3, "SmartCity Stockholm", 10000000),
        (4, "CloudMigrate Nordic", 7500000),
        (5, "HealthTech Pro", 9000000),
        (6, "AutomationHub AB", 6500000),
        (7, "DataVault Solutions", 8500000),
        (8, "SecureNet Nordic", 5500000),
        (9, "PropTech Sverige", 7000000),
        (10, "EdTech Innovation", 6000000),
        (11, "GreenEnergy Tech", 8000000),
        (12, "WinterProject AB", 7000000),
    ]
    
    for month, customer, amount in monthly_sales:
        p = pid(month)
        if p:
            vat = int(amount * 0.25)
            create_voucher(f"Konsulttjänster — {customer}", date(2025, month, 12), p,
                [{"account": "1510", "debit": amount + vat, "credit": 0, "description": f"Kundfordran {customer}"},
                 {"account": "3041", "debit": 0, "credit": amount, "description": "Försäljning tjänster 25%"},
                 {"account": "2610", "debit": 0, "credit": vat, "description": "Utgående moms 25%"}])
            count += 1
    
    # Extra utbildningsförsäljning (12% moms)
    for month in [3, 6, 9]:
        p = pid(month)
        if p:
            amount = 3000000
            vat = int(amount * 0.12)
            create_voucher(f"Utbildningstjänster Q{(month-1)//3+1}/2025", date(2025, month, 20), p,
                [{"account": "1510", "debit": amount + vat, "credit": 0, "description": "Utbildning"},
                 {"account": "3050", "debit": 0, "credit": amount, "description": "Försäljning utbildning"},
                 {"account": "2620", "debit": 0, "credit": vat, "description": "Utgående moms 12%"}])
            count += 1
    
    # Kundinbetalningar (löpande)
    for month in range(2, 13):
        p = pid(month)
        if p:
            amount = monthly_sales[month-2][2] + int(monthly_sales[month-2][2] * 0.25)
            create_voucher(f"Inbetalning kunder {month:02d}/2025", date(2025, month, 28), p,
                [{"account": "1930", "debit": amount, "credit": 0, "description": "Kundinbetalningar"},
                 {"account": "1510", "debit": 0, "credit": amount, "description": "Kundfordringar"}])
            count += 1
    
    # Löner varje månad (2 anställda nu)
    for month in range(1, 13):
        p = pid(month)
        if p:
            create_voucher(f"Löner {month:02d}/2025", date(2025, month, 25), p,
                [{"account": "7010", "debit": 7000000, "credit": 0, "description": "Löner 2 anställda"},
                 {"account": "7510", "debit": 2200000, "credit": 0, "description": "Sociala avgifter"},
                 {"account": "2710", "debit": 0, "credit": 2100000, "description": "Skatt"},
                 {"account": "2730", "debit": 0, "credit": 2200000, "description": "Arbetsgivaravgifter"},
                 {"account": "1930", "debit": 0, "credit": 4900000, "description": "Nettolöner"}])
            count += 1
    
    # Marknadsföring (ökad satsning)
    for month in [2, 5, 8, 11]:
        p = pid(month)
        if p:
            create_voucher(f"Marknadsföring Q{(month-1)//3+1}/2025", date(2025, month, 15), p,
                [{"account": "5910", "debit": 800000, "credit": 0, "description": "Digital marknadsföring"},
                 {"account": "2640", "debit": 200000, "credit": 0, "description": "Ingående moms"},
                 {"account": "1930", "debit": 0, "credit": 1000000, "description": "Bankutbetalning"}])
            count += 1
    
    # Programvaror (fler licenser)
    for month in [1, 4, 7, 10]:
        p = pid(month)
        if p:
            create_voucher(f"Programvaror Q{(month-1)//3+1}/2025", date(2025, month, 5), p,
                [{"account": "6540", "debit": 400000, "credit": 0, "description": "SaaS, GitHub, Azure"},
                 {"account": "2640", "debit": 100000, "credit": 0, "description": "Ingående moms"},
                 {"account": "1930", "debit": 0, "credit": 500000, "description": "Bankutbetalning"}])
            count += 1
    
    # Resor & konferenser
    for month in [3, 9]:
        p = pid(month)
        if p:
            create_voucher(f"Konferens & resor {month:02d}/2025", date(2025, month, 18), p,
                [{"account": "5800", "debit": 1200000, "credit": 0, "description": "Resor och boende"},
                 {"account": "6110", "debit": 500000, "credit": 0, "description": "Konferensavgift"},
                 {"account": "2640", "debit": 425000, "credit": 0, "description": "Ingående moms"},
                 {"account": "1930", "debit": 0, "credit": 2125000, "description": "Bankutbetalning"}])
            count += 1
    
    # Amortering och ränta
    for month in [6, 12]:
        p = pid(month)
        if p:
            create_voucher(f"Amortering + ränta banklån H{month//6}/2025", date(2025, month, 30), p,
                [{"account": "2350", "debit": 2500000, "credit": 0, "description": "Amortering"},
                 {"account": "8410", "debit": 375000, "credit": 0, "description": "Ränta"},
                 {"account": "1930", "debit": 0, "credit": 2875000, "description": "Bankutbetalning"}])
            count += 1
    
    # Försäkring
    p = pid(1)
    if p:
        create_voucher("Företagsförsäkring 2025", date(2025, 1, 15), p,
            [{"account": "6310", "debit": 1500000, "credit": 0, "description": "Årsförsäkring"},
             {"account": "1930", "debit": 0, "credit": 1500000, "description": "Bankutbetalning"}])
        count += 1
    
    # Revisor
    p = pid(3)
    if p:
        create_voucher("Revisorskostnader bokslut 2024", date(2025, 3, 15), p,
            [{"account": "6991", "debit": 2000000, "credit": 0, "description": "Revision"},
             {"account": "2640", "debit": 500000, "credit": 0, "description": "Ingående moms"},
             {"account": "1930", "debit": 0, "credit": 2500000, "description": "Bankutbetalning"}])
        count += 1
    
    # Avskrivningar
    p = pid(12)
    if p:
        create_voucher("Årets avskrivningar 2025", date(2025, 12, 31), p,
            [{"account": "7830", "debit": 2400000, "credit": 0, "description": "Avskrivningar 20%"},
             {"account": "1220", "debit": 0, "credit": 2400000, "description": "Ack avskrivningar"}])
        count += 1
    
    return count


def generate_year_2026(fy_id):
    """2026: Stabiliseringsår - löpande drift, ~600k omsättning."""
    print("\n" + "="*60)
    print("📅 2026 — STABILISERINGSÅR: Löpande drift")
    print("="*60)
    
    count = 0
    
    def pid(month):
        return get_period_id(fy_id, 2026, month)
    
    # Aktieägartillskott
    p = pid(1)
    if p:
        create_voucher("Aktieägartillskott - Startkapital", date(2026, 1, 15), p,
            [{"account": "1930", "debit": 20000000, "credit": 0, "description": "Insättning företagskonto"},
             {"account": "2081", "debit": 0, "credit": 20000000, "description": "Aktieägartillskott"}])
        count += 1
    
    # Kontorsutrustning
    p = pid(1)
    if p:
        create_voucher("Inköp dator och kontorsutrustning", date(2026, 1, 20), p,
            [{"account": "1250", "debit": 2500000, "credit": 0, "description": "Dator och skärmar"},
             {"account": "2640", "debit": 625000, "credit": 0, "description": "Ingående moms 25%"},
             {"account": "2440", "debit": 0, "credit": 3125000, "description": "Leverantörsskuld"}])
        count += 1
    
    # Hyra varje månad
    for month in range(1, 13):
        p = pid(month)
        if p:
            create_voucher(f"Hyra kontor {month:02d}/2026", date(2026, month, 1), p,
                [{"account": "5010", "debit": 1800000, "credit": 0, "description": "Lokalhyra"},
                 {"account": "2640", "debit": 450000, "credit": 0, "description": "Ingående moms"},
                 {"account": "1930", "debit": 0, "credit": 2250000, "description": "Bankutbetalning"}])
            count += 1
    
    # Försäljning per månad
    monthly_sales = [
        (2, "TechStart AB", 10000000),
        (3, "Nordic Cloud", 15000000),
        (4, "FoodTech AB", 1000000),  # 12% moms
        (5, "Enterprise AB", 30000000),
        (6, "DataInsight Nordic", 5000000),
        (9, "PropTech 2.0 AB", 8000000),
        (10, "LogistikTech AB", 6000000),
        (11, "RetailCloud AB", 10000000),
    ]
    
    for month, customer, amount in monthly_sales:
        p = pid(month)
        if p:
            if customer == "FoodTech AB":
                vat = int(amount * 0.12)
                vat_account = "2620"
                sales_account = "3042"
            else:
                vat = int(amount * 0.25)
                vat_account = "2610"
                sales_account = "3041"
            
            create_voucher(f"Konsulttjänster — {customer}", date(2026, month, 15), p,
                [{"account": "1510", "debit": amount + vat, "credit": 0, "description": f"Kundfordran {customer}"},
                 {"account": sales_account, "debit": 0, "credit": amount, "description": "Försäljning"},
                 {"account": vat_account, "debit": 0, "credit": vat, "description": "Utgående moms"}])
            count += 1
    
    # Inbetalningar
    for month, amount in [(3, 12500000), (5, 18750000), (6, 1120000),
                          (7, 37500000), (8, 6250000), (10, 10000000), (11, 7500000)]:
        p = pid(month)
        if p:
            create_voucher(f"Inbetalning kunder {month:02d}/2026", date(2026, month, 25), p,
                [{"account": "1930", "debit": amount, "credit": 0, "description": "Kundinbetalningar"},
                 {"account": "1510", "debit": 0, "credit": amount, "description": "Kundfordringar"}])
            count += 1
    
    # Löner (2 anställda, reducerat jfr 2025)
    for month in range(1, 13):
        p = pid(month)
        if p:
            create_voucher(f"Löner {month:02d}/2026", date(2026, month, 25), p,
                [{"account": "7010", "debit": 5000000, "credit": 0, "description": "Löner"},
                 {"account": "7510", "debit": 1600000, "credit": 0, "description": "Sociala avgifter"},
                 {"account": "2710", "debit": 0, "credit": 1500000, "description": "Skatt"},
                 {"account": "2730", "debit": 0, "credit": 1600000, "description": "Arbetsgivaravgifter"},
                 {"account": "1930", "debit": 0, "credit": 3500000, "description": "Nettolöner"}])
            count += 1
    
    # Telefon och internet kvartalsvis
    for month in [2, 5, 8, 11]:
        p = pid(month)
        if p:
            create_voucher(f"Telefon och internet Q{(month-1)//3+1}", date(2026, month, 20), p,
                [{"account": "6210", "debit": 60000, "credit": 0, "description": "Telefon"},
                 {"account": "2640", "debit": 15000, "credit": 0, "description": "Ingående moms"},
                 {"account": "1930", "debit": 0, "credit": 75000, "description": "Bankutbetalning"}])
            count += 1
    
    # Programvaror
    for month in [3, 8]:
        p = pid(month)
        if p:
            create_voucher("Programvaror — Bokföringssystem + verktyg", date(2026, month, 25), p,
                [{"account": "6540", "debit": 300000, "credit": 0, "description": "Programvaror"},
                 {"account": "2640", "debit": 75000, "credit": 0, "description": "Ingående moms"},
                 {"account": "1930", "debit": 0, "credit": 375000, "description": "Bankutbetalning"}])
            count += 1
    
    # Marknadsföring
    p = pid(4)
    if p:
        create_voucher("Marknadsföring — Google Ads + LinkedIn", date(2026, 4, 15), p,
            [{"account": "5910", "debit": 400000, "credit": 0, "description": "Digital marknadsföring"},
             {"account": "2640", "debit": 100000, "credit": 0, "description": "Ingående moms"},
             {"account": "1930", "debit": 0, "credit": 500000, "description": "Bankutbetalning"}])
        count += 1
    
    # Konferensresa
    p = pid(5)
    if p:
        create_voucher("Konferensresa — PyCon Stockholm", date(2026, 5, 10), p,
            [{"account": "5800", "debit": 800000, "credit": 0, "description": "Resekostnader"},
             {"account": "6110", "debit": 400000, "credit": 0, "description": "Konferensavgift"},
             {"account": "2640", "debit": 300000, "credit": 0, "description": "Ingående moms"},
             {"account": "1930", "debit": 0, "credit": 1500000, "description": "Bankutbetalning"}])
        count += 1
    
    # Momsinbetalningar
    for month, amount in [(6, 9230000), (11, 4500000)]:
        p = pid(month)
        if p:
            create_voucher(f"Momsinbetalning Skatteverket {month:02d}/2026", date(2026, month, 12), p,
                [{"account": "2650", "debit": amount, "credit": 0, "description": "Moms att betala"},
                 {"account": "1930", "debit": 0, "credit": amount, "description": "Bankutbetalning"}])
            count += 1
    
    # Kontorsmaterial
    p = pid(6)
    if p:
        create_voucher("Kontorsmaterial", date(2026, 6, 18), p,
            [{"account": "6180", "debit": 20000, "credit": 0, "description": "Kontorsmaterial"},
             {"account": "2640", "debit": 5000, "credit": 0, "description": "Ingående moms"},
             {"account": "1930", "debit": 0, "credit": 25000, "description": "Bankutbetalning"}])
        count += 1
    
    # Försäkring
    p = pid(9)
    if p:
        create_voucher("Företagsförsäkring 2026", date(2026, 9, 1), p,
            [{"account": "6310", "debit": 600000, "credit": 0, "description": "Försäkringspremier"},
             {"account": "1930", "debit": 0, "credit": 600000, "description": "Bankutbetalning"}])
        count += 1
    
    # Amortering + ränta
    for month in [6, 12]:
        p = pid(month)
        if p:
            create_voucher(f"Amortering + ränta banklån H{month//6}/2026", date(2026, month, 30), p,
                [{"account": "2350", "debit": 2500000, "credit": 0, "description": "Amortering"},
                 {"account": "8410", "debit": 300000, "credit": 0, "description": "Ränta"},
                 {"account": "1930", "debit": 0, "credit": 2800000, "description": "Bankutbetalning"}])
            count += 1
    
    # Revisorskostnader
    p = pid(11)
    if p:
        create_voucher("Revisorskostnader — Årsbokslut", date(2026, 11, 15), p,
            [{"account": "6991", "debit": 1500000, "credit": 0, "description": "Revisorskostnader"},
             {"account": "2640", "debit": 375000, "credit": 0, "description": "Ingående moms"},
             {"account": "1930", "debit": 0, "credit": 1875000, "description": "Bankutbetalning"}])
        count += 1
    
    # Avskrivningar
    p = pid(12)
    if p:
        create_voucher("Årets avskrivningar 2026", date(2026, 12, 31), p,
            [{"account": "7830", "debit": 1300000, "credit": 0, "description": "Avskrivningar inventarier"},
             {"account": "1220", "debit": 0, "credit": 1300000, "description": "Ack avskrivningar"}])
        count += 1
    
    # Eget uttag
    p = pid(12)
    if p:
        create_voucher("Eget uttag — Stefan Wikner", date(2026, 12, 28), p,
            [{"account": "2013", "debit": 2000000, "credit": 0, "description": "Eget uttag"},
             {"account": "1930", "debit": 0, "credit": 2000000, "description": "Bankutbetalning"}])
        count += 1
    
    return count


def main():
    """Huvudfunktion."""
    print("="*60)
    print("🚀 DEMODATAGENERATOR — TechVision AB")
    print("   3 års bokföringsdata (2024-2026)")
    print("="*60)
    print(f"API: {API_URL}")
    
    if not wait_for_api():
        sys.exit(1)
    
    ensure_accounts_exist()
    
    total = 0
    
    # Skapa räkenskapsår och generera data
    for year, generator in [(2024, generate_year_2024), (2025, generate_year_2025), (2026, generate_year_2026)]:
        fy_id = get_or_create_fiscal_year(year)
        if fy_id:
            count = generator(fy_id)
            total += count
            print(f"\n  📊 {year}: {count} verifikationer skapade")
        else:
            print(f"\n  ❌ Kunde inte skapa räkenskapsår {year}")
    
    print("\n" + "="*60)
    print("✅ DEMODATAGENERERING KLAR")
    print("="*60)
    print(f"\n📊 Totalt: {total} verifikationer")
    print(f"📅 Period: 2024-2026 (3 räkenskapsår)")
    print(f"\n💰 TechVision AB — Företagsutveckling:")
    print(f"   2024: Startår — ~500k omsättning, investeringar, lån")
    print(f"   2025: Tillväxt — ~800k omsättning, 2 anställda")
    print(f"   2026: Stabilisering — ~600k omsättning")
    print(f"\n🌐 Visa i frontend: http://localhost:8501")
    print("="*60)
    
    sys.exit(0 if total > 0 else 1)


if __name__ == "__main__":
    main()
