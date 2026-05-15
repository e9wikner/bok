# Phase 2: Bank Input and Direct Posting Context - Research

**Researched:** 2026-05-15
**Status:** Ready for planning

## RESEARCH COMPLETE

## Executive Summary

Phase 2 should extend the existing Phase 1 intake pattern with a separate bank-input aggregate instead of folding bank CSV files into `intake_sources`. The safest implementation path is:

1. Add migration-managed `bank_inputs`, `bank_input_transactions`, `voucher_bank_inputs`, and `voucher_bank_transactions` tables.
2. Add `BankInputService` / `BankInputRepository` for CSV upload storage, status transitions, root-contained file download, import-result counts, and traceability links.
3. Extend `BankIntegrationService.import_csv` with deterministic known-format detection while continuing to use `import_transactions` for duplicate skipping.
4. Extend `GET /api/v1/agent/intake/pending` into a typed queue containing both `voucher_source` and `bank_input` items.
5. Extend `POST /api/v1/agent/vouchers` with `bank_input_ids`, `bank_transaction_ids`, and optional `intake_source_ids`, then reject reuse of already `booked` or matched bank transactions before voucher creation.

This keeps Bok automation-first while leaving non-negotiable accounting invariants in the backend.

## Regulatory and Domain Findings

- Skatteverket describes bookkeeping duty as including continuous recording, a voucher for every bookkeeping item, orderly archiving of accounting information, and annual closing/annual report obligations. It also notes that data on electronic media can be accounting information and that every economic event should normally be based on written source material. Source: https://www.skatteverket.se/foretag/drivaforetag/bokforingochbokslut/bokforingvadkraverlagen.4.18e1b10334ebe8bc80005195.html
- BFN's bookkeeping guidance frames a voucher as documentation that identifies and proves a business event or correction, and states that vouchers are accounting information that can exist on machine-readable media. Source: https://www.bfn.se/wp-content/uploads/2020/06/vagledning-bokforing.pdf
- BFN's archiving FAQ states accounting information must be preserved for seven years after the calendar year in which the fiscal year ended and that electronic receipts/invoices should be preserved in their electronic form when received electronically. Source: https://www.bfn.se/fragor-och-svar/arkivering/

Planning implication: uploaded bank CSV exports should be retained as original source material, but a bank row alone is not always sufficient source evidence for VAT or expense classification. The backend should expose bank rows plus receipt/invoice/payroll/invoice context and correction history, then enforce transaction reuse and traceability after agent posting.

## Codebase Findings

### Existing Bank Integration

- `services/bank_integration.py` already models `BankConnection`, `BankTransaction`, `create_connection`, `get_connections`, `get_connection`, `import_transactions`, `get_transactions`, `get_transaction`, `update_transaction_status`, and `import_csv`.
- `import_transactions(connection_id, transactions)` validates the bank connection exists and is `active`, skips duplicates by `(bank_connection_id, external_id)`, converts SEK amounts to ore, and inserts `bank_transactions` with `status='pending'`.
- `import_csv` currently assumes caller-provided columns defaulting to `Datum`, `Belopp`, and `Text`; Phase 2 needs known-format detection and a clear failure path when detection fails.
- `update_transaction_status(tx_id, status, voucher_id=...)` already sets `matched_voucher_id` and `booked_at` when a voucher ID is supplied, but it does not guard transaction reuse. Phase 2 should add an explicit availability method before voucher creation and use a transaction-scoped status update after successful posting.

### Existing Intake and File Safety

- Phase 1 created a strong pattern in `services/intake.py`: validate upload bytes, hash content, store under `settings.intake_dir`, persist metadata through a repository, and resolve paths with `Path.resolve()` plus `Path.is_relative_to(root)` before serving files.
- `api/routes/intake.py` maps typed service errors to stable structured HTTP errors and serves files only after service-level containment checks.
- `api/routes/agent.py` currently returns a voucher-source-only pending queue and supports one `intake_source_id` on `POST /api/v1/agent/vouchers`. Phase 2 must remove the one-source restriction for ordinary voucher sources when combined with bank-driven posting, or at least allow multiple ordinary source IDs for the bank-driven path.

### Existing Correction History

- `api/routes/accounting_corrections.py` already exposes correction history at `GET /api/v1/accounting-corrections`.
- `repositories/accounting_correction_repo.py` returns original/corrected voucher IDs, original/corrected data, change type, success flag, corrected by, correction reason, and timestamp.
- Phase 2 can either include correction history summary directly in the agent context package or expose a linked endpoint reference from the queue. D-12 says full correction history should be available, so the plan should include a bounded route or response field that surfaces the existing correction endpoint clearly to the agent.

## Recommended Design

### Tables

Add `db/migrations/019_add_bank_inputs.sql`:

- `bank_inputs`: one row per uploaded CSV file with `id`, `bank_connection_id`, `status`, original filename, MIME type, size, SHA-256, stored path, uploaded actor/timestamp, imported/skipped counts, parse error, detected format, processed timestamp.
- `bank_input_transactions`: links each imported `bank_transaction_id` back to the bank input row; add unique `(bank_input_id, bank_transaction_id)`.
- `voucher_bank_inputs`: links posted vouchers to uploaded bank inputs; one input can produce many vouchers, so do not add `UNIQUE(bank_input_id)`.
- `voucher_bank_transactions`: links posted vouchers to exact bank transaction rows; add `UNIQUE(bank_transaction_id)` if Bok treats one transaction row as consumable once, which matches D-15/D-16.

