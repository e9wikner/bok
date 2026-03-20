# System Architecture

## Overview

Bokföringssystem is a Swedish accounting system API built with **domain-driven design** principles. It enforces regulatory compliance at the database and application layers while maintaining a clean, testable architecture.

## Core Principles

### 1. **Append-Only Storage (Varaktighet)**

Posted vouchers are **immutable** — never updated or deleted. This ensures regulatory compliance with Bokföringslagen (BFL §5).

```
Voucher Lifecycle:
draft → (edit/delete) → draft → posted (immutable)
                                   ↓
                        (correct via B-series only)
```

### 2. **Domain-Driven Design**

The system is organized around business domains, not technical layers:

```
├── domain/           # Business logic & entities
│   ├── models.py     # Domain models (Voucher, Account, etc)
│   ├── types.py      # Enums (VoucherStatus, AccountType)
│   └── validation.py # Business rules
├── services/         # Business logic services
├── repositories/     # Data access abstraction
└── api/              # HTTP API layer
```

### 3. **Layered Architecture**

```
┌─────────────────────────────────┐
│      HTTP API (FastAPI)         │
│  /api/v1/vouchers, /invoices    │
└─────────────────────────────────┘
              ↓
┌─────────────────────────────────┐
│   Services (Business Logic)     │
│ LedgerService, InvoiceService   │
└─────────────────────────────────┘
              ↓
┌─────────────────────────────────┐
│     Repositories (Data Access)  │
│  VoucherRepository, etc         │
└─────────────────────────────────┘
              ↓
┌─────────────────────────────────┐
│    Database (SQLite/SQL)        │
│  Append-only, immutable posts   │
└─────────────────────────────────┘
```

## Project Structure

```
bokfoering-api/
├── domain/
│   ├── models.py              # Voucher, Account, Period, etc.
│   ├── types.py               # Enums (VoucherStatus, AccountType)
│   ├── validation.py          # Business rules for Fas 1
│   ├── invoice_models.py      # Invoice, Payment, CreditNote (Fas 2)
│   └── invoice_validation.py  # Invoice rules & VAT calculation
│
├── services/
│   ├── ledger.py              # Core accounting (Fas 1)
│   └── invoice.py             # Invoicing & auto-booking (Fas 2)
│
├── repositories/
│   ├── voucher_repo.py        # Append-only voucher storage
│   ├── account_repo.py        # Chart of accounts (BAS 2026)
│   ├── period_repo.py         # Period management
│   ├── audit_repo.py          # Audit log
│   └── invoice_repo.py        # Invoices, payments, credits
│
├── db/
│   ├── database.py            # SQLite connection & migration
│   └── migrations/
│       ├── 001_initial_schema.sql  # Fas 1 tables
│       └── 002_add_invoices.sql    # Fas 2 tables
│
├── api/
│   ├── main.py                # FastAPI app setup
│   ├── schemas.py             # Pydantic request/response models
│   ├── deps.py                # Dependency injection
│   └── routes/
│       ├── vouchers.py        # POST, GET, POST /post
│       ├── accounts.py        # GET accounts
│       ├── periods.py         # POST fiscal-year, POST /lock
│       ├── reports.py         # Trial balance, ledger, audit
│       └── invoices.py        # POST, GET, POST /send, /book, /payment
│
├── scripts/
│   └── seed_test_data.py      # Generate TestCorp AB demo
│
├── tests/
│   ├── conftest.py            # pytest fixtures
│   └── test_ledger.py         # Fas 1 tests
│
├── Dockerfile                 # Container image
├── docker-compose.yml         # One-command startup
├── main.py                    # CLI entrypoint
├── config.py                  # Settings & env vars
└── requirements.txt           # Python dependencies
```

## Data Flow

### Voucher Posting (Fas 1)

```
1. Agent/User
    ↓
2. API: POST /api/v1/vouchers
    ↓
3. VoucherService.create_voucher()
    • Validate balance (debit = credit)
    • Validate accounts exist & active
    • Validate period is open
    ↓
4. VoucherRepository.create() + add_row()
    • Store in draft status
    ↓
5. AuditRepository.log("created")
    ↓
6. POST /api/v1/vouchers/{id}/post
    ↓
7. VoucherService.post_voucher()
    • Verify period still open
    • Change status → posted
    ↓
8. Database: UPDATE vouchers SET status='posted', posted_at=NOW()
    • Triggers prevent UPDATE/DELETE when status='posted'
    ↓
9. AuditRepository.log("posted")
    ✅ Immutable (varaktighet requirement met)
```

### Invoice Auto-Booking (Fas 2)

```
1. Agent: POST /api/v1/invoices
    ↓
2. InvoiceService.create_invoice()
    • Validate rows, dates, customer
    • Calculate VAT per row
    • Sum totals
    ↓
3. InvoiceRepository.create() + add_row()
    • Store in draft status
    ↓
4. Agent: POST /api/v1/invoices/{id}/send
    → Mark sent, set sent_at
    ↓
5. Agent: POST /api/v1/invoices/{id}/book
    ↓
6. InvoiceService.create_booking_for_invoice()
    • Group revenue by VAT code
    • Create double-entry voucher:
      - Debit: 1510 (Customer receivables) = amount_inc_vat
      - Credit: 3011 (Revenue) = amount_ex_vat
      - Credit: 2610 (VAT) = vat_amount
    ↓
7. LedgerService.create_voucher() + post_voucher()
    • Store accounting entry
    • Validate balance
    ↓
8. InvoiceRepository.link_voucher()
    • Link invoice to voucher
    ↓
9. Agent: POST /api/v1/invoices/{id}/payment
    ↓
10. InvoiceService.register_payment()
    • Update invoice paid_amount
    • Auto-create payment voucher (if period provided)
    ↓
11. LedgerService creates payment voucher:
    - Debit: 1010 (Bank) = payment_amount
    - Credit: 1510 (Customer receivables) = payment_amount
    ↓
12. ✅ Full audit trail: invoice → revenue entry → payment entry
```

