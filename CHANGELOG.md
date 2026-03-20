# Changelog

All notable changes to this project will be documented in this file.

## [0.2.0] - 2026-03-21

### Added (Fas 2: Fakturering & Moms)

**Domain Models:**
- Invoice, InvoiceRow models with full lifecycle management
- Payment model for payment tracking
- CreditNote model for credit notes/refunds
- VAT code system (MP1 25%, MP2 12%, MP3 6%, MF 0%)

**Validation:**
- InvoiceValidator for business rules
- VATCalculator for VAT rate management
- Payment and credit note validation

**Repositories:**
- InvoiceRepository: full CRUD for invoices
- PaymentRepository: payment tracking
- CreditNoteRepository: credit note management

**Services:**
- InvoiceService: complete invoicing workflow
- Auto-booking to accounting system (creates vouchers)
- Payment registration with auto-vouchers
- Credit note creation with reversal logic

**API Routes:**
- `POST /api/v1/invoices` - Create invoice
- `GET /api/v1/invoices/{id}` - Get invoice details
- `POST /api/v1/invoices/{id}/send` - Send to customer
- `POST /api/v1/invoices/{id}/book` - Auto-book to ledger
- `POST /api/v1/invoices/{id}/payment` - Register payment
- `POST /api/v1/invoices/{id}/credit-note` - Create credit note

**Database:**
- Migration 002: invoices, invoice_rows, payments, credit_notes, vat_reports tables
- Automatic migration system

**Seed Data:**
- Enhanced with invoice examples
- Demonstrates full workflow: create → send → book → payment
- Partial payment example (50% of invoice)

### Improved

- Database migration system now auto-applies pending migrations
- More comprehensive test data
- Better error messages for validations

### Status
- Fas 2: Fakturering & Moms complete
- Ready for Fas 3: Rapporter & K2

---

## [0.1.0] - 2026-03-20

### Added (Fas 1: Grundbokföring)

**Core Features:**
- ✅ Append-only voucher storage (varaktighet)
- ✅ Period locking (irreversible)
- ✅ Double-entry bookkeeping with balance validation
- ✅ Correction vouchers (B-series)
- ✅ BAS 2026 Chart of Accounts
- ✅ Audit trail logging (behandlingshistorik)
- ✅ Trial balance & account ledger reports

**Domain Models:**
- FiscalYear, Period, Account models
- Voucher with immutable state management
- VoucherRow for accounting entries
- AuditLogEntry for compliance tracking

**Validation:**
- VoucherValidator: balance, account, period checks
- PeriodValidator: lock state management
- FiscalYearValidator

**Repositories:**
- VoucherRepository: append-only storage
- AccountRepository: BAS 2026 chart
- PeriodRepository: period management
- AuditRepository: audit trail

**Services:**
- LedgerService: core accounting logic
- Trial balance calculation
- Account ledger generation
- Audit history retrieval

**API Routes:**
- `POST /api/v1/vouchers` - Create voucher
- `GET /api/v1/vouchers/{id}` - Get voucher
- `POST /api/v1/vouchers/{id}/post` - Post (immutable)
- `GET /api/v1/accounts` - List accounts
- `POST /api/v1/fiscal-years` - Create fiscal year
- `POST /api/v1/periods/{id}/lock` - Lock period
- `GET /api/v1/reports/trial-balance` - Trial balance
- `GET /api/v1/reports/account/{code}` - Account ledger
- `GET /api/v1/reports/audit/{type}/{id}` - Audit history

**Database:**
- SQLite with append-only design
- Foreign key constraints & validation
- Comprehensive indexes for performance

**Docker:**
- Dockerfile with automatic DB init
- docker-compose.yml for one-command startup
- .dockerignore for clean builds

**Seed Data:**
- TestCorp AB company setup
- 4 sample vouchers (invoices, expenses)
- Locked March period demonstration
- Trial balance showcase

**Documentation:**
- README.md with overview
- SETUP.md with installation guide
- DOCKER.md with container usage
- Comprehensive docstrings

**Tests:**
- Voucher creation & posting
- Balance validation
- Trial balance calculation
- Period locking
- Correction vouchers
- Audit history

### Technical

**Stack:**
- Python 3.11+
- FastAPI for REST API
- SQLite for data storage
- Pydantic for validation
- pytest for testing

**Architecture:**
- Domain-driven design
- Repository pattern for data access
- Service layer for business logic
- Clean separation of concerns

**Regulatory Compliance:**
- BFL (Bokföringslagen)
- BFNAR 2013:2
- BAS 2026 standard
- 7-year data retention support

---

## [0.0.0] - Initial Setup

- Project structure
- Git repo initialized
- Basic configuration
