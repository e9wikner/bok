# Phase 6: Agent Instruction Entrypoint and API Discovery - Research

**Date:** 2026-06-05
**Status:** Complete

## Research Question

What does the planner need to know to implement Phase 6 well?

## Phase Scope

Phase 6 adds a public-safe startup contract at
`GET /api/v1/agent-instructions/entrypoint`, removes misleading placeholder
agent routes, makes authenticated ping useful for deployment verification, and
updates technical README references that would otherwise point to removed or
unsupported behavior.

## Existing Architecture

- `api/routes/agent_instructions.py` already owns the
  `/api/v1/agent-instructions` namespace and is the right place for
  `/entrypoint`.
- `api/routes/agent.py` owns the operational agent endpoints. It contains both
  real behavior (`/vouchers`, `/intake/pending`, `/intake/{id}/processing`,
  `/intake/{id}/failed`, `/test/ping`) and placeholder behavior that Phase 6
  must remove (`/keys/*`, `/spec/*`, `/operations/idempotent/*`).
- `api/deps.py` verifies `Authorization: Bearer <token>` against
  `settings.api_key` or JWT and returns a generic actor through
  `get_current_actor`.
- `api/main.py` already exposes canonical FastAPI schema and docs URLs:
  `/openapi.json`, `/docs`, `/redoc`, plus `/api/v1/health`.

## Implementation Findings

### Entrypoint response should be static and public-safe

The entrypoint should not depend on `get_current_actor`, repositories, or
company state. It can use `settings.api_version`, route constants, and static
guardrails. This avoids leaking source filenames, correction data, pending work,
or secrets to unauthenticated callers.

Recommended response fields:

- `service`
- `version`
- `purpose`
- `auth`
- `links`
- `startup_sequence`
- `workflow_endpoints`
- `guardrails`
- `unsupported_features`
- `agent_start_instructions`

All endpoint references should be relative paths.

### Ping should be dynamic

`POST /api/v1/agent/test/ping` currently returns fixed version and timestamp
values. It should return current data, including:

- `status: "ok"`
- `service: "bokfoering-api"` or consistent configured service name
- `version: settings.api_version`
- `agent: actor`
- current UTC timestamp

This keeps deployment verification useful and removes hard-coded stale output.

### Placeholder routes should be removed, not deprecated

The user explicitly chose removal for:

- `/api/v1/agent/keys/create`
- `/api/v1/agent/keys`
- `/api/v1/agent/keys/{key_id}/revoke`
- `/api/v1/agent/spec/openapi`
- `/api/v1/agent/spec/tools`
- `/api/v1/agent/operations/idempotent/{operation_id}`

Removing these will also remove unused imports (`uuid`, `hashlib`) from
`api/routes/agent.py`.

### README cleanup belongs in this phase

`README.md` currently warns that `/api/v1/agent/keys/*` is not persistent. That
reference becomes stale when the routes are removed. The README agent endpoint
list should add the new entrypoint and remove or rewrite key-lifecycle language.

Broader deployment/OpenClaw docs remain Phase 7 scope.

## Testing Strategy

Add or extend backend tests around agent instructions and agent ping:

- `GET /api/v1/agent-instructions/entrypoint` returns `200` without auth.
- Entrypoint response contains relative paths only for workflow endpoints and
  links.
- Entrypoint response contains auth guidance for
  `Authorization: Bearer <BOKFOERING_API_KEY>`.
- Entrypoint response contains unsupported features for persistent API keys,
  generated tool schema discovery, and durable idempotency.
- Entrypoint does not include secrets or company-specific queue/correction data.
- `POST /api/v1/agent/test/ping` requires auth and returns dynamic version,
  actor, and timestamp fields.
- Removed placeholder routes no longer resolve successfully.

Existing test style uses FastAPI `TestClient` in
`tests/test_agent_instructions_separation.py`; that file is a good home for
entrypoint tests. Agent ping/removal tests can live in a new
`tests/test_agent_entrypoint.py` or adjacent agent workflow test file.

## Threat Model

### Threats

- Public entrypoint leaks company-sensitive state.
- Public entrypoint accidentally exposes the configured API key or token-like
  values.
- Agent follows stale placeholder endpoints and believes unsupported key,
  schema, or idempotency behavior exists.
- Authenticated ping reveals excessive internals.

### Mitigations

- Entrypoint is static/public-safe and does not query repositories.
- Entrypoint returns auth format only, never actual secret values.
- Placeholder routes are removed and unsupported features are explicitly listed.
- Ping returns only bounded service/version/actor/timestamp data.
- Tests assert no sensitive fields and validate route removal behavior.

## Planning Implications

The phase should be planned as three focused execution plans:

1. Entrypoint contract and tests.
2. Agent route cleanup and dynamic ping tests.
3. README cleanup plus final route/schema verification.

This keeps the public contract, route removal, and documentation cleanup
separable while still allowing the final plan to verify end-to-end behavior.

## RESEARCH COMPLETE
