# Phase 3: Frontend Intake Workspace and Review Loop - Context

**Gathered:** 2026-05-15
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers the frontend work surface for intake and review. Users can upload voucher source material and bank CSV inputs, scan the unified intake queue by status/type, open intake details for source metadata and processing history, navigate from processed items to posted vouchers, and review intake source material plus correction-learning context on voucher detail pages.

This phase does not change backend intake semantics, add OCR/text extraction, add Open Banking, add a pre-posting approval workflow, or replace immutable posted vouchers and B-series correction vouchers.

</domain>

<decisions>
## Implementation Decisions

### Workspace Shape
- **D-01:** Use a unified intake table for voucher sources and bank inputs, with a visible type column/indicator to preserve the underlying input separation.
- **D-02:** Use compact filter chips for status and type instead of status tabs or status-lane grouping. This should stay close to the existing voucher list pattern.
- **D-03:** Place the intake workspace under or near `Verifikationer` rather than adding a new top-level sidebar item.
- **D-04:** Use a dedicated intake detail page for item metadata, source files, processing attempts, and linked vouchers. Do not rely on inline row expansion as the main review surface.

### Upload Flow
- **D-05:** Present voucher-source upload and bank CSV upload as two separate upload panels in the workspace.
- **D-06:** Voucher-source uploads collect `source_type` plus an optional short explanation at upload time.
- **D-07:** For bank CSV uploads, the user selects the bank account number associated with the CSV upload. The frontend should map that visible account number to the backend bank connection/account ID instead of exposing an opaque connection ID.
- **D-08:** After successful upload, stay on the intake workspace, show a compact success message, and refresh the table/status counts.

### Status and Failure Review
- **D-09:** In the unified table, show a lifecycle status badge plus one compact detail column for status-specific context such as imported count, linked voucher, or error summary.
- **D-10:** Failed and `needs_attention` rows should show an actionable error summary in the table, truncated if needed.
- **D-11:** Processed rows linked to vouchers should use the posted voucher as the primary row action, with the intake detail page available as a secondary path.
- **D-12:** Failed and `needs_attention` intake detail pages should emphasize raw processing history: attempts, summaries, warnings, errors, actor, and timestamps as an audit-style record.

### Voucher Review Context
- **D-13:** Voucher detail pages should show linked intake source material in a dedicated source-material section, separate from manual voucher attachments.
- **D-14:** Agent processing notes should appear on voucher detail as an audit-style processing section with summaries, warnings/errors, actor, and timestamps.
- **D-15:** Bank inputs should appear in the same dedicated source-material section as voucher-source files, while remaining clearly typed as bank inputs.
- **D-16:** When a voucher has been corrected, show a correction chain section with original voucher, correction voucher(s), correction reason, and a note that this history is agent-readable.

### the agent's Discretion

No areas were delegated to the agent's discretion. The user selected concrete behavior for each discussed area.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Planning Scope
- `.planning/ROADMAP.md` - Phase 3 goal, requirements, success criteria, and planned plan breakdown.
- `.planning/REQUIREMENTS.md` - FRNT requirement IDs and v1/v2 boundaries for intake, bank inputs, and review.
- `.planning/PROJECT.md` - Product constraints: automation-first workflow, traceability, input separation, local storage, and operational frontend surface.
- `.planning/phases/01-intake-foundation-and-agent-queue/01-CONTEXT.md` - Prior locked decisions for voucher source uploads, immutable intake items, lifecycle, file access, and traceability.
- `.planning/phases/02-bank-input-and-direct-posting-context/02-CONTEXT.md` - Prior locked decisions for bank CSV inputs, typed shared queue items, correction history, and bank-created voucher traceability.

### Codebase Context
- `.planning/codebase/CONVENTIONS.md` - Frontend naming, formatting, imports, and UI coding conventions.
- `.planning/codebase/STRUCTURE.md` - Where frontend routes, hooks, API wrappers, and shared components belong.
- `.planning/codebase/STACK.md` - Next.js, React Query, Tailwind, axios, and Playwright stack details.

