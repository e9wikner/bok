---
quick_id: 260605-qfh
status: complete
completed: 2026-06-05
---

# Summary

Analyzed why Verifikationsunderlag can remain `Väntar` after agent voucher posting.

## Root Cause

`POST /api/v1/agent/vouchers` can create and post a voucher without any `intake_source_ids` because `AgentVoucherRequest.intake_source_ids` defaults to an empty list in `api/routes/agent.py`.

When the list is empty, the route still:

- creates a voucher with `LedgerService.create_voucher`
- posts it with `LedgerService.post_voucher`
- skips the `IntakeService.link_existing_voucher` loop
- returns success with `agent.intake_source_ids: []`

The only code path that moves an intake source from `pending` to `processed` is `IntakeService.link_existing_voucher`, which creates the `voucher_intake_sources` link, records a processed attempt, and updates `intake_sources.status`.

This means the backend currently relies on agent discipline instead of enforcing source traceability. Existing tests explicitly preserve the problematic behavior in `test_agent_voucher_without_intake_sources_still_posts_directly`.

## Proposed Solution

Make traceability a backend contract for voucher-source driven agent posting:

1. Require non-empty `intake_source_ids` when an agent is processing `voucher_source` queue items.
2. Reject a voucher-source agent post that omits source IDs with `400` and a structured error such as `missing_intake_source_ids`.
3. Keep the existing validation for invalid, non-processable, and already-linked source IDs.
4. Keep bank-only postings valid when they include `bank_input_ids` and `bank_transaction_ids`.
5. Update tests so omission is no longer accepted when a pending voucher source exists or when the request declares voucher-source origin.

## Files Reviewed

- `api/routes/agent.py`
- `api/routes/vouchers.py`
- `services/intake.py`
- `repositories/intake_repo.py`
- `api/routes/agent_instructions.py`
- `docs/to_agent/02_bokforingsprocess.md`
- `tests/test_intake_api.py`
- `tests/test_bank_input_agent.py`
- `tests/test_agent_accounting_workflow.py`

## Verification

No source code was changed and no tests were run. This was an analysis/proposal task.
