---
phase: 09-corr-simplified-correction-flow
plan: 09-02
subsystem: api
tags: [agent-api, correction-notes, fastapi, learning-context, pytest]
requires:
  - phase: 09-01
    provides: correction note storage, lifecycle service, and voucher-scoped APIs
provides:
  - Pending correction-note queue items for agents
  - Agent entrypoint contract for correction-note suggestion workflow
  - Failed suggestion context in accounting correction responses
affects: [agent-intake-queue, agent-entrypoint, accounting-corrections]
tech-stack:
  added: []
  patterns:
    - Mixed agent queue items sorted by uploaded_at or created_at
    - Agent-readable failed correction context through correction_history JSON fields
key-files:
  created: []
  modified:
    - api/routes/agent.py
    - api/routes/agent_instructions.py
    - api/routes/accounting_corrections.py
    - repositories/correction_note_repo.py
    - services/correction_notes.py
    - tests/test_agent_entrypoint.py
    - tests/test_correction_notes.py
key-decisions:
  - "Correction notes appear in the agent pending queue but remain excluded from the frontend intake workspace."
  - "Rejected notes without draft rows expose rejection_reason in corrected_data for agent learning."
patterns-established:
  - "Agent queue correction_note items include action URLs instead of requiring route discovery."
  - "Accounting correction responses expose original_data, corrected_data, and was_successful."
requirements-completed: [CORR-02, CORR-03, CORR-06]
duration: 5 min
completed: 2026-06-05
---

# Phase 09 Plan 09-02: Agent Correction Note Exposure Summary

**Pending correction notes now appear in the agent queue with draft-suggestion URLs and failed-suggestion learning context**

## Performance

- **Duration:** 5 min
- **Started:** 2026-06-05T19:38:20Z
- **Completed:** 2026-06-05T19:42:46Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments

- Added `kind: "correction_note"` pending queue items with source-context, draft, suggest, and reject URLs.
- Updated the public-safe agent entrypoint contract with correction-note workflow guidance.
- Exposed `was_successful`, `original_data`, and `corrected_data` so dismissed/rejected suggestions are agent-readable.

## Task Commits

1. **Task 1: Add correction notes to the agent pending queue** - `b282cd2` (feat)
2. **Task 2: Document the correction note workflow for agents** - `b7a2684` (docs)
3. **Task 3: Verify agent learning context includes failed suggestions** - `a7772ef` (feat)

## Files Created/Modified

- `api/routes/agent.py` - Mixed pending queue now includes correction-note items.
- `repositories/correction_note_repo.py` - Added pending count and limit/offset support for queue reads.
- `api/routes/agent_instructions.py` - Added correction-note contract and guardrails.
- `tests/test_agent_entrypoint.py` - Entry point assertions for correction-note workflow strings.
- `api/routes/accounting_corrections.py` - Added `was_successful` to correction response payloads.
- `services/correction_notes.py` - Rejected notes now persist rejection context in `corrected_data`.
- `tests/test_correction_notes.py` - Agent learning assertions for dismissed and rejected outcomes.

## Decisions Made

- Kept correction-note queue items out of `/api/v1/intake/workspace`, preserving source-material-only frontend intake semantics.
- Exposed concrete action URLs in queue and entrypoint payloads so agents can work without guessing route shape.

## Deviations from Plan

None - plan executed exactly as written.

**Total deviations:** 0 auto-fixed.  
**Impact on plan:** None.

## Issues Encountered

None.

## Verification

- `.venv/bin/pytest tests/test_agent_entrypoint.py` - 13 passed.
- `.venv/bin/pytest tests/test_agent_accounting_workflow.py tests/test_correction_notes.py` - 9 passed.
- `.venv/bin/pytest tests/test_bank_input_agent.py` - 38 passed.
- `rg "correction_note|correction-draft|source-context|corrected_data|original_data" api/routes/agent.py api/routes/agent_instructions.py api/routes/accounting_corrections.py tests` - passed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

The backend and agent-facing workflow are ready for plan 09-03 to add the voucher detail UI for correction notes and suggested draft review.

---
*Phase: 09-corr-simplified-correction-flow*
*Completed: 2026-06-05*
