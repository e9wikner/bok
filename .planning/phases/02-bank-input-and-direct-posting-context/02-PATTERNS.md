# Phase 2: Bank Input and Direct Posting Context - Pattern Map

**Generated:** 2026-05-15
**Status:** Ready for planning

## Pattern Summary

Phase 2 should reuse the Phase 1 intake architecture, but not the `intake_sources` table, because bank inputs have a distinct source type, lifecycle, CSV processing result, and bank transaction linkage. The closest analogs are:

| New File | Closest Existing Analog | Pattern to Reuse |
|----------|--------------------------|------------------|
| `db/migrations/019_add_bank_inputs.sql` | `db/migrations/018_add_intake_sources.sql`, `db/migrations/005_add_bank_and_categorization.sql` | Handwritten SQLite tables, `CHECK` constraints, indexes, schema version insert, FK links to vouchers and bank transactions. |
| `repositories/bank_input_repo.py` | `repositories/intake_repo.py` | Static repository methods, row-to-dataclass mappers, JSON only when needed, explicit commits with `_commit` override. |
| `services/bank_inputs.py` | `services/intake.py`, `services/bank_integration.py` | Service owns upload validation, filesystem writes, duplicate handling, root-contained resolution, lifecycle transitions, and transaction-scoped orchestration. |
| `api/routes/bank_inputs.py` | `api/routes/intake.py` | Thin FastAPI route layer over service methods, `UploadFile = File(...)`, `Form(...)` metadata, typed error mapping, `FileResponse` only after safe resolution. |
| `api/routes/agent.py` | Existing `api/routes/agent.py` | Keep direct posting through `LedgerService.create_voucher` and `post_voucher`; add preflight guardrails before posting and traceability after posting. |
| `tests/test_bank_input_agent.py` | `tests/test_intake_api.py` | Direct service/route-function tests with repository assertions due local ASGI transport timeout. |

## Existing Excerpts to Follow

### Root-Contained File Resolution

From `services/intake.py`:

```python
root = Path(settings.intake_dir).resolve()
candidate = Path(source.stored_path).resolve()
if candidate != root and not candidate.is_relative_to(root):
    raise IntakeFileAccessError(...)
```

Phase 2 should implement the same pattern for bank input CSV download. Do not serve a raw persisted path in route code.

### Upload and Typed Error Mapping

From `api/routes/intake.py`:

```python
content = file.file.read()
source = IntakeService().create_source_from_upload_content(...)
return _source_to_dict(source)
```

The bank input route should mirror this shape with `bank_connection_id: str = Form(...)`, CSV-only validation, and `_http_error` mapping for duplicate, not found, conflict, validation, and file access errors.

### Duplicate-Skipping Transaction Import

From `services/bank_integration.py`:

```python
existing = db.execute(
    "SELECT id FROM bank_transactions WHERE bank_connection_id = ? AND external_id = ?",
    (connection_id, external_id)
).fetchone()

if existing:
    skipped += 1
    continue
```

Phase 2 should keep this durable duplicate behavior and record imported/skipped counts on `bank_inputs`.

### Agent Posting Must Stay on LedgerService

From `api/routes/agent.py`:

```python
voucher = ledger.create_voucher(...)
voucher = ledger.post_voucher(voucher.id, actor=actor)
```

The bank-driven path must add validation before this block and linking/status updates after this block. It must not create a second voucher-posting implementation.

### Correction History Already Exists

From `api/routes/accounting_corrections.py`, the current response includes correction IDs, original/corrected voucher IDs, change metadata, reason, actor, original/corrected data, and voucher payloads. Phase 2 should make this endpoint discoverable or include it in the agent context response rather than creating a separate correction model.

## Data Flow

1. Human uploads CSV to `POST /api/v1/bank-inputs` with an existing `bank_connection_id`.
2. `BankInputService` validates CSV-only input, writes original bytes under a bank-input storage root, creates `bank_inputs(status='pending')`, detects CSV format, imports transactions through `BankIntegrationService`, links imported rows in `bank_input_transactions`, and marks the input `processed` or `failed`.
3. Agent reads `GET /api/v1/agent/intake/pending` and receives typed `voucher_source` plus `bank_input` items.
4. Agent posts `POST /api/v1/agent/vouchers` with voucher rows, `bank_input_ids`, `bank_transaction_ids`, and optional ordinary `intake_source_ids`.
5. Backend checks transaction availability and linkage before posting, then posts through `LedgerService`, creates voucher-bank traceability links, marks used transactions `booked`, and links ordinary voucher sources if supplied.

## Implementation Risks

- `BankIntegrationService.import_transactions` currently returns only counts, not inserted transaction IDs. Plan 02-02 should add a method that returns imported/skipped IDs or otherwise derive imported IDs deterministically from external IDs after import.
- `bank_transactions.external_id` is nullable but unique with `bank_connection_id`; generated CSV external IDs must be stable enough to skip repeated uploads.
- Existing `IntakeService.link_existing_voucher` validates one ordinary source due `UNIQUE(intake_source_id)`. Phase 2 can call it per source after a successful voucher, but must avoid marking source material processed before ledger posting succeeds.
- `api/routes/import_csv.py` appears stale and calls a non-existent service method. Phase 2 should not build on that route.

