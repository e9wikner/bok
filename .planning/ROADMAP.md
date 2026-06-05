# Roadmap: Bok

## Milestones

- ✅ **v1.0 Intake Automation** — Phases 1-3 (shipped 2026-05-18). Full archive: [v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 Clear Instructions for Deployment** — Phases 4-5 (shipped 2026-06-04). Full archive: [v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md)
- ◆ **v1.2 Agent Onboarding** — Phases 6-7 (planned 2026-06-04).

## v1.2 Agent Onboarding

**Goal:** Make a deployed Bok instance understandable and connectable for an
OpenClaw-style HTTP agent so it can begin bookkeeping through the existing
agent API.

### Phase 6: Agent Instruction Entrypoint and API Discovery

**Goal:** Provide a stable agent startup contract at
`/api/v1/agent-instructions/entrypoint` and make agent-facing discovery/auth
behavior truthful.

**Requirements:** ONBD-01, ONBD-02, ONBD-03, ONBD-04, AUTH-02, API-01, API-02,
API-03, VER-01

**Success criteria:**
1. An HTTP agent can call `/api/v1/agent-instructions/entrypoint` and receive
   service identity, auth guidance, docs/schema URLs, ping URL, and ordered
   bookkeeping workflow steps.
2. The entrypoint response names the existing agent endpoints needed for
   instructions, pending intake, direct voucher posting, failed-processing,
   correction history, and voucher source context.
3. Agent guardrails are included without exposing secrets or company-specific
   pending work to unauthenticated callers.
4. Agent ping returns dynamic service/version/auth data suitable for deployment
   verification.
5. Placeholder agent key/schema/tool endpoints are either made truthful or
   excluded from the supported startup path.
6. Backend tests cover the entrypoint response contract and ping behavior.

### Phase 7: OpenClaw Deployment Instructions and Verification ✅

**Goal:** Document and verify the post-deploy OpenClaw/HTTP-agent setup path so
an owner can connect an external agent without reverse engineering Bok.

**Requirements:** AUTH-01, DOCS-01, DOCS-02, DOCS-03, DOCS-04, VER-02

**Completed:** 2026-06-05

**Success criteria:**
1. ✅ `DEPLOYMENT.md` includes a post-deploy OpenClaw/HTTP-agent setup section.
2. ✅ The docs distinguish the human frontend URL from the backend API URL used by
   agents on LAN.
3. ✅ The docs include concrete `curl` commands for health and authenticated agent
   ping checks.
4. ✅ The docs include a first agent prompt or instruction that tells OpenClaw how
   to begin bookkeeping in Bok through the instruction entrypoint.
5. ✅ Documentation examples are checked against actual route paths and auth
   behavior.

## Coverage

| Requirement | Phase |
|-------------|-------|
| ONBD-01 | Phase 6 |
| ONBD-02 | Phase 6 |
| ONBD-03 | Phase 6 |
| ONBD-04 | Phase 6 |
| AUTH-01 | Phase 7 |
| AUTH-02 | Phase 6 |
| API-01 | Phase 6 |
| API-02 | Phase 6 |
| API-03 | Phase 6 |
| DOCS-01 | Phase 7 |
| DOCS-02 | Phase 7 |
| DOCS-03 | Phase 7 |
| DOCS-04 | Phase 7 |
| VER-01 | Phase 6 |
| VER-02 | Phase 7 |

**Coverage:** 15/15 requirements mapped.
