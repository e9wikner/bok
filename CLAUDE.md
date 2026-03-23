# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Bokföringssystem** — a Swedish accounting system REST API with Next.js frontend. Built for compliance with Swedish accounting law (BFL, BFNAR 2013:2) using double-entry bookkeeping with immutable audit trails.

## Commands

### Backend (Python/FastAPI)

```bash
# Setup
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Initialize DB and seed test data (one-time)
python main.py --init-db --seed

# Run API server
python main.py                          # 127.0.0.1:8000
python main.py --host 0.0.0.0 --port 8000

# Run tests
pytest tests/ -v
pytest tests/test_ledger.py -v          # Single test file
pytest tests/test_ledger.py::test_name  # Single test

# Linting / formatting
black .
isort .
flake8                                  # Config: ignores E203, E266, E501, W503
mypy .
```

### Frontend (Next.js 14)

```bash
cd frontend-v3   # Frontend (port 3000)
npm install
npm run dev
npm run build
npm run lint
```

### Docker

```bash
docker-compose up --build   # Starts all services (API :8000, frontend :3000)
```

## Architecture

### Layered Backend

```
api/routes/        → HTTP endpoints (FastAPI, delegate to services)
services/          → Business logic (orchestrate domain + repositories)
repositories/      → Data access (SQL queries, abstraction over DB)
domain/            → Pure models, types, validation rules
db/                → SQLite manager, migrations (SQL files in db/migrations/)
```

### Core Principle: Append-Only Storage (BFL Compliance)

Posted vouchers are **never** modified or deleted. This is enforced at three levels:
1. **SQL triggers** — prevent UPDATE/DELETE on posted vouchers
2. **Service layer** — `VoucherValidator` checks before posting
3. **API layer** — no PATCH/PUT endpoints for posted resources

Corrections must use B-series reversal vouchers. Period locking is irreversible.

### Voucher Lifecycle

```
draft → (editable) → posted (immutable)
                          ↓
               corrections via B-series only
```

### Key Services

| Service | File | Responsibility |
|---------|------|----------------|
| `LedgerService` | `services/ledger.py` | Create, post, lock vouchers |
| `InvoiceService` | `services/invoice.py` | Invoices, payments, VAT auto-booking |
| `K2ReportService` | `services/k2_report.py` | Annual report generation |
| `SIE4ImportService` | `services/sie4_import.py` | SIE4 format parsing |
| `SIE4ExportService` | `services/sie4_export.py` | SIE4 format generation |
| `PDFExportService` | `services/pdf_export.py` | Jinja2/WeasyPrint PDF rendering |
| `AnomalyDetectionService` | `services/anomaly_detection.py` | 9 types of fraud/error detection |
| `CategorizationService` | `services/categorization.py` | Rule-based auto-booking |
| `LearningService` | `services/learning.py` | Learn from user corrections |
| `ComplianceService` | `services/compliance.py` | BFL regulatory checks |

### Database

- **SQLite** (dev) with WAL mode and thread-local connections (required for FastAPI/uvicorn thread safety)
- Migrations are plain SQL files in `db/migrations/` numbered 001–006
- Key tables: `vouchers`, `voucher_rows`, `periods`, `fiscal_years`, `accounts`, `invoices`, `payments`, `audit_log`

### Invoice Auto-Booking Flow

When an invoice is booked, `InvoiceService` generates a balanced double-entry voucher:
- Debit 1510 (receivables) = total incl. VAT
- Credit 3011 (revenue) = excl. VAT
- Credit 2610 (VAT output) = VAT amount

Payment registration creates a second voucher: debit 1010 (bank), credit 1510 (receivables).

### Frontend

`frontend-v3/` is the frontend (Next.js 14 App Router, React Query, Tailwind CSS, Radix UI).

API client is in `frontend-v3/lib/api.ts` (Axios). Server state is managed with `@tanstack/react-query`.

### Configuration

`config.py` reads from environment variables:
- `DATABASE_URL` — defaults to `sqlite:////tmp/bokfoering.db`
- `API_KEY` — defaults to `dev-key-change-in-production`
- `DEBUG` — boolean flag

### CI/CD

- **tests.yml** — pytest + black + isort + flake8 + mypy (all `continue-on-error: true`)
- **docker-build.yml** — Docker build, health check, Trivy security scan
