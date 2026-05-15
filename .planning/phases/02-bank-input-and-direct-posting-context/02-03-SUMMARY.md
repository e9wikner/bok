---
phase: 02-bank-input-and-direct-posting-context
plan: 02-03
subsystem: agent-api
tags: [agent-context, bank-inputs, voucher-posting, traceability, corrections]
requires:
  - phase: 02-01
    provides: bank input schema, upload API, and file storage
  - phase: 02-02
    provides: processed bank input rows linked to imported transactions
provides:
  - Typed mixed agent intake queue for voucher sources and bank inputs
  - Correction history discovery from the agent context surface
  - Bank transaction availability preflight before voucher creation
  - Voucher-bank input and transaction traceability after posting
  - Booked/matched status updates for bank transactions used by vouchers
affects: [agent-api, bank-inputs, intake, accounting-corrections]
tech-stack:
  added: []
  patterns: [preflight-before-ledger-posting, post-ledger traceability linking, compact typed context items]
key-files:
  created: []
  modified:
    - api/routes/agent.py
    - services/bank_inputs.py
    - repositories/bank_input_repo.py
    - repositories/agent_instruction_repo.py
    - tests/test_bank_input_agent.py
    - tests/test_intake_api.py
    - tests/test_agent_accounting_workflow.py
key-decisions:
  - "Bank-driven posting still uses LedgerService.create_voucher and LedgerService.post_voucher for formal accounting constraints."
  - "Bank transaction reuse is rejected before voucher creation when status is booked or matched_voucher_id is set."
  - "Successful posting links supplied bank inputs and exact transaction rows, then marks transactions booked."
patterns-established:
  - "Agent queue items use kind discriminators with type-specific payload fields."
  - "Bank traceability is linked only after ledger posting succeeds."
requirements-completed: [BANK-04, BANK-05, BANK-06, AGNT-06]
duration: 18 min
completed: 2026-05-15
---

# Phase 02 Plan 03: Agent Context and Posting Safeguards for Bank-Driven Vouchers Summary

**Agent context now exposes typed bank input work and bank-driven voucher posting is guarded against transaction reuse with durable source links**

## Performance

- **Duration:** 18 min
- **Started:** 2026-05-15T08:29:00Z
- **Completed:** 2026-05-15T08:47:00Z
- **Tasks:** 4
- **Files modified:** 7

## Accomplishments

- Extended `/api/v1/agent/intake/pending` with `kind: "voucher_source"` and `kind: "bank_input"` items plus a correction history URL.
- Added compact bank input context with transaction IDs/counts and match signals without inlining full transaction rows.
- Added bank input and bank transaction fields to agent voucher posting requests.
- Added preflight guardrails that reject unprocessed inputs, unlinked transactions, booked transactions, and matched transactions before voucher creation.
- Added post-success traceability linking to `voucher_bank_inputs` and `voucher_bank_transactions`, then marked used transactions `booked` with `matched_voucher_id`.
- Kept ordinary intake source linking available alongside bank evidence.

## Task Commits

Each task was committed atomically:

1. **Tasks 1-3: Typed queue, posting guardrails, and voucher traceability** - `f3b144f` (feat)
2. **Task 4: Expose correction history and cover bank-driven agent workflows** - `6558bef` (test)

## Files Created/Modified

- `api/routes/agent.py` - Adds typed queue output, bank fields on agent voucher requests, preflight guardrails, and traceability response data.
- `services/bank_inputs.py` - Adds agent queue item packaging, transaction availability checks, and posted-voucher linking.
- `repositories/bank_input_repo.py` - Adds transaction/input lookup helpers and booked transaction updates.
- `repositories/agent_instruction_repo.py` - Fixes company invoicing default selection uncovered by current workflow tests.
- `tests/test_bank_input_agent.py` - Covers mixed queue output, correction history discovery, posting traceability, multiple transactions, ordinary source linking, and reuse rejection.
- `tests/test_intake_api.py` - Updates ordinary intake posting coverage for multiple source links.
- `tests/test_agent_accounting_workflow.py` - Aligns instruction and correction tests with current API/date behavior.

## Decisions Made

- Kept the backend duplicate guard deterministic: explicit reuse of `booked` or matched bank transactions returns HTTP 409 before ledger voucher creation.
- Kept queue transaction data compact by returning IDs, counts, and match signals only.
- Exposed correction history through `correction_history_url` instead of duplicating full correction payloads in every queue response.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Invoicing company defaults used accounting text**
- **Found during:** Task 4 combined verification.
- **Issue:** `AgentInstructionRepository._default_content` only checked `scope == "invoicing"`, so `invoicing_company` initialized with accounting instructions.
- **Fix:** Treat both `invoicing` and `invoicing_company` as invoicing scopes.
- **Files modified:** `repositories/agent_instruction_repo.py`, `tests/test_agent_accounting_workflow.py`
- **Verification:** `tests/test_agent_accounting_workflow.py` passed in the combined plan verification.
- **Committed in:** `6558bef`

---

**Total deviations:** 1 auto-fixed (blocking test/API correctness issue).
**Impact on plan:** Fix was adjacent to AGNT-06/current agent context tests and prevented stale instruction behavior from masking verification.

## Issues Encountered

- Existing correction test used a March accounting period while correction vouchers use the current date. The test was updated to use a May 2026 period so the correction date `2026-05-15` is inside the open period.
- Existing instruction tests expected the legacy flat instruction response; they now assert the current `{system, company}` response shape.

## User Setup Required

None - no external service configuration required.

## Verification

- `.venv/bin/python -m py_compile api/routes/agent.py services/bank_inputs.py repositories/bank_input_repo.py tests/test_bank_input_agent.py tests/test_agent_accounting_workflow.py` - passed
- `.venv/bin/pytest tests/test_bank_input_agent.py tests/test_intake_api.py tests/test_agent_accounting_workflow.py -q` - passed, 31 tests
- `git diff --check` - passed

## Next Phase Readiness

Phase 2 backend support is complete: bank CSV inputs are separate source material, imported rows are traceable, agent context is typed, correction history is discoverable, and bank-driven direct posting has backend reuse safeguards.

---
*Phase: 02-bank-input-and-direct-posting-context*
*Completed: 2026-05-15*
