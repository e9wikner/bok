---
phase: 03-frontend-intake-workspace-and-review-loop
plan: 03-01
subsystem: frontend-api
tags: [fastapi, react-query, intake, bank-inputs, vouchers]

requires:
  - phase: 02-bank-input-and-direct-posting-context
    provides: bank input storage, bank-driven posting traceability, agent context
provides:
  - Human intake workspace list and detail endpoints for voucher sources and bank inputs
  - Bank connection selector endpoint for bank CSV uploads
  - Voucher source-context endpoint with source material, processing notes, and correction chain data
  - Frontend intake API types, client methods, and React Query hooks
affects: [03-02, 03-03, intake-ui, voucher-review]

tech-stack:
  added: []
  patterns:
    - FastAPI route-level composition over existing repositories
    - React Query hooks with stable query keys and enabled guards

key-files:
  created:
    - .planning/phases/03-frontend-intake-workspace-and-review-loop/03-01-SUMMARY.md
  modified:
    - repositories/intake_repo.py
    - repositories/bank_input_repo.py
    - api/routes/intake.py
    - api/routes/bank_inputs.py
    - api/routes/vouchers.py
    - frontend-v3/lib/api.ts
    - frontend-v3/hooks/useData.ts
    - tests/test_intake_api.py
    - tests/test_bank_input_agent.py

key-decisions:
  - "Human intake review uses dedicated read endpoints instead of agent-only queue endpoints."
  - "Voucher source material remains separate from manual voucher attachments in the source-context payload."
  - "Frontend file helpers return authenticated API download URLs only, never storage paths."

patterns-established:
  - "Workspace composition: API routes merge voucher_source and bank_input items with stable kind discriminators."
  - "Review hooks: detail queries are disabled until both kind and id or voucher id are available."

requirements-completed: [FRNT-01, FRNT-02, FRNT-03, FRNT-04, FRNT-05, FRNT-06]

duration: 14 min
completed: 2026-05-15
---

# Phase 03 Plan 03-01: Frontend Intake API Client, Hooks, and Human Review Endpoints Summary

**Typed intake review APIs and React Query hooks now support unified source/bank intake listing, uploads, voucher source context, and correction-chain review.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-05-15T12:44:02Z
- **Completed:** 2026-05-15T12:58:03Z
- **Tasks:** 4
- **Files modified:** 9

## Accomplishments

- Added `GET /api/v1/intake/workspace` and `GET /api/v1/intake/workspace/{kind}/{item_id}` with typed `voucher_source` and `bank_input` shapes, status counts, detail metadata, and no storage path exposure.
- Added `GET /api/v1/bank-inputs/connections` before dynamic bank-input routes so the frontend can show visible account fields while submitting `bank_connection_id`.
- Added `GET /api/v1/vouchers/{voucher_id}/source-context` with source material, processing notes, and correction-chain data separate from manual attachments.
- Added frontend intake types, API methods, multipart upload helpers, file URL helpers, and React Query hooks.

## Task Commits

1. **Task 1: Add human intake workspace list and detail read models** - `dac77c3` (feat)
2. **Task 2: Add bank account selector endpoint for bank CSV upload** - `0a2dc5f` (feat)
3. **Task 3: Add voucher source-context endpoint for review pages** - `fb49089` (feat)
4. **Task 4: Add frontend intake types, API methods, and React Query hooks** - `3927abc` (feat)

## Files Created/Modified

- `repositories/intake_repo.py` - Added generic status listing/counting and source-to-voucher link lookup helpers.
- `repositories/bank_input_repo.py` - Added status count and bank-input-to-voucher link lookup helpers.
- `api/routes/intake.py` - Added unified human workspace list/detail endpoints and response serialization helpers.
- `api/routes/bank_inputs.py` - Added active bank connection selector endpoint with account display fields.
- `api/routes/vouchers.py` - Added voucher source-context endpoint for linked intake material, processing notes, and correction history.
- `frontend-v3/lib/api.ts` - Added intake and source-context types plus API client methods and file URL helpers.
- `frontend-v3/hooks/useData.ts` - Added intake workspace/detail, bank connection, and voucher source-context hooks.
- `tests/test_intake_api.py` - Added failed-source detail, ordinary source context, and correction-chain coverage.
- `tests/test_bank_input_agent.py` - Added mixed workspace, connection selector, and bank source-context coverage.

