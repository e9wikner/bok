# Phase 5: Operations, Troubleshooting, and Outdated Infra Warnings - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-04
**Phase:** 5-operations-troubleshooting-and-outdated-infra-warnings
**Areas discussed:** Safe update and rollback flow

---

## Gray Area Selection

| Option | Description | Selected |
|--------|-------------|----------|
| Safe update and rollback flow | Decide whether updates should be Git-based only, how explicit rollback commands should be, and how bluntly to warn against `down -v`. | ✓ |
| Backup and restore model | Decide whether docs should emphasize Docker volume backups, SQLite `.backup`, the existing `offen/docker-volume-backup` service, or a combination. | |
| Troubleshooting depth | Decide how much diagnostic guidance owners need: short symptom table, command checklist, or support-ready diagnostic bundle. | |
| Terraform/Hetzner warning style | Decide whether outdated infra docs get a top-of-file warning only, a short legacy note, or stronger "do not use this path" treatment. | |
| Discuss all of them | Walk through all four decision areas. | |

**User's choice:** Safe update and rollback flow
**Notes:** User chose to discuss only this area and then write context.

---

## Safe Update and Rollback Flow

| Question | Option | Description | Selected |
|----------|--------|-------------|----------|
| How should normal updates be documented for the recommended LAN deployment path? | Git pull | Use `git pull`, rebuild, restart, then verify; this matches the Phase 04 deployment source path. | ✓ |
| How should normal updates be documented for the recommended LAN deployment path? | Bundle path | Document git bundle over SSH as the normal update route for local-repo deployments. | |
| How should normal updates be documented for the recommended LAN deployment path? | Both equal | Give GitHub pull and bundle updates equal weight, which is more complete but heavier for owners. | |
| How explicit should rollback be? | Previous Git commit | Show `git log`, `git checkout <commit>`, rebuild/restart, verify, and then return to the intended branch later. | ✓ |
| How explicit should rollback be? | Tag/release only | Tell owners to roll back only to tagged releases, cleaner but may not fit the repo's current release habits. | |
| How explicit should rollback be? | Minimal warning | Explain rollback conceptually and leave exact commands to support/developer help. | |
| What should the docs tell owners to do before every update? | Backup first | Always create or confirm a backup before pulling and rebuilding. | ✓ |
| What should the docs tell owners to do before every update? | Verify only | Run health checks before updating, but backup instructions live separately. | |
| What should the docs tell owners to do before every update? | Only for risky updates | Require backup before major changes, but not every small pull. | |
| How blunt should the destructive-command warning be? | Very blunt | Repeat that `docker compose down -v`, deleting Docker volumes, or removing `bokfoering-data` can delete bookkeeping data. | ✓ |
| How blunt should the destructive-command warning be? | One warning only | Mention it once in the update section to avoid noisy docs. | |
| How blunt should the destructive-command warning be? | Command allow/deny list | Show safe commands and dangerous commands side by side. | |

**User's choice:** Git pull updates, previous-commit rollback, backup before
every update, and very blunt destructive-command warnings.
**Notes:** These decisions apply primarily to the recommended LAN deployment
path. Bundle-over-SSH remains secondary/advanced from Phase 04.

---

## the agent's Discretion

- Exact section ordering, heading names, and table formatting.
- How much of the update/rollback flow to duplicate for the optional public
  HTTPS Compose path.
- Backup/restore, troubleshooting, and Terraform/Hetzner warning details beyond
  the locked roadmap requirements and carried-forward Phase 4 decisions.

## Deferred Ideas

None.
