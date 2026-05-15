---
phase: 03-frontend-intake-workspace-and-review-loop
reviewed: 2026-05-15T19:38:57Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - api/routes/bank_inputs.py
  - api/routes/intake.py
  - api/routes/vouchers.py
  - frontend-v3/app/vouchers/[id]/page.tsx
  - frontend-v3/app/vouchers/intake/[kind]/[id]/page.tsx
  - frontend-v3/app/vouchers/intake/page.tsx
  - frontend-v3/components/AppShellClient.tsx
  - frontend-v3/components/Sidebar.tsx
  - frontend-v3/hooks/useData.ts
  - frontend-v3/lib/api.ts
  - repositories/bank_input_repo.py
  - repositories/intake_repo.py
  - tests/test_bank_input_agent.py
  - tests/test_intake_api.py
findings:
  critical: 5
  warning: 2
  info: 0
  total: 7
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-05-15T19:38:57Z
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues_found

## Summary

Reviewed the scoped backend routes/repositories, frontend intake/voucher pages, data hooks, API client, and intake/bank tests. The implementation has several ship-blocking correctness and security problems around source-context authorization, upload resource limits, workspace pagination, file access from the frontend, and voucher row data preservation.

## Critical Issues

### CR-01: [BLOCKER] Voucher Source Context Endpoint Bypasses Authentication

**File:** `api/routes/vouchers.py:84`
**Issue:** `GET /api/v1/vouchers/{voucher_id}/source-context` has no `Depends(get_current_actor)` dependency while the new intake and bank-input routes do. Because routers are included without global auth dependencies, this endpoint can be called without an Authorization header and exposes source filenames, explanations, processing errors, actor names, linked bank input metadata, transaction IDs, and correction history for any known voucher ID.
**Fix:**
```python
@router.get("/{voucher_id}/source-context", response_model=dict)
async def get_voucher_source_context(
    voucher_id: str,
    ledger: LedgerService = Depends(get_ledger_service),
    actor: str = Depends(get_current_actor),
):
    ...
```

### CR-02: [BLOCKER] Upload Routes Read Entire Files Before Enforcing Size Limits

**File:** `api/routes/bank_inputs.py:31`, `api/routes/intake.py:34`
**Issue:** Both async upload handlers call `file.file.read()` synchronously and only enforce the 10 MB limit later inside the service. A large multipart request is loaded into memory and blocks the event loop before validation can reject it, so the intended size limit does not protect the API from memory exhaustion or request starvation.
**Fix:**
```python
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

async def _read_limited_upload(file: UploadFile) -> bytes:
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={"error": "File too large", "code": "file_too_large"},
        )
    return content
```
Use this helper in both routes and pass the bounded bytes to the service.

### CR-03: [BLOCKER] Mixed Intake Workspace Pagination Skips Items

**File:** `api/routes/intake.py:67`
**Issue:** The mixed workspace applies the same `limit` and `offset` independently to voucher sources and bank inputs, merges those partial lists, sorts them, then slices again. With 20 voucher sources followed by 20 bank inputs and `limit=15`, page 0 returns only the first 15 sources, page 1 requests `offset=15` from both tables and permanently skips the first 15 bank inputs. The UI reports the combined `total`, but some records can never appear on any page.
**Fix:**
```python
source_items = [
    _workspace_source_item(source, intake_repo)
    for source in intake_repo.list_by_status(status=status, limit=source_limit, offset=0)
]
bank_items = [
    _workspace_bank_item(bank_input, bank_repo)
    for bank_input in bank_repo.list_by_status(status=status, limit=bank_limit, offset=0)
]
items = sorted(source_items + bank_items, key=lambda item: item["uploaded_at"])
page_items = items[offset : offset + limit]
```
For larger data sets, move this into a repository query that `UNION ALL`s the two item types and applies one global `ORDER BY uploaded_at LIMIT/OFFSET`.

### CR-04: [BLOCKER] Intake File Links Cannot Work With Bearer Auth

**File:** `frontend-v3/app/vouchers/intake/[kind]/[id]/page.tsx:206`, `frontend-v3/app/vouchers/[id]/page.tsx:870`
**Issue:** The frontend renders direct `<a href={download_url}>` links for intake and bank files. Those backend file endpoints require `Authorization: Bearer ...`, but browser navigation to an `<a>` URL does not attach the token stored in `localStorage`; only Axios requests do. Users authenticated through the app will get 401s when trying to open the source files that are central to the review workflow.
**Fix:**
```ts
getIntakeFile: async (kind: IntakeKind, id: string): Promise<Blob> => {
  const endpoint =
    kind === "bank_input"
      ? `/api/v1/bank-inputs/${id}/file`
      : `/api/v1/intake/${id}/file`;
  const { data } = await apiClient.get(endpoint, { responseType: "blob" });
  return data as Blob;
}
```
Call this from the button, create an object URL, open it, and revoke it after use. Alternatively, add a backend-issued short-lived signed URL specifically for file viewing.

### CR-05: [BLOCKER] Voucher Row Editing Drops Existing Row Descriptions

**File:** `frontend-v3/app/vouchers/[id]/page.tsx:164`
**Issue:** `startEditing` copies only `account_code`, `debit`, and `credit` into `editedRows`, and `handleSave` sends only `account`, `debit`, and `credit`. Any existing `row.description` values returned by the API are silently discarded on draft updates and omitted from posted-voucher correction rows, causing data loss for row-level notes.
**Fix:**
```tsx
setEditedRows(
  voucher.rows.map((row: any) => ({
    account_code: row.account_code,
    debit: row.debit || 0,
    credit: row.credit || 0,
    description: row.description || "",
  }))
);

const rows = editedRows.map((row: any) => ({
  account: row.account_code || row.account,
  debit: row.debit || 0,
  credit: row.credit || 0,
  description: row.description || undefined,
}));
```
Also update the API client type for `updateVoucher` rows to include `description?: string`.

## Warnings

### WR-01: [WARNING] Workspace Pagination Parameters Are Unbounded

**File:** `api/routes/intake.py:51`
**Issue:** `limit` and `offset` are plain integers with no lower or upper bounds. SQLite treats `LIMIT -1` as effectively unlimited, so an authenticated client can request `?limit=-1` and force a full workspace response plus per-row link/attempt lookups.
**Fix:** Use FastAPI validation and cap the page size.
```python
from fastapi import Query

limit: int = Query(100, ge=1, le=200)
offset: int = Query(0, ge=0)
```

### WR-02: [WARNING] Correction Save Does Not Refresh Source Context

**File:** `frontend-v3/app/vouchers/[id]/page.tsx:217`
**Issue:** After saving a posted-voucher correction, the code invalidates the voucher, audit, voucher list, and accounting-corrections queries, but not `["voucher-source-context", id]`. The correction chain displayed on the same page can remain stale until the source-context query naturally refetches.
**Fix:**
```tsx
queryClient.invalidateQueries({ queryKey: ["voucher-source-context", id] });
```

---

_Reviewed: 2026-05-15T19:38:57Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
