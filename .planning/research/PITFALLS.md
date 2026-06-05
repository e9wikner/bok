# Pitfalls Research

**Domain:** Agent usability improvements for a Swedish bookkeeping system (Bok)
**Researched:** 2026-06-05
**Confidence:** HIGH (based on direct codebase analysis, existing test suite, and Swedish bookkeeping compliance constraints)

## Critical Pitfalls

### Pitfall 1: Race-Condition on Intake Source Linking

**What goes wrong:**
Two concurrent agent requests (or a user action and an agent action) attempt to link the same intake source to different vouchers. The application-level `get_link_by_source_id` check followed by `create_voucher_link` is not atomic. The database `UNIQUE(intake_source_id)` constraint on `voucher_intake_sources` catches the second insert, but the first voucher may already have been posted and the intake source status updated to `processed`, leaving the second request with a cryptic 409 instead of a clear "already linked" error.

**Why it happens:**
The repository uses `get_link_by_source_id` in `IntakeService._ensure_can_record_outcome`, which is a separate SQL query from the subsequent `create_voucher_link`. In SQLite with multiple threads (the app uses thread-local connections), there is a window between the check and the insert. The existing code does not use `SELECT ... FOR UPDATE` or an application-level lock.

**How to avoid:**
1. Make the check-and-link atomic using a single `INSERT` with `ON CONFLICT` handling, or wrap the entire validation-and-link in `db.transaction()` with immediate mode if SQLite concurrency is an issue.
2. Return the *existing* link information in the error response so the agent knows which voucher already owns the source.
3. For deduplication, allow multiple links per source (remove `UNIQUE(intake_source_id)` from `voucher_intake_sources`) if the business rule supports it — but only after confirming that the agent's processing logic can handle 1:N source-to-voucher mappings.

**Warning signs:**
- Intermittent 409 errors in the agent integration logs with `code: "intake_not_processable"` or `code: "intake_already_linked"` during high-load periods.
- Test flakiness when running `test_agent_voucher_rejects_duplicate_intake_link` under parallel pytest.

**Phase to address:**
Intake deduplication/linking (DEDUP-01) — specifically the migration and repository layer changes.

---

### Pitfall 2: Violating BFL Immutability by Replacing Correction Vouchers with Text Notes

**What goes wrong:**
The simplified correction flow (CORR-01) lets users leave a text note instead of creating a B-series correction. If the implementation stores the note and changes the voucher directly (or skips the B-series voucher entirely), it violates the Swedish Bookkeeping Act (BFL §5 kap 6) requirement for immutable posted vouchers. This breaks auditability and could invalidate the books for tax review.

**Why it happens:**
The user story says "text correction note instead of creating a B-series correction themselves." Developers might implement this as a new `correction_notes` table that sits alongside the voucher, or — worse — as a soft-update to the posted voucher rows. The product intent is to *automate* the correction, not to *skip* it.

**How to avoid:**
1. The backend must still create a B-series correction voucher via `LedgerService.create_posted_correction` (or a new service method). The text note is only the *input* to the agent, not the correction mechanism.
2. Store the user's text note in a new `correction_requests` table (or extend `accounting_corrections`), then have the agent read it and generate the actual B-series rows.
3. Never modify `voucher_rows` for a posted voucher. The existing SQLite triggers (`prevent_update_rows_for_posted_vouchers`) enforce this at the DB level; if those triggers start firing, the design is wrong.
4. The approval step must show the user the *proposed B-series voucher rows* before posting, not just a summary.

**Warning signs:**
- `sqlite3.OperationalError: posted vouchers are immutable` in production logs.
- Frontend code calling `api.updateVoucher` on a posted voucher instead of `api.correctVoucher`.
- Missing `correction_of` field on the agent-generated voucher.

**Phase to address:**
Simplified correction flow (CORR-01) — backend service layer and frontend approval UI.

---

### Pitfall 3: Unbounded Growth of Agent Instruction Versions

**What goes wrong:**
The agent instruction repository (`AgentInstructionRepository`) creates a new version row for every `update()` call. If the agent is configured to persist every learned nuance automatically, the `agent_instruction_versions` table grows without bound. This inflates the database, slows down version listing, and eventually makes the instruction payload too large for the agent context window.

