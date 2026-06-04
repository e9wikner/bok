# Phase 6: Agent Instruction Entrypoint and API Discovery - Pattern Map

**Date:** 2026-06-05

## Target Files

| File | Role | Closest Existing Pattern |
|------|------|--------------------------|
| `api/routes/agent_instructions.py` | Add public-safe entrypoint route and response models | Existing instruction routes in same file |
| `api/routes/agent.py` | Remove placeholder routes and make ping dynamic | Existing authenticated agent route pattern |
| `tests/test_agent_instructions_separation.py` or `tests/test_agent_entrypoint.py` | Validate entrypoint, ping, and removed routes | Existing `TestClient` API tests |
| `README.md` | Remove stale key-route references and add entrypoint reference | Existing Swedish endpoint list |

## Existing Patterns

### FastAPI route modules

Routes live under `api/routes/*.py` with module-local `APIRouter` instances.
`agent_instructions.py` already uses:

- `router = APIRouter(prefix="/api/v1/agent-instructions", tags=["agent-instructions"])`
- function-level `response_model=dict`
- auth via `actor: str = Depends(get_current_actor)` for protected routes

The new `GET /entrypoint` route should intentionally not use
`Depends(get_current_actor)`.

### Authenticated agent routes

`api/routes/agent.py` uses `actor: str = Depends(get_current_actor)` for
protected operational calls. Keep that for `/test/ping`, `/vouchers`, and
intake-processing routes. Remove placeholder routes rather than adapting them.

### Test style

Existing tests use:

- `from fastapi.testclient import TestClient`
- `from main import app`
- `client = TestClient(app)`
- `auth_headers` fixture for protected endpoints

Entry-point tests can reuse that shape.

## Data Flow for Entrypoint

1. Unauthenticated caller requests
   `GET /api/v1/agent-instructions/entrypoint`.
2. Route returns static metadata and relative paths only.
3. Agent follows `startup_sequence[0]` or `auth.check.path` to
   `POST /api/v1/agent/test/ping` with bearer auth.
4. After ping succeeds, agent follows the listed protected workflow endpoints.

## Required Assertions

- Entrypoint is available without `Authorization`.
- Entrypoint links include `/openapi.json`, `/docs`, `/redoc`,
  `/api/v1/health`, and `/api/v1/agent/test/ping`.
- Workflow endpoints include accounting instructions, correction history,
  pending intake, processing, failed, voucher posting, and voucher source
  context.
- No entrypoint field contains `settings.api_key`, `secret_key`, pending queue
  items, correction rows, or filenames.
- Placeholder routes return 404 or 405 after removal.
- Ping returns `settings.api_version` and a non-hard-coded timestamp.
