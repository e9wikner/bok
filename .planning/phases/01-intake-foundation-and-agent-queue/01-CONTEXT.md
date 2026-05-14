# Phase 1: Intake Foundation and Agent Queue - Context

**Gathered:** 2026-05-14
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers backend foundation for voucher source intake before a voucher exists. Users can upload receipt/invoice PDF or image source material, the agent can list pending work and download original source files, and agent-posted vouchers can be linked back to the source item while preserving the existing ledger validation and posting path.

This phase does not deliver bank statement/status intake, frontend intake workspace UI, OCR/text extraction, open banking, or a pre-posting approval workflow.

</domain>

<decisions>
## Implementation Decisions

### Intake Item Shape
- **D-01:** One uploaded PDF/image is one intake item. Each item has its own file metadata, hash, explanation, lifecycle status, and actor/timestamp metadata.
- **D-02:** If one real-world voucher needs multiple supporting files, Phase 1 expects the user to combine files first rather than modeling batches or multi-file intake items.
- **D-03:** Duplicate uploads are rejected with a clear conflict response. Do not silently return the existing item as a successful upload.
- **D-04:** Intake items include an optional `source_type` in addition to the optional explanation and required file metadata.
- **D-05:** `source_type` is a small enum, with values such as `receipt`, `supplier_invoice`, `customer_invoice`, `reimbursement`, and `other`.
- **D-06:** Uploaded intake items are not editable after upload. Do not support metadata edits or file replacement in Phase 1.
- **D-07:** Pending intake items can be soft-deleted. Soft-deleted records and files remain preserved, but the item is hidden from the agent pending queue.

### Agent Queue Flow
- **D-08:** Phase 1 does not use an explicit claim step. Items remain `pending` until the agent records a processing outcome.
- **D-09:** Recording a successful outcome must guard against duplicate processing at outcome time. It should fail if the item is no longer pending or is already linked to a voucher.
- **D-10:** The agent outcome API can set only `processed` or `failed` in Phase 1. Other lifecycle statuses may exist for the broader model, but `skipped` and `needs_attention` are not agent-set outcomes yet.
- **D-11:** Failed processing attempts require a short summary and error detail. Warnings may be optional.

### Source File Access
- **D-12:** Pending queue responses should include authenticated download URLs so the agent can fetch original PDFs/images directly.
- **D-13:** Use a stable authenticated intake file endpoint, for example `/api/v1/intake/{id}/file`, protected by the existing auth dependency and storage-root containment checks.
- **D-14:** Store intake files under a separate intake storage root, such as `INTAKE_DIR`, while staying within the existing local filesystem and SQLite deployment model.
- **D-15:** Every intake file download must resolve the persisted path and configured intake root, then reject access unless the resolved file path is inside the configured root.

### Voucher Traceability
- **D-16:** Prefer intake source linkage in the agent voucher posting call, but also allow post-linking for repair/manual cases.
- **D-17:** Phase 1 allows one intake item per voucher, matching the "combine files first" decision.
- **D-18:** When an intake item is linked to a successfully posted voucher, the backend should mark it `processed` atomically.
- **D-19:** Processing attempts store the summary, linked voucher ID, actor, and timestamp as the core traceability details.

### the agent's Discretion

No areas were delegated to the agent's discretion. The user selected concrete behavior for each discussed area.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Planning Scope
- `.planning/ROADMAP.md` - Phase 1 goal, requirements, success criteria, and planned plan breakdown.
- `.planning/REQUIREMENTS.md` - Intake and agent-processing requirement IDs for Phase 1.
- `.planning/PROJECT.md` - Product constraints: automation-first workflow, traceability, compliance, input separation, and local storage.

### Codebase Context
- `.planning/codebase/ARCHITECTURE.md` - Layering, service/repository patterns, and FastAPI integration points.
- `.planning/codebase/INTEGRATIONS.md` - Current auth model, SQLite storage, local filesystem attachment storage, and deployment assumptions.
- `.planning/codebase/CONCERNS.md` - Known attachment path-safety risk and API error-handling concerns relevant to intake downloads.

### Existing Implementation Anchors
- `api/routes/attachments.py` - Existing voucher attachment upload/download pattern and known path-safety gap to avoid repeating.
- `api/routes/agent.py` - Existing agent voucher posting endpoint that creates and posts through `LedgerService`.
- `api/routes/vouchers.py` - Existing voucher create/post/correct endpoints and response mapping.
- `services/ledger.py` - Required validation and posting path for agent-created vouchers.
- `db/migrations/001_initial_schema.sql` - Existing attachment schema shape and voucher/audit base tables.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `LedgerService.create_voucher` and `LedgerService.post_voucher`: agent intake posting must continue through this validation/posting path.
- `api.deps.get_current_actor`: new intake routes should use existing auth/actor dependency, while recognizing current actor attribution is coarse (`api`).
- Existing attachment MIME/type/size/hash handling in `api/routes/attachments.py`: useful as a starting pattern for upload validation, but download/delete path safety must be stronger for intake.

### Established Patterns
- Backend follows FastAPI route modules plus service/repository layers. Intake should add route, service, repository, and migration code rather than putting SQL and storage logic directly in route handlers.
- SQLite migrations are handwritten in `db/migrations/*.sql`, with repositories using explicit SQL.
- API routes commonly translate `ValidationError` into structured 400 responses; new intake APIs should prefer typed errors and stable response payloads instead of broad catch-all behavior.

### Integration Points
- Register a new intake router in `api/main.py`.
- Add migration-managed intake source, processing attempt, and voucher-link storage.
- Extend the existing agent API surface so the agent can list pending intake, download source files, post/link vouchers, and record outcomes.
- Add focused tests for duplicate hash rejection, pending queue behavior, outcome-time guard, source-to-voucher traceability, and storage-root containment.

</code_context>

<specifics>
## Specific Ideas

- The queue should stay simple for Phase 1: no explicit claim/lease model.
- The source file URL should be stable and authenticated rather than signed.
- File path safety is a hard requirement, not an optional cleanup.
- The user prefers a narrow first version over flexible batch/multi-file support.

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within phase scope.

</deferred>

---

*Phase: 1-Intake Foundation and Agent Queue*
*Context gathered: 2026-05-14*
