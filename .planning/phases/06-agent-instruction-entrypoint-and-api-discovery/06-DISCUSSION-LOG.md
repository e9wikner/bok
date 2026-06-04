# Phase 6: Agent Instruction Entrypoint and API Discovery - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-06-05
**Phase:** 6-Agent Instruction Entrypoint and API Discovery
**Areas discussed:** Entrypoint visibility and auth, Placeholder endpoint handling, Agent startup workflow

---

## Entrypoint Visibility and Auth

| Option | Description | Selected |
|--------|-------------|----------|
| Public-safe metadata | No bearer token required; response only includes static setup guidance, auth format, docs/schema URLs, and no company state. | yes |
| Authenticated only | Requires `Authorization: Bearer <BOKFOERING_API_KEY>` and can include richer verification/status details. | |
| Split behavior | Public-safe response without auth, plus extra fields when a valid bearer token is supplied. | |

**User's choice:** Public-safe metadata.
**Notes:** The entrypoint must be bootstrappable before auth is proven, while sensitive operations remain protected.

| Option | Description | Selected |
|--------|-------------|----------|
| Relative paths | Return `/api/v1/...` paths only; safest behind LAN/proxies and avoids guessing external hostnames. | yes |
| Absolute URLs | Return full URLs derived from the request, easier for agents but can be wrong behind reverse proxies. | |
| Both | Return relative paths plus a best-effort base URL/absolute examples. | |

**User's choice:** Relative paths.
**Notes:** Relative paths are canonical for the entrypoint response.

| Option | Description | Selected |
|--------|-------------|----------|
| Structured only | Routes, auth format, workflow steps, and guardrails; no prose prompt. | |
| Embedded prompt | Include a concise `agent_start_prompt` string the owner can paste into OpenClaw. | yes |
| Prompt link only | Point to docs for the first prompt, keeping the API response smaller. | |

**User's choice:** Embedded prompt, modified.
**Notes:** The owner should not paste a long prompt into OpenClaw. The owner sends the entrypoint link, and the agent reads startup instructions from the entrypoint payload.

| Option | Description | Selected |
|--------|-------------|----------|
| Include auth check plan | Response tells the agent to call `POST /api/v1/agent/test/ping` with bearer auth before bookkeeping. | yes |
| Descriptive only | Response describes auth format but does not prescribe verification. | |
| You decide | Planner chooses the safest shape. | |

**User's choice:** Include auth check plan.
**Notes:** Authenticated ping is the required first protected action.

---

## Placeholder Endpoint Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Exclude from entrypoint | Leave existing endpoints alone for compatibility, but do not mention them in the startup contract. | |
| Mark deprecated | Keep endpoints but return explicit deprecation/unsupported notes so agents do not trust them. | |
| Fix critical ones | Make schema/tool discovery truthful now, and mark key/idempotency endpoints unsupported. | |
| Remove endpoints | Delete placeholder routes entirely. | yes |

**User's choice:** Remove endpoints.
**Notes:** User prioritized a clean contract over compatibility with placeholder routes.

| Option | Description | Selected |
|--------|-------------|----------|
| Remove all placeholders | Delete `/keys/*`, `/spec/openapi`, `/spec/tools`, and `/operations/idempotent/{operation_id}`. | yes |
| Keep real schema path | Remove `/keys/*`, `/spec/tools`, and idempotent placeholder; replace `/spec/openapi` with redirect/reference to `/openapi.json`. | |
| Compatibility deprecate | Keep them for one milestone but return clear deprecation-style responses. | |

**User's choice:** Remove all placeholders.
**Notes:** `/openapi.json` should be linked from the new entrypoint instead.

| Option | Description | Selected |
|--------|-------------|----------|
| State unsupported | Include `unsupported_features` or `future_scope` in the entrypoint payload. | yes |
| Do not mention | Keep entrypoint focused only on supported startup workflow. | |
| Docs only | Mention unsupported features only in docs/tests, not API payload. | |

**User's choice:** State unsupported.
**Notes:** Explicit unsupported feature fields should prevent agents from inventing unsupported capabilities.

| Option | Description | Selected |
|--------|-------------|----------|
| Point to /openapi.json | Entrypoint uses the real FastAPI-generated schema URL. | |
| No schema link | Entrypoint only lists the specific supported workflow endpoints. | |
| Workflow plus schema | Entrypoint lists supported endpoints and also links `/openapi.json`. | yes |

**User's choice:** Workflow plus schema.
**Notes:** Supported workflow list is authoritative; `/openapi.json` is available for request/response details.

| Option | Description | Selected |
|--------|-------------|----------|
| README in Phase 6 | Update technical API references now so removed routes are not documented. | yes |
| Phase 7 docs only | Keep Phase 6 code-focused and handle all docs later. | |
| Only if tests fail | Update README only if existing tests/docs checks require it. | |

**User's choice:** README in Phase 6.
**Notes:** Avoid deleting routes while leaving stale technical references in README.

---

## Agent Startup Workflow

| Option | Description | Selected |
|--------|-------------|----------|
| Read entrypoint then ping | Fetch entrypoint, read startup instructions, then call authenticated ping before any company-specific API call. | yes |
| Ping first | Immediately prove the bearer token works, then read entrypoint/workflow. | |
| Read instructions first | Fetch accounting instructions before pinging. | |

**User's choice:** Read entrypoint then ping.
**Notes:** Public-safe entrypoint is the bootstrap document that tells the agent how to verify auth.

| Option | Description | Selected |
|--------|-------------|----------|
| Accounting instructions | Read `/api/v1/agent-instructions/accounting` first. | |
| Corrections first | Read correction history before general instructions. | |
| Both before work | Read accounting instructions, then recent correction history, before scanning intake. | yes |

**User's choice:** Both before work.
**Notes:** Corrections are part of the learning loop and should influence future postings.

| Option | Description | Selected |
|--------|-------------|----------|
| Process all pending | Agent should work through the pending intake queue directly after reading instructions/corrections. | yes |
| Summarize first | Agent should scan pending work and summarize intended actions before posting. | |
| Pick safe items | Agent should only post items it can classify confidently and record failures/warnings for the rest. | |

**User's choice:** Process all pending.
**Notes:** Default workflow should not require a pre-posting summary or approval. Failure/warning endpoints remain available when the agent cannot complete an item.

| Option | Description | Selected |
|--------|-------------|----------|
| One at a time | Process each intake item independently, marking processing/posted/failed as it goes. | yes |
| Batch by source type | Process voucher sources and bank inputs in grouped passes. | |
| Agent discretion | Entrypoint says process pending work, planner/agent chooses batching. | |

**User's choice:** One at a time.
**Notes:** Per-item processing keeps traceability and failure handling cleaner.

## the agent's Discretion

- Exact Pydantic response model names, field ordering, and test organization.

## Deferred Ideas

- MCP adapter for selected Bok agent operations.
- Persistent, revocable per-agent API keys.
- Durable idempotency keys for retry-safe bookkeeping operations.
