---
phase: 05-operations-troubleshooting-and-outdated-infra-warnings
plan: 05-03
subsystem: docs
tags: [deployment, troubleshooting, readme, terraform]
requires: [05-01, 05-02]
provides:
  - Expanded troubleshooting coverage
  - Support-ready diagnostics without secret disclosure
  - README routing to the canonical operations guide
  - Terraform/Hetzner outdated warning
affects: [deployment, docs, infrastructure]
tech-stack:
  added: []
  patterns: [symptom-based troubleshooting, legacy-doc warning banner]
key-files:
  created: []
  modified: [DEPLOYMENT.md, README.md, terraform/README.md]
key-decisions:
  - "Troubleshooting stays LAN-first and separates optional public-domain checks."
  - "Support diagnostics must avoid exposing full .env.production contents."
  - "Terraform/Hetzner stays as legacy reference only."
patterns-established:
  - "README should route operations tasks to DEPLOYMENT.md rather than duplicating commands."
requirements-completed: [OPS-04, DOCS-04]
duration: 1 session
completed: 2026-06-04
---

# Phase 05 Plan 03: Expand Troubleshooting and Mark Outdated Infrastructure Summary

**Expanded `DEPLOYMENT.md` troubleshooting and diagnostics, aligned README routing, and marked `terraform/README.md` as outdated and excluded from the recommended deployment path.**

## Performance

- **Duration:** 1 session
- **Completed:** 2026-06-04T20:05:54Z
- **Tasks:** 4
- **Files modified:** 3

## Accomplishments

- Replaced the short troubleshooting section with symptom-based guidance for container status, backend health, frontend/login health, missing env file, placeholders, and public DNS/HTTPS issues.
- Added a support diagnostics block with version, commit, logs, health checks, and a safe placeholder scan instead of copying `.env.production`.
- Updated README deployment references so they point to `DEPLOYMENT.md` for updates, backups, restore, rollback, and troubleshooting.
- Added a top-of-file warning that the Terraform/Hetzner path is outdated, not validated in v1.1, excluded from the recommended route, and kept only as legacy reference.

## Task Commits

1. No git commit created in this execution context.

## Files Created/Modified

- `DEPLOYMENT.md` - Troubleshooting and support diagnostics.
- `README.md` - Canonical routing to the operations guide.
- `terraform/README.md` - Outdated/excluded warning banner.

## Decisions Made

- Public-domain checks stay optional and separate from the LAN troubleshooting path.
- Terraform documentation is intentionally not repaired in this milestone.

## Deviations from Plan

None.

## Issues Encountered

None.

## User Setup Required

None.

## Next Phase Readiness

Phase 05 is ready for verification and milestone-level follow-up.

## Self-Check: PASSED

Plan verification `rg` checks passed.

---
*Phase: 05-operations-troubleshooting-and-outdated-infra-warnings*
*Completed: 2026-06-04*
