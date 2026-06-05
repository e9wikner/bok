# Phase 7: OpenClaw Deployment Instructions and Verification - Context

**Gathered:** 2026-06-05
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase documents and verifies the post-deploy setup path for connecting an
OpenClaw-style HTTP agent to a deployed Bok instance. The work is limited to
`DEPLOYMENT.md` guidance, copy-pasteable verification commands, a first
OpenClaw starter instruction, and checks that the documented examples match the
actual health, entrypoint, and authenticated ping behavior.

It does not add new backend agent capabilities, persistent API-key lifecycle,
MCP support, durable idempotency, or a new bookkeeping approval workflow.

</domain>

<decisions>
## Implementation Decisions

### Owner Setup Flow

- **D-01:** Add the OpenClaw setup section immediately after "Första inloggning"
  in `DEPLOYMENT.md`, so the owner deploys, verifies, logs in, then connects
  the agent.
- **D-02:** Present the OpenClaw setup as a short checklist, not a full
  walkthrough or appendix.
- **D-03:** Describe OpenClaw generically as an external HTTP agent that can make
  HTTP requests with bearer authentication. Do not rely on exact OpenClaw UI
  screens.
- **D-04:** Tell the owner to give OpenClaw the backend entrypoint URL plus the
  `BOKFOERING_API_KEY`. Do not replace the entrypoint with a long pasted prompt.

### URL Guidance

- **D-05:** For LAN deployment, teach `http://SERVER_IP_OR_HOSTNAME:8000` as the
  backend API base URL for OpenClaw.
- **D-06:** Clearly distinguish the human frontend URL
  `http://SERVER_IP_OR_HOSTNAME:3000` from the backend API URL used by agents.
- **D-07:** Add a brief separate note for optional public HTTPS: OpenClaw uses
  `https://${API_DOMAIN}` while humans use `https://${APP_DOMAIN}`.
- **D-08:** Explicitly warn that `BACKEND_URL=http://api:8000` is Docker-internal
  for the frontend container and must not be given to OpenClaw outside Docker.
- **D-09:** Show entrypoint examples using environment-variable style, such as an
  API base URL variable followed by the `/api/v1/agent-instructions/entrypoint`
  path.

### First OpenClaw Instruction

- **D-10:** The starter instruction should delegate to the entrypoint as the
  authoritative startup contract.
- **D-11:** The first OpenClaw prompt should verify setup only. It should not
  start bookkeeping or process pending intake.
- **D-12:** The first prompt should include a next-step hint: after verifying
  access, OpenClaw should ask the owner before starting the first bookkeeping
  run.
- **D-13:** The first prompt should make OpenClaw report readiness plus the exact
  next owner prompt/action needed to start bookkeeping.

### Verification Examples

- **D-14:** Documented verification examples should cover backend health, the
  public agent entrypoint, and authenticated agent ping.
- **D-15:** Curl examples should use shell variables for the API base URL and
  API key, avoiding repeated inline secrets.
- **D-16:** Setup docs should not include expected response snippets; keep the
  setup checklist command-focused.
- **D-17:** Agent-specific failure handling belongs in the troubleshooting
  section rather than inline response snippets. Cover likely failures there,
  including auth failure, wrong base URL/port, and Docker-internal URL confusion.

### the agent's Discretion

The planner may choose exact heading text, Swedish phrasing, command variable
names, and test organization, provided the decisions above are preserved and the
examples are verified against the actual route paths and auth behavior.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Planning Scope

- `.planning/ROADMAP.md` - Phase 7 goal, requirements, and success criteria.
- `.planning/REQUIREMENTS.md` - v1.2 requirements mapped to Phase 7, especially
  AUTH-01, DOCS-01 through DOCS-04, and VER-02.
- `.planning/PROJECT.md` - deployment scope, Docker-first path, HTTP-agent
  priority, and deferred MCP/key lifecycle constraints.
- `.planning/phases/06-agent-instruction-entrypoint-and-api-discovery/06-CONTEXT.md`
  - locked Phase 6 decisions about the public entrypoint, bearer auth, startup
  sequence, and unsupported future features.

### Documentation Targets

- `DEPLOYMENT.md` - canonical deployment guide to update with post-login
  OpenClaw setup, verification commands, public HTTPS note, and troubleshooting.
- `README.md` - existing high-level agent integration references; use for
  consistency and check for any contradictory setup wording.

### Existing Agent API Behavior

- `api/routes/agent_instructions.py` - public entrypoint route and startup
  payload the docs must point OpenClaw at.
- `api/deps.py` - bearer API-key and JWT auth behavior used by protected agent
  endpoints.
- `api/main.py` - FastAPI docs/schema URLs and health route registration.
- `tests/test_agent_entrypoint.py` - existing coverage for entrypoint shape,
  relative paths, public safety, auth guidance, and ping behavior.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `DEPLOYMENT.md`: already uses Swedish owner-facing operational guidance,
  numbered LAN checklist sections, command blocks, and troubleshooting sections.
  Phase 7 should follow that tone and structure.
- `README.md`: already briefly says agent integration uses
  `BOKFOERING_API_KEY` and the entrypoint; keep deployment docs consistent with
  this.
- `tests/test_agent_entrypoint.py`: already verifies the entrypoint and ping
  contract. Phase 7 can add focused documentation/example checks nearby or in a
  documentation-oriented test file.

### Established Patterns

- Documentation is Swedish, pragmatic, and LAN-first. Public domain/HTTPS is
  treated as optional and separate from the recommended LAN path.
- Deployment commands currently use copy-pasteable shell blocks and avoid broad
  abstractions. New OpenClaw commands should match that style.
- Backend tests use `pytest` and FastAPI/httpx clients with shared fixtures in
  `tests/`.

### Integration Points

- Public entrypoint: `GET /api/v1/agent-instructions/entrypoint`.
- Auth check: `POST /api/v1/agent/test/ping` with
  `Authorization: Bearer <BOKFOERING_API_KEY>`.
- Health check: the deployment guide currently uses
  `curl -fsS http://localhost:8000/health`; the entrypoint payload also links
  `/api/v1/health`, so docs/tests should verify whichever health path is
  documented.
- LAN frontend URL for humans: `http://SERVER_IP_OR_HOSTNAME:3000/login`.
- LAN backend URL for OpenClaw: `http://SERVER_IP_OR_HOSTNAME:8000`.

</code_context>

<specifics>
## Specific Ideas

- Place the new section after first login with a heading along the lines of
  "Koppla OpenClaw eller annan HTTP-agent".
- Use shell variables for examples, e.g. `BOK_API_URL=...` and `API_KEY=...`,
  then build the entrypoint and curl commands from those variables.
- The first OpenClaw prompt should verify the connection, report readiness, and
  provide the owner with the next prompt/action to start bookkeeping. It should
  not process pending work during the initial verification prompt.
- Keep setup examples command-only; put agent-specific failure explanations in
  troubleshooting.

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within phase scope.

</deferred>

---

*Phase: 7-OpenClaw Deployment Instructions and Verification*
*Context gathered: 2026-06-05*
