# Phase 09: CORR — Simplified Correction Flow - Context

**Gathered:** 2026-06-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Users can leave text correction notes on posted vouchers; the notes appear in the agent's intake queue as `kind: 'correction_note'` items. The agent reads them, creates a draft B-series correction voucher via a generic endpoint, and the user reviews and approves it on the voucher detail page before posting. Approved corrections become immutable B-series vouchers linked to the original. The note lifecycle (pending, suggested, applied, dismissed, rejected) is tracked. Dismissed notes and their suggested rows are preserved in `correction_history` for agent learning context.

</domain>

<decisions>
## Implementation Decisions

### Correction note data model
- **D-01:** New `correction_notes` table (not an extension of `correction_history`). `correction_history` records posted corrections; notes track user intent and agent suggestions before resolution.
- **D-02:** Each note stores: `id`, `voucher_id`, `note_text`, `status`, `suggested_voucher_id` (nullable, references a draft B-series voucher), `created_at`, `created_by`. One active note per voucher.
- **D-03:** Resolved notes (applied, dismissed, rejected) are kept with terminal status for audit trail. Not deleted.
- **D-04:** Notes do NOT link to intake sources directly; `voucher_id` is sufficient. The agent can fetch source context via the existing `GET /api/v1/vouchers/{id}/source-context` endpoint if needed.

### Agent queue placement
- **D-05:** Correction notes appear in the agent intake queue (`/api/v1/agent/intake/pending`) with `kind: 'correction_note'`. They do NOT appear in the frontend intake workspace (`/api/v1/intake/workspace`).

### Agent suggestion mechanism
- **D-06:** Agent creates draft B-series corrections via a generic `POST /api/v1/vouchers/{voucher_id}/correction-draft` endpoint (not an agent-specific route). This endpoint calls `LedgerService.create_correction` and returns the draft voucher.
- **D-07:** After creating the draft, the agent updates the note status to `suggested` and links `suggested_voucher_id`.
- **D-08:** No processing attempts table for correction notes. The `status` field is sufficient.
- **D-09:** When a user dismisses a note, the draft B-series voucher is deleted, and a record is added to `correction_history` with `corrected_voucher_id: null` and the suggested rows preserved in JSON for agent learning.

### User approval surface
- **D-10:** User reviews and approves suggested corrections on the existing voucher detail page (`/vouchers/{id}`).
- **D-11:** The voucher detail page shows a "Suggested correction" card when `suggested_voucher_id` is present. The user can edit the draft rows before approving.
- **D-12:** No dedicated corrections inbox page. The primary approval surface is inline on the voucher detail page.

### Note lifecycle and dismissal semantics
- **D-13:** Statuses: `pending` → `suggested` → `applied` | `dismissed` | `rejected`.
- **D-14:** User can dismiss a note at any time (even before the agent suggests). When dismissed, the draft is deleted and logged in `correction_history`.
- **D-15:** Agent can mark a note as `rejected` when it cannot figure out how to suggest a fix. This is distinct from user dismissal.
- **D-16:** Dismissed and rejected notes (with their suggested rows) are visible in the agent's learning context via `/api/v1/accounting-corrections` or a related endpoint. The agent learns from both successful and unsuccessful suggestions.

### Scope / Deferred
- **D-17:** No frontend workspace integration for correction notes. The intake workspace (`/api/v1/intake/workspace`) remains focused on source material only.

### Agent's Discretion
- Exact component styling for the "Suggested correction" card on the voucher detail page is left to the planner/executor to match existing Tailwind patterns.
- Exact error message text for the `rejected` agent action is left to implementation.
- Whether the agent marks a note as `rejected` via a dedicated agent endpoint or by updating the note directly is an implementation detail for the planner.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase Definition & Requirements
- `.planning/ROADMAP.md` — Phase 9 definition, success criteria, and UI hint
- `.planning/REQUIREMENTS.md` — CORR-01 through CORR-06 requirements
- `.planning/PROJECT.md` — Core value, constraints, key decisions (automation-first, immutable B-series, traceability)

### Existing Code to Extend
- `domain/models.py` — `Voucher`, `VoucherRow`, `CorrectionHistory` dataclasses; new `CorrectionNote` dataclass belongs here
- `services/ledger.py` — `create_correction` (creates draft B-series), `create_posted_correction` (creates + posts), `post_voucher`
- `api/routes/vouchers.py` — Existing correction routes (`POST /{voucher_id}/correct`), source-context endpoint, list/get voucher routes
- `api/routes/agent.py` — Agent intake queue (`GET /intake/pending`), agent voucher posting (`POST /vouchers`)
- `api/routes/accounting_corrections.py` — Correction history for agent learning context
- `repositories/accounting_correction_repo.py` — `CorrectionHistory` persistence; must support `corrected_voucher_id = null` for dismissed suggestions
- `repositories/voucher_repo.py` — `VoucherRepository` (draft creation, posting)
- `frontend-v3/app/vouchers/[id]/page.tsx` — Existing voucher detail page with manual correction UI; new "Suggested correction" card belongs here
- `frontend-v3/lib/api.ts` — API client patterns; new methods for creating notes, fetching notes, approving/dismissing
- `db/migrations/` — New migration to add `correction_notes` table

