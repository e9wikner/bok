---
status: complete
phase: 06-agent-instruction-entrypoint-and-api-discovery
source:
  - .planning/phases/06-agent-instruction-entrypoint-and-api-discovery/06-01-SUMMARY.md
  - .planning/phases/06-agent-instruction-entrypoint-and-api-discovery/06-02-SUMMARY.md
started: 2026-06-05T05:33:49Z
updated: 2026-06-05T07:16:17Z
---

## Current Test

[testing complete]

## Tests

### 1. Public Agent Entrypoint
expected: When the agent opens `/api/v1/agent-instructions/entrypoint` without credentials, the API returns a public-safe startup payload. It shows service/version, relative links for health/docs/redoc/openapi, bearer auth guidance, ordered startup steps, workflow endpoints, bookkeeping guardrails, unsupported future features, and no company-specific filenames, pending work, corrections, or secrets.
result: pass

### 2. Owner-to-Agent Startup Workflow
expected: The owner only needs to give OpenClaw the entrypoint URL. From that payload, the agent can see it should verify auth with `POST /api/v1/agent/test/ping`, then read accounting instructions, recent corrections, and pending intake before processing items one at a time.
result: pass

### 3. Authenticated Ping
expected: Calling `POST /api/v1/agent/test/ping` without bearer auth is rejected. Calling it with `Authorization: Bearer <BOKFOERING_API_KEY>` returns `status: ok`, `service: bokfoering-api`, the configured API version, `agent: api`, and a current timestamp.
result: pass

### 4. Removed Placeholder Routes
expected: Old placeholder routes for agent key lifecycle, hand-written spec/tool discovery, and durable idempotency no longer return fake success responses. The agent should use `/openapi.json` for schema discovery and the entrypoint's unsupported-features list for future-scope behavior.
result: pass

### 5. README Agent References
expected: The README tells the owner to use `BOKFOERING_API_KEY` and send `/api/v1/agent-instructions/entrypoint` to the agent. It no longer presents `/api/v1/agent/keys/*` as a current production key-management path.
result: pass

## Summary

total: 5
passed: 5
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none yet]
