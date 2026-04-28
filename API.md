# REST API Reference

Base URL: `http://localhost:8000`

**Authentication:** Most endpoints require `Authorization: Bearer <api-key>` header.

Default API Key (dev): `dev-key-change-in-production`

---

## Table of Contents

1. [Health & Status](#health--status)
2. [Accounts (Konton)](#accounts)
3. [Fiscal Years & Periods](#fiscal-years--periods)
4. [Vouchers (Verifikationer)](#vouchers)
5. [Reports (Rapporter)](#reports)
6. [Invoices (Fakturor)](#invoices)
7. [SIE4 Import & Export](#sie4-import--export)
8. [PDF Export](#pdf-export)
9. [Bank Integration](#bank-integration)
10. [VAT Declarations (Momsdeklarationer)](#vat-declarations)
11. [Compliance](#compliance)
12. [Learning (Auto-Categorization)](#learning-auto-categorization)
13. [Agent Integration](#agent-integration)
14. [Admin / Tenants](#admin--tenants)
15. [Error Handling](#error-handling)

---

## Health & Status

### Health Check

```http
GET /health
```

Also available at `GET /api/v1/health`.

**Response:**
```json
{
  "status": "ok",
  "service": "bokfoering-api",
  "version": "0.1.0"
}
```

### Root

```http
GET /
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

### Create Account

```http
POST /api/v1/accounts
Authorization: Bearer dev-key-change-in-production
Content-Type: application/json

{
  "code": "1520",
  "name": "Övriga kortfristiga fordringar",
  "account_type": "asset",
  "vat_code": null,
  "sru_code": null,
  "active": true
}
```

**Fields:**
- `code` (string, required) - Account code
- `name` (string, required) - Account name
- `account_type` (string, required) - e.g. "asset", "liability", "income", "expense"
- `vat_code` (string, optional)
- `sru_code` (string, optional)
- `active` (boolean, optional)

---

## Fiscal Years & Periods

### List Fiscal Years

```http
GET /api/v1/fiscal-years
Authorization: Bearer dev-key-change-in-production
```

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
GET /api/v1/vouchers?period_id=...&status=posted&search=acme&limit=50&offset=0
Authorization: Bearer dev-key-change-in-production
```

**Parameters:**
- `period_id` (uuid, optional) - Filter by period
- `status` (string, optional) - "draft", "posted", "all"
- `search` (string, optional) - Search in descriptions
- `limit` (integer, optional) - Max results
- `offset` (integer, optional) - Pagination offset

### Update Voucher (Draft Only)

```http
PUT /api/v1/vouchers/a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11
Authorization: Bearer dev-key-change-in-production
Content-Type: application/json

{
  "description": "Updated description",
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
  ],
  "reason": "Corrected account",
  "teach_ai": false
}
```

**Fields:**
- `description` (string, optional) - Updated description
- `rows` (array, required) - Updated voucher rows
- `reason` (string, optional) - Reason for update
- `teach_ai` (boolean, optional) - Feed correction to learning service

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

### Voucher Audit Trail

```http
GET /api/v1/vouchers/a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11/audit
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

### Voucher Attachments

#### List Attachments

```http
GET /api/v1/vouchers/{voucher_id}/attachments
Authorization: Bearer dev-key-change-in-production
```

#### Upload Attachment

```http
POST /api/v1/vouchers/{voucher_id}/attachments
Authorization: Bearer dev-key-change-in-production
Content-Type: multipart/form-data
```

**Parameters:**
- `file` (required) - File to attach

#### Get Attachment

```http
GET /api/v1/vouchers/{voucher_id}/attachments/{attachment_id}
Authorization: Bearer dev-key-change-in-production
```

#### Delete Attachment

```http
DELETE /api/v1/vouchers/{voucher_id}/attachments/{attachment_id}
Authorization: Bearer dev-key-change-in-production
```

---

## Reports

### General Ledger

```http
GET /api/v1/reports/general-ledger/1510?year=2026&month=3
Authorization: Bearer dev-key-change-in-production
```

**Parameters:**
- `account_code` (path, required) - Account code
- `year` (integer, optional) - Year filter
- `month` (integer, optional) - Month filter

### Huvudbok (Account Ledger)

```http
GET /api/v1/reports/huvudbok/1510?period_id=6ba7b810-9dad-11d1-80b4-00c04fd430c8
Authorization: Bearer dev-key-change-in-production
```

**Parameters:**
- `account_code` (path, required) - Account code
- `period_id` (uuid, required) - Period to query

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

### Grundbok (Journal)

```http
GET /api/v1/reports/grundbok/{period_id}
Authorization: Bearer dev-key-change-in-production
```

### Balance Sheet (Balansräkning)

```http
GET /api/v1/reports/balance-sheet?year=2026&as_of_date=2026-03-31
Authorization: Bearer dev-key-change-in-production
```

**Parameters:**
- `year` (integer, optional)
- `as_of_date` (date, optional)

### Income Statement (Resultaträkning)

```http
GET /api/v1/reports/income-statement?year=2026&month=3
Authorization: Bearer dev-key-change-in-production
```

**Parameters:**
- `year` (integer, optional)
- `month` (integer, optional)

### Verifikation Summary

```http
GET /api/v1/reports/verifikation-summary/{period_id}
Authorization: Bearer dev-key-change-in-production
```

### K2 Annual Report (Årsredovisning)

#### Generate K2 Report

```http
POST /api/v1/reports/k2/generate?fiscal_year_id=...&company_name=Demo+AB
Authorization: Bearer dev-key-change-in-production
```

**Parameters:**
- `fiscal_year_id` (string, required)
- `company_name` (string, required)
- `org_number` (string, optional)
- `managing_director` (string, optional)
- `average_employees` (integer, optional)
- `significant_events` (string, optional)

#### Get K2 Report

```http
GET /api/v1/reports/k2/{report_id}
Authorization: Bearer dev-key-change-in-production
```

#### Export K2 as JSON

```http
GET /api/v1/reports/k2/{report_id}/export
Authorization: Bearer dev-key-change-in-production
```

#### Finalize K2 Report

```http
POST /api/v1/reports/k2/{report_id}/finalize
Authorization: Bearer dev-key-change-in-production
```

---

## Invoices

### List Invoices

```http
GET /api/v1/invoices?status_filter=sent
Authorization: Bearer dev-key-change-in-production
```

**Parameters:**
- `status_filter` (string, optional) - Filter by status (e.g. "draft", "sent", "booked", "paid")

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

### Get SIE4 Sample

```http
GET /api/v1/import/sie4/sample
Authorization: Bearer dev-key-change-in-production
```

Returns a sample SIE4 file for reference.

### Import CSV

```http
POST /api/v1/import/csv
Content-Type: multipart/form-data
```

Import accounting data from CSV file.

### Export SIE4

```http
GET /api/v1/export/sie4?fiscal_year_id=...
Authorization: Bearer dev-key-change-in-production
```

Also available as `POST /api/v1/export/sie4` with the same query parameters.

**Parameters:**
- `fiscal_year_id` (required): Fiscal year to export
- `company_name` (optional): Company name for the export
- `org_number` (optional): Organization number
- `format` (optional): `PC8` (default, Windows-1252) or `ASCII`
- `download` (optional, GET only): `true` (default) for file download, `false` for JSON

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

## PDF Export

All PDF export endpoints accept optional company branding query parameters: `company_name`, `org_number`, `vat_number`, `address`, `phone`, `email`, `website`, `bankgiro`, `plusgiro`, `swish`, `iban`, `bic`, `logo_url`.

### Balance Sheet PDF

```http
GET /api/v1/export/pdf/balance-sheet/{period_id}
Authorization: Bearer dev-key-change-in-production
```

### Income Statement PDF

```http
GET /api/v1/export/pdf/income-statement/{period_id}
Authorization: Bearer dev-key-change-in-production
```

### General Ledger PDF

```http
GET /api/v1/export/pdf/general-ledger/{account_code}?period_id=...
Authorization: Bearer dev-key-change-in-production
```

**Parameters:**
- `period_id` (string, required)

### Invoice PDF

```http
GET /api/v1/export/pdf/invoice/{invoice_id}
Authorization: Bearer dev-key-change-in-production
```

HTML variant: `GET /api/v1/export/pdf/invoice/{invoice_id}/html`

### K2 Report PDF

```http
GET /api/v1/export/pdf/k2-report/{fiscal_year_id}?company_name=Demo+AB
Authorization: Bearer dev-key-change-in-production
```

**Additional parameters:**
- `company_name` (string, required)
- `managing_director` (string, optional)
- `average_employees` (integer, optional)
- `significant_events` (string, optional)

---

## Bank Integration

### Connections

#### List Connections

```http
GET /api/v1/bank/connections
Authorization: Bearer dev-key-change-in-production
```

#### Create Connection

```http
POST /api/v1/bank/connections
Authorization: Bearer dev-key-change-in-production
Content-Type: application/json

{
  "bank_name": "Handelsbanken",
  "provider": "manual",
  "account_number": "1234-567890",
  "iban": null,
  "currency": "SEK",
  "sync_from_date": "2026-01-01"
}
```

#### Get Connection

```http
GET /api/v1/bank/connections/{connection_id}
Authorization: Bearer dev-key-change-in-production
```

#### Import Transactions

```http
POST /api/v1/bank/connections/{connection_id}/import
Authorization: Bearer dev-key-change-in-production
Content-Type: application/json

{
  "transactions": [...]
}
```

#### Import CSV

```http
POST /api/v1/bank/connections/{connection_id}/import-csv
Authorization: Bearer dev-key-change-in-production
Content-Type: multipart/form-data
```

**Parameters:**
- `file` (required) - CSV file
- `date_column` (string, default: "Datum")
- `amount_column` (string, default: "Belopp")
- `description_column` (string, default: "Text")
- `delimiter` (string, default: ";")

### Transactions

#### List Transactions

```http
GET /api/v1/bank/transactions?status=pending&limit=100&offset=0
Authorization: Bearer dev-key-change-in-production
```

**Parameters:**
- `connection_id` (string, optional)
- `status` (string, optional)
- `from_date` (string, optional)
- `to_date` (string, optional)
- `limit` (integer, default: 100)
- `offset` (integer, default: 0)

#### Get Transaction

```http
GET /api/v1/bank/transactions/{tx_id}
Authorization: Bearer dev-key-change-in-production
```

#### Correct Transaction

```http
POST /api/v1/bank/transactions/{tx_id}/correct
Authorization: Bearer dev-key-change-in-production
Content-Type: application/json

{
  "account_code": "6200",
  "vat_code": null
}
```

#### Ignore Transaction

```http
POST /api/v1/bank/transactions/{tx_id}/ignore
Authorization: Bearer dev-key-change-in-production
```

### Rules

#### List Rules

```http
GET /api/v1/bank/rules?include_inactive=false
Authorization: Bearer dev-key-change-in-production
```

#### Create Rule

```http
POST /api/v1/bank/rules
Authorization: Bearer dev-key-change-in-production
Content-Type: application/json

{
  "rule_type": "keyword",
  "match_description": "Spotify",
  "match_is_expense": true,
  "target_account_code": "6993",
  "target_vat_code": null,
  "target_description_template": "Spotify subscription",
  "priority": 10
}
```

**Fields:**
- `rule_type` (string, optional)
- `match_description` (string, optional)
- `match_counterpart` (string, optional)
- `match_is_expense` (boolean, optional)
- `match_amount_min` (number, optional)
- `match_amount_max` (number, optional)
- `target_account_code` (string, required)
- `target_vat_code` (string, optional)
- `target_description_template` (string, optional)
- `priority` (integer, optional)

### Categorize Pending

```http
POST /api/v1/bank/categorize?auto_book=false
Authorization: Bearer dev-key-change-in-production
```

**Parameters:**
- `auto_book` (boolean, default: false) - Automatically create vouchers

### Bank Summary

```http
GET /api/v1/bank/summary
Authorization: Bearer dev-key-change-in-production
```

---

## VAT Declarations

### List Declarations

```http
GET /api/v1/vat/declarations?year=2026
Authorization: Bearer dev-key-change-in-production
```

**Parameters:**
- `year` (integer, optional)

### Generate Monthly Declaration

```http
POST /api/v1/vat/declarations/monthly?year=2026&month=3
Authorization: Bearer dev-key-change-in-production
```

**Parameters:**
- `year` (integer, required)
- `month` (integer, required)

### Generate Quarterly Declaration

```http
POST /api/v1/vat/declarations/quarterly?year=2026&quarter=1
Authorization: Bearer dev-key-change-in-production
```

**Parameters:**
- `year` (integer, required)
- `quarter` (integer, required)

### Get Declaration

```http
GET /api/v1/vat/declarations/{decl_id}
Authorization: Bearer dev-key-change-in-production
```

---

## Compliance

### Run Compliance Check

```http
POST /api/v1/compliance/check
Authorization: Bearer dev-key-change-in-production
```

### List Issues

```http
GET /api/v1/compliance/issues?severity=high
Authorization: Bearer dev-key-change-in-production
```

**Parameters:**
- `severity` (string, optional) - Filter by severity level

### Acknowledge Issue

```http
POST /api/v1/compliance/issues/{issue_id}/acknowledge
Authorization: Bearer dev-key-change-in-production
```

### Mark False Positive

```http
POST /api/v1/compliance/issues/{issue_id}/false-positive
Authorization: Bearer dev-key-change-in-production
```

### Resolve Issue

```http
POST /api/v1/compliance/issues/{issue_id}/resolve?resolved_by=user
Authorization: Bearer dev-key-change-in-production
```

**Parameters:**
- `resolved_by` (string, default: "user")

---

## Learning (Auto-Categorization)

### Suggest Account

```http
GET /api/v1/learning/suggest?description=Spotify+Premium&amount=14900
Authorization: Bearer dev-key-change-in-production
```

**Parameters:**
- `description` (string, required)
- `counterparty` (string, optional)
- `amount` (number, optional)
- `suggested_account` (string, optional) - Pre-suggestion to validate

### Record Correction

```http
POST /api/v1/learning/corrections
Authorization: Bearer dev-key-change-in-production
Content-Type: application/json

{
  "original_voucher_id": "...",
  "corrected_voucher_id": null,
  "corrected_rows": [...],
  "reason": "Wrong account",
  "teach_ai": true
}
```

### List Learned Rules

```http
GET /api/v1/learning/rules?active_only=true&min_confidence=0.5&limit=100
Authorization: Bearer dev-key-change-in-production
```

**Parameters:**
- `active_only` (boolean, default: true)
- `min_confidence` (float, default: 0.0)
- `pattern_type` (string, optional)
- `limit` (integer, default: 100)

### Get Rule

```http
GET /api/v1/learning/rules/{rule_id}
Authorization: Bearer dev-key-change-in-production
```

### Confirm Rule

```http
PUT /api/v1/learning/rules/{rule_id}/confirm
Authorization: Bearer dev-key-change-in-production
```

### Deactivate Rule

```http
DELETE /api/v1/learning/rules/{rule_id}
Authorization: Bearer dev-key-change-in-production
```

### Learning Stats

```http
GET /api/v1/learning/stats
Authorization: Bearer dev-key-change-in-production
```

---

## Agent Integration

Endpoints for AI agent/tool integration.

### Test Connectivity

```http
POST /api/v1/agent/test/ping
Authorization: Bearer dev-key-change-in-production
```

### Seed Demo Data

```http
POST /api/v1/agent/seed
Authorization: Bearer dev-key-change-in-production
```

### Get OpenAPI Spec

```http
GET /api/v1/agent/spec/openapi?format=json
Authorization: Bearer dev-key-change-in-production
```

**Parameters:**
- `format` (string, default: "json")

### Get Tools Definition

```http
POST /api/v1/agent/spec/tools
Authorization: Bearer dev-key-change-in-production
```

### API Keys

#### List API Keys

```http
GET /api/v1/agent/keys
Authorization: Bearer dev-key-change-in-production
```

#### Create API Key

```http
POST /api/v1/agent/keys/create?name=my-agent&rate_limit_per_minute=100
Authorization: Bearer dev-key-change-in-production
```

**Parameters:**
- `name` (string, required)
- `description` (string, optional)
- `rate_limit_per_minute` (integer, default: 100)

#### Revoke API Key

```http
POST /api/v1/agent/keys/{key_id}/revoke
Authorization: Bearer dev-key-change-in-production
```

### Idempotent Operations

```http
POST /api/v1/agent/operations/idempotent/{operation_id}
Authorization: Bearer dev-key-change-in-production
Content-Type: application/json

{...}
```

Executes an operation idempotently — repeated calls with the same `operation_id` return the cached result.

### Operations Log

```http
GET /api/v1/agent/operations/log?limit=100
Authorization: Bearer dev-key-change-in-production
```

**Parameters:**
- `limit` (integer, default: 100)

---

## Admin / Tenants

### Public Tenant Endpoints

```http
GET /api/v1/tenants
GET /api/v1/tenants/current
```

### Admin Tenant Management

```http
GET    /api/v1/admin/tenants
POST   /api/v1/admin/tenants
GET    /api/v1/admin/tenants/{tenant_id}
DELETE /api/v1/admin/tenants/{tenant_id}
```

#### Create Tenant

```http
POST /api/v1/admin/tenants
Authorization: Bearer dev-key-change-in-production
Content-Type: application/json

{
  "id": "tenant-001",
  "name": "Demo Company AB",
  "api_key": "secret-key",
  "org_number": "556000-0000"
}
```

---

## Anomaly Detection

### Detect Anomalies

```http
GET /api/v1/anomalies?period_id=...&min_score=0.5&limit=50
Authorization: Bearer dev-key-change-in-production
```

**Parameters:**
- `period_id` (string, optional)
- `rule_types` (string, optional) - Comma-separated list
- `min_score` (float, default: 0.0)
- `limit` (integer, default: 50)

### Trigger Anomaly Scan

```http
POST /api/v1/anomalies/scan?period_id=...
Authorization: Bearer dev-key-change-in-production
```

### Anomaly Summary

```http
GET /api/v1/anomalies/summary?period_id=...
Authorization: Bearer dev-key-change-in-production
```

### List Anomaly Types

```http
GET /api/v1/anomalies/types
Authorization: Bearer dev-key-change-in-production
```

### Check Voucher Anomalies

```http
GET /api/v1/anomalies/voucher/{voucher_id}
Authorization: Bearer dev-key-change-in-production
```

### Update Thresholds

```http
PUT /api/v1/anomalies/thresholds
Authorization: Bearer dev-key-change-in-production
```

**Parameters (all optional):**
- `unusual_amount_z_score` (float)
- `min_transactions_for_stats` (integer)
- `frequent_small_tx_count` (integer)
- `small_tx_threshold` (integer)
- `balance_change_pct` (float)
- `duplicate_window_days` (integer)
- `voucher_count_z_score` (float)

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

## Interactive API Docs

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

All endpoints can be tested directly from these interfaces!
