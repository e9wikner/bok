---
phase: 06-agent-instruction-entrypoint-and-api-discovery
plan: 06-01
subsystem: api
tags: [fastapi, agent-entrypoint, onboarding, tests]
requires:
  - phase: 04-intake-agent-traceability
    provides: Existing agent intake, voucher posting, and source-context endpoints referenced by the entrypoint.
provides:
  - Public-safe `GET /api/v1/agent-instructions/entrypoint` startup contract.
  - Contract tests for unauthenticated access, relative links, workflow paths, guardrails, and unsupported features.
affects: [agent-api, openclaw-onboarding, deployment-docs]
tech-stack:
  added: []
  patterns: [Static public-safe discovery payload, async ASGI API tests]
key-files:
  created:
    - tests/test_agent_entrypoint.py
  modified:
    - api/routes/agent_instructions.py
    - tests/conftest.py
    - tests/test_agent_instructions_separation.py
key-decisions:
  - "Entrypoint returns only static metadata and settings.api_version; it does not use auth dependencies or repositories."
  - "Entrypoint uses relative paths only and links /openapi.json as the canonical generated schema."
  - "Existing synchronous TestClient instruction tests were converted to async ASGI transport because local TestClient requests hang under the current Python/runtime combination."
patterns-established:
  - "Public agent discovery endpoints should be static and unauthenticated unless they need company state."
  - "Agent API tests should use httpx.ASGITransport async clients in this environment."
requirements-completed: [ONBD-01, ONBD-02, ONBD-03, ONBD-04, API-03, VER-01]
duration: 18min
completed: 2026-06-04T22:23:32Z
---

# Phase 6 Plan 06-01 Summary

**Public-safe agent instruction entrypoint with relative startup paths and contract tests**

## Performance

- **Duration:** 18 min
- **Started:** 2026-06-04T22:15:56Z
- **Completed:** 2026-06-04T22:23:32Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Added unauthenticated `GET /api/v1/agent-instructions/entrypoint`.
- Returned service identity, configured API version, auth check guidance, docs/schema links, ordered startup sequence, workflow endpoints, guardrails, unsupported features, and owner-to-agent startup instructions.
- Added tests proving unauthenticated access, required paths, relative-path-only payload values, startup ordering, guardrails, unsupported feature disclosure, and absence of sensitive field markers.

## Task Commits

1. **Task 1-2: Entrypoint contract and tests** - `ab9188e` (feat)

## Files Created/Modified

- `api/routes/agent_instructions.py` - Adds static public-safe entrypoint route.
- `tests/test_agent_entrypoint.py` - Adds entrypoint contract tests.
- `tests/test_agent_instructions_separation.py` - Repairs existing instruction API tests so required verification can run.
- `tests/conftest.py` - Adds shared `auth_headers` fixture for protected API tests.

## Decisions Made

- Used `settings.api_version` as the only dynamic value in the public payload.
- Avoided repository calls and `Depends(get_current_actor)` in the entrypoint to prevent unauthenticated company-state leakage.
- Used `BOKFOERING_API_KEY` only as a credential-format placeholder and avoided response keys such as `api_key`, `secret_key`, and `token_value`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Repaired existing instruction test app import**
- **Found during:** Plan verification
- **Issue:** `tests/test_agent_instructions_separation.py` imported `app` from `main.py`, but FastAPI's app lives in `api.main`.
- **Fix:** Updated the import to `from api.main import app`.
- **Files modified:** `tests/test_agent_instructions_separation.py`
- **Verification:** `.venv/bin/python -m pytest tests/test_agent_instructions_separation.py`
- **Committed in:** `ab9188e`

**2. [Rule 3 - Blocking] Repaired existing instruction test runtime fixtures**
- **Found during:** Plan verification
- **Issue:** The file depended on a non-shared `auth_headers` fixture, synchronous `TestClient` requests hung locally, and repository routes lacked `test_db`.
- **Fix:** Added shared `auth_headers`, converted endpoint tests to async ASGI transport, and attached `test_db` to repository-backed endpoint tests.
- **Files modified:** `tests/conftest.py`, `tests/test_agent_instructions_separation.py`
- **Verification:** `.venv/bin/python -m pytest tests/test_agent_instructions_separation.py`
- **Committed in:** `ab9188e`

---

**Total deviations:** 2 auto-fixed blocking test-harness issues.
**Impact on plan:** Required to execute the plan's verification commands. No application behavior outside the new entrypoint changed.

## Issues Encountered

- System Python lacks pytest; verification used `.venv/bin/python -m pytest`.
- The local synchronous `TestClient` request path hangs in this environment; async ASGI transport is the reliable repository pattern.

## Verification

- `.venv/bin/python -m pytest tests/test_agent_entrypoint.py` - passed, 6 tests.
- `.venv/bin/python -m pytest tests/test_agent_instructions_separation.py` - passed, 12 tests.

## Next Phase Readiness

Plan 06-02 can remove placeholder agent routes, make ping dynamic, and update README references. The entrypoint already lists unsupported future-scope features and links `/openapi.json`.

---
*Phase: 06-agent-instruction-entrypoint-and-api-discovery*
*Completed: 2026-06-04*