Do not overload `intake_sources`. Phase 2 needs separate lifecycle, CSV-only validation, bank connection selection, import results, and transaction-row linkage.

### Service and Repository

Add `repositories/bank_input_repo.py` and `services/bank_inputs.py`:

- Store bank input CSV files under `settings.intake_dir / "bank-inputs"` or a new `settings.bank_input_dir`. Reusing `INTAKE_DIR` with a `bank-inputs/` subdirectory keeps config small and still separates paths from voucher-source records.
- Accept only CSV MIME/extension combinations in Phase 2: `text/csv`, `application/csv`, `application/vnd.ms-excel`, `text/plain` with `.csv`, or blank browser MIME with `.csv`.
- Require an existing active bank connection. Do not create hidden manual connections.
- Save the original file before parsing so failed uploads are still traceable.
- Mark unknown format as `failed` with `parse_error='unsupported_bank_csv_format'` and no imported transactions.
- For successful parsing, call `BankIntegrationService.import_transactions`, record imported/skipped counts, link imported rows back to `bank_input_transactions`, and mark input `processed`.

### CSV Detection

Add a deterministic detector near `BankIntegrationService.import_csv`:

- Known headers should include current defaults: `Datum`, `Belopp`, `Text`.
- Also support common Swedish variants by mapping date/amount/description/reference/counterpart columns from header sets, not by free-form guessing.
- Return a stable format key such as `swedish_standard_semicolon`, `swedbank_semicolon`, or `seb_semicolon`.
- If no mapping matches, raise a typed validation/service error that `BankInputService` stores on the bank input row.

### Agent Context

Extend `GET /api/v1/agent/intake/pending`:

- Each item must include `kind`.
- `voucher_source` items keep the Phase 1 fields and download URL.
- `bank_input` items include `id`, `kind`, `status`, file metadata, `bank_connection` summary, `imported_count`, `skipped_count`, `parse_error`, `transaction_ids`, `transaction_count`, and `download_url`.
- Do not inline every transaction row in the queue response. Add a focused route or service read helper for bank input details if execution needs full rows.
- Include `correction_history_url` or `correction_history` in the agent context surface so AGNT-06 is not left implicit.

### Agent Posting Guardrails

Extend `AgentVoucherRequest`:

- `bank_input_ids: list[str] = Field(default_factory=list)`
- `bank_transaction_ids: list[str] = Field(default_factory=list)`
- `intake_source_ids` remains supported and should allow multiple ordinary sources in the bank-driven path.

Before creating a voucher:

- Ensure every supplied bank input exists and is `processed`.
- Ensure every supplied bank transaction exists, belongs to one of the supplied bank inputs, has `status != 'booked'`, and has `matched_voucher_id IS NULL`.
- Surface duplicate/match candidates in context, but reject explicit reuse server-side with HTTP 409 and code `bank_transaction_already_booked` or `bank_transaction_already_matched`.

After `LedgerService.post_voucher` succeeds:

- Create `voucher_bank_inputs` and `voucher_bank_transactions` rows.
- Update every used bank transaction to `status='booked'` and `matched_voucher_id=<voucher_id>`.
- Preserve ordinary source links through `IntakeService.link_existing_voucher` where provided.
- Return `agent.bank_input_ids`, `agent.bank_transaction_ids`, and traceability link IDs in the response.

## Threat Model

- HIGH: Bank transaction reuse creates duplicate vouchers. Mitigation: preflight status/match checks plus unique voucher-bank-transaction linkage and post-success booked status update.
- HIGH: A posted voucher lacks bank CSV/transaction traceability. Mitigation: link rows inside the same service transaction after posting; tests assert links for every supplied ID.
- HIGH: Tampered stored path leaks local files. Mitigation: mirror `IntakeService.resolve_source_file` root containment for bank input downloads.
- MEDIUM: Unknown CSV format silently imports zero rows. Mitigation: mark bank input `failed`, persist parse error, and return that status to the queue.
- MEDIUM: Queue conflates bank inputs with voucher sources. Mitigation: require `kind` and type-specific fields.

## Test Strategy

Use `tests/test_bank_input_agent.py` for new coverage and keep Phase 1 `tests/test_intake_api.py` passing:

- Service tests for CSV-only validation, active connection requirement, file metadata preservation, unsupported format failure, and path containment.
- Import tests for known header detection, duplicate row skip counts, and `bank_input_transactions` linkage.
- Agent queue tests for mixed `voucher_source` and `bank_input` typed items.
- Agent posting tests for successful one-transaction and multi-transaction bank vouchers, ordinary intake-source co-linking, reuse rejection before voucher creation, and traceability rows.
- Correction-history availability test using existing accounting corrections route/repository.

Known local test constraint: Phase 1 summaries record a Python 3.14 `TestClient`/AnyIO hang. Prefer direct route-function tests and service/repository assertions when ASGI transport hangs locally.

## Planning Implications

- Plan 02-01 should create the bank-input storage model, upload/download API, and file safety tests.
- Plan 02-02 should focus on CSV detection/import integration and transaction linkage.
- Plan 02-03 should extend the typed agent queue and direct posting guardrails with traceability and correction history.