## Decisions Made

- Human review uses dedicated `/intake/workspace` and voucher `/source-context` endpoints rather than reusing the agent queue shape.
- Bank upload selection returns only active connections by default, with account number/name fields for the visible selector.
- Source-context responses intentionally omit manual voucher attachments so intake source material remains auditably distinct.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Direct route tests received FastAPI Query sentinel defaults**
- **Found during:** Task 1 (workspace endpoint tests)
- **Issue:** Direct async route-function tests passed FastAPI `Query(None)` sentinel objects into `list_intake_workspace`, which made omitted `status` and `kind` look invalid.
- **Fix:** Used plain Python defaults for scalar workspace query parameters while preserving FastAPI query binding behavior.
- **Files modified:** `api/routes/intake.py`
- **Verification:** `.venv/bin/pytest tests/test_intake_api.py tests/test_bank_input_agent.py -q`
- **Committed in:** `dac77c3`

---

**Total deviations:** 1 auto-fixed (Rule 1)
**Impact on plan:** No scope change. The fix keeps direct route tests and HTTP behavior aligned.

## Issues Encountered

- `cd frontend-v3 && npm run build` is blocked in the working tree because the ignored generated directory `frontend-v3/.next` is owned by `nobody`, causing `EACCES` on `.next/trace`.
- Verification workaround: copied `frontend-v3` to `/tmp` without `.next`, copied `node_modules`, and ran `npm run build` there with escalated permissions. The clean production build passed.

## Verification

- `rg "workspace" api/routes/intake.py` - PASS
- `rg "kind.*voucher_source" api/routes/intake.py tests/test_intake_api.py` - PASS
- `rg "kind.*bank_input" api/routes/intake.py tests/test_bank_input_agent.py` - PASS
- `rg "connections" api/routes/bank_inputs.py` - PASS
- `rg "source-context" api/routes/vouchers.py` - PASS
- `rg "getIntakeWorkspace" frontend-v3/lib/api.ts frontend-v3/hooks/useData.ts` - PASS
- `rg "uploadIntakeSource" frontend-v3/lib/api.ts` - PASS
- `rg "useVoucherSourceContext" frontend-v3/hooks/useData.ts` - PASS
- `.venv/bin/python -m py_compile repositories/intake_repo.py repositories/bank_input_repo.py api/routes/intake.py api/routes/bank_inputs.py api/routes/vouchers.py tests/test_intake_api.py tests/test_bank_input_agent.py` - PASS
- `.venv/bin/pytest tests/test_intake_api.py tests/test_bank_input_agent.py -q` - PASS, 33 passed
- `cd frontend-v3 && npm run lint` - PASS
- `cd frontend-v3 && npm run build` - BLOCKED by pre-existing ignored `.next` ownership (`nobody:nobody`)
- `npm run build` from clean `/tmp/bok-frontend-build-6ljEsT` copy - PASS
- `git diff --check` - PASS

## Known Stubs

None. Stub-pattern scan only found intentional empty collection initializers and test assertions.

## Threat Flags

None. New endpoint surfaces were anticipated by the plan threat model and return API download URLs rather than filesystem paths.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Ready for Plan 03-02. The frontend can now call typed intake workspace, upload, detail, bank selector, and voucher source-context APIs needed to build the operational intake UI.

## Self-Check: PASSED

- Summary file created at `.planning/phases/03-frontend-intake-workspace-and-review-loop/03-01-SUMMARY.md`.
- Task commits present: `dac77c3`, `0a2dc5f`, `fb49089`, `3927abc`.
- Key modified files exist and plan-level verification results are recorded above.

---
*Phase: 03-frontend-intake-workspace-and-review-loop*
*Completed: 2026-05-15*
