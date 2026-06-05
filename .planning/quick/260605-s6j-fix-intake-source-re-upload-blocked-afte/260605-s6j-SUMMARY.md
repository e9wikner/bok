---
status: complete
---

# Quick Task Summary: 260605-s6j

## Description
Fix intake source re-upload blocked after soft-delete: deleted intake items still block re-upload due to sha256 unique constraint and repository query not excluding deleted sources.

## Changes Made

### 1. Repository fix
- **File:** `repositories/intake_repo.py`
- Changed `get_by_sha256()` to exclude sources with `status = 'deleted'` from duplicate detection.

### 2. Database migration
- **File:** `db/migrations/021_allow_reupload_deleted_intake_sources.sql`
- Replaced the full `UNIQUE(sha256)` table constraint on `intake_sources` with a partial unique index `UNIQUE(sha256) WHERE status != 'deleted'`.
- Migration recreates the table safely while preserving all data and foreign key relationships.

### 3. Regression test
- **File:** `tests/test_intake_api.py`
- Added `test_intake_service_allows_reupload_after_soft_delete` verifying that a file can be re-uploaded after soft-delete, while duplicate active sources are still rejected.

## Verification
- All 22 intake API tests pass.
- All 96 intake + bank + API tests pass.
- Existing duplicate-rejection behavior for active (non-deleted) sources remains intact.

## Commit
```
(repositories/intake_repo.py, db/migrations/021_allow_reupload_deleted_intake_sources.sql, tests/test_intake_api.py)
```
