---
phase: 05-operations-troubleshooting-and-outdated-infra-warnings
plan: 05-02
subsystem: docs
tags: [deployment, backup, restore]
requires: [05-01]
provides:
  - Backup scope explanation for bokfoering-data
  - Manual LAN backup and verification commands
  - Restore flow with explicit replacement warning
affects: [deployment, docs, configuration]
tech-stack:
  added: []
  patterns: [local volume archive backup, cautious restore messaging]
key-files:
  created: []
  modified: [DEPLOYMENT.md, .env.production.example]
key-decisions:
  - "The protected state is /app/data inside the bokfoering-data volume."
  - "LAN backup/restore remains the primary documented path."
  - "Optional S3 variables stay placeholders and are not presented as validated off-site backup."
patterns-established:
  - "Backup guidance should distinguish protected runtime data from Git checkout and env file."
requirements-completed: [OPS-02]
duration: 1 session
completed: 2026-06-04
---

# Phase 05 Plan 02: Document Backup and Restore Operations Summary

**Extended `DEPLOYMENT.md` with explicit backup scope, manual LAN backup commands, restore steps, and optional backup-sidecar context; aligned `.env.production.example` comments with that boundary.**

## Performance

- **Duration:** 1 session
- **Completed:** 2026-06-04T20:05:54Z
- **Tasks:** 4
- **Files modified:** 2

## Accomplishments

- Documented that `/app/data` in `bokfoering-data` is the protected bookkeeping state.
- Added concrete manual backup commands using a helper container, `mkdir -p backups`, `ls -lh backups/`, and archive listing verification.
- Added restore instructions that stop services without `-v`, restore into `bokfoering-data`, and verify backend/frontend health afterward.
- Clarified that `offen/docker-volume-backup` and S3-compatible variables are optional and not a validated off-site backup path in this milestone.

## Task Commits

1. No git commit created in this execution context.

## Files Created/Modified

- `DEPLOYMENT.md` - Backup/restore instructions and optional backup-sidecar note.
- `.env.production.example` - Optional backup/S3 comments clarified as non-validated placeholders.

## Decisions Made

- `./backups` is the owner-facing local archive directory.
- Restore messaging explicitly states that current bookkeeping data is replaced.

## Deviations from Plan

None.

## Issues Encountered

None.

## User Setup Required

None.

## Next Phase Readiness

Ready for troubleshooting and outdated-infrastructure warnings.

## Self-Check: PASSED

Plan verification `rg` checks passed.

---
*Phase: 05-operations-troubleshooting-and-outdated-infra-warnings*
*Completed: 2026-06-04*
