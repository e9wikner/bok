---
phase: 02-bank-input-and-direct-posting-context
status: clean
reviewed_at: 2026-05-15
depth: standard
reviewer: inline-codex
files_reviewed:
  - api/routes/agent.py
  - api/routes/bank_inputs.py
  - config.py
  - db/migrations/019_add_bank_inputs.sql
  - domain/models.py
  - domain/types.py
  - repositories/agent_instruction_repo.py
  - repositories/bank_input_repo.py
  - services/bank_integration.py
  - services/bank_inputs.py
  - tests/test_agent_accounting_workflow.py
  - tests/test_bank_categorization.py
  - tests/test_bank_input_agent.py
  - tests/test_intake_api.py
findings_open: 0
findings_fixed: 1
---

# Phase 02 Code Review

## Verdict

Clean after one fix.

## Fixed Findings

### 1. Preserved bank input file could be deleted after row creation

- **Severity:** warning
- **File:** `services/bank_inputs.py`
- **Issue:** `create_from_upload_content` committed the `bank_inputs` row before processing the CSV, but its broad exception handler still deleted the stored file for unexpected post-commit processing failures. That could leave a durable bank input row pointing at a missing original CSV.
- **Fix:** Track whether the row was created and only clean up the file before that point. Once the row exists, preserve the original file and let the failure surface for diagnosis.
- **Commit:** `7ba4b6f`
- **Verification:** `.venv/bin/pytest tests/test_bank_input_agent.py -q` passed.

## Open Findings

None.

## Notes

- Root containment checks are present before bank input file serving.
- Bank-driven agent posting preflights transaction status/linkage before voucher creation.
- Successful bank-driven posting links voucher-bank evidence and marks transactions booked after `LedgerService.post_voucher` succeeds.
- Phase tests cover duplicate upload rejection, unsupported CSV failure state, transaction skip counts, mixed queue items, ordinary source linking, and booked/matched reuse rejection.
