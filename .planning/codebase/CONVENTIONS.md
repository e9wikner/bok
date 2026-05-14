# Coding Conventions

**Analysis Date:** 2026-05-14

## Naming Patterns

**Files:**
- Python modules use `snake_case.py` naming, grouped by layer (`api/routes/invoices.py`, `services/vat_report.py`, `repositories/voucher_repo.py`).
- Frontend React components use `PascalCase.tsx` for feature components and `lowercase.tsx` for UI primitives (`frontend-v3/components/AppShellClient.tsx`, `frontend-v3/components/ui/button.tsx`).

**Functions:**
- Python functions and methods use `snake_case` (`services/ledger.py`, `api/routes/invoices.py`).
- TypeScript functions/hooks use `camelCase`, with hooks prefixed by `use` (`frontend-v3/hooks/useAuth.ts`, `frontend-v3/lib/api.ts`).

**Variables:**
- Python uses `snake_case` for locals/arguments and constants in all-caps when module-level (`tests/test_api.py`, `services/ledger.py`).
- TypeScript uses `camelCase` for values and all-caps for environment-backed constants (`frontend-v3/lib/api.ts`, `frontend-v3/hooks/useAuth.ts`).

**Types:**
- Python domain models are `PascalCase` dataclasses and enums (`domain/models.py`, `domain/types.py`).
- TypeScript interfaces/types are `PascalCase` (`frontend-v3/lib/api.ts`).

## Code Style

**Formatting:**
- Python style aligns with Black-like formatting conventions (4-space indentation, trailing commas in multiline structures, type hints) but no formatter config file is detected in repo root.
- Frontend formatting is Prettier-compatible style (double quotes, semicolons, trailing commas), inferred from `frontend-v3/**/*.ts(x)`; no `.prettierrc*` file is detected.

**Linting:**
- Frontend linting uses ESLint 9 with Next.js presets via `frontend-v3/eslint.config.mjs` and `frontend-v3/.eslintrc.json`.
- Project-specific rule overrides:
- `@typescript-eslint/no-explicit-any`: off
- `@typescript-eslint/no-unused-vars`: warn with `_` ignored for args
- `import/no-anonymous-default-export`: off

## Import Organization

**Order:**
1. Standard library imports first (`datetime`, `typing`) in Python modules (`services/ledger.py`, `api/routes/invoices.py`).
2. Third-party packages next (`fastapi`, `pydantic`, `pytest`) (`api/routes/invoices.py`, `tests/test_api.py`).
3. Local app imports last (`api.*`, `domain.*`, `services.*`, `repositories.*`) (`api/routes/invoices.py`, `tests/conftest.py`).

**Path Aliases:**
- Frontend uses `@/*` alias to project root configured in `frontend-v3/tsconfig.json`.

## Error Handling

**Patterns:**
- FastAPI routes catch domain validation exceptions and translate them to `HTTPException` with `400` and structured `detail` payloads (`api/routes/invoices.py`).
- Unexpected exceptions are converted to `500` responses in route handlers (`api/routes/invoices.py`).
- Service layer raises explicit domain errors (`ValidationError`) for business rule violations (`services/ledger.py`, `services/invoice.py`).
- Best-effort side effects are wrapped in guarded `try/except` to avoid failing primary workflow (`services/ledger.py` posting flow).

## Logging

**Framework:** repository-level audit logging service (not Python `logging` module).

**Patterns:**
- Domain events are persisted through `AuditRepository.log(...)` with typed actions and payloads (`services/ledger.py`).
- User/action metadata (`actor`, `entity_type`, `entity_id`) is included on mutation paths (`services/ledger.py`).

## Comments

**When to Comment:**
- Comments explain accounting/legal intent (BFL/BFNAR constraints) and workflow rationale rather than line-level mechanics (`services/ledger.py`, `domain/models.py`, `api/main.py`).

**JSDoc/TSDoc:**
- TypeScript primarily uses inline code readability and interfaces, with sparse block comments (`frontend-v3/lib/api.ts`, `frontend-v3/hooks/useAuth.ts`).
- Python uses docstrings consistently for modules, classes, fixtures, and tests (`api/main.py`, `tests/conftest.py`, `domain/models.py`).

## Function Design

**Size:** Domain/service methods can be medium-to-large and orchestrate multiple repository calls plus validation (`services/ledger.py`, `services/invoice.py`).

**Parameters:** Explicit named parameters with type hints; business context passed as primitives/IDs and structured row lists (`services/ledger.py`, `services/invoice.py`).

**Return Values:** Services return domain objects; API routes shape those objects into JSON dictionaries (`services/ledger.py`, `api/routes/invoices.py`).

## Module Design

**Exports:** Python modules export classes/functions directly per file; no Python barrel/export aggregator pattern is used beyond package `__init__.py` files (`services/__init__.py`, `repositories/__init__.py`).

**Barrel Files:** Frontend primarily imports direct module paths; no dominant TS barrel `index.ts` pattern is detected (`frontend-v3/components/*`, `frontend-v3/hooks/*`).

---

*Convention analysis: 2026-05-14*
