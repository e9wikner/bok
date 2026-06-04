# Research: Architecture for v1.2 Agent Onboarding

**Date:** 2026-06-04
**Milestone:** v1.2 Agent Onboarding

## Question

How should agent onboarding integrate with the existing Bok architecture?

## Existing Integration Points

- `api/main.py` registers the agent router and generated OpenAPI URL.
- `api/deps.py` centralizes static API key and JWT bearer verification.
- `api/routes/agent.py` contains direct posting, intake queue, ping, placeholder
  key/spec/tool/idempotency endpoints.
- `api/routes/agent_instructions.py` exposes read-only system instructions plus
  mutable company instructions.
- `api/routes/accounting_corrections.py` exposes correction history.
- `api/routes/vouchers.py` exposes voucher source context for review and
  correction-chain learning.
- `DEPLOYMENT.md` already explains `BOKFOERING_API_KEY` setup.

## Recommended Shape

Add a small onboarding route rather than a new subsystem:

```text
GET /api/v1/agent-onboarding
```

Suggested route ownership:

- Either a new `api/routes/agent_onboarding.py` router with tag
  `agent-onboarding`.
- Or a route in `api/routes/agent.py` if the team wants all agent integration
  under one file.

The response should be a stable contract, not prose-only:

```json
{
  "service": "bok",
  "version": "...",
  "auth": {
    "type": "bearer",
    "header": "Authorization",
    "value_format": "Bearer <BOKFOERING_API_KEY>"
  },
  "urls": {
    "health": "/api/v1/health",
    "openapi": "/openapi.json",
    "docs": "/docs",
    "ping": "/api/v1/agent/test/ping"
  },
  "workflow": [
    {
      "step": "read_accounting_instructions",
      "method": "GET",
      "path": "/api/v1/agent-instructions/accounting"
    }
  ],
  "guardrails": [...]
}
```

## Data Flow

1. Deployed Bok starts with `BOKFOERING_API_KEY`.
2. Owner configures OpenClaw HTTP tool profile with base URL and bearer token.
3. Agent calls onboarding without or with auth. Prefer public-safe content if
   unauthenticated; include operational details after auth if protected.
4. Agent calls ping with bearer key.
5. Agent reads instructions and pending queue.
6. Agent posts vouchers via existing `LedgerService` path, preserving backend
   validation and intake/bank traceability.

## Auth Boundary

The onboarding route can safely expose generic instructions without secrets, but
anything that reveals company state, pending queue, corrections, or source files
must continue to require `get_current_actor`.

Pragmatic v1.2 option:

- Make `GET /api/v1/agent-onboarding` public-safe and never include secrets or
  company data.
- Keep all linked workflow endpoints authenticated.
- Include a boolean or optional `authenticated_check_url` rather than checking
  auth inside the onboarding route.

## MCP Consideration

If MCP is added later, it should likely be an adapter over the same agent
workflow contract, not a new bookkeeping path. The MCP transport spec requires
JSON-RPC lifecycle semantics and Streamable HTTP session behavior, including
`Mcp-Session-Id` and `MCP-Protocol-Version` handling:
https://modelcontextprotocol.io/specification/2025-06-18/basic/transports

That future adapter can expose tools equivalent to:

- `bok_get_onboarding`
- `bok_get_accounting_instructions`
- `bok_list_pending_intake`
- `bok_post_voucher`
- `bok_record_intake_failure`
- `bok_list_corrections`

## Build Order

1. Add onboarding response model and route.
2. Make agent ping dynamic and useful for deployment verification.
3. Align agent schema/tool definitions with real endpoints or mark them
   deprecated.
4. Update deployment docs and README references.
5. Add backend tests for onboarding and ping/auth behavior.
