# Bokföringssystem API

Egenbyggt bokföringssystem med REST API för svenska aktiebolag. Uppfyller alla krav enligt Bokföringslagen (BFL) och BFNAR 2013:2.

**Status:** 🎉 **ALL PHASES COMPLETE + FAS 5 IN PROGRESS**
- ✅ **Fas 1** – Grundbokföring (Complete)
- ✅ **Fas 2** – Fakturering & Moms (Complete)
- ✅ **Fas 3** – Rapporter & K2 (Complete)
- ✅ **Fas 4** – Agent Integration (Complete)
- ✅ **SIE4** – Import & Export (Complete)
- ✅ **PDF Export** – Fakturor & Rapporter (Complete)
- ✅ **Anomalidetektering** – Felprevention (Complete)
- 🚀 **Fas 5** – Bank Integration, Auto-Kategorisering, BFL Compliance, Momsdeklaration

## Stack

### Backend
- **Language:** Python 3.10+
- **Framework:** FastAPI
- **Database:** SQLite + migrations
- **Other:** Pydantic, SQLAlchemy, Alembic

### Frontend
- **Frontend v2:** Next.js 14 (React 18 + TypeScript)
- **Styling:** Tailwind CSS
- **State:** React Query + hooks
- **Dark mode:** Native support
- **Port:** 3000 (Docker) / 3000 (localhost)

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

### ✅ PDF Export (Fakturor & Rapporter)
Professionell PDF-export för alla företagsdokument med svenska termer och format:

**Fakturor:**
- Professionell layout med företagslogga och info
- Svenska termer (Fakturadatum, Förfallodatum, Summa, etc.)
- QR-kod för Swish-betalning
- Momsspecifikation per momskod (MP1 25%, MP2 12%, MP3 6%, MF 0%)
- Betalningsinstruktioner (Swish, bankgiro, plusgiro, IBAN)
- Footer med organisationsnummer, momsregistreringsnummer, F-skatt

**Rapporter:**
- Resultaträkning (P&L) – PDF
- Balansräkning – PDF
- K2-årsredovisning – PDF
- Råbalans (Trial Balance) – PDF
- Huvudbok per konto – PDF
- Alla med logotyp, datum, period

**Teknik:**
- Jinja2 template engine med professionella HTML-mallar
- WeasyPrint för HTML→PDF rendering
- HTML-fallback för utveckling (kräver inte WeasyPrint)
- Konfigurerbar företagsinformation via API-parametrar

**API-endpoints:**
- `GET /api/v1/export/pdf/invoice/{id}` – Faktura-PDF
- `GET /api/v1/export/pdf/trial-balance/{period_id}` – Råbalans-PDF
- `GET /api/v1/export/pdf/general-ledger/{account_code}?period_id=...` – Huvudbok-PDF
- `GET /api/v1/export/pdf/income-statement/{period_id}` – Resultaträkning-PDF
- `GET /api/v1/export/pdf/balance-sheet/{period_id}` – Balansräkning-PDF
- `GET /api/v1/export/pdf/k2-report/{fiscal_year_id}` – K2-årsredovisning-PDF
- `GET /api/v1/export/pdf/.../html` – HTML-fallback för alla ovan

### 🧠 AI Learning (Maskininlärning)
Systemet lär sig automatiskt från användares korrigeringar för att förbättra framtida kategorisering:

**Hur det fungerar:**
1. Användare korrigerar en felaktig bokföring
2. Systemet analyserar skillnaden mellan original och korrigering
3. En learning rule skapas/uppdateras med mönster (keyword, regex, motpart, belopp)
4. Framtida transaktioner med liknande mönster föreslås automatiskt
5. Confidence ökar med varje lyckad användning

**Regeltyper:**
- `keyword` – Matcha nyckelord i beskrivning (t.ex. "resa" → 5610)
- `regex` – Regex-mönster för avancerad matchning
- `counterparty` – Matcha motpartsnamn (t.ex. "Telia" → 4020)
- `amount_range` – Beloppsintervall (t.ex. 1000-5000 kr)
- `composite` – Kombination av flera villkor (JSON)

**Confidence & Golden Rules:**
- Confidence: 0.0–1.0 (börjar på 0.5, ökar med lyckade användningar)
- Golden: Manuellt bekräftad av redovisningskonsult (confidence = 1.0)
- Threshold: Endast regler med confidence ≥ 0.8 används automatiskt

