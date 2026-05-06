# Bokföringssystem API

Egenbyggt bokföringssystem med REST API för svenska aktiebolag. Uppfyller alla krav enligt Bokföringslagen (BFL) och BFNAR 2013:2.

**Licens:** MIT License — Fri att använda, modifiera och hosta för ditt eget företag. Se [LICENSE](LICENSE) för detaljer.

## 🚀 Quick Start

```bash
# Clone and start
git clone https://github.com/e9wikner/bok.git
cd bok
docker-compose up --build

# Access
# API: http://localhost:8000/docs
# Frontend: http://localhost:3000
# Login: admin / admin
```

**Status:** 🎉 **ALLA FASER KLARA + FAS 5 PÅGÅR**
- ✅ **Fas 1** – Grundbokföring (Klar)
- ✅ **Fas 2** – Fakturering & Moms (Klar)
- ✅ **Fas 3** – Rapporter & K2 (Klar)
- ✅ **Fas 4** – Agentintegration (Klar)
- ✅ **SIE4** – Import & Export (Klar)
- ✅ **PDF-export** – Fakturor & Rapporter (Klar)
- ✅ **Anomalidetektering** – Felprevention (Klar)
- 🚀 **Fas 5** – Bankintegration, Auto-kategorisering, BFL-compliance, Momsdeklaration

## Teknikstack

### Backend
- **Språk:** Python 3.10+
- **Ramverk:** FastAPI
- **Databas:** SQLite + migreringar
- **Övrigt:** Pydantic, SQLAlchemy, Alembic

### Frontend
- **Frontend:** Next.js 14 (React 18 + TypeScript)
- **Styling:** Tailwind CSS
- **State:** React Query + hooks
- **Mörkt läge:** Inbyggt stöd
- **Port:** 3000 (Docker) / 3000 (localhost)

## Huvudfunktioner

### ✅ Fas 1: Grundbokföring
- Append-only lagring av verifikationer (varaktighet – oföränderlighetskrav)
- Periodlåsning (oåterkallelig enligt BFL)
- Dubbel bokföring med automatisk validering
- Korrigeringsverifikationer (B-serie)
- Huvudboksuttag
- Komplett revisionsspår

### ✅ Fas 2: Fakturering & Moms
- Kundfakturahantering (utkast → skickad → betald)
- Automatisk momsberäkning (MP1 25%, MP2 12%, MP3 6%, MF 0%)
- Betalningsregistrering med flera metoder
- Kreditfakturor
- **Autobokföring:** Fakturor skapar automatiskt bokföringsverifikationer
- Betalningsbevakning och statusuppdateringar

### ✅ Fas 3: Rapporter & K2
- **K2-årsredovisningsgenerering** (för små företag)
- Autoberäkning av resultaträkning
- Autoberäkning av balansräkning
- Autoberäkning av kassaflödesanalys
- JSON-export för myndighetsinlämning
- Rapportstatusbevakning (utkast → slutlig → inlämnad)

### ✅ Fas 4: Agentintegration
- **OpenAPI 3.1-specifikation** för agentintegration
- **Tool-definieringar** för Claude/agent-användning
- API-nyckelhantering med detaljerade behörigheter
- Idempotenta operations-ID (retry-säkra för agenter)
- Agentoperationsloggning och revisionsspår
- Hastighetsbegränsning per API-nyckel
- Anslutningstestningsendpoints

### ✅ SIE4 Import & Export
- **SIE4 Import:** Importera bokföringsdata från andra system
  - Stöd för Windows-1252 och ISO-8859-1 teckenkodning
  - Automatisk kontoskapning vid import
  - Validering av SIE4-format före import
- **SIE4 Export:** Exportera till SIE4-format för andra bokföringsprogram
  - Alla obligatoriska SIE4-sektioner: #FLAGGA, #FORMAT, #GEN, #PROGRAM, #SIETYP, #FNAMN, #FORGN, #ADRESS, #RAR, #KPTYP, #KONTO, #SRU, #IB, #UB, #RES, #PSALDO, #VER, #TRANS
  - Automatisk beräkning av IB (ingående balans), UB (utgående balans), RES (resultat) och PSALDO (periodsaldon)
  - Windows-1252 teckenkodning med CRLF radbrytningar
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
- Huvudbok per konto – PDF
- Alla med logotyp, datum, period

