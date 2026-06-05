# Phase 8: GUIDE — Per-Source Agent Guidance - Research

**Researched:** 2026-06-05
**Status:** Ready for planning gate checks

## Research Complete

Phase 8 adds a dedicated `agent_guidance` text field for voucher-source intake items. The implementation should extend the existing intake pipeline rather than introduce a parallel model: SQLite migration, `IntakeSource` domain model, `IntakeRepository`, `IntakeService`, `api/routes/intake.py`, `api/routes/agent.py`, frontend API types/client, upload form, intake detail page, and tests.

## Phase Scope

### Must Deliver

- Add nullable `agent_guidance` storage on `intake_sources`.
- Accept optional guidance during voucher-source upload.
- Expose guidance in voucher-source workspace/detail responses.
- Add `PUT /api/v1/intake/{id}/agent-guidance` for editing guidance.
- Lock edits once a source is not `pending` or `processing`; processed/deleted/failed/needs_attention/skipped sources should return `409 Conflict`.
- Include a uniform `guidance` field in `GET /api/v1/agent/intake/pending` items.
- Return `guidance: null` for bank input queue items.
- Show the upload textarea below `Kort förklaring` with label `Meddelande till agent`.
- Show and edit guidance on `/vouchers/intake/voucher_source/{id}` only.
- Hide guidance entirely for `/vouchers/intake/bank_input/{id}`.
- Update the public agent entrypoint so agents know pending intake items may include per-source guidance.

### Must Not Deliver

- Do not reuse the existing `explanation` field for agent guidance.
- Do not add guidance to bank input storage or bank input detail UI.
- Do not add a guidance badge/indicator to the intake workspace list.
- Do not let processed voucher sources mutate guidance.

## Current Code Patterns

### Backend Intake Flow

- `api/routes/intake.py` handles voucher-source upload, workspace list/detail, source metadata, file serving, and delete.
- `services/intake.py` owns validation, file storage, state transitions, and processability checks.
- `repositories/intake_repo.py` owns SQL insert/select/update and converts rows to `IntakeSource`.
- `domain/models.py` defines `IntakeSource` as the typed domain object.
- `db/migrations/018_add_intake_sources.sql` created `intake_sources`; the next migration number is `020` because `019_add_bank_inputs.sql` already exists.

### Agent Queue Flow

- `api/routes/agent.py` builds voucher-source queue items in `list_pending_intake_sources`.
- Bank queue items come from `BankInputService().agent_queue_items(...)`.
- The final response merges source items and bank input items, sorts by `uploaded_at`, and slices by offset/limit.
- The queue currently exposes `explanation` for voucher sources and no guidance field for either kind.

### Frontend Flow

- `frontend-v3/lib/api.ts` defines `VoucherSourceWorkspaceItem`, `IntakeDetailResponse`, `IntakeSourceUploadResponse`, and `api.uploadIntakeSource`.
- `frontend-v3/app/vouchers/intake/page.tsx` stores upload form state locally and posts `FormData` through `api.uploadIntakeSource`.
- `frontend-v3/app/vouchers/intake/[kind]/[id]/page.tsx` renders voucher-source metadata and bank-input metadata in separate branches.
- `frontend-v3/hooks/useData.ts` provides `useIntakeWorkspace` and `useIntakeDetail`; there is no existing mutation hook for detail edits, so either call the API directly on the page and invalidate the detail/workspace query keys, or add a small hook if following current data-hook style.

## Recommended Implementation Shape

### Schema and Domain

- Create `db/migrations/020_add_agent_guidance_to_intake_sources.sql`.
- Migration should run `ALTER TABLE intake_sources ADD COLUMN agent_guidance TEXT;`.
- Add `agent_guidance: Optional[str] = None` to `domain.models.IntakeSource`.
- Extend `IntakeRepository.create_source(...)` with `agent_guidance: Optional[str] = None`.
- Include `agent_guidance` in the `INSERT INTO intake_sources` column/value list.
- Pass `agent_guidance` into the returned `IntakeSource`.
- Hydrate `agent_guidance=row["agent_guidance"]` in `_row_to_source`.

### Service

- Extend `IntakeService.create_source_from_upload_content(...)` with `agent_guidance: str | None`.
- Normalize guidance consistently before storage:
  - `None` stays `None`.
  - whitespace-only strings become `None`.
  - non-empty strings are stripped.
- Add `IntakeService.update_agent_guidance(source_id: str, agent_guidance: str | None, actor: str) -> IntakeSource`.
- Reuse `get_source` and raise `IntakeConflictError` if status is not `pending` or `processing`.
- Use `IntakeRepository.update_agent_guidance(...)` for persistence.
- The method should return the updated source so route responses can reuse `_source_to_dict`.

### Repository

- Add `IntakeRepository.update_agent_guidance(source_id: str, agent_guidance: Optional[str], _commit: bool = True) -> None`.
- Execute `UPDATE intake_sources SET agent_guidance = ? WHERE id = ?`.
- Commit when `_commit` is true.

### HTTP API

