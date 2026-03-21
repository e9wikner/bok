# Bokföringssystem API

Egenbyggt bokföringssystem med REST API för svenska aktiebolag. Uppfyller alla krav enligt Bokföringslagen (BFL) och BFNAR 2013:2.

**Status:** 🎉 **ALL PHASES COMPLETE + FAS 5 IN PROGRESS**
- ✅ **Fas 1** – Grundbokföring (Complete)
- ✅ **Fas 2** – Fakturering & Moms (Complete)
- ✅ **Fas 3** – Rapporter & K2 (Complete)
- ✅ **Fas 4** – Agent Integration (Complete)
- ✅ **SIE4** – Import & Export (Complete)
- 🚀 **Fas 5** – Bank Integration, Auto-Kategorisering, BFL Compliance, Momsdeklaration

## Stack

- **Language:** Python 3.10+
- **Framework:** FastAPI
- **Database:** SQLite + migrations
- **Other:** Pydantic, SQLAlchemy, Alembic

## Key Features

### ✅ Fas 1: Grundbokföring (Basic Accounting)
- Append-only voucher storage (varaktighet - immutability requirement)
- Period locking (irreversible per BFL)
- Double-entry bookkeeping with automatic validation
- Correction vouchers (B-series)
- Trial balance & account ledger reports
- Complete audit trail

### ✅ Fas 2: Fakturering & Moms (Invoicing & VAT)
- Customer invoice management (draft → sent → paid)
- Automatic VAT calculation (MP1 25%, MP2 12%, MP3 6%, MF 0%)
- Payment registration with multiple methods
- Credit notes (kreditfakturor)
- **Auto-booking:** Invoices automatically create accounting vouchers
- Payment tracking & status updates

### ✅ Fas 3: Rapporter & K2 (Annual Reports)
- **K2 Annual Report Generation** (Årsredovisning för små företag)
- Auto-calculate Income Statement (Resultaträkning)
- Auto-calculate Balance Sheet (Balansräkning)
- Auto-calculate Cash Flow Statement
- JSON export for authority submission
- Report status tracking (draft → finalized → submitted)

### ✅ Fas 4: Agent Integration
- **OpenAPI 3.1 specification** for agent integration
- **Tool definitions** for Claude/agent use
- API key management with granular permissions
- Idempotent operation IDs (retry-safe for agents)
- Agent operation logging & audit trail
- Rate limiting per API key
- Connectivity testing endpoints

### ✅ SIE4 Import & Export
- **SIE4 Import:** Import bokföringsdata från andra system
  - Stöd för Windows-1252 och ISO-8859-1 encoding
  - Automatisk kontoskapning vid import
  - Validering av SIE4-format innan import
- **SIE4 Export:** Exportera till SIE4-format för andra bokföringsprogram
  - Alla obligatoriska SIE4-sektioner: #FLAGGA, #FORMAT, #GEN, #PROGRAM, #SIETYP, #FNAMN, #FORGN, #ADRESS, #RAR, #KPTYP, #KONTO, #SRU, #IB, #UB, #RES, #PSALDO, #VER, #TRANS
  - Automatisk beräkning av IB (ingående balans), UB (utgående balans), RES (resultat) och PSALDO (periodsaldon)
  - Windows-1252 encoding med CRLF radbrytningar
  - Filnedladdning eller JSON-svar
  - Export → Import roundtrip verifierad

## Project Structure

