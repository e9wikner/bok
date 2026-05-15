---
phase: 02-bank-input-and-direct-posting-context
plan: 02-01
subsystem: api
tags: [bank-inputs, csv-upload, sqlite, filesystem, traceability]
requires:
  - phase: 01-intake-foundation-and-agent-queue
    provides: voucher source intake storage, agent queue patterns, and direct posting traceability
provides:
  - Separate bank input upload schema for CSV bank source files
  - Bank input repository and service with active connection validation
  - Authenticated bank input metadata and original CSV download API
  - Root-contained file resolution and duplicate upload rejection
affects: [bank-inputs, agent-intake, bank-integration]
tech-stack:
  added: []
  patterns: [service-owned upload validation, repository row mappers, root-contained local file serving]
key-files:
  created:
    - db/migrations/019_add_bank_inputs.sql
    - repositories/bank_input_repo.py
    - services/bank_inputs.py
    - api/routes/bank_inputs.py
    - tests/test_bank_input_agent.py
  modified:
    - config.py
    - domain/types.py
    - domain/models.py
    - api/main.py
key-decisions:
  - "Bank CSV uploads are stored in a separate bank_inputs model rather than intake_sources."
  - "Uploads require an existing active bank connection before a bank input row is created."
  - "Original CSV downloads are served only after resolving the stored path under settings.bank_input_dir."
patterns-established:
  - "Bank input routes mirror intake routes: thin FastAPI handlers over typed service errors."
  - "Bank input repository methods support _commit=False for service-level transactions."
requirements-completed: [BANK-01, BANK-02]
duration: 15 min
completed: 2026-05-15
---

# Phase 02 Plan 01: Bank Statement/Status Intake Records and Upload API Summary

**CSV bank input uploads with separate SQLite source records, active bank connection validation, and safe original-file downloads**

## Performance

- **Duration:** 15 min
- **Started:** 2026-05-15T08:00:00Z
- **Completed:** 2026-05-15T08:15:00Z
- **Tasks:** 4
- **Files modified:** 9

## Accomplishments

- Added `bank_inputs`, `bank_input_transactions`, `voucher_bank_inputs`, and `voucher_bank_transactions` schema with lifecycle, duplicate, and traceability constraints.
- Added bank input domain types plus repository/service layers for CSV-only uploads, duplicate detection, active connection validation, and safe filesystem resolution.
- Added authenticated `POST /api/v1/bank-inputs`, metadata retrieval, and original CSV download routes.
- Added direct route/service tests covering pending upload metadata, duplicate rejection, non-CSV rejection, active connection enforcement, download behavior, and outside-root protection.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add bank input schema and domain model** - `cf6866c` (feat)
2. **Task 2: Add repository and service for CSV-only bank input storage** - `1e2195e` (feat)
3. **Task 3: Add authenticated bank input upload, metadata, and file routes** - `d8eb7c6` (feat)
4. **Task 4: Cover bank input storage and upload behavior** - `625caf1` (test)

## Files Created/Modified

- `db/migrations/019_add_bank_inputs.sql` - Bank input, transaction linkage, and voucher traceability schema.
- `config.py` - Adds `bank_input_dir` defaulting under the intake storage root.
- `domain/types.py` - Adds `BankInputStatus`.
- `domain/models.py` - Adds bank input and voucher-bank traceability dataclasses.
- `repositories/bank_input_repo.py` - Persists bank inputs, processing metadata, and traceability links.
- `services/bank_inputs.py` - Validates CSV uploads, selected bank connections, duplicate hashes, and root-contained downloads.
- `api/routes/bank_inputs.py` - Adds upload, metadata, and original file download routes.
- `api/main.py` - Registers bank input routes.
- `tests/test_bank_input_agent.py` - Covers storage and API behavior.

## Decisions Made

- Followed the Phase 2 plan by keeping bank inputs separate from voucher intake sources.
- Used `settings.bank_input_dir` as an explicit storage setting with a default under `settings.intake_dir`.
- Kept Plan 02-01 uploads `pending`; immediate CSV import is intentionally handled by Plan 02-02.

## Deviations from Plan

None - plan executed exactly as written.

---

**Total deviations:** 0 auto-fixed.
**Impact on plan:** No scope changes.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Verification

- `.venv/bin/python -m py_compile domain/types.py domain/models.py repositories/bank_input_repo.py services/bank_inputs.py api/routes/bank_inputs.py tests/test_bank_input_agent.py` - passed
- `.venv/bin/pytest tests/test_bank_input_agent.py -q` - passed, 6 tests
- `git diff --check` - passed

## Next Phase Readiness

Bank input rows and original CSV storage are ready for Plan 02-02 to process uploads immediately through `BankIntegrationService.import_csv`.

---
*Phase: 02-bank-input-and-direct-posting-context*
*Completed: 2026-05-15*