**Why it happens:**
The current `update()` method always inserts a new version with an auto-incrementing integer. There is no size limit on `content_markdown`, no versioning retention policy, and no deduplication. The agent might call the update endpoint after every single correction.

**How to avoid:**
1. Add a max version limit (e.g., keep last 100 versions) with a background cleanup or a capped insert policy.
2. Add a `content_markdown` length limit (e.g., 50KB) validated at the API layer.
3. Implement a "diff" update: if the agent's new content is identical to the last version, skip the insert.
4. Provide a "prune" or "compress" instruction endpoint that consolidates older versions into a summary.

**Warning signs:**
- `SELECT COUNT(*) FROM agent_instruction_versions` returns thousands of rows for a single scope.
- The GET `/versions` endpoint becomes slow (>500ms).
- Agent context window truncation because the instruction markdown is too large.

**Phase to address:**
Agent instruction persistence (INSTR-01) — repository and API layer.

---

### Pitfall 4: Conflating "Explanation" with "Agent Guidance" on Intake Sources

**What goes wrong:**
Per-source agent guidance (GUIDE-01) might reuse the existing `explanation` field on `intake_sources`. This confuses two distinct user intents: "explain what this document is" vs. "tell the agent how to book this document." The frontend might display the guidance text in the explanation area, confusing users during review. Worse, the agent might treat user guidance as a factual override and ignore accounting rules or historical corrections.

**Why it happens:**
The `explanation` field already exists and is shown in the intake workspace and voucher source context. It is tempting to reuse it rather than add a new column. But the user who uploads a receipt may not be the same person who reviews the agent's output, and conflating the fields breaks the separation of concerns.

**How to avoid:**
1. Add a dedicated `agent_guidance` column to `intake_sources` (or a separate `intake_source_guidance` table if the guidance needs versioning).
2. In the frontend, keep the explanation field as a general description and the guidance field as a collapsible "Agent instructions" textarea.
3. In the agent prompt / system instructions, explicitly state that user guidance is a *hint*, not an *override*, and that formal rules (balance, period, account validity) and correction history take precedence.
4. Include the `agent_guidance` field in the agent's context only when processing that specific source, not in the global instruction document.

**Warning signs:**
- The frontend shows the agent guidance text in the "Förklaring" (Explanation) field on the intake detail page.
- The agent produces incorrect vouchers because it over-weights the user's guidance.
- Users complain that their "explanation" is being used by the agent in unexpected ways.

**Phase to address:**
Per-source agent guidance (GUIDE-01) — database migration, frontend upload form, and agent context builder.

---

### Pitfall 5: Bank Transaction Matchability Exposes Already-Booked Transactions as Actionable

**What goes wrong:**
Bank transaction matchability (MATCH-01) exposes imported bank transactions in the agent API. If the agent queue or matchability endpoint includes transactions that are already `booked` or `matched`, the agent will waste cycles trying to create vouchers from them. Worse, if the API allows the agent to "suggest a match" for an already-booked transaction, it might create duplicate vouchers or confusing error states.

**Why it happens:**
The current `agent_queue_items` in `BankInputService` returns all processed bank inputs and their transactions, but the `match_signals` already include `status` and `matched_voucher_id`. The agent is supposed to read these, but the agent's reasoning might be imperfect. If the matchability endpoint is designed to let the agent *find* matchable transactions, it needs to explicitly exclude booked/matched ones from the "actionable" set, or at least label them clearly.

**How to avoid:**
1. Split the API into two views: `GET /agent/bank-transactions` returns all transactions (for reference), and `GET /agent/bank-transactions/matchable` returns only those with `status = 'pending'` and `matched_voucher_id IS NULL`.
2. Include a clear `matchable: false` flag and `reason` ("already booked", "already matched") in the response for non-actionable transactions.
3. Ensure the existing guardrails in `BankInputService.ensure_transactions_available` remain active — they already reject `booked` and `matched` transactions, but the error should be surfaced in the agent's context before it attempts posting.

**Warning signs:**
- Agent logs show repeated attempts to create vouchers from the same bank transaction.
- The `bank_transaction_already_booked` or `bank_transaction_already_matched` error rate spikes.
- The matchability endpoint returns a large list where most items are not actionable.

**Phase to address:**
Bank transaction matchability (MATCH-01) — agent API routes and service filtering.

---

### Pitfall 6: Agent Entrypoint Becomes Out of Sync with New Capabilities