```
bokfoering-api/
├── db/
│   ├── migrations/
│   │   ├── 001_initial_schema.sql       # Fas 1: Core tables
│   │   ├── 002_add_invoices.sql         # Fas 2: Invoice tables
│   │   └── 003_add_reports_and_k2.sql   # Fas 3 & 4: Reports + Agent
│   └── database.py
├── domain/
│   ├── models.py                # Voucher, Account, Period
│   ├── invoice_models.py        # Invoice, Payment, CreditNote
│   ├── validation.py            # Voucher business rules
│   ├── invoice_validation.py    # Invoice rules & VAT
│   └── types.py                 # Enums
├── services/
│   ├── ledger.py                # Fas 1: Core accounting
│   ├── invoice.py               # Fas 2: Invoicing
│   ├── k2_report.py             # Fas 3: K2 report generation
│   ├── sie4_import.py           # SIE4: Parser & import
│   └── sie4_export.py           # SIE4: Filgenerering & export
├── api/
│   ├── routes/
│   │   ├── vouchers.py          # Fas 1: Voucher endpoints
│   │   ├── accounts.py          # Account management
│   │   ├── periods.py           # Period management
│   │   ├── reports.py           # Trial balance, ledger, audit
│   │   ├── invoices.py          # Fas 2: Invoice endpoints
│   │   ├── k2_reports.py        # Fas 3: K2 report endpoints
│   │   ├── agent.py             # Fas 4: Agent integration
│   │   ├── import_sie4.py       # SIE4: Import endpoints
│   │   └── export_sie4.py       # SIE4: Export endpoints
│   ├── schemas.py               # Pydantic models
│   ├── deps.py                  # Dependency injection
│   └── main.py                  # FastAPI app
├── repositories/
│   ├── voucher_repo.py
│   ├── account_repo.py
│   ├── period_repo.py
│   ├── invoice_repo.py
│   └── audit_repo.py
├── config.py
├── main.py                      # CLI entrypoint
└── requirements.txt
```

## Quick Start

### Docker (Recommended)
```bash
docker-compose up --build
# Server: http://localhost:8000
# API Docs: http://localhost:8000/docs
# Test data: TestCorp AB (auto-seeded)
```

### Local Setup
```bash
pip install -r requirements.txt
python main.py --init-db --seed
python main.py
# Then visit http://localhost:8000/docs
```

## Documentation

- **[QUICKSTART.md](QUICKSTART.md)** - 2-minute setup guide
- **[API.md](API.md)** - Complete endpoint reference with examples
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System design & data flow
- **[FAS3_FAS4.md](FAS3_FAS4.md)** - K2 reports & agent integration
- **[DEMO.md](DEMO.md)** - Detailed feature demonstration
- **[STATUS.md](STATUS.md)** - Project status report
- **[CHANGELOG.md](CHANGELOG.md)** - Version history

## Regulatory Compliance

✅ **BFL (Bokföringslagen)**
- Varaktighet: Posted vouchers immutable
- Grundbokföring: Chronological journal
- Huvudbokföring: Systematic ledger
- Verifikationer: Numbered, fully detailed
- Rättelser: Via correction vouchers only
- Systemdokumentation: Auto-logged

✅ **BFNAR 2013:2**
- Bokföring vägledning
- Systemdokumentation
- Behandlingshistorik (audit trail)

✅ **BAS 2026**
- Standard chart of accounts
- Account type classification
- VAT code mapping

✅ **K2 Årsredovisning**
- Income statement generation
- Balance sheet generation
- Mandatory notes & disclosures

✅ **Mervärdesskattelagen (VAT)**
- 4 VAT codes (MP1-MP3, MF)
- Automatic calculation
- VAT breakdown reporting

## Fas 5: Bank Integration & AI-Automatisering

### 🏦 Bank Integration
- Bank connection management (manual + Open Banking ready)
- Transaction import (JSON API + Swedish bank CSV)
- Transaction deduplication (external_id based)
- Sync status tracking

### 🤖 Auto-Kategorisering
- Rule-based engine with 18 pre-loaded Swedish business patterns
- Keyword, regex, counterpart, and amount-range matching
- **AI-learning:** System learns from user corrections
- Auto-booking of high-confidence matches (≥90%)
- Covers: telecom, rent, fuel, insurance, software, bank fees, Swish, etc.

### ✅ BFL Compliance Checker
- 8 automated compliance checks:
  - Booking timeliness (BFL 5 kap 2§)
  - Period closing deadlines
  - Voucher sequence gaps (BFL 5 kap 6§)
  - Trial balance accuracy
  - VAT declaration deadlines
  - Unbooked transaction backlogs
  - Missing voucher attachments
  - Unusually large transaction flagging
- Issue lifecycle: open → acknowledged → resolved / false positive

### 🧾 VAT Declarations (Momsdeklaration)
- Monthly and quarterly VAT declaration generation
- SKV 4700 format mapping (Ruta 05-49)
- Automatic calculation from booked vouchers
- Sales breakdown by VAT rate (25%, 12%, 6%, exempt)
- Net VAT to pay/receive calculation