- Update `upload_intake_source(...)` in `api/routes/intake.py` to accept `agent_guidance: str | None = Form(None)`.
- Pass guidance to `create_source_from_upload_content`.
- Add `PUT /api/v1/intake/{source_id}/agent-guidance`.
- Use a Pydantic request model such as `UpdateAgentGuidanceRequest` with `agent_guidance: str | None = None`.
- Return `_source_to_dict(updated_source)`.
- Include `agent_guidance` in `_source_to_dict` and `_workspace_source_item`.
- Do not include `agent_guidance` in `_workspace_bank_item`.
- `IntakeConflictError` already maps to `409 Conflict` through `_http_error`.

### Agent Queue and Entrypoint

- In `api/routes/agent.py`, add `"guidance": source.agent_guidance` to voucher-source queue items.
- Ensure bank input queue items have `"guidance": None`; if they are produced in `services/bank_inputs.py`, add the field there rather than patching after merge.
- Update `api/routes/agent_instructions.py`:
  - Add documentation in the pending intake endpoint entry that each queue item includes `guidance`.
  - Add a guardrail/startup instruction telling agents to consider item guidance before posting.
- Update `tests/test_agent_entrypoint.py` to assert the entrypoint mentions `guidance`.

### Frontend API

- Add `agent_guidance?: string | null` to `VoucherSourceWorkspaceItem` and `IntakeSourceUploadResponse`.
- Add optional `agent_guidance?: string` to `api.uploadIntakeSource(...)` payload.
- Append `agent_guidance` to the `FormData` only when non-empty after trim.
- Add `api.updateIntakeGuidance(id: string, agent_guidance?: string | null)` that calls `PUT /api/v1/intake/${id}/agent-guidance`.

### Upload UI

- In `frontend-v3/app/vouchers/intake/page.tsx`, add `agentGuidance` state.
- Render a textarea directly below `Kort förklaring`.
- Label must be `Meddelande till agent`.
- Placeholder must be `Valfritt — beskriv hur agenten ska bokföra detta underlag`.
- No helper text under the field.
- Include `agent_guidance: agentGuidance.trim() || undefined` in upload payload.
- Reset the state after successful upload.

### Detail UI

- In `frontend-v3/app/vouchers/intake/[kind]/[id]/page.tsx`, render a separate voucher-source-only guidance card or section.
- The card should show `Meddelande till agent`.
- It should support editing when `item.status` is `pending` or `processing`.
- It should show locked/read-only content when status is not `pending` or `processing`.
- Save should call `api.updateIntakeGuidance`, then invalidate/refetch the detail and workspace data so stale values disappear.
- Bank input detail must not render the guidance UI.

## Test Strategy

### Backend Tests

Add tests in `tests/test_intake_api.py`:

- Service persists `agent_guidance` on upload and hydrates it through `IntakeRepository.get_source`.
- Upload route returns `agent_guidance` when provided.
- Pending agent queue includes `guidance` for voucher-source items.
- Mixed pending queue returns `guidance: null` for bank input items.
- Workspace detail includes `agent_guidance` for voucher sources.
- `PUT /api/v1/intake/{id}/agent-guidance` updates pending and processing sources.
- The same endpoint returns `409` for processed sources.
- Whitespace-only guidance stores as `None`.

Update `tests/test_agent_entrypoint.py`:

- Assert the entrypoint describes item-level guidance in startup instructions, endpoint docs, or guardrails.

### Frontend Checks

- `npm run build` should type-check the changed frontend API types and pages.
- If frontend tests are not available, manual verification should cover:
  - Upload form sends `agent_guidance`.
  - Detail page shows guidance for voucher sources.
  - Detail page does not show guidance for bank inputs.
  - Save path handles 409 by showing a visible error.

### Backend Checks

- Run targeted tests first:
  - `pytest tests/test_intake_api.py tests/test_bank_input_agent.py tests/test_agent_entrypoint.py`
- If targeted tests pass, run full backend tests if time allows:
  - `pytest`

## Risks and Pitfalls

- **Schema drift:** adding the column without updating `_row_to_source` will make guidance disappear from all hydrated paths.
- **Duplicate semantics:** using `explanation` as guidance violates the phase decision and will confuse agents.
- **Queue uniformity:** bank input items must include `guidance: null` so agents can treat queue items uniformly without kind-specific missing-field checks.
- **Edit lock:** using only `processed` as the forbidden status is too narrow. The context says edits are allowed only for `pending` and `processing`.
- **Frontend stale cache:** detail and workspace queries use different keys. Save should invalidate both `["intake-detail", kind, id]` and `["intake-workspace"]` or refetch detail explicitly.
- **409 UX:** the detail page should surface a clear error if the source becomes processed between loading and saving.

## Planning Recommendation

Use three plans:

1. Backend schema/API/agent queue.
2. Frontend upload/detail guidance surfaces.
3. Tests and entrypoint documentation.

This keeps the schema/API foundation ahead of frontend changes, then validates end-to-end behavior and agent discoverability.

## RESEARCH COMPLETE
