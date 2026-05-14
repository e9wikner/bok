<!-- GSD:project-start source:PROJECT.md -->
## Project

**Bok**

Bok is a self-hosted bookkeeping application for small Swedish limited companies that want to run accounting without external accountants and without needing deep bookkeeping knowledge. It combines a FastAPI backend, a Next.js frontend, Swedish accounting compliance rules, and an AI-agent-facing API so bookkeeping decisions can be automated while the backend enforces formal accounting constraints.

The current project focus is an intake system for source material: users upload receipts, invoices, and bank statements/statuses through the frontend, and the agent uses that material to decide which vouchers to post. The intended workflow favors automation over pre-approval: the agent should post vouchers directly, and user review plus B-series correction vouchers become the feedback loop the agent learns from.

**Core Value:** The system should let a small Swedish company keep compliant books with minimal manual interaction by giving an agent enough source material, history, and correction feedback to post accurate vouchers.

### Constraints

- **Compliance**: Posted vouchers must remain immutable and corrections must happen through correction vouchers — required for Swedish bookkeeping durability and auditability.
- **Automation first**: Intake should support direct agent posting by default — the project exists to minimize user interaction.
- **Traceability**: Every agent-posted voucher created from intake must remain linked to its source files and user explanation — necessary for review, audit, and correction learning.
- **Input separation**: Voucher source material and bank statements/statuses should be uploaded and modeled separately — they play different roles in the agent's decision process.
- **Storage**: Initial implementation should fit the existing SQLite plus local filesystem architecture — consistent with current deployment and backup model.
- **Frontend**: The UI should be an operational work surface, not a landing page — users need to upload, scan status, and review outcomes efficiently.
- **Security**: File-serving paths must be constrained to the configured attachment/intake storage root — existing codebase concern and high-risk surface.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.11 - Backend API and business logic in `main.py`, `api/`, `services/`, `repositories/`, `db/`
- TypeScript - Frontend app and UI logic in `frontend-v3/app/`, `frontend-v3/components/`, `frontend-v3/lib/`
- SQL - Schema and migrations in `db/migrations/*.sql`
- HCL (Terraform) - Infrastructure definitions in `terraform/main.tf`, `terraform/variables.tf`
## Runtime
- Python runtime via `python:3.11-slim` in `Dockerfile`
- Node.js runtime via `node:20-alpine` in `frontend-v3/Dockerfile`
- `pip` (requirements-based) for backend dependencies from `requirements.txt`
- `npm` for frontend dependencies in `frontend-v3/package.json`
- Lockfile: present for frontend (`frontend-v3/package-lock.json`), missing for backend (no `poetry.lock`/`Pipfile.lock`)
## Frameworks
- FastAPI (>=0.109.0) - HTTP API framework in `api/main.py`, declared in `requirements.txt`
- Next.js (^16.2.6) - Frontend framework in `frontend-v3/package.json` with app router in `frontend-v3/app/`
- React (^18) - UI runtime in `frontend-v3/package.json`
- Pytest (`pytest==7.4.3`) - Backend test runner in `tests/` and `.github/workflows/tests.yml`
- Playwright (`^1.59.1`) - Frontend/E2E dependency in `frontend-v3/package.json`
- Uvicorn (>=0.27.0) - ASGI server launched from `main.py`
- Tailwind CSS (`^3.4.1`) - Styling pipeline in `frontend-v3/tailwind.config.ts`
- PostCSS (`8.5.14`) - CSS transform config in `frontend-v3/postcss.config.mjs`
- ESLint (`^9`) - Frontend linting in `frontend-v3/eslint.config.mjs`
## Key Dependencies
- `pydantic` / `pydantic-settings` - API schemas/settings in `api/schemas.py`, `config.py`
- `PyJWT` - JWT signing/verification in `services/auth.py`
- `weasyprint`, `jinja2`, `qrcode`, `pillow` - PDF and QR rendering in `services/pdf_export.py`, templates in `templates/pdf/`
- `axios` - Frontend API client in `frontend-v3/lib/api.ts`
- `docker-compose` service definitions in `docker-compose.yml`, `docker-compose.local.yml`, `docker-compose.prod.yml`
- Traefik (`traefik:v3.0`) as reverse proxy/TLS in `docker-compose.prod.yml`
- Terraform Hetzner provider (`hetznercloud/hcloud ~> 1.45`) in `terraform/main.tf`
## Configuration
- Backend settings centralized in `config.py` (`BaseSettings`, `.env` support)
- Frontend API routing config via `NEXT_PUBLIC_API_URL` and `BACKEND_URL` in `frontend-v3/next.config.mjs`
- Environment files detected: `.env.example`, `.env.production`, `.env.production.example`
- Backend container build in `Dockerfile`
- Frontend multi-stage build in `frontend-v3/Dockerfile`
- Frontend TS config in `frontend-v3/tsconfig.json`
- Frontend Next config in `frontend-v3/next.config.mjs`
- CI workflows in `.github/workflows/tests.yml`, `.github/workflows/docker-build.yml`
## Platform Requirements
- Python 3.11-compatible environment for backend (`requirements.txt`, CI in `.github/workflows/tests.yml`)
- Node.js 20-compatible environment for frontend (`frontend-v3/Dockerfile`)
- Docker and Docker Compose for local/full-stack runs (`docker-compose.yml`, `docker-compose.local.yml`)
- Containerized deployment with Docker Compose and Traefik in `docker-compose.prod.yml`
- Persistent volume-backed SQLite storage (`bokfoering-data` volume) in `docker-compose*.yml`
- Optional Terraform-managed Hetzner Cloud infrastructure in `terraform/main.tf`
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- Python modules use `snake_case.py` naming, grouped by layer (`api/routes/invoices.py`, `services/vat_report.py`, `repositories/voucher_repo.py`).
- Frontend React components use `PascalCase.tsx` for feature components and `lowercase.tsx` for UI primitives (`frontend-v3/components/AppShellClient.tsx`, `frontend-v3/components/ui/button.tsx`).
- Python functions and methods use `snake_case` (`services/ledger.py`, `api/routes/invoices.py`).
- TypeScript functions/hooks use `camelCase`, with hooks prefixed by `use` (`frontend-v3/hooks/useAuth.ts`, `frontend-v3/lib/api.ts`).
- Python uses `snake_case` for locals/arguments and constants in all-caps when module-level (`tests/test_api.py`, `services/ledger.py`).
- TypeScript uses `camelCase` for values and all-caps for environment-backed constants (`frontend-v3/lib/api.ts`, `frontend-v3/hooks/useAuth.ts`).
- Python domain models are `PascalCase` dataclasses and enums (`domain/models.py`, `domain/types.py`).
- TypeScript interfaces/types are `PascalCase` (`frontend-v3/lib/api.ts`).
## Code Style
- Python style aligns with Black-like formatting conventions (4-space indentation, trailing commas in multiline structures, type hints) but no formatter config file is detected in repo root.
- Frontend formatting is Prettier-compatible style (double quotes, semicolons, trailing commas), inferred from `frontend-v3/**/*.ts(x)`; no `.prettierrc*` file is detected.
- Frontend linting uses ESLint 9 with Next.js presets via `frontend-v3/eslint.config.mjs` and `frontend-v3/.eslintrc.json`.
- Project-specific rule overrides:
- `@typescript-eslint/no-explicit-any`: off
- `@typescript-eslint/no-unused-vars`: warn with `_` ignored for args
- `import/no-anonymous-default-export`: off
## Import Organization
- Frontend uses `@/*` alias to project root configured in `frontend-v3/tsconfig.json`.
## Error Handling
- FastAPI routes catch domain validation exceptions and translate them to `HTTPException` with `400` and structured `detail` payloads (`api/routes/invoices.py`).
- Unexpected exceptions are converted to `500` responses in route handlers (`api/routes/invoices.py`).
- Service layer raises explicit domain errors (`ValidationError`) for business rule violations (`services/ledger.py`, `services/invoice.py`).
- Best-effort side effects are wrapped in guarded `try/except` to avoid failing primary workflow (`services/ledger.py` posting flow).
## Logging
- Domain events are persisted through `AuditRepository.log(...)` with typed actions and payloads (`services/ledger.py`).
- User/action metadata (`actor`, `entity_type`, `entity_id`) is included on mutation paths (`services/ledger.py`).
## Comments
- Comments explain accounting/legal intent (BFL/BFNAR constraints) and workflow rationale rather than line-level mechanics (`services/ledger.py`, `domain/models.py`, `api/main.py`).
- TypeScript primarily uses inline code readability and interfaces, with sparse block comments (`frontend-v3/lib/api.ts`, `frontend-v3/hooks/useAuth.ts`).
- Python uses docstrings consistently for modules, classes, fixtures, and tests (`api/main.py`, `tests/conftest.py`, `domain/models.py`).
## Function Design
## Module Design
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## System Overview
```text
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
- Keep HTTP concerns in `api/routes`, not inside repositories.
- Keep business rules in `services` using `domain` models and validators.
- Keep SQL and storage details in `repositories` and `db`.
## Layers
- Purpose: Render user workflows and call backend endpoints.
- Location: `frontend-v3/app`, `frontend-v3/components`, `frontend-v3/hooks`.
- Contains: Next.js App Router pages/layouts, React Query hooks, API client.
- Depends on: `frontend-v3/lib/api.ts`, browser storage/auth state.
- Used by: End users.
- Purpose: Expose REST endpoints and enforce auth dependencies.
- Location: `api/main.py`, `api/routes/*.py`, `api/deps.py`, `api/schemas.py`.
- Contains: `APIRouter` modules, Pydantic request/response schemas, auth checks.
- Depends on: `services/*`, `domain.validation`, `config.py`.
- Used by: Frontend and external API callers.
- Purpose: Implement bookkeeping workflows and BFL/BFNAR business constraints.
- Location: `services/*.py`, `domain/*.py`.
- Contains: Orchestration services, validators, dataclass entities, enum types.
- Depends on: `repositories/*`, `db.database` transaction context.
- Used by: `api/routes`.
- Purpose: Store and retrieve entities via SQL and migration-managed schema.
- Location: `repositories/*.py`, `db/database.py`, `db/migrations/*.sql`.
- Contains: CRUD/query repositories, transaction and connection management.
- Depends on: SQLite and filesystem path configured by `config.py`.
- Used by: `services/*`.
## Data Flow
### Primary Request Path
### Frontend Query Flow
- Backend state is persisted in SQLite through repositories (`db/database.py`).
- Frontend server state is cached in React Query via `QueryClientProvider` (`frontend-v3/app/providers.tsx`).
- Frontend auth state is local-storage backed context (`frontend-v3/hooks/useAuth.ts`).
## Key Abstractions
- Purpose: Represent a verifikation with rows, status, and correction linkage.
- Examples: `domain/models.py`, `repositories/voucher_repo.py`.
- Pattern: Aggregate root loaded/saved via repository methods.
- Purpose: Orchestrate period/account validation, posting, correction, and audit logging.
- Examples: `services/ledger.py`.
- Pattern: Application service over repositories + validators.
- Purpose: Encapsulate SQL and row mapping from the rest of the app.
- Examples: `repositories/voucher_repo.py`, `repositories/period_repo.py`.
- Pattern: Static-method repositories called by services.
## Entry Points
- Location: `main.py`
- Triggers: `python main.py`, docker command/entrypoint.
- Responsibilities: Optional DB init/seed and uvicorn startup.
- Location: `api/main.py`
- Triggers: `uvicorn api.main:app`.
- Responsibilities: Build FastAPI app, CORS, route inclusion, health endpoints.
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
### N+1 repository hydration for list endpoints
## Error Handling
- Validate-and-raise in service/domain (`services/ledger.py`, `domain/validation.py`).
- Route-level try/except translation to status codes (`api/routes/vouchers.py`).
## Cross-Cutting Concerns
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
