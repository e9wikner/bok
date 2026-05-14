<!-- refreshed: 2026-05-14 -->
# Architecture

**Analysis Date:** 2026-05-14

## System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│                   Client + API Boundary                     │
├──────────────────┬──────────────────┬───────────────────────┤
│ Next.js App      │ FastAPI Routes   │ Auth/Deps             │
│ `frontend-v3/app`│ `api/routes`     │ `api/deps.py`         │
└────────┬─────────┴────────┬─────────┴──────────┬────────────┘
         │                  │                     │
         ▼                  ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│               Domain + Service Orchestration               │
│ `services/*.py`, `domain/*.py`, `api/schemas.py`           │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│               Persistence + Schema Migrations              │
│ `repositories/*.py`, `db/database.py`, `db/migrations/*.sql`│
└─────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| API composition | Boot FastAPI app, register middleware/routers, expose health/root | `api/main.py` |
| HTTP route handlers | Parse request/response models and map domain errors to HTTP status | `api/routes/vouchers.py` |
| Business logic services | Enforce accounting rules, validation order, and audit side effects | `services/ledger.py` |
| Domain model layer | Represent accounting entities and invariants in typed dataclasses/enums | `domain/models.py`, `domain/types.py` |
| Persistence/repositories | SQL data access and aggregate rehydration | `repositories/voucher_repo.py` |
| DB runtime/migrations | Thread-local SQLite connections and migration application | `db/database.py` |
| Frontend shell | Route-level UI, auth gate, app shell, data hooks | `frontend-v3/app/layout.tsx`, `frontend-v3/hooks/useData.ts` |

## Pattern Overview

**Overall:** Layered monolith (frontend and backend in one repo) with service-repository backend and API-client/hooks frontend.

**Key Characteristics:**
- Keep HTTP concerns in `api/routes`, not inside repositories.
- Keep business rules in `services` using `domain` models and validators.
- Keep SQL and storage details in `repositories` and `db`.

## Layers

**Presentation Layer (Frontend):**
- Purpose: Render user workflows and call backend endpoints.
- Location: `frontend-v3/app`, `frontend-v3/components`, `frontend-v3/hooks`.
- Contains: Next.js App Router pages/layouts, React Query hooks, API client.
- Depends on: `frontend-v3/lib/api.ts`, browser storage/auth state.
- Used by: End users.

**Transport Layer (Backend HTTP):**
- Purpose: Expose REST endpoints and enforce auth dependencies.
- Location: `api/main.py`, `api/routes/*.py`, `api/deps.py`, `api/schemas.py`.
- Contains: `APIRouter` modules, Pydantic request/response schemas, auth checks.
- Depends on: `services/*`, `domain.validation`, `config.py`.
- Used by: Frontend and external API callers.

**Domain/Service Layer:**
- Purpose: Implement bookkeeping workflows and BFL/BFNAR business constraints.
- Location: `services/*.py`, `domain/*.py`.
- Contains: Orchestration services, validators, dataclass entities, enum types.
- Depends on: `repositories/*`, `db.database` transaction context.
- Used by: `api/routes`.

**Persistence Layer:**
- Purpose: Store and retrieve entities via SQL and migration-managed schema.
- Location: `repositories/*.py`, `db/database.py`, `db/migrations/*.sql`.
- Contains: CRUD/query repositories, transaction and connection management.
- Depends on: SQLite and filesystem path configured by `config.py`.
- Used by: `services/*`.

## Data Flow

### Primary Request Path

1. FastAPI registers all routers and middleware (`api/main.py:43`).
2. Voucher create endpoint parses schema and calls service (`api/routes/vouchers.py:25`).
3. Service validates period/accounts and voucher balance before persist (`services/ledger.py:47`).
4. Service persists voucher+rows atomically in transaction (`services/ledger.py:90`).
5. Repository writes SQL rows and returns domain objects (`repositories/voucher_repo.py:15`).
6. API maps domain object to response DTO (`api/routes/vouchers.py:68`).

