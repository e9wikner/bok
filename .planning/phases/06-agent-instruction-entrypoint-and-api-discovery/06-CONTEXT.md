# Phase 6: Agent Instruction Entrypoint and API Discovery - Context

**Gathered:** 2026-06-05
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers the machine-readable startup contract for an external HTTP
agent. The work is limited to `/api/v1/agent-instructions/entrypoint`, truthful
agent API discovery, dynamic ping behavior, removal of misleading placeholder
agent routes, tests, and immediate README cleanup for removed technical
references.

It does not implement MCP, persistent per-agent key lifecycle, durable
idempotency, frontend UI, or a separate bookkeeping decision engine.

</domain>

<decisions>
## Implementation Decisions

### Entrypoint Visibility and Auth

- **D-01:** `/api/v1/agent-instructions/entrypoint` must be public-safe and unauthenticated.
- **D-02:** The unauthenticated entrypoint must not expose company-specific state, pending work, secrets, correction content, or source filenames.
- **D-03:** The entrypoint must return relative paths only, not absolute URLs derived from the request host.
- **D-04:** The owner should give OpenClaw only the entrypoint URL. The agent should read startup instructions from the entrypoint payload; the owner should not paste a long prompt into OpenClaw.
- **D-05:** The entrypoint must prescribe an auth verification step: call `POST /api/v1/agent/test/ping` with `Authorization: Bearer <BOKFOERING_API_KEY>` before any company-specific API call.

### Placeholder Endpoint Handling

- **D-06:** Remove the placeholder agent key lifecycle routes entirely:
  `/api/v1/agent/keys/create`, `/api/v1/agent/keys`, and
  `/api/v1/agent/keys/{key_id}/revoke`.
- **D-07:** Remove the placeholder discovery routes entirely:
  `/api/v1/agent/spec/openapi` and `/api/v1/agent/spec/tools`.
- **D-08:** Remove the placeholder idempotent operation route entirely:
  `/api/v1/agent/operations/idempotent/{operation_id}`.
- **D-09:** The entrypoint must explicitly state unsupported or future-scope features: persistent API-key lifecycle, generated tool-schema discovery, and durable idempotency.
- **D-10:** The entrypoint must list supported workflow endpoints as the authoritative startup path and also link the real FastAPI-generated schema at `/openapi.json`.
- **D-11:** Phase 6 must update `README.md` technical API references if they mention routes removed in this phase. Broader deployment guidance remains Phase 7 scope.

### Agent Startup Workflow

- **D-12:** First action after the owner gives OpenClaw the entrypoint URL: fetch the public entrypoint, read its startup instructions, then verify auth with `POST /api/v1/agent/test/ping`.
- **D-13:** After ping succeeds, the agent should read `/api/v1/agent-instructions/accounting`, then recent correction history from `/api/v1/accounting-corrections`, before scanning pending work.
- **D-14:** After reading instructions and corrections, the agent should scan pending intake and process all pending items automatically. The workflow should not require a pre-posting summary or user approval.
- **D-15:** If the agent cannot complete an item, it should use existing processing/failure/warning endpoints instead of guessing or requiring approval.
- **D-16:** Pending work should be processed one item at a time, marking each item processing, posted, or failed/warning as appropriate.

### the agent's Discretion

The planner may choose the exact Pydantic response model names, field ordering,
and test organization, provided the decisions above are preserved and the
entrypoint remains public-safe.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Planning Scope

- `.planning/ROADMAP.md` - Phase 6 goal, requirements, and success criteria.
- `.planning/REQUIREMENTS.md` - v1.2 requirements mapped to Phase 6.
- `.planning/PROJECT.md` - product constraints, automation-first direction, and agent integration scope.
- `.planning/research/SUMMARY.md` - research summary recommending REST onboarding, real `/openapi.json`, and MCP deferral.
- `.planning/research/ARCHITECTURE.md` - suggested route shape and integration points.
- `.planning/research/PITFALLS.md` - risks around stale discovery data, fake key lifecycle, and unsafe onboarding leakage.

### Existing API Code

- `api/routes/agent_instructions.py` - target router for the new `entrypoint` route.
- `api/routes/agent.py` - existing agent posting, pending intake, ping, and placeholder routes to remove.
- `api/deps.py` - bearer API-key/JWT auth behavior used by protected agent endpoints.
- `api/main.py` - FastAPI app metadata, `/openapi.json`, `/docs`, `/redoc`, and router registration.
- `api/routes/accounting_corrections.py` - correction history endpoint the startup workflow should reference.
- `api/routes/vouchers.py` - voucher `source-context` route and correction-chain context.

### Documentation

- `README.md` - technical agent API references that must be cleaned if they mention removed placeholder routes.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `api/routes/agent_instructions.py`: already owns instruction-related routes under `/api/v1/agent-instructions`; add `GET /entrypoint` here rather than creating a separate onboarding router.
- `api/deps.py`: existing protected endpoints accept `Authorization: Bearer <BOKFOERING_API_KEY>` or JWT; the entrypoint should describe this, while protected calls continue using `get_current_actor`.
- `api/main.py`: already exposes canonical FastAPI docs/schema URLs at `/docs`, `/redoc`, and `/openapi.json`.
- `api/routes/agent.py`: existing `POST /api/v1/agent/test/ping` should be made dynamic and useful for auth verification.

### Established Patterns

- Backend routes use `APIRouter` modules in `api/routes` and Pydantic request models near the route handlers.
- Business/accounting behavior remains in services such as `LedgerService`; this phase should not add new posting logic outside existing agent posting paths.
- Authenticated protected routes depend on `get_current_actor`; the public entrypoint must avoid calling company-state repositories.
- Existing agent instructions separate read-only system instructions from writable company instructions; the entrypoint should guide agents to read the combined accounting instructions endpoint after ping.

### Integration Points

- New route: `GET /api/v1/agent-instructions/entrypoint`.
- Existing protected auth check: `POST /api/v1/agent/test/ping`.
- Existing workflow endpoints to reference: `/api/v1/agent-instructions/accounting`, `/api/v1/accounting-corrections`, `/api/v1/agent/intake/pending`, `/api/v1/agent/intake/{source_id}/processing`, `/api/v1/agent/intake/{source_id}/failed`, `/api/v1/agent/vouchers`, `/api/v1/vouchers/{voucher_id}/source-context`.
- Remove placeholder routes from `api/routes/agent.py` and remove any now-unused imports such as `uuid` or `hashlib`.

</code_context>

<specifics>
## Specific Ideas

- The entrypoint payload should include agent-readable startup instructions, but the owner workflow is simply: give OpenClaw the entrypoint link.
- The startup workflow should be explicit enough that OpenClaw can proceed from the link: read entrypoint, ping with bearer auth, read accounting instructions, read recent corrections, scan pending intake, process all pending items one at a time.
- Relative paths are canonical. Avoid host-derived absolute URLs because LAN/proxy setups can make them wrong.

</specifics>

<deferred>
## Deferred Ideas

- MCP adapter for selected Bok agent operations remains future scope.
- Persistent, revocable per-agent API keys remain future scope.
- Durable idempotency keys for retry-safe bookkeeping operations remain future scope.

</deferred>

---

*Phase: 6-Agent Instruction Entrypoint and API Discovery*
*Context gathered: 2026-06-05*
