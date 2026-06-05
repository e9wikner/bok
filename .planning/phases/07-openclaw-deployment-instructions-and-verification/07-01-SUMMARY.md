---
phase: 07-openclaw-deployment-instructions-and-verification
plan: 07-01
subsystem: docs
tags: [deployment, openclaw, agent, documentation, bearer-auth]

requires:
  - phase: 06-agent-instruction-entrypoint-and-api-discovery
    provides: Public agent entrypoint and ping routes

provides:
  - Owner-facing LAN-first OpenClaw/HTTP-agent setup checklist in DEPLOYMENT.md
  - Shell-variable-based curl verification commands for health, entrypoint, and authenticated ping
  - Setup-only starter instruction that delegates to the entrypoint and asks owner before bookkeeping
  - Public HTTPS URL separation note for agent vs human
  - Agent-specific troubleshooting for auth, wrong port, and Docker-internal URL confusion

affects:
  - Phase 7 verification tests (07-02)
  - Future deployment doc updates

tech-stack:
  added: []
  patterns:
    - "Swedish LAN-first deployment docs with command-focused verification"
    - "Shell variable placeholders for secrets in documentation examples"

key-files:
  created: []
  modified:
    - DEPLOYMENT.md - Added OpenClaw/HTTP-agent setup section after first login

key-decisions:
  - "LAN-first agent setup with BOK_API_URL and API_KEY shell variables avoids inline secrets"
  - "First agent instruction is setup-only: verifies access, reports readiness, asks owner before bookkeeping"
  - "Agent-specific troubleshooting lives in deployment docs rather than inline response snippets"

patterns-established:
  - "Deployment docs: separate human frontend URL from agent backend URL clearly"
  - "Deployment docs: warn that Docker-internal BACKEND_URL must not be given to external agents"

requirements-completed: [AUTH-01, DOCS-01, DOCS-02, DOCS-03, DOCS-04]

duration: 15min
completed: 2026-06-05
---

# Phase 7 Plan 01: OpenClaw Deployment Instructions Summary

**Owner-facing LAN-first OpenClaw/HTTP-agent setup checklist with shell-variable verification commands, setup-only starter prompt, and agent-specific troubleshooting in DEPLOYMENT.md**

## Performance

- **Duration:** 15min
- **Started:** 2026-06-05T11:30:00Z
- **Completed:** 2026-06-05T11:45:00Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments
- Added post-login `### 10. Koppla OpenClaw eller annan HTTP-agent` section to DEPLOYMENT.md
- Documented frontend/backend URL separation (port 3000 vs 8000) and Docker-internal URL warning
- Included command-focused curl checks using `BOK_API_URL` and `API_KEY` shell variables
- Added setup-only starter instruction that delegates to entrypoint and asks owner before bookkeeping
- Added public HTTPS note distinguishing `https://${APP_DOMAIN}` for humans and `https://${API_DOMAIN}` for agents
- Added troubleshooting for 401 auth failures, wrong port/base URL, and Docker-internal URL confusion

## Task Commits

Each task was committed atomically:

1. **Task 1: Add post-login OpenClaw setup checklist** - `27da703` (docs)
2. **Task 2: Add setup-only starter prompt and agent troubleshooting** - `4628e8a` (docs)

**Plan metadata:** `4628e8a` (docs: complete plan)

## Files Created/Modified
- `DEPLOYMENT.md` - Added OpenClaw/HTTP-agent setup section, public HTTPS note, and agent troubleshooting

## Decisions Made
- Followed existing Swedish, pragmatic, LAN-first documentation tone
- Used shell variables (`BOK_API_URL`, `API_KEY`) to avoid inline secret repetition
- Kept setup examples command-only; placed failure explanations in troubleshooting
- Starter instruction explicitly constrained to verification only (no pending intake processing)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- DEPLOYMENT.md content is stable and ready for deterministic verification tests in 07-02
- All Phase 7 documentation requirements (AUTH-01, DOCS-01-04) are addressed

---
*Phase: 07-openclaw-deployment-instructions-and-verification*
*Completed: 2026-06-05*
