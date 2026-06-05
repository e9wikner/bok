---
phase: 8
plan: 08-03
subsystem: verification
duration: 18 min
completed: "2026-06-05T14:40:00Z"
---

# Phase 8 Plan 08-03: Verification and Entrypoint Documentation Summary

Verified Phase 8 end to end: backend tests, mixed queue checks, entrypoint documentation, and source assertions.

## What Changed

- **Backend tests** `tests/test_intake_api.py`: Added 6 new tests proving guidance persistence, upload response field, detail response field, pending queue exposure, update endpoint behavior, whitespace-only normalization to null, and 409 rejection for processed sources.
- **Mixed queue tests** `tests/test_bank_input_agent.py`: Updated `test_agent_pending_queue_returns_voucher_sources_and_bank_inputs` to assert voucher source `guidance` equals uploaded `agent_guidance` and bank item `guidance is None`.
- **Entrypoint docs** `api/routes/agent_instructions.py`: Added sentence in startup sequence guidance telling agents to consider item-level `guidance` when deciding how to book vouchers.
- **Entrypoint tests** `tests/test_agent_entrypoint.py`: Asserts serialized entrypoint text contains `guidance` while still excluding forbidden sensitive/company-state fields.

## Tasks Completed

| Task | Title | Files |
|------|-------|-------|
| T01 | Add backend guidance API tests | tests/test_intake_api.py |
| T02 | Add mixed queue and entrypoint guidance checks | tests/test_bank_input_agent.py, tests/test_agent_entrypoint.py, api/routes/agent_instructions.py |
| T03 | Run integrated verification and source assertions | (verification output recorded below) |

## Verification

- `pytest tests/test_intake_api.py tests/test_bank_input_agent.py tests/test_agent_entrypoint.py` — 68/68 passed.
- Source assertions via `rg` found `agent_guidance`, `agent-guidance`, `Meddelande till agent`, and `"guidance"` in expected backend and frontend files.
- TypeScript `npx tsc --noEmit` from `frontend-v3` passed (zero errors).

## Self-Check

Self-Check: PASSED

## Deviations from Plan

- Frontend `npm run build` could not execute due to pre-existing `.next/trace-build` permission error (EACCES). TypeScript type-check (`tsc --noEmit`) passed as build verification substitute.

## Next Up

Phase 8 complete. Ready for `/gsd-verify-work 8` and milestone close.