**Teknik:**
- Jinja2 template engine med professionella HTML-mallar
- WeasyPrint för HTML→PDF rendering
- HTML-fallback för utveckling (kräver inte WeasyPrint)
- Konfigurerbar företagsinformation via API-parametrar

**API-endpoints:**
- `GET /api/v1/export/pdf/invoice/{id}` – Faktura-PDF
- `GET /api/v1/export/pdf/general-ledger/{account_code}?period_id=...` – Huvudbok-PDF
- `GET /api/v1/export/pdf/income-statement/{period_id}` – Resultaträkning-PDF
- `GET /api/v1/export/pdf/balance-sheet/{period_id}` – Balansräkning-PDF
- `GET /api/v1/export/pdf/k2-report/{fiscal_year_id}` – K2-årsredovisning-PDF
- `GET /api/v1/export/pdf/.../html` – HTML-fallback för alla ovan

### 🧠 AI Learning (Maskininlärning)
Systemets agentlärande bygger på ett levande Markdown-dokument med generella
bokföringsinstruktioner. Agenten läser instruktionerna ungefär som en
`AGENTS.md`-fil, hämtar historiska verifikationer och korrigeringar via API:t,
och bokför därefter direkt som postade verifikationer.

**Hur det fungerar:**
1. Agenten läser aktuella bokföringsinstruktioner från backend.
2. Agenten läser tidigare postade verifikationer och korrigeringar via API:t.
3. Agenten uppdaterar instruktionerna när historiken visar bättre generell vägledning.
4. Agenten skapar och postar verifikationer direkt.
5. Användaren granskar i frontend och rättar fel i efterhand.
6. Rättelser skapas som spårbara B-serie-korrigeringar och blir ny inlärningsdata.

**Principer:**
- Backend fattar inte bokföringsbeslutet, men validerar formella krav.
- Agenten använder Markdown-instruktioner och historik som kontext.
- Postade verifikationer ändras inte direkt; fel rättas med korrigeringsverifikation.
- Frontend är en mänsklig gransknings- och korrigeringsyta.

**API-endpoints:**
- `GET /api/v1/agent-instructions/accounting` – Läs aktivt instruktionsdokument
- `PUT /api/v1/agent-instructions/accounting` – Uppdatera instruktioner och skapa ny version
- `GET /api/v1/agent-instructions/accounting/versions` – Versionshistorik
- `POST /api/v1/agent/vouchers` – Agenten skapar och postar verifikation direkt
- `POST /api/v1/vouchers/{id}/correct` – Skapa postad B-serie-korrigering
- `GET /api/v1/accounting-corrections` – Lista korrigeringar för agentens inlärning

**Integration:**
Äldre learning rules och backtest finns kvar som analysstöd, men de ska inte vara
den primära mekanismen för agentens beslut. Den primära mekanismen är det aktiva
instruktionsdokumentet plus historiken som agenten läser via API:t.

## Projektstruktur

```
bokfoering-api/
├── db/
│   ├── migrations/
│   │   ├── 001_initial_schema.sql       # Fas 1: Core tables
│   │   ├── 002_add_invoices.sql         # Fas 2: Invoice tables
│   │   ├── 003_add_reports_and_k2.sql   # Fas 3 & 4: Reports + Agent
│   │   ├── 004_add_company_info.sql     # Company metadata
│   │   ├── 005_add_bank_and_categorization.sql  # Bank integration
│   │   ├── 006_add_learning_rules.sql   # Legacy AI learning tables
│   │   ├── 013_add_agent_instructions.sql # Agent instruction versions
│   │   └── 014_add_posted_voucher_immutability_triggers.sql
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
│   │   ├── agent_instructions.py # Agent instruction documents
│   │   ├── accounting_corrections.py # Agent-readable corrections
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
│   ├── agent_instruction_repo.py
│   ├── account_repo.py
│   ├── period_repo.py
│   ├── invoice_repo.py
│   └── audit_repo.py
├── config.py
├── main.py                      # CLI entrypoint
└── requirements.txt
```

