# Research: Pitfalls for v1.2 Agent Onboarding

**Date:** 2026-06-04
**Milestone:** v1.2 Agent Onboarding

## Question

What mistakes should Bok avoid when adding agent onboarding?

## Pitfalls

### Shipping Stale Discovery Data

`/api/v1/agent/spec/openapi` currently returns a tiny hand-written schema that
does not reflect the real application. If onboarding points agents there as the
truth, agents will miss the actual workflow and may call the wrong endpoints.

Prevention: link `/openapi.json` as the canonical full schema, and only keep a
scoped agent schema if it is generated or deliberately maintained.

### Presenting Placeholder API Key Management as Production

`/api/v1/agent/keys/create`, `/keys`, and `/revoke` return generated/static data
but do not appear to persist or enforce per-key lifecycle. Publishing these in
deployment instructions would cause false confidence.

Prevention: document `BOKFOERING_API_KEY` as the supported v1.2 credential and
explicitly mark persistent key management as future work unless implemented.

### Overbuilding MCP

OpenClaw can manage MCP servers, and the MCP protocol is useful for tool
discovery. But a compliant MCP server adds a second protocol and session model.
The current milestone need is an HTTP agent with an API key.

Prevention: defer MCP implementation. At most, document that Bok's REST API can
be wrapped by a future MCP adapter after onboarding is stable.

### Exposing Sensitive State Through Onboarding

Onboarding should not leak source filenames, pending work, company data,
corrections, or secrets to unauthenticated callers.

Prevention: keep public onboarding limited to static connection metadata and
guardrails, or require auth if any company-specific content is returned.

### Creating a Separate Agent Bookkeeping Path

The backend must remain the formal constraint enforcer. A new onboarding route
should not bypass `LedgerService`, intake traceability, bank transaction reuse
guards, period locking, or correction semantics.

Prevention: onboarding should point to existing posting endpoints, not introduce
new posting logic.

### Ambiguous "Start Bookkeeping" Instructions

If docs only say "connect your agent to the API", owners and agents still have
to infer the workflow.

Prevention: provide explicit startup checks, first agent prompt, endpoint order,
and expected success/failure behavior.

### LAN URL Confusion

The frontend is normally reached at port 3000 while backend health is on port
8000 in local verification. Browser API calls may proxy through `/api`, while
external agents usually need the backend URL.

Prevention: docs should distinguish:

- Frontend URL for humans: `http://SERVER:3000`
- Backend/API URL for agents on LAN: `http://SERVER:8000`
- Optional public deployment URL if configured separately

## Phase Placement

- API discovery/auth truthfulness should be early, before docs.
- Documentation should follow once endpoint behavior is verified.
- MCP should remain outside the v1.2 roadmap unless explicitly re-scoped.
