---
status: complete
phase: 05-operations-troubleshooting-and-outdated-infra-warnings
source:
  - 05-01-SUMMARY.md
  - 05-02-SUMMARY.md
  - 05-03-SUMMARY.md
started: 2026-06-04T20:29:21Z
updated: 2026-06-04T20:29:21Z
updated: 2026-06-04T20:54:38Z
---

## Current Test

[testing complete]

## Tests

### 1. Safe LAN Update Guide
expected: In `DEPLOYMENT.md`, the normal LAN update path should be easy to follow in order: backup first, then `git status`, `git pull`, rebuild/restart with `docker compose --env-file .env.production -f docker-compose.local.yml up -d --build`, and health verification. It should also clearly warn that `docker compose down -v`, deleting Docker volumes, or removing `bokfoering-data` can delete bookkeeping data.
result: pass

### 2. Backup and Restore Instructions
expected: In `DEPLOYMENT.md`, backup and restore should clearly identify `/app/data` in `bokfoering-data` as the protected state, use `./backups` as the local archive directory, include concrete backup and restore commands, and warn that restore replaces current bookkeeping data.
result: pass

### 3. Troubleshooting and Support Diagnostics
expected: In `DEPLOYMENT.md`, troubleshooting should cover container status, backend health, frontend/login health, env-file or placeholder-secret problems, optional public DNS/HTTPS checks, and a diagnostics block that gathers useful output without telling the owner to paste the full `.env.production`.
result: pass

### 4. Canonical Routing and Outdated Terraform Warning
expected: `README.md` should point owners to `DEPLOYMENT.md` for updates, backup, restore, rollback, and troubleshooting, while `terraform/README.md` should begin with a clear warning that the Terraform/Hetzner path is outdated, not validated in v1.1, excluded from the recommended path, and kept only as legacy reference.
result: pass

## Summary

total: 4
passed: 4
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

<!-- none yet -->
