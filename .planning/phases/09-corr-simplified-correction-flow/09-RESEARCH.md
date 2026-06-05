# Phase 9: CORR - Simplified Correction Flow - Research

**Researched:** 2026-06-05
**Status:** Ready for planning gate checks

## Research Complete

Phase 9 should extend the existing correction-voucher architecture instead of replacing it. The current system already enforces posted-voucher immutability and creates B-series correction vouchers through `LedgerService.create_correction` and `LedgerService.create_posted_correction`. The missing layer is a durable correction-note workflow: user note storage, agent-visible pending queue items, draft B-series suggestions, user approval/dismissal, and terminal history for agent learning.

## Phase Scope

### Must Deliver

- Store one active correction note per original posted voucher.
- Track correction note statuses: `pending`, `suggested`, `applied`, `dismissed`, `rejected`.
- Expose correction notes on voucher detail APIs for the frontend.
- Add a generic `POST /api/v1/vouchers/{voucher_id}/correction-draft` endpoint that creates a draft B-series voucher using `LedgerService.create_correction`.
- Let the agent link a note to a draft correction voucher and move the note to `suggested`.
- Add pending correction notes to `GET /api/v1/agent/intake/pending` as `kind: "correction_note"` without adding them to the frontend intake workspace.
- Let users approve a suggested draft correction after optional row edits.
- Let users dismiss pending/suggested notes, delete any draft voucher, and preserve suggestion details in `correction_history`.
- Let agents mark a note as `rejected` when no correction can be suggested.

### Must Not Deliver

- Do not edit posted vouchers in place.
- Do not make correction notes part of voucher-source intake workspace APIs.
- Do not create a dedicated corrections inbox page.
- Do not require pre-approval before normal agent voucher posting.
- Do not delete resolved notes; keep terminal statuses for auditability.

## Current Code Patterns

### Correction Voucher Flow

- `api/routes/vouchers.py` exposes `POST /api/v1/vouchers/{voucher_id}/correct`, which calls `LedgerService.create_posted_correction`.
- `LedgerService.create_correction(...)` creates a draft B-series voucher and validates supplied rows.
- `LedgerService.create_posted_correction(...)` creates reversal rows, appends corrected rows, posts the correction, and records agent-readable correction history.
- `VoucherRepository.create_correction(...)` creates a draft B-series voucher with `correction_of` pointing to the original voucher.
- `VoucherRepository.delete_draft(...)`, `replace_rows(...)`, and `post(...)` already support the approve/dismiss mechanics needed for suggested corrections.

### Correction History Flow

- `repositories/accounting_correction_repo.py` accepts `corrected_voucher_id: Optional[str]`.
- `db/migrations/006_add_learning_rules.sql` and `015_drop_legacy_ai_rules.sql` define `correction_history.corrected_voucher_id TEXT`, so dismissed/rejected suggestions can be recorded with no posted correction voucher.
- `api/routes/accounting_corrections.py` lists correction history for agents.
- `api/routes/vouchers.py` includes correction chain data in `/source-context`.

### Agent Queue Flow

- `api/routes/agent.py` builds source-material queue items in `list_pending_intake_sources`.
- Voucher-source items and bank-input items are merged and sorted by `uploaded_at`.
- The queue response already includes `correction_history_url`.
- Phase 9 should add a third stream for correction notes with `kind: "correction_note"`, sorted with the same timestamp logic.

### Frontend Voucher Detail Flow

- `frontend-v3/app/vouchers/[id]/page.tsx` already uses `useVoucherSourceContext`, `api.updateVoucher`, `api.correctVoucher`, React Query invalidation, and a manual correction row-editing table.
- The existing manual correction form immediately posts a B-series correction for posted vouchers.
- Phase 9 should add a separate correction-note card and a suggested-correction card, reusing the existing row input/select/table classes and `formatCurrency`, `formatOreInput`, and `parseOreInput` helpers.

## Recommended Backend Shape

### Schema and Domain

- Add `db/migrations/022_add_correction_notes.sql` because `021_allow_reupload_deleted_intake_sources.sql` is already present.
- Create `correction_notes` with:
  - `id TEXT PRIMARY KEY`
  - `voucher_id TEXT NOT NULL REFERENCES vouchers(id)`
  - `note_text TEXT NOT NULL`
  - `status TEXT NOT NULL`
  - `suggested_voucher_id TEXT REFERENCES vouchers(id)`
  - `rejection_reason TEXT`
  - `created_at TEXT NOT NULL`
  - `created_by TEXT NOT NULL`
  - `updated_at TEXT`
  - `resolved_at TEXT`
- Add a partial unique index for one active note per voucher:
  - `CREATE UNIQUE INDEX ... ON correction_notes(voucher_id) WHERE status IN ('pending', 'suggested');`
- Add a `CorrectionNote` dataclass and status literals/constants in `domain/models.py` or a small domain type if the codebase pattern warrants it.

### Repository and Service

- Add `repositories/correction_note_repo.py`.
- Repository should provide `create`, `get`, `list_for_voucher`, `get_active_for_voucher`, `list_pending`, `set_suggested`, `set_applied`, `set_dismissed`, and `set_rejected`.
- Add `services/correction_notes.py` to own lifecycle validation:
  - create only for posted original vouchers
  - reject active-note conflicts with a domain error that routes map to `409`
  - create draft suggestions through `LedgerService.create_correction`
  - link the draft using `set_suggested`
  - approve by updating draft rows, posting the draft, marking note `applied`, and recording correction history
  - dismiss by deleting any draft voucher, preserving suggested rows in `correction_history`, and marking note `dismissed`
  - reject by recording failure context and marking note `rejected`