### Frontend Query Flow

1. Route component calls React Query hook (`frontend-v3/app/page.tsx`).
2. Hook resolves query key/function to API method (`frontend-v3/hooks/useData.ts:6`).
3. Axios client injects `Authorization` from local storage (`frontend-v3/lib/api.ts:13`).
4. Backend auth dependency validates API key or JWT (`api/deps.py:10`).

**State Management:**
- Backend state is persisted in SQLite through repositories (`db/database.py`).
- Frontend server state is cached in React Query via `QueryClientProvider` (`frontend-v3/app/providers.tsx`).
- Frontend auth state is local-storage backed context (`frontend-v3/hooks/useAuth.ts`).

## Key Abstractions

**Voucher Aggregate:**
- Purpose: Represent a verifikation with rows, status, and correction linkage.
- Examples: `domain/models.py`, `repositories/voucher_repo.py`.
- Pattern: Aggregate root loaded/saved via repository methods.

**LedgerService:**
- Purpose: Orchestrate period/account validation, posting, correction, and audit logging.
- Examples: `services/ledger.py`.
- Pattern: Application service over repositories + validators.

**Repository Interface-by-convention:**
- Purpose: Encapsulate SQL and row mapping from the rest of the app.
- Examples: `repositories/voucher_repo.py`, `repositories/period_repo.py`.
- Pattern: Static-method repositories called by services.

## Entry Points

**Backend CLI/App Entrypoint:**
- Location: `main.py`
- Triggers: `python main.py`, docker command/entrypoint.
- Responsibilities: Optional DB init/seed and uvicorn startup.

**Backend ASGI Entrypoint:**
- Location: `api/main.py`
- Triggers: `uvicorn api.main:app`.
- Responsibilities: Build FastAPI app, CORS, route inclusion, health endpoints.

**Frontend Entrypoint:**
- Location: `frontend-v3/app/layout.tsx`
- Triggers: Next.js runtime.
- Responsibilities: Global providers, auth guard, app shell.

## Architectural Constraints

- **Threading:** SQLite access is thread-local; each thread has its own connection (`db/database.py:31`).
- **Global state:** Global singletons are used for settings and DB instance (`config.py`, `db/database.py:135`).
- **Circular imports:** Service-to-service imports are deferred inside methods to avoid import cycles (`services/ledger.py:172`).
- **Storage engine:** Persistence is SQLite-centric and SQL strings are handwritten in repositories (`repositories/*.py`).

## Anti-Patterns

### Route-level catch-all exception conversion

**What happens:** Endpoints catch generic `Exception` and return HTTP 500 with `str(e)`.
**Why it's wrong:** It risks exposing internal error text and duplicates error handling logic across routes.
**Do this instead:** Move generic exception mapping to centralized FastAPI exception handlers in `api/main.py` and keep route handlers focused on domain exceptions.

### N+1 repository hydration for list endpoints

**What happens:** `list_*` queries fetch IDs first, then load each voucher via `get`.
**Why it's wrong:** It multiplies SQL calls and can degrade as datasets grow.
**Do this instead:** Add batched list queries with joins in `repositories/voucher_repo.py` and map rows in one pass.

## Error Handling

**Strategy:** Domain validators raise structured `ValidationError`; routes convert to HTTP 400 and use `HTTPException` for auth/not-found.

**Patterns:**
- Validate-and-raise in service/domain (`services/ledger.py`, `domain/validation.py`).
- Route-level try/except translation to status codes (`api/routes/vouchers.py`).

## Cross-Cutting Concerns

**Logging:** Business events are audit-logged through repository calls (`repositories/audit_repo.py`, invoked from services).
**Validation:** Pre-persistence domain validation is required (`services/ledger.py:84`).
**Authentication:** API key or JWT via shared dependency (`api/deps.py`), login flow in `api/routes/auth.py`.

---

*Architecture analysis: 2026-05-14*
