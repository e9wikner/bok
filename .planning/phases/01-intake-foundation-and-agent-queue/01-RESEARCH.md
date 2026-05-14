# Phase 1: Intake Foundation and Agent Queue - Research

**Researched:** 2026-05-14
**Status:** Complete
**Phase:** 01 - Intake Foundation and Agent Queue

## Research Question

What does the executor need to know to plan Phase 1 well: users can upload voucher source material before a voucher exists, and the agent can consume a pending queue with durable source-to-voucher traceability.

## Executive Summary

Phase 1 should add a backend intake subsystem that follows the repo's existing FastAPI -> service -> repository -> handwritten SQLite migration pattern. The critical implementation choice is to keep intake records separate from voucher attachments while preserving an atomic bridge to posted vouchers. Existing voucher attachments are useful for upload validation and hashing, but their download path currently trusts persisted paths; the intake file endpoint must instead resolve the configured intake root and persisted path before serving any file.

The agent voucher endpoint already posts through `LedgerService.create_voucher` and `LedgerService.post_voucher`. Phase 1 should extend that flow with optional intake source IDs, then atomically create voucher links, record a processing attempt, and mark intake items processed only after the voucher is posted.

## Existing Implementation Findings

### Upload and file storage

- `api/routes/attachments.py` validates MIME type, max size, SHA-256 hash, and duplicate attachment uploads.
- That route writes directly to `ATTACHMENTS_DIR` and persists `stored_path` in `attachments`.
- Its download/delete paths do not enforce that `stored_path.resolve()` stays inside the attachment root. Intake must not repeat this pattern.
- The current max upload size is 10 MB and allowed types are JPEG, PNG, GIF, WebP, and PDF. Phase 1 can reuse the same initial MIME set unless implementation context requires a narrower image set.

### Agent posting

- `api/routes/agent.py` defines `POST /api/v1/agent/vouchers`.
- The endpoint calls `LedgerService.create_voucher(... created_by="agent")`, then `LedgerService.post_voucher(voucher.id, actor=actor)`.
- This is the correct validation path for `AGNT-03`; intake linkage should wrap or extend this endpoint, not create a bypass.
- The existing `reasoning_summary` field is response-only metadata today. Phase 1 should persist processing summaries in a dedicated intake attempt table.

### Domain and persistence patterns

- Domain models live in `domain/models.py`; enums live in `domain/types.py`.
- Repositories use static methods and explicit SQL against the global thread-local `db`.
- Service-level multi-step persistence should use `with db.transaction():` to avoid partial writes.
- `AuditRepository.log(...)` commits immediately; if used inside a larger atomic flow, it can break transaction boundaries. Intake processing attempts should be first-class records rather than relying only on audit log entries.
- Migrations are ordered files in `db/migrations/*.sql`, with numeric prefixes. The next migration should be `018_add_intake_sources.sql`.

### Tests

- API tests use `fastapi.testclient.TestClient` and the `test_db` fixture in `tests/conftest.py`.
- `tests/test_agent_accounting_workflow.py` already covers direct agent posting and correction visibility.
- Phase 1 tests should add intake-specific coverage for upload, duplicate conflict, pending queue, file path containment, successful agent posting linkage, failed outcome recording, and duplicate outcome guard.

## Recommended Data Model

### `intake_sources`

Purpose: one row per uploaded voucher source file before a voucher exists.

Recommended columns:

- `id TEXT PRIMARY KEY`
- `source_type TEXT` with `CHECK(source_type IN ('receipt', 'supplier_invoice', 'customer_invoice', 'reimbursement', 'other'))`
- `status TEXT NOT NULL DEFAULT 'pending'` with lifecycle values `pending`, `processing`, `processed`, `skipped`, `failed`, `needs_attention`, `deleted`
- `original_filename TEXT NOT NULL`
- `mime_type TEXT NOT NULL`
- `size_bytes INTEGER NOT NULL`
- `sha256 TEXT NOT NULL UNIQUE`
- `stored_path TEXT NOT NULL`
- `explanation TEXT`
- `uploaded_by TEXT NOT NULL`
- `uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP`
- `deleted_at TIMESTAMP`
- `deleted_by TEXT`

Notes:

- The requirements list `skipped` and `needs_attention`, while Phase 1 context says the agent outcome API can only set `processed` or `failed`. The table can support the full lifecycle, but the Phase 1 API should restrict agent-set outcomes.
- Duplicate detection should use a global unique hash for source intake to prevent duplicate pending work.
- Soft-delete should set `status='deleted'` or `deleted_at` and exclude the item from the pending queue. If using both, status keeps queue filtering cheap.

### `intake_processing_attempts`

Purpose: durable trace of agent/user processing outcomes.

Recommended columns:

- `id TEXT PRIMARY KEY`
- `intake_source_id TEXT NOT NULL REFERENCES intake_sources(id)`
- `status TEXT NOT NULL CHECK(status IN ('processing', 'processed', 'failed'))`
- `summary TEXT NOT NULL`
- `warnings TEXT` as JSON text
- `error_detail TEXT`
- `voucher_id TEXT REFERENCES vouchers(id)`
- `actor TEXT NOT NULL`
- `created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP`

Notes:

- Failed attempts require `summary` and `error_detail`.
- Successful processed attempts require `voucher_id`.
- Recording attempts separately lets the review UI later show multiple failures before a successful voucher.

### `voucher_intake_sources`

Purpose: traceability link between posted vouchers and intake sources.

Recommended columns:

