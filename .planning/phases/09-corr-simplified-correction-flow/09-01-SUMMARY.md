---
phase: 09-corr-simplified-correction-flow
plan: 09-01
subsystem: api
tags: [fastapi, sqlite, corrections, vouchers, pytest]
requires:
  - phase: 08
    provides: intake source traceability and agent voucher posting context
provides:
  - Correction note storage with pending/suggested/applied/dismissed/rejected lifecycle
  - Voucher-scoped APIs for notes and draft B-series correction suggestions
  - Service-level dismissal and rejection history for agent learning
affects: [agent-correction-queue, voucher-detail-ui, accounting-corrections]
tech-stack:
  added: []
  patterns:
    - FastAPI route to service to repository lifecycle flow
    - SQLite partial unique index for one active correction note per voucher
key-files:
  created:
    - db/migrations/022_add_correction_notes.sql
    - repositories/correction_note_repo.py
    - services/correction_notes.py
    - tests/test_correction_notes.py
  modified:
    - domain/models.py
    - api/schemas.py
    - api/routes/vouchers.py
    - repositories/accounting_correction_repo.py
key-decisions:
  - "Correction notes remain voucher-scoped and do not link directly to intake sources."
  - "Suggested draft deletion uses ON DELETE SET NULL so terminal notes remain stored."
patterns-established:
  - "CorrectionNoteService owns note lifecycle transitions and maps conflicts through CorrectionNoteError."
  - "Dismissed and rejected suggestions write correction_history with corrected_voucher_id=None."
requirements-completed: [CORR-01, CORR-03, CORR-04, CORR-05, CORR-06]
duration: 35 min
completed: 2026-06-05
---

# Phase 09 Plan 09-01: Backend Correction Notes Summary

**Voucher-scoped correction notes with draft B-series suggestion lifecycle and agent-readable terminal history**

## Performance

- **Duration:** 35 min
- **Started:** 2026-06-05T19:03:00Z
- **Completed:** 2026-06-05T19:38:20Z
- **Tasks:** 4
- **Files modified:** 9

## Accomplishments

- Added `correction_notes` storage, domain model, lifecycle repository, and service.
- Added APIs for creating notes, creating drafts, suggesting, approving, dismissing, and rejecting correction suggestions.
- Added focused API tests covering pending, suggested, applied, dismissed, and rejected lifecycle states.

## Task Commits

1. **Task 1: Add correction note schema and domain model** - `78b829f` (feat)
2. **Task 2: Add repository and lifecycle service** - `307b4b6` (feat)
3. **Task 3: Add voucher-scoped correction note APIs** - `5482706` (feat)
4. **Task 4: Cover backend lifecycle behavior with tests** - `a14d5bc` (test)

## Files Created/Modified

- `db/migrations/022_add_correction_notes.sql` - Correction notes table, indexes, active-note uniqueness, draft FK behavior.
- `domain/models.py` - `CorrectionNote` dataclass.
- `repositories/correction_note_repo.py` - Note CRUD and lifecycle state persistence.
- `repositories/accounting_correction_repo.py` - `_commit` support for transaction-controlled history writes.
- `services/correction_notes.py` - Lifecycle orchestration for draft suggestions, approval, dismissal, rejection.
- `api/schemas.py` - Correction note and draft request/response schemas.
- `api/routes/vouchers.py` - Voucher-scoped correction note and draft routes.
- `tests/test_correction_notes.py` - Focused lifecycle API coverage.

## Decisions Made

- Kept correction notes separate from `correction_history`; history is written only for dismissed/rejected learning context in this plan.
- Let dismissed suggested notes delete the draft voucher and rely on `ON DELETE SET NULL` for `suggested_voucher_id`, preserving the note while removing the draft.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Allowed draft deletion for suggested notes**
- **Found during:** Task 4 (backend lifecycle tests)
- **Issue:** Dismissing a suggested note attempted to delete a draft voucher still referenced by `correction_notes.suggested_voucher_id`, causing a foreign-key failure.
- **Fix:** Added `ON DELETE SET NULL` to the suggested draft foreign key in migration 022.
- **Files modified:** `db/migrations/022_add_correction_notes.sql`
- **Verification:** `.venv/bin/pytest tests/test_correction_notes.py`
- **Committed in:** `a14d5bc`

---

**Total deviations:** 1 auto-fixed (1 blocking).  
**Impact on plan:** Required for the planned dismissal behavior. No scope expansion.

## Issues Encountered

- `pytest` was not available on PATH; verification used `.venv/bin/pytest`.

## Verification

- `.venv/bin/pytest tests/test_correction_notes.py` - 7 passed.
- `.venv/bin/pytest tests/test_agent_accounting_workflow.py tests/test_intake_api.py` - 24 passed.
- `rg "correction_notes|correction-draft|correction-notes|suggested_voucher_id|CorrectionNote" ...` - passed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Backend lifecycle APIs are ready for plan 09-02 to expose correction notes in the agent queue and learning instructions.

---
*Phase: 09-corr-simplified-correction-flow*
*Completed: 2026-06-05*