### Frontend Implementation Anchors
- `frontend-v3/lib/api.ts` - Existing API client/types and voucher attachment helpers; add intake/bank-input client methods and types here or adjacent to this pattern.
- `frontend-v3/hooks/useData.ts` - Existing React Query hooks; add intake and bank-input hooks following current query-key/stale-time style.
- `frontend-v3/app/vouchers/page.tsx` - Current dense voucher list with filter chips/table pattern to mirror for intake.
- `frontend-v3/app/vouchers/[id]/page.tsx` - Voucher detail page to extend with source material, processing notes, bank traceability, and correction chain context.
- `frontend-v3/components/Sidebar.tsx` - Existing navigation structure; intake should sit under/near vouchers rather than as a new top-level sidebar item unless routing constraints require otherwise.
- `frontend-v3/components/ui/button.tsx`, `frontend-v3/components/ui/card.tsx`, `frontend-v3/components/ui/badge.tsx`, `frontend-v3/components/ui/skeleton.tsx` - Existing UI primitives to reuse.

### Backend API Anchors
- `api/routes/intake.py` - Human intake upload/get/file/delete endpoints for voucher source material.
- `api/routes/bank_inputs.py` - Bank CSV upload/get/file endpoints; frontend bank upload must provide mapped backend bank connection/account ID.
- `api/routes/agent.py` - Shared typed pending intake queue shape, correction history URL, and agent processing endpoints.
- `services/intake.py` - Intake source lifecycle, storage-root containment, soft-delete, processing attempts, and voucher links.
- `services/bank_inputs.py` - Bank input lifecycle, CSV processing results, bank queue items, file access, and voucher/bank transaction traceability.
- `repositories/intake_repo.py` - Intake source, processing attempt, and voucher source link persistence.
- `repositories/bank_input_repo.py` - Bank input, input transaction, and voucher bank-input link persistence.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `frontend-v3/app/vouchers/page.tsx`: dense table, search/filter chip patterns, status badges, pagination, and operational page layout are the closest UI analogue for the intake workspace.
- `frontend-v3/app/vouchers/[id]/page.tsx`: already has voucher metadata, correction form, manual attachments, and audit history; extend it with separate intake source material and processing/correction-learning sections.
- `frontend-v3/lib/api.ts`: axios client already handles auth token injection and multipart uploads for voucher attachments; reuse this style for voucher-source and bank CSV uploads.
- `frontend-v3/hooks/useData.ts`: existing React Query hooks centralize server-state fetching and invalidation patterns.
- UI primitives in `frontend-v3/components/ui/`: reuse existing `Button`, `Card`, `Badge`, and `Skeleton` styling.

### Established Patterns
- Frontend pages are client components under `frontend-v3/app`, with API calls via `api` and React Query hooks.
- Operational pages use restrained card/table layouts, compact filters, badges, and lucide icons.
- Voucher attachments are currently separate from intake source material; Phase 3 should preserve that distinction visually.
- Current voucher correction UI already tells the user that posted-voucher corrections become agent-readable history; the new correction chain section should build on that wording.

### Integration Points
- Add frontend types and API client methods for intake sources, bank inputs, pending/shared queue items, processing attempts, source file URLs, bank account/connection selection, and voucher source traceability.
- Add React Query hooks for listing/filtering intake items, fetching intake details, uploading voucher source files, uploading bank CSV files, and fetching voucher-linked source context.
- Add an intake workspace route under or near `Verifikationer`, likely as a nested or sibling route that keeps sidebar navigation compact.
- Add an intake detail route that handles both voucher-source and bank-input item types.
- Extend voucher detail data fetching and rendering to include linked intake sources, linked bank inputs/transactions, processing attempt notes, and correction chain information.

</code_context>

<specifics>
## Specific Ideas

- The bank CSV upload UI should ask for a bank account number, not a technical bank connection ID. Planners should verify whether existing backend APIs expose enough bank account/connection metadata for this selection and add a small frontend-facing lookup if needed.
- The unified intake table should make type separation obvious without splitting the daily workflow into separate pages.
- The intake detail page is mainly the audit/detail surface; processed rows can still send the user straight to the posted voucher.
- Raw processing history is preferred on failed/needs_attention detail pages over a guided remediation panel.

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within phase scope.

</deferred>

---

*Phase: 3-Frontend Intake Workspace and Review Loop*
*Context gathered: 2026-05-15*
