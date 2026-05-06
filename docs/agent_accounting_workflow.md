# Agent Accounting Workflow

This document defines the target workflow for AI-driven bookkeeping.

## Goal

The accounting agent should book directly from its current instructions. The
frontend is a review and correction surface after the fact, not an approval gate
before posting.

The backend owns persistence, validation, audit trails, correction mechanics,
and the current instruction document. The agent owns interpretation and
bookkeeping decisions.

## Core Flow

1. The agent reads the active accounting instruction document from the backend.
2. The agent reads historical posted vouchers and correction history through the API.
3. The agent updates the instruction document when it has learned better general guidance.
4. The agent creates vouchers directly as posted accounting entries.
5. A human reviews posted vouchers in the frontend.
6. If a voucher is wrong, the human creates a correction.
7. The correction is stored as a posted B-series correction voucher and exposed to the agent.
8. The agent later uses the correction history to improve the instruction document.

## Instruction Document

The instruction document is Markdown, similar in spirit to `AGENTS.md`.

It should contain general, reusable bookkeeping guidance:

- hard constraints, such as balancing and active accounts
- default accounts and VAT principles
- company-specific routines
- recurring suppliers and customers
- known exceptions and warnings
- guidance learned from previous human corrections

It should not try to encode every possible voucher as deterministic percentage
rules. The agent is expected to reason from the document and the source material.

## Direct Posting

Agent-created vouchers are posted immediately. Backend validation is still
mandatory:

- debit equals credit
- all accounts exist and are active
- period exists and is open
- voucher date belongs to the selected period
- voucher has complete rows and description

The backend does not decide which accounts should be used. It only validates the
formal accounting constraints.

## Corrections

Posted vouchers remain immutable. Corrections are represented by a separate
B-series voucher linked to the original voucher.

The correction voucher should contain:

- reversing rows for the original posting
- corrected rows representing the intended posting
- a reason supplied by the user or agent
- audit trail metadata

The correction history is exposed to the agent so it can update the instruction
document.

## API Surface

Minimum API surface:

- `GET /api/v1/agent-instructions/accounting`
- `PUT /api/v1/agent-instructions/accounting`
- `GET /api/v1/agent-instructions/accounting/versions`
- `POST /api/v1/agent/vouchers`
- `POST /api/v1/vouchers/{id}/correct`
- `GET /api/v1/accounting-corrections`

Existing voucher, account, period and report endpoints remain the primary way
for the agent to read historical bookkeeping data.

## Frontend Role

Frontend responsibilities:

- show active instructions and version history
- show posted agent vouchers
- allow a human to create corrections
- show correction chains and audit trail
- expose corrections that the agent can learn from

Frontend should not contain bookkeeping decision logic.
