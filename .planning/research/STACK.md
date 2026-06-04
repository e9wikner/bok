# Research: Stack Additions for v1.2 Agent Onboarding

**Date:** 2026-06-04
**Milestone:** v1.2 Agent Onboarding

## Question

What stack additions or changes are needed so an OpenClaw-style HTTP agent can
connect to a deployed Bok instance and start bookkeeping?

## Findings

### Keep FastAPI REST as the primary integration surface

Bok already runs FastAPI with automatic OpenAPI at `/openapi.json`, Swagger UI
at `/docs`, and ReDoc at `/redoc` (`api/main.py`). FastAPI's official docs
confirm the default OpenAPI schema location and configurable docs URLs:
https://fastapi.tiangolo.com/tutorial/metadata/#openapi-url

The existing `/api/v1/agent` router already exposes core agent operations:

- `POST /api/v1/agent/vouchers`
- `GET /api/v1/agent/intake/pending`
- `POST /api/v1/agent/intake/{source_id}/processing`
- `POST /api/v1/agent/intake/{source_id}/failed`
- `POST /api/v1/agent/test/ping`
- `GET /api/v1/agent/spec/openapi`
- `POST /api/v1/agent/spec/tools`

The gap is not framework support. The gap is a stable onboarding document/API
that tells an external agent which endpoints matter, how auth works, and what
order to call them in.

### Use Bearer auth with the existing static API key for v1.2

`api/deps.py` accepts `Authorization: Bearer <token>` where the token is either
`settings.api_key` (`BOKFOERING_API_KEY`) or a valid JWT. The v1.1 deployment
guide already tells users to generate `BOKFOERING_API_KEY`.

For v1.2, document the static API key as the supported agent credential. The
existing `/api/v1/agent/keys/*` endpoints are placeholder-like and should not
be presented as persistent production key management until implemented.

### Avoid MCP implementation in this milestone

OpenClaw has MCP support, but its official docs distinguish between OpenClaw as
an MCP server and OpenClaw as an MCP client registry:

- OpenClaw MCP docs: https://docs.openclaw.ai/cli/mcp
- OpenClaw MCP registry docs: https://github.com/openclaw/openclaw/blob/main/docs/cli/mcp.md

The current MCP spec uses Streamable HTTP and has session/header requirements:
https://modelcontextprotocol.io/specification/2025-06-18/basic/transports

Implementing a correct MCP server would add a second protocol, JSON-RPC
lifecycle handling, tool discovery semantics, and MCP session behavior. That is
larger than the immediate user need: OpenClaw can call HTTP APIs with an API
key.

## Recommended Stack Work

- Add a FastAPI router or route for `GET /api/v1/agent-onboarding`.
- Reuse existing Pydantic/FastAPI response models; no new dependency required.
- Return absolute or origin-relative URLs for health, OpenAPI, docs, ping,
  instructions, intake queue, voucher posting, corrections, and source-context.
- Keep authentication description explicit: `Authorization: Bearer
  <BOKFOERING_API_KEY>`.
- Update or replace `/api/v1/agent/spec/openapi` so it points to the real
  generated OpenAPI schema or returns a scoped agent schema derived from actual
  routes, not stale hand-written placeholder data.
- Keep MCP as documented future scope unless v1.2 chooses to publish only a
  "how to wrap Bok REST endpoints with an MCP adapter" note.

## Non-Goals

- Do not add a persistent API key database unless explicitly scoped.
- Do not implement MCP Streamable HTTP in v1.2.
- Do not create a separate bookkeeping decision engine in the backend.
