# Phase 5: Operations, Troubleshooting, and Outdated Infra Warnings - Research

**Researched:** 2026-06-04
**Status:** Ready for planning

## Research Complete

Phase 5 is documentation-only operational work over the existing Docker deployment
surface. No backend, frontend, database schema, or runtime behavior changes are
needed to satisfy the mapped requirements.

## Scope Anchors

- Phase goal: give owners enough operational instructions to update, back up,
  restore, roll back, and troubleshoot deployments without risking bookkeeping
  data.
- Requirement IDs: OPS-01, OPS-02, OPS-03, OPS-04, DOCS-04.
- Canonical owner guide: `DEPLOYMENT.md`.
- Recommended deployment path: LAN/local Docker with `docker-compose.local.yml`.
- Optional path: public-domain HTTPS with `docker-compose.prod.yml`.
- Outdated infrastructure path: Terraform/Hetzner docs are excluded from the
  recommended route and should be marked outdated, not repaired.

## Existing Deployment Surface

### `DEPLOYMENT.md`

Current guide is LAN-first and Swedish. It already covers:

- prerequisites,
- clone and first startup,
- `.env.production`,
- LAN frontend/backend defaults,
- `docker compose --env-file .env.production -f docker-compose.local.yml up -d --build`,
- container status,
- backend/frontend health checks,
- first login,
- advanced git bundle over SSH,
- optional public-domain HTTPS,
- a short troubleshooting section.

Phase 5 should extend this guide after first deployment rather than create a
competing operations document.

### `docker-compose.local.yml`

LAN deployment has:

- `api` and `frontend` services,
- `bokfoering-data:/app/data` as the persistent data volume,
- backend healthcheck at `http://localhost:8000/health`,
- frontend depends on healthy API,
- frontend build arg `NEXT_PUBLIC_API_URL` defaulting empty,
- `BACKEND_URL=http://api:8000`.

The local compose file does not mount `./backups` or define the backup service.
Owner docs should therefore document explicit backup commands for LAN, not imply
the public-domain backup sidecar exists in the LAN path.

### `docker-compose.prod.yml`

Optional public-domain deployment has:

- Traefik with ports 80/443 and Let's Encrypt storage under `./letsencrypt`,
- API with `bokfoering-data:/app/data`, `./backups:/app/backups`, and
  `./logs:/app/logs`,
- frontend behind Traefik,
- `backup` service using `offen/docker-volume-backup:latest`,
- backup service reads `bokfoering-data:/backup/data:ro` and archives to
  `./backups`,
- optional S3-compatible variables are commented in compose and env example.

Docs should describe this as existing optional public-domain behavior. It should
not be silently imported into the LAN path unless the plan explicitly adds or
documents a LAN-compatible command.

### `.env.production.example`

The env example already groups required secrets, LAN defaults, optional public
domain settings, and optional backup/S3 settings. Phase 5 may add small comments
if needed, but the main operational content belongs in `DEPLOYMENT.md`.

### `README.md`

README already routes owner deployment to `DEPLOYMENT.md` and should remain a
short entry point. Phase 5 should avoid adding a second operational manual here.

### `terraform/README.md`

The Terraform guide still presents Hetzner/Terraform as an active deployment
path with prerequisites, quick start, deployment steps, costs, troubleshooting,
and migration commands. Phase 5 DOCS-04 requires a prominent outdated/excluded
warning. This file should not be repaired or expanded into a validated path.

## Existing Helper Scripts

### `deploy.sh`

`deploy.sh` contains useful operational command ideas:

- health checks for API/frontend,
- `git pull origin main` update flow,
- backup with SQLite access and archive creation,
- restore with a confirmation prompt,
- logs/status helpers.

However, it is oriented around `docker-compose.prod.yml`, public HTTPS defaults,
and script-driven deployment. It should be treated as a source of command
patterns, not as the recommended owner workflow. The backup function also appears
to contain a stray `fi` after the archive block, so the docs should not tell
owners to rely on this script without verification.

### `update.sh`

`update.sh` is closer to LAN updates:

- `git fetch --quiet origin`,
- compare `HEAD` to `origin/main`,
- `git pull --ff-only`,
- rebuild with `docker compose -f "$COMPOSE_FILE" up -d --build`.

Docs can reuse the concept, but Phase 5 context locked the owner-facing normal
flow as explicit `git pull` plus rebuild/restart plus verification, not an
automated cron workflow.

### `deploy-local.sh`

`deploy-local.sh` runs `docker compose ... down --remove-orphans` and then
`up -d --build`. This is not `down -v`, but Phase 5 should still avoid routing
owners to scripts that obscure the "do not remove volumes" warning.

## Operational Guidance Needed

### Updates and Rollback

Plan should document:

- backup or confirm backup before every update,
- `git status`,
- `git pull --ff-only` or `git pull`,
- rebuild/restart with the correct Compose file,
- status and health checks after update,
- practical rollback to a previous commit with `git log --oneline`, `git checkout <commit>`, rebuild/restart, verify, then later return to `main`.

Repeated warning required:

- Do not use `docker compose down -v`.
- Do not delete Docker volumes.
- Do not remove `bokfoering-data`.

### Backup and Restore

Plan should cover:

- what data must be protected: SQLite database and local filesystem data under
  `/app/data` inside `bokfoering-data`,
- where local backup archives should live: `./backups` for owner-managed files,
- LAN manual backup commands that create a dated archive from the Docker volume,
- optional public-domain backup sidecar in `docker-compose.prod.yml`,
- restore command flow with explicit warning that restore replaces current
  bookkeeping data,
- verification after backup and restore: list archive, inspect archive contents,
  start services, run health checks, open login page.

Avoid presenting optional S3 placeholders as a validated off-site backup feature.

### Troubleshooting

Troubleshooting should be expanded from the current short section into an owner
checklist or symptom table covering:

- unhealthy containers,
- backend health failure,
- frontend/backend connection failure,
- missing `.env.production`,
- placeholder secrets,
- bad LAN `NEXT_PUBLIC_API_URL` / `BACKEND_URL`,
- DNS/HTTPS and Let's Encrypt prerequisites for public-domain path,
- logs with `docker compose ... logs --tail ...`,
- support-ready diagnostic output that avoids secrets.

Support output should include Docker version, Compose version, `git rev-parse --short HEAD`,
`docker compose ... ps`, selected health curls, and sanitized env checks. It
should not ask owners to paste full `.env.production`.

## Planning Recommendation

Use three plans:

1. Extend `DEPLOYMENT.md` with safe update and rollback flow.
2. Extend `DEPLOYMENT.md` with backup and restore operations.
3. Expand troubleshooting in `DEPLOYMENT.md`, keep `README.md` routing aligned,
   and mark `terraform/README.md` outdated/excluded.

This split keeps each plan small, maps cleanly to OPS/DOCS requirements, and
lets update/backup/troubleshooting work proceed with clear review commands.

## Validation Architecture

This phase is documentation-oriented. Verification should use source assertions
with `rg` and, where useful, shell parsing checks:

- `DEPLOYMENT.md` contains safe update commands and no normal-flow `down -v`.
- `DEPLOYMENT.md` contains backup and restore sections referencing
  `bokfoering-data`, `/app/data`, and `./backups`.
- `DEPLOYMENT.md` contains troubleshooting coverage for containers, health,
  frontend/backend connectivity, missing env vars, DNS/HTTPS, logs, and
  diagnostic output.
- `terraform/README.md` starts with a prominent outdated/excluded warning.
- README still routes owner deployment to `DEPLOYMENT.md`.

## RESEARCH COMPLETE
