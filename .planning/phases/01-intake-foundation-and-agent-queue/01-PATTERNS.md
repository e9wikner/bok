# Phase 1: Intake Foundation and Agent Queue - Pattern Map

**Generated:** 2026-05-14
**Phase:** 01 - Intake Foundation and Agent Queue

## File Mapping

| New or Modified File | Role | Closest Existing Analog | Pattern to Reuse |
|---|---|---|---|
| `db/migrations/018_add_intake_sources.sql` | SQLite schema | `db/migrations/005_add_bank_and_categorization.sql`, `db/migrations/014_add_posted_voucher_immutability_triggers.sql` | Handwritten `CREATE TABLE IF NOT EXISTS`, indexes, `CHECK` constraints, final `INSERT INTO schema_version`. |
| `domain/types.py` | Enums | Existing `VoucherStatus`, `AuditAction` | String enum classes with lower-case values. |
| `domain/models.py` | Dataclasses | Existing `VoucherAttachment`, `CorrectionHistory` | Dataclasses with optional fields and `datetime.now` defaults. |
| `repositories/intake_repo.py` | SQL access | `repositories/voucher_repo.py`, `repositories/accounting_correction_repo.py` | Static repository methods, explicit SQL, row-to-dataclass mapping helpers, JSON text for warnings. |
| `services/intake.py` | Business workflow | `services/ledger.py`, `services/invoice_draft.py` | Service orchestrates repository calls and `db.transaction()` for multi-step state changes. |
| `api/routes/intake.py` | Human upload/download API | `api/routes/attachments.py`, `api/routes/vouchers.py` | FastAPI router with auth dependency, upload validation, typed HTTP errors. Avoid the attachment download path-safety gap. |
| `api/routes/agent.py` | Agent queue and posting API | Existing `create_and_post_agent_voucher` | Extend existing request/response while preserving `LedgerService` posting path. |
| `api/main.py` | Router registration | Existing router includes | Import new route module and call `app.include_router(intake.router)`. |
| `config.py` | Storage root config | Existing settings class and `ATTACHMENTS_DIR` env pattern | Add `intake_dir: str = os.getenv("INTAKE_DIR", "/app/data/intake")`. |
| `tests/test_intake_api.py` | Integration coverage | `tests/test_api.py`, `tests/test_agent_accounting_workflow.py` | `TestClient(app)`, `auth_headers`, temp DB fixture, direct DB mutation for path safety test. |

## Concrete Patterns

### Upload validation

`api/routes/attachments.py` already establishes:

- Allowed MIME types: JPEG, PNG, GIF, WebP, PDF.
- Max upload size: 10 MB.
- SHA-256 hashing with `hashlib.sha256(content).hexdigest()`.
- Duplicate conflict response using HTTP 409.

Intake should move this logic into `services/intake.py` so both human and agent-adjacent routes stay thin.

### Repository mapping

`repositories/accounting_correction_repo.py` shows the expected JSON mapping style:

- Store complex lists/dicts as JSON text.
- Parse JSON in `_row_to_*` helper and tolerate decode failure.
- Return domain dataclasses rather than raw rows.

`repositories/intake_repo.py` should follow that shape for `warnings`.

### Transaction boundaries

`services/ledger.py` uses `with db.transaction():` for voucher creation with rows. Intake should do the same for:

- successful processing attempt + voucher link + intake status update
- failed processing attempt + intake status update
- soft-delete status/deleted metadata update

Because `LedgerService.post_voucher` currently commits internally, the plan should call out that a future executor may need to keep the intake link immediately after posting and log a repairable failed attempt if link creation fails after the voucher commit.

### Root containment

The safe helper should be service-level and testable:

- `root = Path(settings.intake_dir).resolve()`
- `candidate = Path(stored_path).resolve()`
- reject if candidate is not equal to root and not under root
- only then return `FileResponse`

Use `Path.is_relative_to` on Python 3.11.

## Plan Boundaries

### Plan 01-01

Owns schema, models, repository, service, settings, and service-level tests for upload and secure storage. It should not modify agent voucher posting.

### Plan 01-02

Owns human and agent intake APIs, router registration, pending queue, file download, soft-delete, and failed/processing outcomes. It should not modify `POST /api/v1/agent/vouchers` beyond shared imports if avoidable.

### Plan 01-03

Owns intake linkage in agent voucher posting and end-to-end traceability tests. It should avoid reworking the base upload API except where needed for integration.
