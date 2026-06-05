# Phase 8: GUIDE — Per-Source Agent Guidance - Context

**Gathered:** 2026-06-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Users can attach explicit agent guidance messages to individual uploaded receipts/invoices (voucher sources), and agents see those messages when processing the intake item. This is a new text field on `intake_sources`, separate from the existing `explanation` field, exposed in the agent queue and frontend upload/review surfaces.

</domain>

<decisions>
## Implementation Decisions

### Naming
- **D-01:** Canonical field name is `agent_guidance` — used for DB column, API field, and code references.
- **D-02:** API endpoint is `PUT /api/v1/intake/{id}/agent-guidance` — explicit and self-documenting.
- **D-03:** Frontend label is `Meddelande till agent` — Swedish, matches the requirements' wording, and aligns with the existing Swedish UI.

### Frontend Discoverability
- **D-04:** The guidance field is **always visible** below the `Förklaring` (explanation) textarea on the upload form. Not collapsed behind an accordion.
- **D-05:** The guidance field is **editable on the intake detail page** (`/vouchers/intake/voucher_source/{id}`). Users can review and edit what they wrote.
- **D-06:** Placeholder text: `Valfritt — beskriv hur agenten ska bokföra detta underlag` — emphasizes that the field is optional.
- **D-07:** No helper text below the field — keep the form minimal.

### Edit Lifecycle
- **D-08:** Users can add or edit guidance **anytime before the source is processed** (status = `pending` or `processing`).
- **D-09:** Processed sources are **locked** — attempts to edit guidance return `409 Conflict` with a clear error message.
- **D-10:** Guidance is **optional (nullable)** — most sources will have no guidance. This matches the automation-first product goal.

### Scope
- **D-11:** Guidance applies **only to voucher sources** (receipts, invoices, etc.). Bank inputs do NOT get a guidance field.
- **D-12:** The agent queue endpoint (`GET /api/v1/agent/intake/pending`) returns a uniform schema: every item includes a `guidance` field. Bank inputs show `guidance: null`.
- **D-13:** The bank input detail page **hides the guidance field entirely** — no read-only placeholder.
- **D-14:** The intake workspace list does **not** show a guidance indicator badge — keep the table clean. Guidance is visible on the detail page and upload form.

### Agent's Discretion
- The exact component styling (textarea height, spacing) is left to the planner/executor to match existing Tailwind patterns.
- The exact error message text for the 409 response is left to implementation (should be clear in Swedish or English per existing conventions).

### Folded Todos
None.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase Definition & Requirements
- `.planning/ROADMAP.md` — Phase 8 definition, success criteria, and UI hint
- `.planning/REQUIREMENTS.md` — GUIDE-01, GUIDE-02, GUIDE-03 requirements
- `.planning/PROJECT.md` — v1.3 context, constraints, key decisions (especially brownfield approach and automation-first goal)

### Research & Prior Decisions
- `.planning/research/SUMMARY.md` — Research findings, recommended phase ordering, and architecture approach
- `.planning/research/PITFALLS.md` — Pitfall #4: Conflating "Explanation" with "Agent Guidance" (critical: must add dedicated column, never reuse `explanation`)
- `.planning/research/FEATURES.md` — Feature dependency notes, scope recommendations

### Existing Code to Extend
- `api/routes/intake.py` — Existing intake routes (upload, workspace, detail, delete). The new `PUT /api/v1/intake/{id}/agent-guidance` endpoint belongs here.
- `api/routes/agent.py` — Existing agent queue endpoint (`GET /api/v1/agent/intake/pending`). Must include `guidance` field in queue items.
- `services/intake.py` — Existing `IntakeService`. Add `update_agent_guidance()` method.
- `repositories/intake_repo.py` — Existing `IntakeRepository`. Add `update_agent_guidance()` method.
- `frontend-v3/app/vouchers/intake/page.tsx` — Upload form. Add `agent_guidance` textarea below the explanation field.
- `frontend-v3/app/vouchers/intake/[kind]/[id]/page.tsx` — Detail page. Add editable `agent_guidance` field for voucher sources.
- `frontend-v3/lib/api.ts` — API client. Add `updateIntakeGuidance()` method.
- `db/migrations/018_add_intake_sources.sql` — Existing schema. New migration adds `agent_guidance TEXT` column.
- `domain/models.py` — `IntakeSource` dataclass. Add `agent_guidance` attribute.
- `api/schemas.py` — Add request/response schema for guidance update if needed.

### Entrypoint & Tests
- `api/routes/agent_instructions.py` — Agent entrypoint. Must be updated to document the new field in the intake queue schema.
- `tests/test_agent_entrypoint.py` — Must assert that the new `guidance` field is documented in the entrypoint.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Card/textarea components:** `frontend-v3/components/ui/card.tsx` and standard `<textarea>` with Tailwind classes — reuse the existing explanation textarea pattern.
- **API client pattern:** `frontend-v3/lib/api.ts` uses `axios` with typed methods. Follow the existing `api.updateIntakeSource`-style pattern.
- **React Query hooks:** `frontend-v3/hooks/useData.ts` has `useIntakeWorkspace` and `useIntakeDetail`. Add a mutation hook for guidance updates.

### Established Patterns
- **Backend:** FastAPI `APIRouter` → `IntakeService` → `IntakeRepository` → SQLite migration. Follow this layer for the new PUT endpoint.
- **Error handling:** `IntakeError` subclasses map to HTTPException in `api/routes/intake.py`. Add `IntakeConflictError` for processed-source edits.
- **Frontend:** Next.js App Router page with `useQueryClient` for cache invalidation after mutations.

### Integration Points
- **Upload form:** Add the `agent_guidance` FormData field to `api.uploadIntakeSource` in `frontend-v3/lib/api.ts`.
- **Agent queue:** The `source_items` builder in `api/routes/agent.py` (`list_pending_intake_sources`) must include `agent_guidance` from the source.
- **Detail page:** Add a new card section for `agent_guidance` with an edit button that calls the PUT endpoint.
- **Migration:** New migration `020_add_agent_guidance_to_intake_sources.sql` adds the column.

</code_context>

<specifics>
## Specific Ideas

No specific visual references — the existing explanation textarea in `frontend-v3/app/vouchers/intake/page.tsx` is the reference pattern. The new field should look and behave identically, just with a different label and placeholder.

</specifics>

<deferred>
## Deferred Ideas

### Bank input guidance
Adding `agent_guidance` to bank inputs was discussed and deferred. The requirements focus on receipts/invoices. If users request this later, it can be added as a small follow-up.

### Workspace list guidance indicator
A badge/icon in the workspace table showing which sources have guidance was deferred. The guidance is visible on the detail page and upload form.

### Reviewed Todos (not folded)
None.

</deferred>

---

*Phase: 08-GUIDE — Per-Source Agent Guidance*
*Context gathered: 2026-06-05*
