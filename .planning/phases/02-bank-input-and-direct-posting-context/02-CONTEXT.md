# Phase 2: Bank Input and Direct Posting Context - Context

**Gathered:** 2026-05-15
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers backend support for bank CSV input as a separate source type while exposing it through the existing agent intake workflow. Users upload bank CSV exports against an existing bank connection, the system preserves the original upload, immediately imports parseable transactions, and the agent can use bank inputs plus correction history to post missing vouchers directly. The backend must preserve traceability to uploaded bank input and imported transaction rows, and it must prevent explicit reuse of already-booked bank transactions.

This phase does not deliver a frontend intake workspace, PDF/image bank statement support, OCR/text extraction, Open Banking synchronization, or broad fuzzy duplicate matching across every accounting entity.

</domain>

<decisions>
## Implementation Decisions

### Bank Input Shape and Lifecycle
- **D-01:** One bank input record represents one uploaded file.
- **D-02:** Phase 2 bank inputs accept CSV only. Treat "bank statement/status" in this phase as uploaded bank CSV exports, not PDFs, screenshots, or images.
- **D-03:** Bank inputs use a minimal lifecycle: `pending`, `processed`, and `failed`.
- **D-04:** Duplicate transaction rows inside an uploaded CSV are skipped while the rest of the upload is processed. Preserve imported and skipped counts on the bank input or related processing record.

### CSV Import Behavior
- **D-05:** The user must select from relevant existing bank accounts/connections for a bank CSV upload. Do not silently create or reuse a default manual connection.
- **D-06:** CSV parsing should auto-detect the format from a known list of supported bank formats.
- **D-07:** If CSV format auto-detection fails, mark the bank input `failed` with a clear parsing error.
- **D-08:** A successful bank CSV upload immediately imports transactions and records imported/skipped counts.

### Agent Context Package
- **D-09:** Bank inputs should appear in the existing agent pending intake queue alongside voucher sources, while remaining a separate model underneath.
- **D-10:** Shared queue items must be typed with a `kind`, such as `voucher_source` or `bank_input`, and include type-specific fields.
- **D-11:** Bank input queue entries include compact summary data plus linked transaction IDs. Do not inline every transaction row in the queue response.
- **D-12:** Phase 2 should expose full correction history to the agent for learning context.

### Duplicate and Matching Safeguards
- **D-13:** The backend surfaces duplicate/match candidates, but the agent decides whether to post for inferred matches.
- **D-14:** Phase 2 match surfacing is limited to bank transaction link/status signals, especially whether a transaction is already booked or has `matched_voucher_id`.
- **D-15:** The backend must reject explicit reuse of a bank transaction already marked `booked` or already matched to a voucher.
- **D-16:** When a bank-driven voucher is posted successfully, every used bank transaction is marked `booked` and receives `matched_voucher_id`.

### Traceability for Bank-Created Vouchers
- **D-17:** Every bank-driven voucher must link to both the uploaded bank input and the specific imported bank transaction rows used.
- **D-18:** One bank-driven voucher may use multiple bank transaction rows.
- **D-19:** One bank input CSV may lead to multiple vouchers over time.
- **D-20:** Bank-driven posting can also link ordinary voucher intake sources, such as receipts or invoices, when available.

### the agent's Discretion

No areas were delegated to the agent's discretion. The user selected concrete behavior for each discussed area.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Planning Scope
- `.planning/ROADMAP.md` - Phase 2 goal, requirements, success criteria, and planned plan breakdown.
- `.planning/REQUIREMENTS.md` - BANK and AGNT requirement IDs for Phase 2.
- `.planning/PROJECT.md` - Product constraints: automation-first workflow, input separation, traceability, compliance, and local storage.
- `.planning/phases/01-intake-foundation-and-agent-queue/01-CONTEXT.md` - Prior locked decisions for voucher source intake, agent queue behavior, file access, and traceability.

### Codebase Context
- `.planning/codebase/ARCHITECTURE.md` - Service/repository layering, FastAPI route integration, SQLite migration pattern.
- `.planning/codebase/STACK.md` - Backend/runtime/testing stack.
- `.planning/codebase/INTEGRATIONS.md` - Existing internal API/auth model, SQLite storage, and local filesystem assumptions.