## Database Design

### Append-Only Pattern

**Vouchers table:**
```sql
CREATE TABLE vouchers (
    id UUID PRIMARY KEY,
    series TEXT,           -- A (normal), B (correction)
    number INT,            -- Sequential per series
    status TEXT,           -- draft, posted
    date DATE,
    created_at TIMESTAMP,
    posted_at TIMESTAMP,
    -- Triggers prevent UPDATE/DELETE when status='posted'
);
```

**Immutability Enforced At:**
1. **Database Level:** SQL triggers block UPDATE/DELETE when status='posted'
2. **Application Level:** VoucherValidator checks before posting
3. **API Level:** No PATCH/PUT endpoints for posted vouchers

### Period Locking (Irreversible)

```sql
CREATE TABLE periods (
    id UUID PRIMARY KEY,
    fiscal_year_id UUID,
    month INT,
    locked BOOLEAN DEFAULT 0,
    locked_at TIMESTAMP,
    -- Triggers prevent unlock (locked=1 is one-way)
);
```

### Audit Trail

```sql
CREATE TABLE audit_log (
    id UUID PRIMARY KEY,
    entity_type TEXT,      -- voucher, invoice, period
    entity_id UUID,
    action TEXT,           -- created, posted, paid, locked
    actor TEXT,            -- user ID or "system"
    payload JSON,          -- Before/after values
    timestamp TIMESTAMP,
    -- Comprehensive history for compliance
);
```

## BAS 2026 Chart of Accounts

Accounts are organized by type:

```
1000-1999  Assets (Tillgångar)
  1510     Kundfordringar (Customer receivables)
  1010     PlusGiro/Bank

2000-2799  Liabilities & Equity (Skulder & Eget kapital)
  2610     Utgående moms 25% (Output VAT 25%)
  2640     Ingående moms (Input VAT)
  2900     Aktiekapital (Share capital)

3000-3999  Revenue (Intäkter)
  3011     Försäljning tjänster 25% (Service revenue 25% VAT)

4000-8999  Expenses (Kostnader)
  4020     Hyra (Rent)
  4040     Resor (Travel)
```

## Validation Layers

### 1. **Domain Validation**
- Voucher must balance (debit = credit)
- All accounts must exist and be active
- Period must be open for new vouchers

### 2. **Business Rule Validation**
- Posted vouchers can't be edited (only corrected)
- Periods can't be unlocked
- Invoice amounts must match row sums

### 3. **Data Integrity**
- Foreign key constraints
- NOT NULL checks
- CHECK constraints (dates, amounts > 0)

## API Security

### Authentication
- Bearer token (API key) in Authorization header
- Validated in `api/deps.py:verify_api_key()`

### Error Handling
```json
{
  "error": "Voucher rows do not balance",
  "code": "balance_error",
  "details": "debit and credit must be equal"
}
```

## Performance Considerations

### Indexes
```sql
CREATE INDEX idx_vouchers_period ON vouchers(period_id);
CREATE INDEX idx_vouchers_status ON vouchers(status);
CREATE INDEX idx_invoice_rows_invoice ON invoice_rows(invoice_id);
CREATE INDEX idx_payments_invoice ON payments(invoice_id);
```

### Queries
- Trial balance: Single scan of posted vouchers per period
- Account ledger: Filtered by account code + period
- Audit history: Indexed by entity_id

## Compliance

### Bokföringslagen (BFL)
- ✅ Varaktighet: Posted vouchers immutable
- ✅ Grundbokföring: Vouchers in registration order
- ✅ Huvudbokföring: Account ledgers in systematic order
- ✅ Verifikationer: Numbered sequentially, fully detailed
- ✅ Rättelser: Via correction vouchers (B-series), never edits
- ✅ Arkivering: 7-year retention via backups

### BFNAR 2013:2
- ✅ Systemdokumentation: Auto-generated
- ✅ Behandlingshistorik: Audit log
- ✅ Double-entry bookkeeping

### BAS 2026
- ✅ Standard chart of accounts
- ✅ Account type classification
- ✅ VAT code mapping

## Phases

| Phase | Name | Status | Focus |
|-------|------|--------|-------|
| 1 | Grundbokföring | ✅ Complete | Append-only, period locking, reports |
| 2 | Fakturering & Moms | 🚀 In Progress | Invoicing, VAT calculation, auto-booking |
| 3 | Rapporter & K2 | 📋 Planned | Income statement, balance sheet, annual report |
| 4 | Agent Integration | 🔌 Planned | OpenAPI spec, idempotent ops |

## Testing Strategy

**Unit Tests:**
- Domain validation rules
- VAT calculations
- Account ledger logic

**Integration Tests:**
- End-to-end voucher workflow
- Invoice → payment → ledger
- Period locking prevents posting

**Docker Testing:**
- Full app in container
- Seed data verification
- API endpoint smoke tests

## Future Improvements

- [ ] PostgreSQL support for production
- [ ] SIE4 export/import
- [ ] Advanced VAT reporting
- [ ] Multi-currency support
- [ ] Integration with Swedish banks
- [ ] GraphQL API option
- [ ] Web UI (optional)
