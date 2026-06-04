# Research Summary: v1.2 Agent Onboarding

**Date:** 2026-06-04
**Milestone:** v1.2 Agent Onboarding

## Bottom Line

Build REST onboarding first. Bok already has FastAPI, bearer auth, agent
instructions, intake queues, correction history, and direct voucher posting.
The missing product capability is a trustworthy startup contract and deployment
guide for an external HTTP agent.

MCP should be deferred. OpenClaw supports MCP, and MCP is a viable future adapter
shape, but implementing a compliant MCP server would add protocol and session
complexity that is not needed for the current OpenClaw HTTP/API-key path.

## Stack Additions

- Add `GET /api/v1/agent-onboarding`.
- Reuse FastAPI/Pydantic; no new dependency is required.
- Use `Authorization: Bearer <BOKFOERING_API_KEY>` as the documented v1.2 agent
  credential.
- Use `/openapi.json` as the canonical machine-readable schema.
- Treat `/api/v1/agent/spec/openapi`, `/api/v1/agent/spec/tools`, and
  `/api/v1/agent/keys/*` as endpoints needing truthfulness review before docs
  recommend them.

## Feature Table Stakes

- Agent can discover base URLs, auth header format, health/ping checks, docs,
  schema, and the supported bookkeeping workflow.
- Owner can follow `DEPLOYMENT.md` after deploying to configure an OpenClaw-style
  HTTP agent.
- Agent startup order is explicit: health, ping, instructions, pending intake,
  posting, correction history, failure recording.
- Docs distinguish human frontend URL from agent backend API URL.
- Onboarding communicates Bok guardrails: immutable posted vouchers, B-series
  corrections, source traceability, bank/voucher input separation, and backend
  validation boundaries.

## Watch Out For

- Do not expose secrets or company-specific pending work through unauthenticated
  onboarding.
- Do not tell users to rely on placeholder persistent key endpoints.
- Do not point agents to stale hand-written OpenAPI data as the source of truth.
- Do not implement MCP before the HTTP onboarding path is stable.
- Do not create a separate posting path outside `LedgerService` and existing
  intake/bank traceability services.

## Sources

- FastAPI metadata and OpenAPI docs URL behavior:
  https://fastapi.tiangolo.com/tutorial/metadata/
- OpenClaw MCP docs:
  https://docs.openclaw.ai/cli/mcp
- OpenClaw ACP/MCP positioning:
  https://docs.openclaw.ai/tools/acp-agents
- MCP Streamable HTTP transport specification:
  https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
- Existing Bok code reviewed:
  `api/main.py`, `api/deps.py`, `api/routes/agent.py`,
  `api/routes/agent_instructions.py`, `api/routes/accounting_corrections.py`,
  `api/routes/vouchers.py`, `DEPLOYMENT.md`
