# Research: Feature Expectations for v1.2 Agent Onboarding

**Date:** 2026-06-04
**Milestone:** v1.2 Agent Onboarding

## Question

How should agent onboarding work for a deployed Bok instance?

## Table Stakes

### Discoverability

An agent can call one stable endpoint and learn:

- Service identity, version, and health URL.
- Auth method and header format.
- Canonical API base URL.
- Human docs URLs (`/docs`, `/redoc`, `DEPLOYMENT.md` guidance).
- Machine-readable schema URLs (`/openapi.json`, agent tool definitions if kept).
- Supported agent workflow steps.

### Connectivity Test

The onboarding response should direct the agent to a ping endpoint that proves
the API key works. Bok already has `POST /api/v1/agent/test/ping`; v1.2 should
make it part of the startup path and remove stale fixed timestamps if necessary.

### Workflow Instructions

The agent should be told a concrete startup order:

1. Verify health.
2. Verify auth with agent ping.
3. Read accounting instructions.
4. Read pending intake queue.
5. Inspect source files or bank input rows as needed.
6. Post vouchers through `POST /api/v1/agent/vouchers`.
7. Read correction history before future decisions.
8. Leave failures or warnings on intake items.

### Deployment Documentation

`DEPLOYMENT.md` should include a post-deploy "connect an agent" section with:

- Where to find the Bok base URL on LAN.
- Which secret to copy into the agent.
- A `curl` health check.
- A `curl` authenticated ping check.
- How to point an OpenClaw HTTP tool/API profile at Bok.
- The first prompt/instruction to give the agent.
- Security notes: keep the key in a password manager or agent secret store, do
  not paste it into public chats, rotate by changing `.env.production` and
  restarting.

### API Coherence

Existing placeholder endpoints should not be recommended if they mislead:

- `/api/v1/agent/keys/*` appears non-persistent.
- `/api/v1/agent/spec/openapi` is hand-written and incomplete.
- `/api/v1/agent/operations/idempotent/{operation_id}` is placeholder-like.

v1.2 should either revise these to be truthful or keep them out of onboarding.

## Differentiators

- An onboarding response that includes "bookkeeping guardrails": immutability,
  B-series corrections, backend validation boundaries, source traceability, and
  automation-first expectations.
- A compact agent startup prompt embedded in the onboarding payload and
  deployment docs.
- Explicit separation between voucher source intake and bank input intake.
- Clear correction-learning loop: corrections are not only audit data; the
  agent should read them before posting future similar vouchers.

## Anti-Features

- Pre-approval as default agent flow. This conflicts with Bok's automation-first
  product direction.
- Generic MCP work before the HTTP path is reliable.
- Telling users to use generated `/api/v1/agent/keys/*` secrets before those
  keys are persisted and enforced.
- Publishing broad unsafe tool advice that lets an agent call every backend
  endpoint without a documented bookkeeping workflow.