- `id TEXT PRIMARY KEY`
- `voucher_id TEXT NOT NULL REFERENCES vouchers(id)`
- `intake_source_id TEXT NOT NULL REFERENCES intake_sources(id)`
- `linked_by TEXT NOT NULL`
- `linked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP`
- `link_reason TEXT`
- `UNIQUE(voucher_id, intake_source_id)`
- `UNIQUE(intake_source_id)` for Phase 1's one-intake-item-per-voucher rule

Notes:

- `UNIQUE(intake_source_id)` enforces that one intake item cannot be linked to multiple vouchers in Phase 1.
- Future multi-file support can relax this by replacing the unique constraint with a batch concept.

## Recommended Backend Shape

### New domain/types

- Add `IntakeStatus` and `IntakeSourceType` enums in `domain/types.py`.
- Add `IntakeSource`, `IntakeProcessingAttempt`, and `VoucherIntakeSource` dataclasses in `domain/models.py`.

### New repository

Add `repositories/intake_repo.py` with focused methods:

- `create_source(...)`
- `get_source(source_id)`
- `get_by_sha256(sha256)`
- `list_pending(limit, offset)`
- `soft_delete(source_id, actor)`
- `mark_processing(source_id, actor, summary)`
- `record_attempt(...)`
- `link_voucher(source_id, voucher_id, actor, link_reason=None)`
- `mark_processed_with_link(...)` for atomic success paths

### New service

Add `services/intake.py` to keep route handlers thin:

- Upload validation and content hashing.
- Stable file path creation under `settings.intake_dir`.
- Root containment helper:
  - Resolve configured root.
  - Resolve stored path.
  - Reject unless `stored_path.resolve().is_relative_to(root.resolve())`.
- Duplicate hash rejection with 409 semantics.
- Pending queue read model with authenticated download URL `/api/v1/intake/{id}/file`.
- Outcome guard: processed/failed transitions must require current pending or processing state and reject already linked/processed sources.
- Agent voucher posting helper that calls `LedgerService` and then links intake source(s) in a single transaction-aware flow.

## API Surface Recommendation

Human-facing intake routes:

- `POST /api/v1/intake` multipart upload with fields `file`, optional `explanation`, optional `source_type`.
- `GET /api/v1/intake/{id}` metadata response.
- `GET /api/v1/intake/{id}/file` authenticated original file download with root containment.
- `DELETE /api/v1/intake/{id}` soft-delete pending source.

Agent-facing routes:

- `GET /api/v1/agent/intake/pending?limit=&offset=` returns metadata and `download_url`.
- `POST /api/v1/agent/intake/{id}/processing` records processing attempt/status.
- `POST /api/v1/agent/intake/{id}/failed` records failed processing with summary and error detail.
- Extend `POST /api/v1/agent/vouchers` with optional `intake_source_ids: list[str]` and persist links after successful posting.

Route placement options:

- Put human routes in new `api/routes/intake.py` with prefix `/api/v1/intake`.
- Keep agent routes in `api/routes/agent.py` to preserve the agent API surface.
- Register the new router in `api/main.py`.

## Security Threat Model

### Assets

- Original source PDFs/images uploaded by users.
- Voucher traceability records connecting source material to posted accounting entries.
- Processing summaries and error details that may contain financial or personal information.

### Threats and mitigations

- High: Arbitrary file read through tampered `stored_path`.
  - Mitigation: enforce `stored_path.resolve().is_relative_to(settings.intake_dir.resolve())` before `FileResponse`; test by mutating DB to `/etc/passwd` or an outside temp file and expecting 404 or 403.
- High: Duplicate upload creates duplicate pending agent work and duplicate vouchers.
  - Mitigation: unique `sha256` on `intake_sources`; service pre-check returns 409; handle DB uniqueness race as 409.
- High: Duplicate processing links one intake source to multiple vouchers.
  - Mitigation: transaction guard checks source is pending/processing and unlinked; `UNIQUE(intake_source_id)` in `voucher_intake_sources`.
- Medium: Unauthorized source download.
  - Mitigation: use `get_current_actor` on every intake route, including file download.
- Medium: Partial success posts a voucher but fails to link source.
  - Mitigation: service-level atomic orchestration around voucher creation/post/link where feasible; if `LedgerService.post_voucher` commits internally, immediately record a failed processing attempt when linking fails and surface a 500 with repair path.
- Medium: Error details leak filesystem paths.
  - Mitigation: route responses use stable error codes/messages and do not echo full stored paths.

## Validation Architecture

Tests to add:

- Upload accepts PDF/image before voucher exists and returns metadata including status `pending`.
- Upload stores original filename, MIME type, size, SHA-256, actor, timestamp, explanation, and source type.
- Duplicate upload by identical bytes returns HTTP 409 and only one pending source exists.
- Pending agent queue excludes soft-deleted and processed sources and includes `/api/v1/intake/{id}/file`.
- File download succeeds for a valid stored path under the intake root.
- File download rejects a DB-mutated path outside the intake root.
- Agent failed outcome requires `summary` and `error_detail` and persists an attempt row.
- Agent voucher posting with `intake_source_ids` creates and posts a voucher through `LedgerService`, creates `voucher_intake_sources`, records a processed attempt, and marks source `processed`.
- A second successful outcome/link attempt for the same intake source returns 409.

Verification commands:

- `pytest tests/test_intake_api.py tests/test_agent_accounting_workflow.py`
- `pytest tests/test_api.py tests/test_ledger.py`

## Planning Implications

- Plan 01-01 should create the durable intake model, repository/service, secure storage helper, and service-level tests without exposing the full API yet.
- Plan 01-02 should expose upload/download/pending/outcome APIs and register the router.
- Plan 01-03 should extend agent voucher posting with intake source linkage and integration tests for traceability and duplicate guards.

## RESEARCH COMPLETE
