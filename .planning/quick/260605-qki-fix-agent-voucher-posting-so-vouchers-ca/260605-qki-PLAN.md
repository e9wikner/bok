---
quick_id: 260605-qki
status: in_progress
created: 2026-06-05
mode: quick
---

# Quick Task 260605-qki: Enforce source traceability for agent voucher posting

## Goal

Prevent `POST /api/v1/agent/vouchers` from creating posted vouchers with no source traceability, so Verifikationsunderlag cannot remain `pending` because an agent omitted `intake_source_ids`.

## Tasks

### T1 - Add endpoint validation

Files:
- `api/routes/agent.py`

Action:
- Reject agent voucher requests that include neither `intake_source_ids` nor `bank_input_ids`.
- Return a structured `400` response with a stable code.
- Preserve existing bank transaction validation, including the rule that transaction IDs require bank input IDs.

Verify:
- Ordinary voucher-source requests still link and process intake sources.
- Bank-input requests still post.

Done:
- Agent endpoint cannot post untraceable vouchers.

### T2 - Update regression tests

Files:
- `tests/test_intake_api.py`
- `tests/test_bank_input_agent.py`
- `tests/test_agent_accounting_workflow.py`

Action:
- Replace the existing "without intake sources still posts" expectation with rejection coverage.
- Ensure rollback/no-voucher behavior is tested for missing traceability.
- Update direct agent workflow tests to provide traceability when using the agent endpoint.

Verify:
- Run focused pytest for intake, bank input agent, and agent workflow tests.

Done:
- Tests encode the new backend contract.
