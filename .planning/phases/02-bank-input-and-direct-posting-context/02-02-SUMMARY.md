---
phase: 02-bank-input-and-direct-posting-context
plan: 02-02
subsystem: bank-import
tags: [bank-inputs, csv-detection, bank-transactions, import-lifecycle]
requires:
  - phase: 02-01
    provides: bank input storage, metadata, upload API, and transaction link schema
provides:
  - Deterministic supported Swedish bank CSV format detection
  - Detailed bank CSV import result with imported transaction IDs and skipped duplicate IDs
  - Immediate bank input processing lifecycle after upload
  - Bank input to bank transaction traceability links
affects: [bank-inputs, bank-integration, agent-intake]
tech-stack:
  added: []
  patterns: [CSV format detector, detailed import result object, retained failed source records]
key-files:
  created: []
  modified:
    - services/bank_integration.py
    - services/bank_inputs.py
    - tests/test_bank_input_agent.py
    - tests/test_bank_categorization.py
key-decisions:
  - "Bank CSV import now returns a CsvImportResult object rather than only two counts."
  - "Failed CSV format detection preserves the bank input row and original file with parse_error."
  - "Repeated transaction rows are counted as skipped and not linked to bank_input_transactions."
patterns-established:
  - "BankInputService creates a durable pending row before import, then transitions it to processed or failed."
  - "BankIntegrationService keeps import_transactions backwards-compatible while exposing detailed IDs for bank input orchestration."
requirements-completed: [BANK-02, BANK-03]
duration: 14 min
completed: 2026-05-15
---

# Phase 02 Plan 02: CSV Import Integration and Source Batch Linkage Summary

**Supported Swedish bank CSV uploads now import transactions immediately, store lifecycle counts, and link imported rows to their source file**

## Performance

- **Duration:** 14 min
- **Started:** 2026-05-15T08:15:00Z
- **Completed:** 2026-05-15T08:29:00Z
- **Tasks:** 4
- **Files modified:** 4

## Accomplishments

- Added supported bank CSV detection for `Datum;Belopp;Text` and a Swedish booking-day/message variant.
- Extended CSV import to return imported counts, skipped counts, imported transaction IDs, skipped external IDs, and detected format.
- Updated bank input upload processing so supported CSVs become `processed`, unsupported CSVs become retained `failed` records, and original files remain preserved.
- Linked imported transaction rows to `bank_input_transactions` and covered duplicate transaction skip counts.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add known-format CSV detection to bank integration** - `8fef11b` (feat)
2. **Tasks 2-3: Process bank inputs immediately and link imported rows** - `de1d3c4` (feat)
3. **Task 4: Cover CSV import lifecycle, detection failure, and duplicate skipping** - `3b2d258` (test)

## Files Created/Modified

- `services/bank_integration.py` - Adds `CsvImportResult`, format detection, detailed import IDs, and unsupported-format errors.
- `services/bank_inputs.py` - Processes persisted CSV uploads into `processed` or `failed` lifecycle states.
- `tests/test_bank_input_agent.py` - Covers supported import, failed lifecycle, transaction links, duplicate hash rejection, and duplicate row skip counts.
- `tests/test_bank_categorization.py` - Aligns existing CSV import assertion with detailed result output.

## Decisions Made

- Kept `import_transactions` compatible for existing callers while adding a `return_details` option for bank input orchestration.
- Failed parsing does not delete the uploaded CSV or row; it records the stable parse error for agent/user inspection.
- Duplicate transaction external IDs increment skip counts but do not create traceability links for skipped duplicate rows.

## Deviations from Plan

None - plan executed exactly as written.

---

**Total deviations:** 0 auto-fixed.
**Impact on plan:** No scope changes.

## Issues Encountered

Existing `tests/test_bank_categorization.py` expected two-count tuple unpacking from `import_csv`; it was updated to assert against `CsvImportResult.imported_count`.

## User Setup Required

None - no external service configuration required.

## Verification

- `.venv/bin/python -m py_compile services/bank_integration.py services/bank_inputs.py repositories/bank_input_repo.py tests/test_bank_input_agent.py` - passed
- `.venv/bin/pytest tests/test_bank_input_agent.py -q` - passed, 11 tests
- `.venv/bin/pytest tests/test_bank_input_agent.py tests/test_bank_categorization.py -q` - passed, 35 tests
- `git diff --check` - passed

## Next Phase Readiness

Processed bank inputs now provide transaction links and match signals for Plan 02-03 to expose in the agent intake queue and enforce during bank-driven voucher posting.

---
*Phase: 02-bank-input-and-direct-posting-context*
*Completed: 2026-05-15*
