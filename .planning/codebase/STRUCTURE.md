# Codebase Structure

**Analysis Date:** 2026-05-14

## Directory Layout

```text
bok/
├── api/                  # FastAPI app wiring, deps, schemas, and route handlers
├── services/             # Business logic orchestration layer
├── repositories/         # SQL data-access layer
├── domain/               # Core dataclasses, enums, and domain validation
├── db/                   # DB runtime + SQL migrations
├── frontend-v3/          # Next.js frontend (App Router)
├── tests/                # Pytest suite (API + service integration-focused)
├── scripts/              # Utility scripts (seed/setup/import helpers)
├── proxy/                # Nginx/reverse-proxy config
├── terraform/            # Infrastructure definitions
├── main.py               # Backend process entrypoint
└── config.py             # Centralized backend settings
```

## Directory Purposes

**`api/`:**
- Purpose: HTTP transport boundary.
- Contains: `main.py`, `deps.py`, `schemas.py`, `routes/*.py`, middleware package.
- Key files: `api/main.py`, `api/routes/vouchers.py`, `api/deps.py`.

**`services/`:**
- Purpose: Business use-cases and orchestration.
- Contains: Ledger, invoice, VAT, payroll, import/export, compliance services.
- Key files: `services/ledger.py`, `services/invoice.py`, `services/payroll.py`.

**`repositories/`:**
- Purpose: Encapsulate SQL and persistence mapping.
- Contains: Entity-specific repositories and audit/system-instruction storage logic.
- Key files: `repositories/voucher_repo.py`, `repositories/account_repo.py`, `repositories/audit_repo.py`.

**`domain/`:**
- Purpose: Domain model and validation primitives.
- Contains: Dataclasses, enums/types, invoice/payroll validation/model files.
- Key files: `domain/models.py`, `domain/types.py`, `domain/validation.py`.

**`db/`:**
- Purpose: DB connection lifecycle and schema evolution.
- Contains: `database.py` and incremental SQL migrations.
- Key files: `db/database.py`, `db/migrations/001_initial_schema.sql`.

**`frontend-v3/`:**
- Purpose: User-facing UI and API consumption.
- Contains: App Router routes, shared components, hooks, lib API client, assets/config.
- Key files: `frontend-v3/app/layout.tsx`, `frontend-v3/hooks/useData.ts`, `frontend-v3/lib/api.ts`.

## Key File Locations

**Entry Points:**
- `main.py`: Backend CLI/server startup and DB initialization flow.
- `api/main.py`: FastAPI ASGI app assembly and route registration.
- `frontend-v3/app/layout.tsx`: Global frontend composition (providers + auth + shell).

**Configuration:**
- `config.py`: Backend settings via environment.
- `requirements.txt`: Python dependency set.
- `frontend-v3/package.json`: Frontend dependencies and scripts.
- `frontend-v3/next.config.mjs`: Next.js runtime/build config.
- `frontend-v3/tsconfig.json`: TypeScript config + alias behavior.

**Core Logic:**
- `services/`: Domain workflows and invariants coordination.
- `repositories/`: SQL persistence operations.
- `domain/`: Data structures and business rule validation.

**Testing:**
- `tests/conftest.py`: Shared fixtures/test setup.
- `tests/test_api.py`: API route behavior coverage.
- `tests/test_ledger.py`: Ledger workflow checks.

## Naming Conventions

**Files:**
- Backend modules use `snake_case.py` by responsibility, e.g. `invoice_draft_repo.py`, `tax_ink2.py`.
- Frontend route files follow Next.js `page.tsx` and `layout.tsx` conventions in nested folders, e.g. `frontend-v3/app/invoices/[id]/page.tsx`.
- Shared frontend primitives use PascalCase component files, e.g. `frontend-v3/components/AuthGuard.tsx`.

**Directories:**
- Backend layer directories are singular by concern: `api`, `services`, `repositories`, `domain`, `db`.
- Frontend App Router uses URL-segment directories under `frontend-v3/app`.

## Where to Add New Code

**New Backend Feature:**
- Primary code: Add route in `api/routes/` and corresponding service in `services/`.
- Persistence: Add repository methods in `repositories/` and migration in `db/migrations/` if schema changes.
- Tests: Add coverage in `tests/test_<feature>.py`.

**New Frontend Feature:**
- Route/page: Add under `frontend-v3/app/<segment>/page.tsx`.
- Data-fetch hook: Add to `frontend-v3/hooks/useData.ts` (or feature hook file if split later).
- API wrapper/types: Add endpoint + types in `frontend-v3/lib/api.ts`.

**New Component/Module:**
- UI component: `frontend-v3/components/` or `frontend-v3/components/ui/` for reusable primitives.
- Domain object/validation: `domain/`.

**Utilities:**
- Backend operational scripts: `scripts/`.
- Frontend helpers: `frontend-v3/lib/`.

## Special Directories

**`.planning/codebase/`:**
- Purpose: Generated architecture/quality/stack mapping artifacts for planner/executor agents.
- Generated: Yes.
- Committed: Yes.

**`frontend-v3/.next/`:**
- Purpose: Next.js build output/cache.
- Generated: Yes.
- Committed: No.

**`.venv/`:**
- Purpose: Local Python virtual environment.
- Generated: Yes.
- Committed: No.

---

*Structure analysis: 2026-05-14*
