# Requirements: Bok

**Defined:** 2026-06-04
**Milestone:** v1.2 Agent Onboarding
**Core Value:** The system should let a small Swedish company keep compliant books with minimal manual interaction by giving an agent enough source material, history, and correction feedback to post accurate vouchers.

## v1.2 Requirements

### Agent Onboarding

- [x] **ONBD-01**: Agent can call a stable instruction entrypoint at `/api/v1/agent-instructions/entrypoint`.
- [x] **ONBD-02**: Agent can discover Bok service identity, API version, docs URLs, schema URL, health URL, and authenticated ping URL.
- [x] **ONBD-03**: Agent can discover the supported bookkeeping startup workflow in ordered steps.
- [x] **ONBD-04**: Agent onboarding communicates Bok guardrails: immutable posted vouchers, B-series corrections, source traceability, bank/voucher input separation, and backend validation boundaries.

### Agent Authentication

- [ ] **AUTH-01**: Deployment docs and the instruction entrypoint explain `Authorization: Bearer <BOKFOERING_API_KEY>` as the supported v1.2 agent credential.
- [ ] **AUTH-02**: Existing placeholder API-key lifecycle endpoints are not presented as production key management unless made truthful and persistent.

### Agent API Coherence

- [ ] **API-01**: Agent ping returns current service, version, and authenticated actor data suitable for deployment verification.
- [ ] **API-02**: Agent-facing schema and tool discovery points to truthful current endpoints rather than stale hand-written placeholder data.
- [x] **API-03**: Agent startup flow links to existing instructions, pending intake, direct voucher posting, failed-processing, correction-history, and voucher source-context endpoints.

### Deployment Documentation

- [ ] **DOCS-01**: `DEPLOYMENT.md` includes a post-deploy OpenClaw/HTTP-agent setup section.
- [ ] **DOCS-02**: Deployment docs distinguish human frontend URL from backend API URL for agents on LAN.
- [ ] **DOCS-03**: Deployment docs include concrete `curl` checks for health and authenticated agent ping.
- [ ] **DOCS-04**: Deployment docs include a first agent prompt or instruction that tells OpenClaw how to begin bookkeeping in Bok.

### Verification

- [x] **VER-01**: Backend tests verify instruction entrypoint response shape, public-safe content, auth guidance, and ping behavior.
- [ ] **VER-02**: Documentation examples are checked against actual route paths and auth behavior.

## Future Requirements

### MCP

- **MCP-01**: Bok can expose selected agent workflow operations through an MCP adapter.

### Agent Keys

- **KEYS-01**: Bok supports persistent, revocable per-agent API keys with audit metadata.

### Idempotency

- **IDEM-01**: Agent posting supports durable idempotency keys for retry-safe bookkeeping operations.

## Out of Scope

| Feature | Reason |
|---------|--------|
| MCP server implementation | Defer until HTTP onboarding and instruction entrypoint are stable. |
| Persistent API-key management | Existing key endpoints are placeholder-like; durable key lifecycle is separate scope unless explicitly re-scoped. |
| Pre-posting approval workflow | Conflicts with Bok's automation-first direction. |
| Separate agent bookkeeping engine | The agent decides bookkeeping treatment, but Bok backend must continue enforcing formal constraints through existing services. |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| ONBD-01 | Phase 6 | Complete |
| ONBD-02 | Phase 6 | Complete |
| ONBD-03 | Phase 6 | Complete |
| ONBD-04 | Phase 6 | Complete |
| AUTH-01 | Phase 7 | Pending |
| AUTH-02 | Phase 6 | Pending |
| API-01 | Phase 6 | Pending |
| API-02 | Phase 6 | Pending |
| API-03 | Phase 6 | Complete |
| DOCS-01 | Phase 7 | Pending |
| DOCS-02 | Phase 7 | Pending |
| DOCS-03 | Phase 7 | Pending |
| DOCS-04 | Phase 7 | Pending |
| VER-01 | Phase 6 | Complete |
| VER-02 | Phase 7 | Pending |

**Coverage:**
- v1.2 requirements: 15 total
- Mapped to phases: 15
- Unmapped: 0

---
*Requirements defined: 2026-06-04*
*Last updated: 2026-06-04 after v1.2 roadmap creation*
