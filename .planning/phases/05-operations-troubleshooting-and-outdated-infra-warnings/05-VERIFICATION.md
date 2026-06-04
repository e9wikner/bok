---
phase: 05-operations-troubleshooting-and-outdated-infra-warnings
status: passed
verified: 2026-06-04
plans_verified: 3
requirements_verified: [OPS-01, OPS-02, OPS-03, OPS-04, DOCS-04]
human_verification: []
gaps: []
---

# Phase 05 Verification: Operations, Troubleshooting, and Outdated Infra Warnings

## Verdict

Status: passed

Phase 05 achieved its goal: the canonical deployment guide now covers safe updates,
backup/restore, rollback, troubleshooting, and support diagnostics while keeping
LAN/local Docker as the default owner path and marking Terraform/Hetzner as legacy-only.

## Automated Checks

### DEPLOYMENT.md

Passed:

- The update flow starts with backup confirmation and uses `git status`, `git pull`, rebuild, and verification.
- The guide explicitly warns against `docker compose down -v`, deleting Docker volumes, and removing `bokfoering-data`.
- Backup and restore instructions identify `/app/data` in `bokfoering-data` as the protected state and use `./backups` as the local archive directory.
- Restore instructions warn that current bookkeeping data is replaced and verify backend/frontend health after restart.
- Rollback instructions use `git log --oneline -n 10`, `git checkout <COMMIT_SHA>`, rebuild, verification, and later return to `main`.
- Troubleshooting covers container status, backend health, frontend/login health, env-file problems, placeholder secrets, logs, and optional public-domain DNS/HTTPS checks.
- Support diagnostics include Docker versions, current Git commit, logs, health checks, and a safe placeholder scan without asking users to paste full `.env.production`.

Commands run:

```bash
rg -n "Uppdatera|git status|git pull|docker compose --env-file \.env\.production -f docker-compose\.local\.yml up -d --build|curl -fsS http://localhost:8000/health|git bundle|Rollback|git log --oneline -n 10|git checkout <COMMIT_SHA>|git checkout main|down -v|bokfoering-data|volym|bokföringsdata" DEPLOYMENT.md
rg -n "Säkerhetskop|Återställ|bokfoering-data|/app/data|backups|offen/docker-volume-backup" DEPLOYMENT.md
rg -n "Felsökning|diagnostik|logs --tail=100|NEXT_PUBLIC_API_URL|BACKEND_URL=http://api:8000|APP_DOMAIN|API_DOMAIN|LETSENCRYPT_EMAIL|docker --version|git rev-parse --short HEAD" DEPLOYMENT.md
```

### .env.production.example

Passed:

- Backup/S3 settings remain optional.
- The file now states that off-site backup variables should stay empty unless validated separately.
- The milestone does not present S3-compatible settings as a validated backup path.

Command run:

```bash
rg -n "AWS_S3_BUCKET_NAME|AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|AWS_S3_ENDPOINT|Optional backup" .env.production.example
```

### README.md

Passed:

- README routes operations work to `DEPLOYMENT.md`.
- README stays short and does not create a competing operations guide.
- README now names updates, backup, restore, rollback, and troubleshooting as belonging to `DEPLOYMENT.md`.

Command run:

```bash
rg -n "DEPLOYMENT.md|uppdater|säkerhetskop|återställ|rollback|felsök" README.md
```

### terraform/README.md

Passed:

- The file starts with an outdated/excluded warning before the previous quick start.
- The warning says the Terraform/Hetzner path is not validated in v1.1.
- The warning points owners to `../DEPLOYMENT.md`.
- The milestone does not re-position Terraform as the recommended deployment route.

Commands run:

```bash
sed -n '1,20p' terraform/README.md
rg -n "outdated|not validated|inte validerad|excluded|legacy|DEPLOYMENT.md" terraform/README.md
```

## Requirement Traceability

All Phase 05 requirements are accounted for and satisfied by documentation updates:

- OPS-01
- OPS-02
- OPS-03
- OPS-04
- DOCS-04

## Gates

- Code review gate: skipped because Phase 05 changed docs and config examples only.
- Regression gate: skipped because no application code or runtime behavior changed.
- Schema drift gate: passed, no schema or migration files changed.

## Gaps

None.

## Human Verification

None required for this documentation-only phase.