## Snabbstart

### Docker (Rekommenderad)
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

### Lokal installation - Frontend
```bash
cd frontend-v3
npm install
npm run dev
# Besök sedan http://localhost:3000
```

### Miljövariabler
```bash
# Backend
export API_KEY=dev-key-change-in-production
export DATABASE_URL=sqlite:///bokfoering.db

# Frontend
export NEXT_PUBLIC_API_URL=http://localhost:8000
export NEXT_PUBLIC_API_KEY=dev-key-change-in-production
```

## Dokumentation

### Kärndokumentation
- **[API.md](API.md)** - Komplett endpoint-referens med exempel
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Systemdesign & dataflöde
- **[FAS3_FAS4.md](FAS3_FAS4.md)** - K2-rapporter & agentintegration

### Frontend
- **[frontend-v3/README.md](frontend-v3/README.md)** - Frontend-guide
  - Arkitektur & komponenter
  - Routes & sidor
  - AI-inlärningsarbetsflöde
  - Utvecklingsguide
  - Deploymentsinstruktioner

### Deployment
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - 🚀 Komplett deployment-guide
  - Docker-deployment on-premise
  - Hetzner Cloud-deployment (Console, API, Terraform)
  - SSL/TLS-konfiguration med Let's Encrypt
  - Monitorering & loggning
  - Backup-strategi & automatisering
  - Produktions-docker-compose-konfiguration

## Reglering och Compliance

✅ **BFL (Bokföringslagen)**
- Varaktighet: Bokförda verifikationer oföränderliga
- Grundbokföring: Kronologisk journal
- Huvudbokföring: Systematisk huvudbok
- Verifikationer: Nummerade, fullständigt detaljerade
- Rättelser: Endast via korrigeringsverifikationer
- Systemdokumentation: Automatiskt loggad

✅ **BFNAR 2013:2**
- Vägledning för bokföring
- Systemdokumentation
- Behandlingshistorik (revisionsspår)

✅ **BAS 2026**
- Standard kontoplan
- Kontotypklassificering
- Momskodsmappning

✅ **K2 Årsredovisning**
- Generering av resultaträkning
- Generering av balansräkning
- Obligatoriska noter & upplysningar

✅ **Mervärdesskattelagen (VAT)**
- 4 momskoder (MP1-MP3, MF)
- Automatisk beräkning
- Momsuppdelningsrapportering

## Fas 5: Bankintegration & AI-Automatisering

### 🏦 Bankintegration
- Bankanslutningshantering (manuell + Open Banking redo)
- Transaktionsimport (JSON API + Svensk bank CSV)
- Transaktionsdeduplicering (baserat på external_id)
- Synkroniseringsstatusbevakning

### 🤖 Auto-kategorisering
- Agentstyrd bokföring baserad på levande Markdown-instruktioner
- Agenten läser historiska verifikationer och korrigeringar via API:t
- Direktpostning av agentverifikationer med backendvalidering
- Rättelser sker via B-serie och blir ny inlärningsdata
- Äldre regel-/mönsteranalys används som beslutsunderlag, inte som hårt facit

### ✅ BFL Compliance-kontroll
- 8 automatiserade compliance-kontroller:
  - Bokföringstillfällighet (BFL 5 kap 2§)
  - Periodavslutningsdeadlines
  - Verifikationsnummerluckor (BFL 5 kap 6§)
  - Råbalansnoggrannhet
  - Momsdeklarationsdeadlines
  - Obokförda transaktionsbackloggar
  - Saknade verifikationsbilagor
  - Flagging av ovanligt stora transaktioner
- Ärendelifecykel: öppen → kvitterad → löst / falskt positiv

### 🧾 Momsdeklarationer
- Generering av månadsvisa och kvartalsvisa momsdeklarationer
- SKV 4700 formatmappning (Ruta 05-49)
- Automatisk beräkning från bokförda verifikationer
- Försäljningsuppdelning efter momssats (25%, 12%, 6%, undantagen)
- Nettomoms att betala/få tillbaka beräkning
