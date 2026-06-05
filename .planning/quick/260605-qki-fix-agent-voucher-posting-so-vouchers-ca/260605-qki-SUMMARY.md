---
quick_id: 260605-qki
status: complete
completed: 2026-06-05
---

# Summary

Implemented source traceability enforcement for agent voucher posting.

## Changes

- `POST /api/v1/agent/vouchers` now rejects requests that include neither `intake_source_ids` nor `bank_input_ids`.
- Rejection happens before voucher creation and returns `400` with code `missing_source_traceability`.
- Existing bank transaction validation remains intact; bank transaction IDs still require a supplied bank input ID.
- Tests now assert untraceable agent voucher posting does not create a voucher.
- Agent workflow and bank-input tests now provide real traceability IDs where posting is expected.
- Agent-facing documentation and API examples now describe the traceability requirement.

## Verification

- `.venv/bin/pytest tests/test_intake_api.py tests/test_bank_input_agent.py tests/test_agent_accounting_workflow.py tests/test_agent_entrypoint.py tests/test_deployment_docs.py`
  - 95 passed

Attempted a full `.venv/bin/pytest` run, but the PTY stopped returning output after the start of `tests/test_api.py`; no pytest process was visible afterward. The focused regression suite covering the changed behavior completed successfully.
