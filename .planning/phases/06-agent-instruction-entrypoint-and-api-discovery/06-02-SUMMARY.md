---
phase: 06-agent-instruction-entrypoint-and-api-discovery
plan: 06-02
subsystem: api
tags: [fastapi, agent-api, ping, readme, tests]
requires:
  - phase: 06-agent-instruction-entrypoint-and-api-discovery
    provides: Public agent instruction entrypoint from plan 06-01.
provides:
  - Removed placeholder agent key, spec/tool, and idempotency routes.
  - Dynamic authenticated agent ping using configured API version and UTC timestamp.
  - README references aligned with the supported entrypoint and credential flow.
affects: [agent-api, openclaw-onboarding, deployment-docs]
tech-stack:
  added: []
  patterns: [Bounded auth-check response, truthful README endpoint inventory]
key-files:
  created: []
  modified:
    - api/routes/agent.py
    - tests/test_agent_entrypoint.py
    - tests/test_agent_accounting_workflow.py
    - README.md
key-decisions:
  - "Removed misleading placeholder routes instead of deprecating them."
  - "Ping returns only status, service, configured version, authenticated actor, and current UTC timestamp."
  - "README points owner/agent setup to the entrypoint and BOKFOERING_API_KEY, not fake key lifecycle routes."
patterns-established:
  - "Unsupported future features are disclosed through the entrypoint rather than placeholder endpoints."
  - "Date-sensitive correction tests should create periods for the current date."
requirements-completed: [AUTH-02, API-01, API-02, API-03, VER-01]
duration: 10min
completed: 2026-06-04T22:28:06Z
---

# Phase 6 Plan 06-02 Summary

**Truthful agent API discovery with placeholder routes removed and dynamic ping verification**

## Performance

- **Duration:** 10 min
- **Started:** 2026-06-04T22:23:32Z
- **Completed:** 2026-06-04T22:28:06Z
- **Tasks:** 4
- **Files modified:** 4

## Accomplishments

- Removed `/keys/create`, `/keys`, `/keys/{key_id}/revoke`, `/spec/openapi`, `/spec/tools`, and `/operations/idempotent/{operation_id}` from `api/routes/agent.py`.
- Removed unused `uuid` and `hashlib` imports.
- Updated `POST /api/v1/agent/test/ping` to return `settings.api_version`, authenticated actor, and current UTC ISO timestamp.
- Added tests for ping auth/no-auth behavior and removed placeholder route behavior.
- Cleaned README agent integration references to point to `/api/v1/agent-instructions/entrypoint`, `/openapi.json`, and `BOKFOERING_API_KEY`.

## Task Commits

1. **Tasks 1-4: Route cleanup, dynamic ping, README cleanup, focused verification** - `172b2d7` (feat)

## Files Created/Modified

- `api/routes/agent.py` - Removes fake placeholder routes and makes ping dynamic.
- `tests/test_agent_entrypoint.py` - Adds ping and removed-route assertions.
- `tests/test_agent_accounting_workflow.py` - Repairs date-sensitive correction workflow test data.
- `README.md` - Replaces stale placeholder-route references with the entrypoint startup flow.

## Decisions Made

- Kept `/api/v1/agent/operations/log` because it was not listed among placeholder routes to remove.
- Used `/openapi.json` as the only schema discovery path in README and entrypoint tests.
- Preserved `BOKFOERING_API_KEY` as the supported current credential without implying persistent key management exists.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Repaired date-sensitive agent workflow test**
- **Found during:** Task 4 focused verification
- **Issue:** `tests/test_agent_accounting_workflow.py` created a May 2026 period, but correction vouchers are dated to today. On June 5, 2026 local time, the correction was correctly rejected as outside the May period.
- **Fix:** The test now creates a fiscal period for the current month and posts the original voucher on `date.today()`.
- **Files modified:** `tests/test_agent_accounting_workflow.py`
- **Verification:** `.venv/bin/python -m pytest tests/test_agent_entrypoint.py tests/test_agent_instructions_separation.py tests/test_agent_accounting_workflow.py`
- **Committed in:** `172b2d7`

---

**Total deviations:** 1 auto-fixed blocking test-data issue.
**Impact on plan:** Required for stable verification. No application behavior was broadened.

## Issues Encountered

- None beyond the date-sensitive test-data fix documented above.

## Verification

- `.venv/bin/python -m pytest tests/test_agent_entrypoint.py tests/test_agent_instructions_separation.py tests/test_agent_accounting_workflow.py` - passed, 23 tests.
- `rg "/api/v1/agent/keys|/api/v1/agent/spec|/api/v1/agent/operations/idempotent" README.md api/routes tests` - no matches; command exits 1 as expected when nothing is found.
- `rg "/api/v1/agent-instructions/entrypoint" README.md tests api/routes/agent_instructions.py` - found README, tests, and route references.
- `rg -n "uuid|hashlib|2026-03-21T10:00:00|/keys/create|/keys\"|/keys/\\{key_id\\}/revoke|/spec/openapi|/spec/tools|/operations/idempotent" api/routes/agent.py tests/test_agent_entrypoint.py README.md` - no matches; command exits 1 as expected when nothing is found.

## Next Phase Readiness

Phase 6 implementation is ready for aggregate verification. Phase 7 can document OpenClaw deployment as: owner sends the entrypoint URL, agent reads startup instructions, then agent verifies access with bearer auth.

---
*Phase: 06-agent-instruction-entrypoint-and-api-discovery*
*Completed: 2026-06-04*
