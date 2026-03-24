#!/bin/bash
# Populate the deployed Bokföringssystem at q.stefanwikner.se with example data.
# Usage: ./scripts/populate_deployment.sh [BASE_URL] [API_KEY]
#
# This creates a realistic Swedish consulting company dataset:
# - Fiscal year 2026 with monthly periods
# - Multiple invoices to different customers
# - Various expense vouchers (rent, travel, software, office supplies)
# - Payments registered
# - A mix of draft and posted vouchers

set -euo pipefail

BASE_URL="${1:-https://q.stefanwikner.se}"
API_KEY="${2:-dev-key-change-in-production}"

AUTH="Authorization: Bearer ${API_KEY}"
CT="Content-Type: application/json"

# Helper: POST with JSON
post() {
  local path="$1"
  local body="$2"
  echo "  POST ${path}"
  curl -s -X POST "${BASE_URL}${path}" -H "${AUTH}" -H "${CT}" -d "${body}"
  echo
}

# Helper: GET
get() {
  local path="$1"
  echo "  GET ${path}"
  curl -s "${BASE_URL}${path}" -H "${AUTH}"
  echo
}

echo "=== Populating ${BASE_URL} with example data ==="
echo

# ──────────────────────────────────────────────
# Step 0: Health check
# ──────────────────────────────────────────────
echo "--- Step 0: Health check ---"
curl -sf "${BASE_URL}/health" && echo " OK" || { echo " FAILED - is the server running?"; exit 1; }
echo

# ──────────────────────────────────────────────
# Step 1: Seed base data (accounts, fiscal year, etc.)
# ──────────────────────────────────────────────
echo "--- Step 1: Seed base data via /agent/seed ---"
post "/api/v1/agent/seed" '{}'
echo

# ──────────────────────────────────────────────
# Step 2: Create fiscal year 2026 (if not already created by seed)
# ──────────────────────────────────────────────
echo "--- Step 2: Ensure fiscal year exists ---"
FISCAL_YEARS=$(curl -s "${BASE_URL}/api/v1/fiscal-years" -H "${AUTH}")
echo "  Fiscal years: ${FISCAL_YEARS}"
echo

# ──────────────────────────────────────────────
# Step 3: Get periods
# ──────────────────────────────────────────────
echo "--- Step 3: List periods ---"
PERIODS=$(curl -s "${BASE_URL}/api/v1/periods" -H "${AUTH}")
echo "  Periods: ${PERIODS}" | head -c 500
echo
echo

# Extract period IDs (we need unlocked periods for new vouchers)
# The seed creates Jan, Feb, Mar and locks March.
# We'll create additional periods if needed.

# ──────────────────────────────────────────────
# Step 4: Create additional invoices
# ──────────────────────────────────────────────
echo "--- Step 4: Create invoices ---"

# Invoice 2: Web development for TechStart AB
post "/api/v1/invoices" '{
  "customer_name": "TechStart AB",
  "customer_org_number": "559100-1234",
  "customer_email": "ekonomi@techstart.se",
  "invoice_date": "2026-01-20",
  "due_date": "2026-02-20",
  "description": "Webbutveckling - Fas 1",
  "rows": [
    {
      "description": "Frontend-utveckling React (60 timmar)",
      "quantity": 60,
      "unit_price": 125000,
      "vat_code": "MP1"
    },
    {
      "description": "Backend-utveckling Python (40 timmar)",
      "quantity": 40,
      "unit_price": 135000,
      "vat_code": "MP1"
    },
    {
      "description": "Projektledning (10 timmar)",
      "quantity": 10,
      "unit_price": 150000,
      "vat_code": "MP1"
    }
  ]
}'
echo