**What goes wrong:**
The `GET /api/v1/agent-instructions/entrypoint` endpoint is hardcoded with a list of supported endpoints, workflow steps, and guardrails. When new features (deduplication, matchability, guidance, correction suggestions) are added, the entrypoint is not updated. The external agent (e.g., OpenClaw) relies on the entrypoint to discover capabilities, so it never learns about the new endpoints.

**Why it happens:**
The entrypoint is a static dict in `api/routes/agent_instructions.py`. It is easy to add new routes but forget to update the entrypoint. The existing test suite (`tests/test_agent_entrypoint.py`) validates the entrypoint content, but only for the features that existed at the time of v1.2.

**How to avoid:**
1. Treat the entrypoint as a contract that must be updated in the same PR as the new routes.
2. Extend `tests/test_agent_entrypoint.py` with assertions for every new workflow endpoint, guardrail, and unsupported feature note.
3. Add a code-review checklist item: "If you added a new agent-facing route, is it listed in the entrypoint?"
4. Consider generating the entrypoint dynamically from router metadata (though the current static approach is simpler and less error-prone if tests are maintained).

**Warning signs:**
- The deployed agent doesn't use the new `/agent/bank-transactions/matchable` endpoint because it wasn't in the startup sequence.
- `tests/test_agent_entrypoint.py` passes but the new routes are missing from the entrypoint payload.

**Phase to address:**
All phases — entrypoint update must be part of each feature's definition of done.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Reuse `explanation` for agent guidance | No migration needed | Field semantics blur, agent confusion | Never — add a dedicated column |
| Let agent append instructions without size limits | Simple implementation | Database bloat, context overflow | Only if a pruning job is added immediately after |
| Skip B-series voucher for "simplified" correction | Faster UX | Illegal books, audit failure | Never — the simplification must be in the UX, not the backend |
| Allow 1:N source-to-voucher links without updating `UNIQUE(intake_source_id)` | No schema change | Data inconsistency, duplicate processing | Only if the business rule explicitly allows it and tests are added |
| Return all bank transactions as "matchable" | Fewer endpoints | Agent confusion, wasted processing | Never — filter by status |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-----------|----------------|------------------|
| Agent → Intake linking | Not returning existing voucher ID in 409 response | Include `existing_voucher_id` in the `IntakeConflictError` details so the agent can review |
| Agent → Bank transaction matching | Including `booked` transactions in the matchable queue | Explicitly split into `all` and `matchable` endpoints |
| Agent → Instruction update | Agent overwrites user guidance | Store `created_by` and allow user/ agent scopes; merge or append rather than blind overwrite |
| Frontend → Intake upload | Showing agent guidance field as required | Keep it optional; most users don't need to guide the agent |
| Frontend → Correction flow | Calling `updateVoucher` instead of `correctVoucher` for posted vouchers | Always use the correction endpoint; the backend enforces immutability via triggers |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Loading all instruction versions | GET `/versions` becomes slow | Cap at 100 versions, add pagination | ~500+ versions |
| Loading all bank transactions in agent queue | Large CSV imports create huge JSON payloads | Paginate transaction lists, add `matchable_only` filter | ~1000+ transactions per bank input |
| Full-text search on intake sources without index | Workspace list slows down | Add index on `explanation` if searching, or use FTS | ~10,000+ intake sources |
| N+1 on match_signals in agent queue | Each bank input queries transactions individually | Eager-load or join in the repository query | ~50+ bank inputs per page |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Agent guidance field contains PII or sensitive business info | Exposure in audit logs or agent context | Treat guidance with same privacy as `explanation`; don't log it in audit unless necessary |
| Agent can update instructions without user review | Agent learns a bad pattern and corrupts all future bookkeeping | Require approval for agent instruction updates, or at least log them prominently |
| File-serving path for intake sources bypasses root check | Arbitrary file read | Keep `resolve_source_file` and `resolve_input_file` checks; add tests for every new file route |
| Correction note bypasses auth or actor tracking | Untracked changes | Ensure `corrected_by` is populated, even for agent-suggested corrections |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Agent guidance field is always visible | Non-expert users feel overwhelmed | Collapse it behind an "Advanced" or "Agent instructions" accordion |
| Simplified correction shows no preview of the B-series voucher | User approves blindly, leading to wrong corrections | Show the proposed rows and reason before the user confirms |
| Intake workspace shows "processed" items without link to voucher | User can't verify what the agent did | Always show the linked voucher ID and a direct link |
| Bank transaction match signals are too technical | User doesn't understand why a transaction is "not matchable" | Human-readable status labels: "Redan bokförd", "Väntar på matchning" |

