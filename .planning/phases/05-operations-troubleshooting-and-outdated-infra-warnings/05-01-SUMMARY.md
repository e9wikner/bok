---
phase: 05-operations-troubleshooting-and-outdated-infra-warnings
plan: 05-01
subsystem: docs
tags: [deployment, operations, updates, rollback]
requires: []
provides:
  - Safe LAN-first update checklist
  - Explicit destructive-command warnings
  - Rollback instructions to a previous commit
affects: [deployment, docs, operations]
tech-stack:
  added: []
  patterns: [owner-facing Swedish operations guide, LAN-first maintenance flow]
key-files:
  created: []
  modified: [DEPLOYMENT.md]
key-decisions:
  - "Normal owner updates stay on local Git checkout plus docker-compose.local.yml."
  - "Backup confirmation is the first step before every update."
  - "Rollback must rebuild from a prior commit without deleting Docker volumes."
patterns-established:
  - "Operational warnings should name docker compose down -v and bokfoering-data explicitly."
requirements-completed: [OPS-01, OPS-03]
duration: 1 session
completed: 2026-06-04
---

# Phase 05 Plan 01: Document Safe Updates and Rollback Summary

**Expanded `DEPLOYMENT.md` with a LAN-first update flow, concrete rollback steps, and blunt data-loss warnings around Docker volume deletion.**

## Performance

- **Duration:** 1 session
- **Completed:** 2026-06-04T20:05:54Z
- **Tasks:** 3
- **Files modified:** 1

## Accomplishments

- Added a normal LAN update checklist with `git status`, `git pull`, rebuild/restart, and health verification.
- Moved `git bundle` over SSH into an advanced secondary path instead of the default update route.
- Added rollback instructions using `git log --oneline -n 10`, `git checkout <COMMIT_SHA>`, rebuild, verification, and return to `main`.
- Repeated explicit warnings that `docker compose down -v`, deleting Docker volumes, or removing `bokfoering-data` can delete bookkeeping data.

## Task Commits

1. No git commit created in this execution context.

## Files Created/Modified

- `DEPLOYMENT.md` - Safe update, destructive-command warning, and rollback guidance.

## Decisions Made

- LAN/local Docker remains the default owner operations path.
- Rollback guidance keeps `.env.production` and Docker volumes intact.

## Deviations from Plan

None.

## Issues Encountered

None.

## User Setup Required

None.

## Next Phase Readiness

Ready for backup/restore documentation.

## Self-Check: PASSED

Plan verification `rg` checks passed.

---
*Phase: 05-operations-troubleshooting-and-outdated-infra-warnings*
*Completed: 2026-06-04*