# Invoice 3: Design work for Kreativ Byrå AB
post "/api/v1/invoices" '{
  "customer_name": "Kreativ Byrå AB",
  "customer_org_number": "556789-0001",
  "customer_email": "fakturor@kreativbyra.se",
  "invoice_date": "2026-02-01",
  "due_date": "2026-03-01",
  "description": "UX/UI Design - Mobilapp",
  "rows": [
    {
      "description": "UX-research och användarintervjuer",
      "quantity": 20,
      "unit_price": 110000,
      "vat_code": "MP1"
    },
    {
      "description": "Wireframes och prototyper (Figma)",
      "quantity": 35,
      "unit_price": 120000,
      "vat_code": "MP1"
    }
  ]
}'
echo

# Invoice 4: Training for Stockholms Kommun
post "/api/v1/invoices" '{
  "customer_name": "Stockholms Kommun",
  "customer_org_number": "212000-0142",
  "customer_email": "leverantorsreskontra@stockholm.se",
  "invoice_date": "2026-02-15",
  "due_date": "2026-03-15",
  "description": "Utbildning - Systemadministration",
  "rows": [
    {
      "description": "Heldagsutbildning (2 dagar)",
      "quantity": 2,
      "unit_price": 2500000,
      "vat_code": "MP1"
    },
    {
      "description": "Kursmaterial och dokumentation",
      "quantity": 15,
      "unit_price": 50000,
      "vat_code": "MP1"
    }
  ]
}'
echo

# Invoice 5: Small consultancy job
post "/api/v1/invoices" '{
  "customer_name": "Norden Fastigheter AB",
  "customer_org_number": "556234-5678",
  "customer_email": "info@nordenfastigheter.se",
  "invoice_date": "2026-01-10",
  "due_date": "2026-02-10",
  "description": "IT-konsultation",
  "rows": [
    {
      "description": "Systemgranskning och rådgivning (8 timmar)",
      "quantity": 8,
      "unit_price": 150000,
      "vat_code": "MP1"
    }
  ]
}'
echo

# ──────────────────────────────────────────────
# Step 5: Create additional expense vouchers
# ──────────────────────────────────────────────
echo "--- Step 5: Create expense vouchers ---"