## "Looks Done But Isn't" Checklist

- [ ] **Intake deduplication:** The `UNIQUE(intake_source_id)` constraint is removed or confirmed intentional — verify with a test that links one source to two vouchers if the rule allows it.
- [ ] **Bank matchability:** The `matchable` endpoint excludes `booked` and `matched` transactions — verify with a query that returns only pending transactions.
- [ ] **Agent instruction persistence:** A version limit or pruning strategy is in place — verify by creating 105 versions and confirming only 100 remain.
- [ ] **Per-source guidance:** The frontend has a separate field from `explanation` — verify in the upload form and the intake detail page.
- [ ] **Simplified correction:** The backend still creates a B-series voucher — verify by checking the `correction_of` field and the `AccountingCorrectionRepository` entry.
- [ ] **Agent entrypoint:** New endpoints are listed in the entrypoint — verify with `tests/test_agent_entrypoint.py` assertions.
- [ ] **File path security:** Any new file-serving route checks `is_relative_to(root)` — verify with a path traversal test.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Race-condition on intake linking | LOW | Re-run the agent processing; the second request will see the existing link and skip. If data is inconsistent, manually update `intake_sources.status` to `processed` and ensure the link exists. |
| BFL immutability violation | HIGH | Stop the agent. Use `db.database.py` to manually inspect `voucher_rows` for direct edits. If triggers were bypassed (e.g., via `PRAGMA foreign_keys = OFF`), restore from backup. The only safe fix is a full restore. |
| Instruction version bloat | LOW | Add a migration that deletes versions older than N, or compresses them. Add a size limit and test. |
| Explanation/guidance conflation | LOW | Add a migration to rename/repurpose the column, update the frontend, and re-ingest any existing "explanation" values that were actually agent guidance. |
| Bank transaction mismatch | MEDIUM | Identify the duplicate vouchers, create compensating B-series corrections if needed, and re-mark the transaction status correctly. |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Race-condition on intake linking | DEDUP-01 (repository + transaction layer) | Test concurrent linking attempts with `pytest-asyncio` and `asyncio.gather` |
| BFL immutability violation | CORR-01 (backend service layer) | Assert that `correctVoucher` is called, `updateVoucher` is rejected for posted vouchers, and DB triggers are not bypassed |
| Unbounded instruction versions | INSTR-01 (repository + API layer) | Test version limit, content length validation, and deduplication logic |
| Explanation/guidance conflation | GUIDE-01 (migration + frontend) | Verify the upload form has two separate fields and the API accepts both |
| Bank transaction matchability exposure | MATCH-01 (service + API layer) | Test that `matchable` endpoint excludes `booked` and `matched` transactions |
| Entrypoint drift | All phases | Extend `test_agent_entrypoint.py` to assert new routes are present in the entrypoint |

## Sources

- Bok codebase: `api/routes/agent.py`, `api/routes/intake.py`, `api/routes/agent_instructions.py`, `services/ledger.py`, `services/intake.py`, `services/bank_inputs.py`, `repositories/intake_repo.py`, `repositories/bank_input_repo.py`, `repositories/agent_instruction_repo.py`, `db/migrations/018_add_intake_sources.sql`, `db/migrations/019_add_bank_inputs.sql`, `db/migrations/014_add_posted_voucher_immutability_triggers.sql`
- Bok test suite: `tests/test_intake_api.py`, `tests/test_bank_input_agent.py`, `tests/test_agent_entrypoint.py`, `tests/test_agent_accounting_workflow.py`
- Bok frontend: `frontend-v3/app/vouchers/intake/page.tsx`, `frontend-v3/app/vouchers/intake/[kind]/[id]/page.tsx`, `frontend-v3/app/vouchers/[id]/page.tsx`
- Swedish Bookkeeping Act (BFL) §5 kap 6 — immutability requirements for posted vouchers
- Known codebase concerns from `PROJECT.md`: file retrieval path constraints, broad exception conversion, SQLite + local filesystem storage

---
*Pitfalls research for: Agent usability improvements in Bok*
*Researched: 2026-06-05*
