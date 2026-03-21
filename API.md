# REST API Reference

Base URL: `http://localhost:8000`

**Authentication:** All endpoints require `Authorization: Bearer <api-key>` header.

Default API Key (dev): `dev-key-change-in-production`

---

## Table of Contents

1. [Health & Status](#health--status)
2. [Accounts (Konton)](#accounts)
3. [Fiscal Years & Periods](#fiscal-years--periods)
4. [Vouchers (Verifikationer)](#vouchers)
5. [Reports (Rapporter)](#reports)
6. [Invoices (Fakturor)](#invoices-fas-2)
7. [SIE4 Import & Export](#sie4-import--export)
8. [Error Handling](#error-handling)

---

## Health & Status

### Health Check

```http
GET /health
```

**Response:**
```json
{
  "status": "ok",
  "service": "bokfoering-api",
  "version": "0.2.0"
}
```

---

## Accounts

### List All Accounts

```http
GET /api/v1/accounts?active_only=true
Authorization: Bearer dev-key-change-in-production
```

**Parameters:**
- `active_only` (boolean, default: true) - Only return active accounts

**Response:**
```json
{
  "accounts": [
    {
      "code": "1510",
      "name": "Kundfordringar",
      "account_type": "asset",
      "vat_code": null,
      "sru_code": null,
      "active": true
    }
  ],
  "total": 25
}
```

### Get Account by Code

```http
GET /api/v1/accounts/1510
Authorization: Bearer dev-key-change-in-production
```

**Response:**
```json
{
  "code": "1510",
  "name": "Kundfordringar",
  "account_type": "asset",
  "vat_code": null,
  "active": true
}
```

---

## Fiscal Years & Periods

### Create Fiscal Year

```http
POST /api/v1/fiscal-years?start_date=2026-01-01&end_date=2026-12-31
Authorization: Bearer dev-key-change-in-production
```

**Parameters:**
- `start_date` (date, required) - Start of fiscal year
- `end_date` (date, required) - End of fiscal year

Automatically creates 12 monthly periods.

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "start_date": "2026-01-01",
  "end_date": "2026-12-31",
  "locked": false,
  "locked_at": null,
  "created_at": "2026-03-21T10:30:00"
}
```

### Get Fiscal Year

```http
GET /api/v1/fiscal-years/550e8400-e29b-41d4-a716-446655440000
Authorization: Bearer dev-key-change-in-production
```

### List Periods

```http
GET /api/v1/periods?fiscal_year_id=550e8400-e29b-41d4-a716-446655440000
Authorization: Bearer dev-key-change-in-production
```

**Response:**
```json
{
  "fiscal_year_id": "550e8400-e29b-41d4-a716-446655440000",
  "total": 3,
  "periods": [
    {
      "id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
      "fiscal_year_id": "550e8400-e29b-41d4-a716-446655440000",
      "year": 2026,
      "month": 1,
      "start_date": "2026-01-01",
      "end_date": "2026-01-31",
      "locked": false,
      "locked_at": null
    }
  ]
}
```

### Get Period

```http
GET /api/v1/periods/6ba7b810-9dad-11d1-80b4-00c04fd430c8
Authorization: Bearer dev-key-change-in-production
```

### Lock Period (Irreversible)

```http
POST /api/v1/periods/6ba7b810-9dad-11d1-80b4-00c04fd430c8/lock
Authorization: Bearer dev-key-change-in-production
```

⚠️ **Warning:** Once locked, period cannot be unlocked (varaktighet requirement).

**Response:**
```json
{
  "id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "locked": true,
  "locked_at": "2026-03-21T10:35:00"
}
```

---

## Vouchers

### Create Voucher

```http
POST /api/v1/vouchers
Authorization: Bearer dev-key-change-in-production
Content-Type: application/json

{
  "series": "A",
  "date": "2026-03-20",
  "period_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "description": "Invoice #1042 - Acme Corp",
  "auto_post": false,
  "rows": [
    {
      "account": "1510",
      "debit": 12500000,
      "credit": 0,
      "description": "Customer invoice"
    },
    {
      "account": "3011",
      "debit": 0,
      "credit": 10000000,
      "description": "Revenue"
    },
    {
      "account": "2610",
      "debit": 0,
      "credit": 2500000,
      "description": "VAT 25%"
    }
  ]
}
```

**Note:** All amounts in **öre** (1 kr = 100 öre)

**Response:**
```json
{
  "id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
  "series": "A",
  "number": 1,
  "date": "2026-03-20",
  "period_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "description": "Invoice #1042 - Acme Corp",
  "status": "draft",
  "rows": [...],
  "created_at": "2026-03-21T10:40:00",
  "created_by": "api",
  "posted_at": null
}
```

### Get Voucher

```http
GET /api/v1/vouchers/a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11
Authorization: Bearer dev-key-change-in-production
```

### List Vouchers

```http
GET /api/v1/vouchers?period_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8&status=posted
Authorization: Bearer dev-key-change-in-production
```

**Parameters:**
- `period_id` (uuid, required) - Filter by period
- `status` (string, optional) - "draft", "posted", "all"

### Post Voucher (Immutable)

```http
POST /api/v1/vouchers/a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11/post
Authorization: Bearer dev-key-change-in-production
```

⚠️ **Warning:** Once posted, voucher is immutable (BFL varaktighet). Can only be corrected via B-series correction voucher.

**Response:**
```json
{
  "id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
  "status": "posted",
  "posted_at": "2026-03-21T10:42:00"
}
```

---

## Reports

### Trial Balance (Råbalans)

```http
GET /api/v1/reports/trial-balance?period_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8
Authorization: Bearer dev-key-change-in-production
```

**Response:**
```json
{
  "period_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "period": "2026-03",
  "as_of": "2026-03-31",
  "rows": [
    {
      "account_code": "1510",
      "debit": 12500000,
      "credit": 0,
      "balance": 12500000
    },
    {
      "account_code": "3011",
      "debit": 0,
      "credit": 10000000,
      "balance": -10000000
    }
  ],
  "total_debit": 12500000,
  "total_credit": 12500000
}
```

### Account Ledger (Huvudbok)

```http
GET /api/v1/reports/account/1510?period_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8
Authorization: Bearer dev-key-change-in-production
```

**Response:**
```json
{
  "account_code": "1510",
  "account_name": "Kundfordringar",
  "period_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "rows": [
    {
      "date": "2026-03-20",
      "voucher_series": "A",
      "voucher_number": "000001",
      "description": "Invoice #1042",
      "debit": 12500000,
      "credit": 0,
      "balance": 12500000
    }
  ],
  "ending_balance": 12500000
}
```

### Audit History (Behandlingshistorik)

```http
GET /api/v1/reports/audit/voucher/a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11
Authorization: Bearer dev-key-change-in-production
```

**Response:**
```json
{
  "entity_type": "voucher",
  "entity_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
  "entries": [
    {
      "id": "...",
      "action": "created",
      "actor": "api",
      "timestamp": "2026-03-21T10:40:00",
      "payload": {
        "series": "A",
        "number": 1,
        "rows_count": 3
      }
    },
    {
      "id": "...",
      "action": "posted",
      "actor": "api",
      "timestamp": "2026-03-21T10:42:00",
      "payload": {
        "total_debit": 12500000,
        "total_credit": 12500000
      }
    }
  ]
}
```

---

## Invoices (Fas 2)

### Create Invoice

```http
POST /api/v1/invoices
Authorization: Bearer dev-key-change-in-production
Content-Type: application/json

{
  "customer_name": "Acme Corp AB",
  "invoice_date": "2026-03-20",
  "due_date": "2026-04-20",
  "customer_org_number": "556000-0000",
  "customer_email": "accounting@acme.se",
  "description": "Q1 2026 Consulting",
  "rows": [
    {
      "description": "Senior consultant (40 hrs @ 1,500 kr/hr)",
      "quantity": 40,
      "unit_price": 150000,
      "vat_code": "MP1"
    }
  ]
}
```

**VAT Codes:**
- `MP1` - 25% (Standard for consulting)
- `MP2` - 12%
- `MP3` - 6%
- `MF` - 0% (Export/exempt)

**Response:**
```json
{
  "id": "inv-001",
  "invoice_number": "20260320001",
  "customer_name": "Acme Corp AB",
  "invoice_date": "2026-03-20",
  "due_date": "2026-04-20",
  "amount_ex_vat": 6000000,
  "vat_amount": 1500000,
  "amount_inc_vat": 7500000,
  "status": "draft",
  "rows_count": 1,
  "created_at": "2026-03-21T10:50:00"
}
```

### Get Invoice

```http
GET /api/v1/invoices/inv-001
Authorization: Bearer dev-key-change-in-production
```

**Response:**
```json
{
  "id": "inv-001",
  "invoice_number": "20260320001",
  "customer_name": "Acme Corp AB",
  "amount_inc_vat": 7500000,
  "paid_amount": 0,
  "remaining_amount": 7500000,
  "status": "draft",
  "is_overdue": false,
  "rows": [...],
  "created_at": "2026-03-21T10:50:00",
  "sent_at": null
}
```

### Send Invoice

```http
POST /api/v1/invoices/inv-001/send
Authorization: Bearer dev-key-change-in-production
```

Changes status from `draft` to `sent`.

### Book Invoice (Auto-Booking)

```http
POST /api/v1/invoices/inv-001/book?period_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8
Authorization: Bearer dev-key-change-in-production
```

Creates accounting voucher:
- Debit: 1510 (Customer receivables) = amount_inc_vat
- Credit: 3011 (Revenue) = amount_ex_vat
- Credit: 2610 (VAT) = vat_amount

**Response:**
```json
{
  "invoice_id": "inv-001",
  "voucher_id": "a0eebc99-...",
  "status": "booked"
}
```

### Register Payment

```http
POST /api/v1/invoices/inv-001/payment
Authorization: Bearer dev-key-change-in-production
Content-Type: application/json

{
  "amount": 3750000,
  "payment_date": "2026-03-25",
  "payment_method": "bank_transfer",
  "reference": "PAYMENT-001",
  "period_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
}
```

**Payment Methods:**
- `bank_transfer`
- `card`
- `cash`
- `cheque`
- `other`

**Response:**
```json
{
  "payment_id": "pay-001",
  "amount": 3750000,
  "invoice_status": "partially_paid",
  "remaining_amount": 3750000,
  "voucher_id": "..."
}
```

### Create Credit Note

```http
POST /api/v1/invoices/inv-001/credit-note
Authorization: Bearer dev-key-change-in-production
Content-Type: application/json

{
  "amount_ex_vat": 1000000,
  "reason": "Service discount",
  "credit_date": "2026-03-28",
  "period_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
}
```

**Response:**
```json
{
  "credit_note_id": "cn-001",
  "credit_note_number": "CN-20260328-ABC1234",
  "amount_inc_vat": 1250000,
  "reason": "Service discount",
  "voucher_id": "..."
}
```

---

## Error Handling

All errors follow this format:

```json
{
  "error": "Voucher rows do not balance: debit=12500000 credit=10000000",
  "code": "balance_error",
  "details": "total debit must equal total credit",
  "timestamp": "2026-03-21T10:45:00"
}
```

### Common Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| `balance_error` | 400 | Voucher debit ≠ credit |
| `validation_error` | 400 | Invalid input |
| `period_locked` | 400 | Cannot post to locked period |
| `account_not_found` | 404 | Account does not exist |
| `voucher_not_found` | 404 | Voucher does not exist |
| `invoice_not_found` | 404 | Invoice does not exist |
| `already_posted` | 400 | Cannot edit posted voucher |
| `unauthorized` | 401 | Invalid or missing API key |

---

## Example Workflow

### 1. Create Fiscal Year

```bash
curl -X POST http://localhost:8000/api/v1/fiscal-years \
  -H "Authorization: Bearer dev-key-change-in-production" \
  "?start_date=2026-01-01&end_date=2026-12-31"
```

### 2. Create Invoice

```bash
curl -X POST http://localhost:8000/api/v1/invoices \
  -H "Authorization: Bearer dev-key-change-in-production" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_name": "Acme Corp",
    "invoice_date": "2026-03-20",
    "due_date": "2026-04-20",
    "rows": [{
      "description": "Consulting",
      "quantity": 10,
      "unit_price": 100000,
      "vat_code": "MP1"
    }]
  }'
```

### 3. Send & Book

```bash
# Send
curl -X POST http://localhost:8000/api/v1/invoices/inv-001/send \
  -H "Authorization: Bearer dev-key-change-in-production"

# Book (auto-voucher)
curl -X POST "http://localhost:8000/api/v1/invoices/inv-001/book?period_id=..." \
  -H "Authorization: Bearer dev-key-change-in-production"
```

### 4. Register Payment

```bash
curl -X POST http://localhost:8000/api/v1/invoices/inv-001/payment \
  -H "Authorization: Bearer dev-key-change-in-production" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 5000000,
    "payment_date": "2026-03-25",
    "payment_method": "bank_transfer",
    "period_id": "..."
  }'
```

### 5. View Trial Balance

```bash
curl http://localhost:8000/api/v1/reports/trial-balance \
  -H "Authorization: Bearer dev-key-change-in-production" \
  "?period_id=..."
```

---

---

## SIE4 Import & Export

### Import SIE4

```http
POST /api/v1/import/sie4
Content-Type: multipart/form-data
```

Upload a SIE4 file to import accounting data.

**Parameters:**
- `file` (required): SIE4 file (.si, .sie, .txt)
- `fiscal_year_id` (optional): Target fiscal year ID

**Response:**
```json
{
  "success": true,
  "imported": {
    "accounts": 9,
    "vouchers": 3,
    "periods_created": 0
  },
  "errors": []
}
```

### Validate SIE4

```http
POST /api/v1/import/sie4/validate
Content-Type: multipart/form-data
```

Validate a SIE4 file without importing.

### Export SIE4

```http
GET /api/v1/export/sie4?fiscal_year_id=...
```

Export accounting data to SIE4 format.

**Parameters:**
- `fiscal_year_id` (required): Fiscal year to export
- `company_name` (optional): Company name for the export
- `org_number` (optional): Organization number
- `format` (optional): `PC8` (default, Windows-1252) or `ASCII`
- `download` (optional): `true` (default) for file download, `false` for JSON

**Example (file download):**
```bash
curl -o export.si "http://localhost:8000/api/v1/export/sie4?fiscal_year_id=fy-2026&company_name=Demo+AB" \
  -H "Authorization: Bearer dev-key-change-in-production"
```

**Example (JSON response):**
```bash
curl "http://localhost:8000/api/v1/export/sie4?fiscal_year_id=fy-2026&download=false" \
  -H "Authorization: Bearer dev-key-change-in-production"
```

**Response (JSON):**
```json
{
  "content": "#FLAGGA 0\r\n#FORMAT PC8\r\n...",
  "format": "SIE4",
  "encoding": "windows-1252",
  "warnings": []
}
```

**SIE4-sektioner som genereras:**
- `#FLAGGA 0` - Alltid 0 för export
- `#FORMAT PC8` - Windows-1252 encoding
- `#GEN` - Genereringsdatum och program
- `#PROGRAM` - Programnamn och version
- `#SIETYP 4` - SIE version 4
- `#FNAMN` - Företagsnamn
- `#FORGN` - Organisationsnummer
- `#RAR` - Räkenskapsår (start/slut)
- `#KPTYP` - Kontoplanstyp (EUBAS97)
- `#KONTO` - Alla konton
- `#SRU` - SRU-koder för skattedeklaration
- `#IB` - Ingående balanser
- `#UB` - Utgående balanser
- `#RES` - Resultat per konto
- `#PSALDO` - Periodsaldon
- `#VER` / `#TRANS` - Verifikationer med transaktionsrader

---

## Interactive API Docs

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

All endpoints can be tested directly from these interfaces!