- Keep transaction boundaries tight around note state and voucher draft/post changes. Use `db.transaction()` for multi-step state changes.

### HTTP API

- Add note routes under `api/routes/vouchers.py` or a dedicated router included by `api/main.py`. The simplest local extension is `api/routes/vouchers.py` because all routes are voucher scoped:
  - `GET /api/v1/vouchers/{voucher_id}/correction-notes`
  - `POST /api/v1/vouchers/{voucher_id}/correction-notes`
  - `POST /api/v1/vouchers/{voucher_id}/correction-draft`
  - `POST /api/v1/vouchers/{voucher_id}/correction-notes/{note_id}/suggest`
  - `POST /api/v1/vouchers/{voucher_id}/correction-notes/{note_id}/approve`
  - `POST /api/v1/vouchers/{voucher_id}/correction-notes/{note_id}/dismiss`
  - `POST /api/v1/vouchers/{voucher_id}/correction-notes/{note_id}/reject`
- Add Pydantic request/response schemas in `api/schemas.py`.
- Return full `VoucherResponse` for draft and approved correction actions where the caller needs rows.
- Map lifecycle conflicts to `409 Conflict`.

### Agent Queue and Learning Context

- Add pending correction notes to `/api/v1/agent/intake/pending` with:
  - `kind: "correction_note"`
  - `id`
  - `voucher_id`
  - `original_voucher_id`
  - `note_text`
  - `status`
  - `created_at`
  - `created_by`
  - `source_context_url: "/api/v1/vouchers/{voucher_id}/source-context"`
  - `correction_draft_url: "/api/v1/vouchers/{voucher_id}/correction-draft"`
- Do not add these items to `/api/v1/intake/workspace`.
- Extend agent entrypoint/instructions so agents know to read correction notes, inspect source context, create a draft correction, and update the note status.

## Recommended Frontend Shape

- Add `CorrectionNote`, `CorrectionNoteStatus`, and request/response types in `frontend-v3/lib/api.ts`.
- Add API methods for list/create/suggest/approve/dismiss/reject as needed by the UI and agent-facing frontend hooks.
- Add `useCorrectionNotes(voucherId)` in `frontend-v3/hooks/useData.ts`.
- Add correction note state and suggested draft state in `frontend-v3/app/vouchers/[id]/page.tsx`.
- Render `Korrigeringsnotering` directly below the existing save-result banner and above the main row card.
- Render `Foreslagen korrigering` only for active `suggested` notes with `suggested_voucher_id`.
- Reuse the existing editable rows table mechanics; do not build a new table system.
- On approval, update draft rows if changed, post the draft or call the approve endpoint, mark note `applied`, and invalidate:
  - `["voucher", id]`
  - `["voucher", suggested_voucher_id]`
  - `["correction-notes", id]`
  - `["voucher-source-context", id]`
  - `["vouchers"]`
  - `["accounting-corrections"]`

## Test Strategy

### Backend

- Add migration/domain/repository tests for:
  - one active note per voucher
  - terminal notes remain queryable
  - pending note queue ordering
- Add API/service tests in `tests/test_agent_accounting_workflow.py` or a new `tests/test_correction_notes.py`:
  - posted voucher accepts correction note
  - draft voucher rejects correction note creation
  - active-note duplicate returns `409`
  - agent pending queue includes `kind: "correction_note"`
  - correction draft returns a draft B-series voucher linked to the original
  - suggested note links `suggested_voucher_id`
  - approve posts immutable B-series voucher and marks note `applied`
  - dismiss deletes draft and records `correction_history.corrected_voucher_id == None`
  - reject marks note `rejected` and is visible in learning context

### Frontend

- `npm run build` should cover TypeScript API/hook/page changes.
- If no frontend test harness is available, include source assertions and manual UAT criteria in the summary:
  - note creation disabled on empty textarea
  - active pending note replaces editor
  - suggested card disables approval while unbalanced
  - dismiss and approve invalidate the expected query keys

### Backend Commands

- `pytest tests/test_agent_accounting_workflow.py tests/test_intake_api.py`
- `pytest tests/test_correction_notes.py` if a new test module is created.
- Full `pytest` if time allows.

## Risks and Pitfalls

- **Immediate-posting shortcut:** Reusing `POST /correct` for suggestions would skip user review and violate CORR-04.
- **Mutable posted voucher risk:** Approval must post a draft B-series voucher, never edit the original.
- **Draft orphaning:** Dismissal must delete the draft voucher or explicitly prove it is already absent.
- **State mismatch:** `suggested_voucher_id` must point to a draft B-series voucher until approval.
- **Queue confusion:** Correction notes must appear in the agent queue but not in the frontend intake workspace.
- **Learning loss:** Dismissed/rejected suggestions must preserve suggested rows or rejection reason in `correction_history`.
- **Cache staleness:** The voucher detail page has several related query keys; approval/dismissal must invalidate all of them.

## Planning Recommendation

Use three plans:

1. Backend correction-note storage, lifecycle service, and voucher-scoped APIs.
2. Agent queue and learning context integration.
3. Voucher detail frontend correction-note and suggested-correction review UI.

## RESEARCH COMPLETE