# We need an unlocked period. January should be unlocked.
# First, find January period ID
JAN_PERIOD_ID=$(echo "${PERIODS}" | python3 -c "
import sys, json
data = json.load(sys.stdin)
periods = data if isinstance(data, list) else data.get('periods', [])
for p in periods:
    if p.get('month') == 1 or '2026-01' in p.get('start_date', ''):
        print(p['id'])
        break
" 2>/dev/null || echo "")

FEB_PERIOD_ID=$(echo "${PERIODS}" | python3 -c "
import sys, json
data = json.load(sys.stdin)
periods = data if isinstance(data, list) else data.get('periods', [])
for p in periods:
    if p.get('month') == 2 or '2026-02' in p.get('start_date', ''):
        print(p['id'])
        break
" 2>/dev/null || echo "")

echo "  January period: ${JAN_PERIOD_ID:-not found}"
echo "  February period: ${FEB_PERIOD_ID:-not found}"

if [ -n "${JAN_PERIOD_ID}" ]; then
  # Software subscription
  post "/api/v1/vouchers" "{
    \"series\": \"A\",
    \"date\": \"2026-01-05\",
    \"period_id\": \"${JAN_PERIOD_ID}\",
    \"description\": \"GitHub Team - Månadsavgift januari\",
    \"rows\": [
      {\"account\": \"6540\", \"debit\": 250000, \"credit\": 0, \"description\": \"IT-tjänster\"},
      {\"account\": \"2640\", \"debit\": 62500, \"credit\": 0, \"description\": \"Ingående moms 25%\"},
      {\"account\": \"1010\", \"debit\": 0, \"credit\": 312500, \"description\": \"Betalning från PlusGiro\"}
    ]
  }"

  # Office supplies
  post "/api/v1/vouchers" "{
    \"series\": \"A\",
    \"date\": \"2026-01-12\",
    \"period_id\": \"${JAN_PERIOD_ID}\",
    \"description\": \"Kontorsmaterial - Staples\",
    \"rows\": [
      {\"account\": \"6110\", \"debit\": 345000, \"credit\": 0, \"description\": \"Kontorsmaterial\"},
      {\"account\": \"2640\", \"debit\": 86250, \"credit\": 0, \"description\": \"Ingående moms 25%\"},
      {\"account\": \"1010\", \"debit\": 0, \"credit\": 431250, \"description\": \"Betalning\"}
    ]
  }"

  # Phone bill
  post "/api/v1/vouchers" "{
    \"series\": \"A\",
    \"date\": \"2026-01-25\",
    \"period_id\": \"${JAN_PERIOD_ID}\",
    \"description\": \"Telia - Mobilabonnemang januari\",
    \"rows\": [
      {\"account\": \"6210\", \"debit\": 49900, \"credit\": 0, \"description\": \"Telefon\"},
      {\"account\": \"2640\", \"debit\": 12475, \"credit\": 0, \"description\": \"Ingående moms 25%\"},
      {\"account\": \"1010\", \"debit\": 0, \"credit\": 62375, \"description\": \"Autogiro\"}
    ]
  }"

  # Insurance
  post "/api/v1/vouchers" "{
    \"series\": \"A\",
    \"date\": \"2026-01-02\",
    \"period_id\": \"${JAN_PERIOD_ID}\",
    \"description\": \"Trygg-Hansa - Företagsförsäkring Q1\",
    \"rows\": [
      {\"account\": \"6310\", \"debit\": 750000, \"credit\": 0, \"description\": \"Försäkringspremie\"},
      {\"account\": \"1010\", \"debit\": 0, \"credit\": 750000, \"description\": \"Betalning\"}
    ]
  }"
fi

if [ -n "${FEB_PERIOD_ID}" ]; then
  # Cloud hosting
  post "/api/v1/vouchers" "{
    \"series\": \"A\",
    \"date\": \"2026-02-03\",
    \"period_id\": \"${FEB_PERIOD_ID}\",
    \"description\": \"AWS - Molntjänster februari\",
    \"rows\": [
      {\"account\": \"6540\", \"debit\": 890000, \"credit\": 0, \"description\": \"IT-tjänster\"},
      {\"account\": \"2640\", \"debit\": 222500, \"credit\": 0, \"description\": \"Ingående moms 25%\"},
      {\"account\": \"1010\", \"debit\": 0, \"credit\": 1112500, \"description\": \"Kreditkort\"}
    ]
  }"

  # Coworking space
  post "/api/v1/vouchers" "{
    \"series\": \"A\",
    \"date\": \"2026-02-01\",
    \"period_id\": \"${FEB_PERIOD_ID}\",
    \"description\": \"Epicenter - Kontorsplats februari\",
    \"rows\": [
      {\"account\": \"5010\", \"debit\": 1200000, \"credit\": 0, \"description\": \"Lokalhyra\"},
      {\"account\": \"2640\", \"debit\": 300000, \"credit\": 0, \"description\": \"Ingående moms 25%\"},
      {\"account\": \"1010\", \"debit\": 0, \"credit\": 1500000, \"description\": \"Betalning\"}
    ]
  }"

  # Conference
  post "/api/v1/vouchers" "{
    \"series\": \"A\",
    \"date\": \"2026-02-18\",
    \"period_id\": \"${FEB_PERIOD_ID}\",
    \"description\": \"Nordic.js konferens - 2 biljetter\",
    \"rows\": [
      {\"account\": \"6910\", \"debit\": 1190000, \"credit\": 0, \"description\": \"Konferensavgift\"},
      {\"account\": \"2640\", \"debit\": 297500, \"credit\": 0, \"description\": \"Ingående moms 25%\"},
      {\"account\": \"1010\", \"debit\": 0, \"credit\": 1487500, \"description\": \"Kortbetalning\"}
    ]
  }"

  # Travel expense
  post "/api/v1/vouchers" "{
    \"series\": \"A\",
    \"date\": \"2026-02-22\",
    \"period_id\": \"${FEB_PERIOD_ID}\",
    \"description\": \"Kundbesök Malmö - tåg och hotell\",
    \"rows\": [
      {\"account\": \"5800\", \"debit\": 450000, \"credit\": 0, \"description\": \"Resekostnader\"},
      {\"account\": \"2640\", \"debit\": 54000, \"credit\": 0, \"description\": \"Ingående moms 12%\"},
      {\"account\": \"1010\", \"debit\": 0, \"credit\": 504000, \"description\": \"Utlägg\"}
    ]
  }"
fi

# ──────────────────────────────────────────────
# Step 6: Post some vouchers (make them immutable)
# ──────────────────────────────────────────────
echo "--- Step 6: Post draft vouchers ---"
VOUCHERS=$(curl -s "${BASE_URL}/api/v1/vouchers?status=draft" -H "${AUTH}")
echo "  Draft vouchers response received"

# Post the first few draft vouchers
echo "${VOUCHERS}" | python3 -c "
import sys, json
data = json.load(sys.stdin)
vouchers = data.get('vouchers', data) if isinstance(data, dict) else data
for v in vouchers[:6]:
    print(v['id'])
" 2>/dev/null | while read -r vid; do
  if [ -n "${vid}" ]; then
    echo "  Posting voucher ${vid}..."
    curl -s -X POST "${BASE_URL}/api/v1/vouchers/${vid}/post" -H "${AUTH}" -H "${CT}" > /dev/null 2>&1 || echo "    (may already be posted)"
  fi
done
echo

# ──────────────────────────────────────────────
# Step 7: Send and book some invoices
# ──────────────────────────────────────────────
echo "--- Step 7: Send and book invoices ---"
INVOICES=$(curl -s "${BASE_URL}/api/v1/invoices" -H "${AUTH}")
echo "  Invoice list received"

echo "${INVOICES}" | python3 -c "
import sys, json
data = json.load(sys.stdin)
invoices = data.get('invoices', data) if isinstance(data, dict) else data
for inv in invoices:
    if inv.get('status') == 'draft':
        print(inv['id'])
" 2>/dev/null | head -3 | while read -r iid; do
  if [ -n "${iid}" ]; then
    echo "  Sending invoice ${iid}..."
    curl -s -X POST "${BASE_URL}/api/v1/invoices/${iid}/send" -H "${AUTH}" -H "${CT}" > /dev/null 2>&1 || true
  fi
done
echo

# ──────────────────────────────────────────────
# Step 8: Run compliance check
# ──────────────────────────────────────────────
echo "--- Step 8: Run compliance check ---"
post "/api/v1/compliance/check" '{}'
echo

# ──────────────────────────────────────────────
# Step 9: Verify final state
# ──────────────────────────────────────────────
echo "--- Step 9: Final verification ---"
echo
echo "Vouchers:"
curl -s "${BASE_URL}/api/v1/vouchers" -H "${AUTH}" | python3 -c "
import sys, json
data = json.load(sys.stdin)
v = data.get('vouchers', data) if isinstance(data, dict) else data
total = data.get('total', len(v)) if isinstance(data, dict) else len(v)
posted = sum(1 for x in v if x.get('status') == 'posted')
draft = sum(1 for x in v if x.get('status') == 'draft')
print(f'  Total: {total}, Posted: {posted}, Draft: {draft}')
" 2>/dev/null

echo
echo "Invoices:"
curl -s "${BASE_URL}/api/v1/invoices" -H "${AUTH}" | python3 -c "
import sys, json
data = json.load(sys.stdin)
inv = data.get('invoices', data) if isinstance(data, dict) else data
print(f'  Total: {len(inv)}')
for i in inv:
    print(f'    {i.get(\"invoice_number\", \"?\")} - {i.get(\"customer_name\", \"?\")} - {i.get(\"status\", \"?\")}')
" 2>/dev/null

echo
echo "Accounts:"
curl -s "${BASE_URL}/api/v1/accounts" -H "${AUTH}" | python3 -c "
import sys, json
data = json.load(sys.stdin)
acc = data.get('accounts', data) if isinstance(data, dict) else data
print(f'  Total: {len(acc)}')
" 2>/dev/null

echo
echo "=== Done! Visit ${BASE_URL} to see the populated system ==="