### Existing Implementation Anchors
- `services/intake.py` - Existing voucher source intake service, lifecycle transitions, secure file resolution, and voucher-linking behavior.
- `repositories/intake_repo.py` - Existing intake source, processing attempt, and voucher-source link persistence patterns.
- `api/routes/intake.py` - Existing human intake upload/download API shape and typed intake error mapping.
- `api/routes/agent.py` - Existing agent voucher posting endpoint and pending intake queue endpoint to extend.
- `services/bank_integration.py` - Existing bank connection, transaction import, CSV parsing, duplicate handling, and transaction status update behavior.
- `api/routes/import_csv.py` - Existing CSV import route; note that it appears stale and calls a non-existent `import_transaction` method, so planners should prefer `services/bank_integration.py` as the real integration anchor.
- `db/migrations/005_add_bank_and_categorization.sql` - Existing `bank_connections` and `bank_transactions` schema.
- `db/migrations/018_add_intake_sources.sql` - Existing voucher source intake and voucher-link schema.
- `domain/types.py` - Existing `IntakeStatus` and `IntakeSourceType` enums.
- `domain/models.py` - Existing intake domain dataclasses and voucher-source link model.
- `config.py` - Existing `intake_dir` storage setting; bank input storage should fit local filesystem settings.
- `api/main.py` - Router registration point.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `BankIntegrationService.import_csv` and `BankIntegrationService.import_transactions`: reuse the current transaction import and duplicate-skip behavior, but add supported-format detection instead of relying on caller-provided column names as the primary path.
- `bank_connections` and `bank_transactions`: existing tables already model manual bank connections, imported transactions, status, and `matched_voucher_id`.
- `IntakeService` and `IntakeRepository`: useful pattern for storing uploaded source files, metadata, lifecycle, processing attempts, and authenticated download resolution.
- `api/routes/agent.py`: extend the existing pending queue and agent voucher posting surface instead of creating a separate agent workflow.

### Established Patterns
- Backend features are implemented as FastAPI route modules backed by services, repositories, and handwritten SQLite migrations.
- Existing intake files are stored on local filesystem with root containment checks; bank input files should follow the same storage-safety principle.
- Existing bank transaction duplicate detection uses `(bank_connection_id, external_id)` and skips duplicates during import.
- Agent-created vouchers must continue through `LedgerService.create_voucher` and `LedgerService.post_voucher` so period/account/balance validation remains centralized.

### Integration Points
- Add bank input schema/migration and persistence for original CSV metadata, lifecycle, import result counts, parse errors, and storage path.
- Add upload API for bank CSV inputs that requires a selected existing bank connection.
- Extend CSV import to auto-detect known bank formats and mark bank input `failed` when detection/parsing fails.
- Extend the agent pending intake queue with typed `kind` items for `voucher_source` and `bank_input`.
- Extend agent posting request/logic to accept bank input IDs, bank transaction IDs, and optional ordinary intake source IDs.
- Add hard validation that used bank transaction IDs are not already `booked` or matched to a voucher.
- Add persistence for bank-input-to-voucher and bank-transaction-to-voucher traceability, then update used transactions to `booked` with `matched_voucher_id`.
- Add focused tests for CSV-only upload, connection selection, known-format detection failure, duplicate row skipping, typed queue output, booked transaction reuse rejection, multi-transaction voucher posting, and traceability links.

</code_context>

<specifics>
## Specific Ideas

- "Relevant accounts" means the upload flow should present/select from existing bank connections/accounts; no hidden default connection should be used.
- Unknown CSV formats should fail clearly instead of becoming pending manual work in Phase 2.
- The shared agent queue is acceptable only if bank inputs remain typed and separately modeled underneath.
- Full correction history should be available to the agent even if later phases may summarize or filter it for scale.

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within phase scope.

</deferred>

---

*Phase: 2-Bank Input and Direct Posting Context*
*Context gathered: 2026-05-15*
