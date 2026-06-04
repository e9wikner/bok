# Phase 5: Pattern Map

**Mapped:** 2026-06-04

## Files and Roles

| File | Role | Closest Existing Pattern |
|------|------|--------------------------|
| `DEPLOYMENT.md` | Canonical owner-facing deployment and operations guide | Phase 04 LAN-first Swedish checklist |
| `README.md` | Short entry point that routes owners to the canonical guide | Phase 04 README deployment routing |
| `.env.production.example` | Optional comments for operational settings | Phase 04 env grouping and comments |
| `docker-compose.local.yml` | Source of truth for LAN service names, health checks, data volume | Existing Compose service definitions |
| `docker-compose.prod.yml` | Source of truth for optional HTTPS, backup sidecar, backups/logs mounts | Existing Compose service definitions |
| `terraform/README.md` | Outdated infrastructure guide requiring warning | Existing broad Terraform quick-start doc |

## Documentation Patterns to Reuse

- `DEPLOYMENT.md` uses Swedish explanatory text with literal commands, file
  paths, env vars, and URLs.
- The guide is structured as concrete ordered steps with short prose between
  command blocks.
- Warnings are direct, especially around unsafe secrets and data loss.
- LAN/local server comes before optional public-domain HTTPS.
- README should stay short and point to `DEPLOYMENT.md`, not duplicate the full
  guide.

## Command Patterns to Reuse Carefully

- LAN start/update base command:
  `docker compose --env-file .env.production -f docker-compose.local.yml up -d --build`
- LAN status:
  `docker compose --env-file .env.production -f docker-compose.local.yml ps`
- LAN logs:
  `docker compose --env-file .env.production -f docker-compose.local.yml logs --tail=100`
- API health:
  `curl -fsS http://localhost:8000/health`
- Frontend checks:
  `curl -fsSI http://localhost:3000/login` and `curl -fsS http://localhost:3000/health`
- Public path status/health should use `docker-compose.prod.yml` and HTTPS URLs
  with `${API_DOMAIN}` / `${APP_DOMAIN}`.

## Landmines

- Do not recommend `docker compose down -v`.
- Do not tell owners to delete `bokfoering-data`.
- Do not treat optional S3 variables as a validated off-site backup feature.
- Do not repair Terraform/Hetzner in this milestone.
- Do not ask owners to paste full `.env.production` into support output.
- Do not make older helper scripts the canonical owner path.
