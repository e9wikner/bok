---
status: resolved
trigger: "Failed bank upload rows should be deletable, not retried; pending voucher-source rows need clearer agent completion guidance."
created: 2026-06-05
updated: 2026-06-05
---

# Debug Session: Bank Input Delete and Pending Agent Guidance

## Symptoms

- Failed bank CSV uploads remain in the intake list and block uploading the same bytes again.
- Voucher-source rows remain `pending` after upload until the external agent explicitly completes them.

## Current Focus

- hypothesis: Failed bank input cleanup needs an explicit delete path, and agent instructions need to state that successful voucher posting must include the source IDs.
- test: Add backend delete coverage and entrypoint instruction assertions.
- expecting: Failed bank inputs can be deleted and re-uploaded; processed bank inputs cannot be deleted; instructions mention `intake_source_ids`.
- next_action: Complete.

## Evidence

- timestamp: 2026-06-05; observation: `bank_inputs.sha256` is unique, so undeleted failed rows block exact re-upload.
- timestamp: 2026-06-05; observation: voucher sources leave `pending` only when linked through `/api/v1/agent/vouchers` with `intake_source_ids`, or when `/api/v1/agent/intake/{source_id}/failed` is called.
- timestamp: 2026-06-05; observation: the process doc's voucher example did not include `intake_source_ids`.

## Resolution

- root_cause: Missing delete operation for failed bank inputs, plus agent docs that did not explicitly require source IDs in successful voucher posts.
- fix: Added bank input delete support for non-processed rows, frontend delete actions, and clearer entrypoint/system instructions.
- verification: `.venv/bin/pytest tests/test_bank_input_agent.py -q`; `.venv/bin/pytest tests/test_agent_entrypoint.py -q`.
- files_changed: `services/bank_inputs.py`, `repositories/bank_input_repo.py`, `api/routes/bank_inputs.py`, `frontend-v3/lib/api.ts`, `frontend-v3/app/vouchers/intake/page.tsx`, `docs/to_agent/02_bokforingsprocess.md`, `tests/test_bank_input_agent.py`, `tests/test_agent_entrypoint.py`.
