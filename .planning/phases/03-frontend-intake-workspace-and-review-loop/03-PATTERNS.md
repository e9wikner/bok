# Phase 03: Frontend Intake Workspace and Review Loop - Pattern Map

**Mapped:** 2026-05-15
**Status:** Complete

## Scope Files and Closest Analogs

| New/Modified File | Role | Closest Analog | Pattern to Reuse |
|-------------------|------|----------------|------------------|
| `api/routes/intake.py` | Human review list/detail endpoints | Existing upload/get/file routes in same file | Keep HTTP mapping thin; use service errors and `_http_error`; declare static routes before `/{source_id}` |
| `api/routes/bank_inputs.py` | Bank connection selector and bank input detail support | Existing bank upload/get/file routes | Reuse `_bank_input_to_dict` and `_http_error`; declare `/connections` before `/{bank_input_id}` |
| `api/routes/vouchers.py` | Voucher source-context endpoint | `get_voucher_audit` in same file | Verify voucher exists, compose repository/service data, return plain dict |
| `repositories/intake_repo.py` | List/filter helpers | Existing `list_pending`, `list_links_for_voucher`, `list_attempts_for_source` | SQL string helpers returning domain dataclasses |
| `repositories/bank_input_repo.py` | Count/link lookup helpers | Existing `list_by_status`, `list_inputs_for_voucher`, `list_transactions_for_voucher` | Reuse dataclass row mappers and compact dict helpers |
| `frontend-v3/lib/api.ts` | Types and API client methods | Existing `Voucher`, `getVouchers`, attachment upload methods | Add interfaces near existing types; use `FormData` for upload methods and axios params for list methods |
| `frontend-v3/hooks/useData.ts` | React Query hooks | `useVouchers`, `useVoucher`, `useAccountingCorrections` | Stable query keys; `enabled: !!id` on detail hooks; invalidate list/detail after uploads |
| `frontend-v3/app/vouchers/intake/page.tsx` | Intake workspace UI | `frontend-v3/app/vouchers/page.tsx` | Operational page shell, filter card, table card, skeleton rows, pagination controls |
| `frontend-v3/app/vouchers/intake/[kind]/[id]/page.tsx` | Intake detail UI | `frontend-v3/app/vouchers/[id]/page.tsx` | Back link, header/status badge, metadata cards, audit-style history cards |
| `frontend-v3/app/vouchers/[id]/page.tsx` | Voucher source/review extensions | Existing attachments and audit cards | Add separate cards after rows and before manual attachments/history |
| `frontend-v3/components/Sidebar.tsx` | Route discoverability | Existing nav item array | Keep intake adjacent to `Verifikationer` if added; do not create a new feature group |

## Data Flow

1. User opens `/vouchers/intake`.
2. React Query calls `api.getIntakeWorkspace({ status, kind, limit, offset })`.
3. Upload panel posts multipart data to `POST /api/v1/intake` or `POST /api/v1/bank-inputs`.
4. Upload success invalidates `["intake-workspace", ...]` and displays the approved Swedish compact success message.
5. Processed row primary action links to `/vouchers/{voucher_id}` when `linked_voucher_ids[0]` exists.
6. Secondary row action links to `/vouchers/intake/{kind}/{id}` for item detail.
7. Voucher detail calls `api.getVoucherSourceContext(id)` and renders source material/agent/correction sections separately from manual attachments.

## UI Pattern Details

- Use `Card` only for upload panels, filters, table container, and detail sections. Do not nest cards.
- Use existing `Badge` variants:
  - `pending`: `secondary`
  - `processing`: `outline`
  - `processed`: `success`
  - `skipped`: `outline`
  - `failed`: `destructive`
  - `needs_attention`: `warning`
- Use lucide icons: `Upload`, `FileText`, `Landmark`, `AlertTriangle`, `CheckCircle2`, `Clock`, `History`, `ExternalLink`, `Download`, `Brain`.
- Keep table text at `text-sm`; truncate summaries in table but show full error text on detail pages.
- Keep file links as API download URLs. Never render `stored_path`.

## Backend Pattern Details

- Avoid introducing a new persistence model in Phase 03.
- Add repository helpers only for reads/counts/links required by the frontend.
- Keep safety-critical file serving inside existing `GET .../file` endpoints.
- Return `download_url` values as relative API paths. The frontend helper can prefix `API_URL`.
- Keep route error shapes compatible with existing `detail: { error, code, details }` conventions.

## Testing Pattern

- Backend tests should follow direct async route function calls used in `tests/test_intake_api.py` and `tests/test_bank_input_agent.py`.
- Frontend verification should use `npm run lint` and `npm run build` from `frontend-v3`.
- Plans should require manual/Playwright viewport checks for the new operational screens because no component test harness exists.

## PATTERN MAPPING COMPLETE