**API-endpoints:**
- `POST /api/v1/learning/corrections` – Spela in korrigering och lär av den
- `GET /api/v1/learning/rules` – Lista alla inlärda regler
- `GET /api/v1/learning/rules/{id}` – Hämta specifik regel
- `PUT /api/v1/learning/rules/{id}/confirm` – Bekräfta regel (golden)
- `DELETE /api/v1/learning/rules/{id}` – Inaktivera felaktig regel
- `GET /api/v1/learning/stats` – Statistik om AI-lärande
- `GET /api/v1/learning/suggest` – Föreslå konto baserat på inlärda regler

**Integration:**
LearningService är integrerat i CategorizationService och kontrolleras först vid auto-kategorisering, före standardregler.

## Project Structure

```
bokfoering-api/
├── db/
│   ├── migrations/
│   │   ├── 001_initial_schema.sql       # Fas 1: Core tables
│   │   ├── 002_add_invoices.sql         # Fas 2: Invoice tables
│   │   ├── 003_add_reports_and_k2.sql   # Fas 3 & 4: Reports + Agent
│   │   ├── 004_add_company_info.sql     # Company metadata
│   │   ├── 005_add_bank_and_categorization.sql  # Bank integration
│   │   └── 006_add_learning_rules.sql   # AI learning tables
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
│   ├── sie4_export.py           # SIE4: Filgenerering & export
│   ├── pdf_export.py            # PDF: Fakturor & rapporter
│   ├── categorization.py        # Auto-kategorisering
│   ├── learning.py              # AI learning från korrigeringar
│   ├── bank_integration.py      # Bankintegration
│   ├── compliance.py            # BFL compliance
│   └── vat_report.py            # Momsdeklaration
├── templates/
│   └── pdf/                     # Jinja2-mallar för PDF
│       ├── base.html            # Grundmall med header/footer
│       ├── invoice.html         # Fakturamall
│       ├── income_statement.html
│       ├── balance_sheet.html
│       ├── trial_balance.html
│       ├── general_ledger.html
│       └── k2_report.html
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
│   │   ├── export_sie4.py       # SIE4: Export endpoints
│   │   ├── export_pdf.py        # PDF: Fakturor & rapporter
│   │   ├── bank.py              # Bankintegration
│   │   ├── compliance.py        # BFL compliance
│   │   └── vat.py               # Momsdeklaration
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
# API Server: http://localhost:8000
# API Docs: http://localhost:8000/docs
# Frontend v2: http://localhost:3000 ✨ NEW
# Streamlit (old): http://localhost:8501
# Test data: TestCorp AB (auto-seeded)
```

### Local Setup - Backend
```bash
pip install -r requirements.txt
python main.py --init-db --seed
python main.py
# Then visit http://localhost:8000/docs
```

### Local Setup - Frontend
```bash
cd frontend-v3
npm install
npm run dev
# Then visit http://localhost:3000
```

### Environment Variables
```bash
# Backend
export API_KEY=dev-key-change-in-production
export DATABASE_URL=sqlite:///bokfoering.db

# Frontend
export NEXT_PUBLIC_API_URL=http://localhost:8000
export NEXT_PUBLIC_API_KEY=dev-key-change-in-production
```

## Documentation

### Core
- **[QUICKSTART.md](QUICKSTART.md)** - 2-minute setup guide
- **[API.md](API.md)** - Complete endpoint reference with examples
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System design & data flow
- **[FAS3_FAS4.md](FAS3_FAS4.md)** - K2 reports & agent integration
- **[DEMO.md](DEMO.md)** - Detailed feature demonstration
- **[CHANGELOG.md](CHANGELOG.md)** - Version history

### Frontend
- **[frontend-v3/README.md](frontend-v3/README.md)** - Frontend guide
  - Architecture & components
  - Routes & pages
  - AI-learning workflow
  - Development guide
  - Deployment instructions

### Deployment
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - 🚀 Complete deployment guide
  - On-premise Docker deployment
  - Hetzner Cloud deployment (Console, API, Terraform)
  - SSL/TLS configuration with Let's Encrypt
  - Monitoring & logging setup
  - Backup strategy & automation
  - Production docker-compose configuration
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