### Patterns & Conventions
- `frontend-v3/hooks/useData.ts` — `useVoucher`, `useVoucherSourceContext` hooks; new `useCorrectionNotes` hook belongs here
- `frontend-v3/components/ui/card.tsx` — Reusable card component for the suggested correction UI

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Card components:** `frontend-v3/components/ui/card.tsx` and standard Tailwind card pattern used throughout the voucher detail page.
- **React Query hooks:** `frontend-v3/hooks/useData.ts` has `useVoucher`, `useVoucherSourceContext`, `useAccountingCorrections`. Add `useCorrectionNotes(voucherId)` following the same pattern.
- **API client:** `frontend-v3/lib/api.ts` uses typed axios methods. Follow the existing `api.updateVoucher` / `api.correctVoucher` pattern for the new note endpoints.
- **Voucher row editing:** The existing voucher detail page already has editable row tables for manual corrections. The "edit before approve" flow can reuse the same row editing components.

### Established Patterns
- **Backend:** FastAPI `APIRouter` → Service (`LedgerService`) → Repository (`VoucherRepository`) → SQLite migration. Follow this layer for the new `POST /api/v1/vouchers/{id}/correction-draft` endpoint and the correction note routes.
- **Agent queue:** `api/routes/agent.py` returns a uniform `kind` field for every item (`voucher_source`, `bank_input`). Add `correction_note` as a new kind with relevant fields (`voucher_id`, `note_text`, `status`, `original_voucher_id`).
- **Error handling:** `ValidationError` in service layer maps to `HTTPException(400)` in routes. Add typed errors for note conflicts (e.g., note already exists for voucher).
- **Frontend:** Next.js App Router page with `useQueryClient` for cache invalidation after mutations. The voucher detail page already invalidates `voucher`, `voucher-audit`, `voucher-source-context`, and `accounting-corrections` on save.

### Integration Points
- **Agent queue builder:** In `api/routes/agent.py` (`list_pending_intake_sources`), add a third source stream for `correction_notes` with `status = 'pending'`, merged alongside voucher sources and bank inputs.
- **Voucher detail page:** Add a new card section below the existing "Korrigering" form that appears conditionally when `correction_notes` data indicates a pending or suggested note. Include note text, draft row preview (editable), and Approve/Dismiss buttons.
- **LedgerService:** The new `POST /api/v1/vouchers/{id}/correction-draft` route calls `ledger.create_correction` directly (not `create_posted_correction`). Ensure the draft B-series voucher is returned with full row data.
- **Correction history:** Extend `AccountingCorrectionRepository.create` or add a new method to log dismissed/rejected suggestions where `corrected_voucher_id` is null but `corrected_data` contains the suggested rows JSON.

</code_context>

<specifics>
## Specific Ideas

- The "Suggested correction" card on the voucher detail page should reuse the existing row-editing table pattern from the manual correction flow, but pre-populated with the draft B-series rows.
- When a user approves, the frontend can either: (1) `PUT` the edited draft rows to update the draft voucher, then `POST /api/v1/vouchers/{draft_id}/post` to post it; or (2) call a single "approve" endpoint that handles both. The planner should decide which pattern fits the existing frontend mutation style best.
- The agent's queue item for a correction note should include `original_voucher_id`, `note_text`, and a link to the original voucher's source context so the agent has full context without extra API calls.

</specifics>

<deferred>
## Deferred Ideas

### Frontend workspace badge for pending corrections
Showing a count of pending correction notes in the intake workspace was discussed and deferred. The intake workspace remains focused on source material only; correction notes are surfaced on voucher detail pages.

### Dedicated corrections inbox page
A central `/corrections/pending` page was discussed and deferred in favor of inline approval on the voucher detail page. If the volume of corrections grows, a dedicated inbox can be added later.

### Agent auto-retry on rejected notes
Automatically re-queuing rejected notes for another agent attempt was not discussed. If needed, it would be a small follow-up enhancement.

</deferred>

---

*Phase: 09-CORR — Simplified Correction Flow*
*Context gathered: 2026-06-05*
