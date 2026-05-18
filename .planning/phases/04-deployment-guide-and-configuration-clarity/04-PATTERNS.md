# Phase 4 Pattern Map

**Created:** 2026-05-18
**Phase:** 04 - Deployment Guide and Configuration Clarity

## Files and Closest Analogs

| Target | Role | Closest analog / source | Notes |
|--------|------|-------------------------|-------|
| `DEPLOYMENT.md` | Canonical owner-facing deployment guide | Existing `DEPLOYMENT.md` plus `docker-compose.local.yml`, `docker-compose.prod.yml`, `.env.production.example` | Rewrite structure around the LAN path rather than adding another competing section. |
| `README.md` | Entry-point routing and quick start | Existing README quick start and documentation list | Remove stale status and broken LAN-doc link; keep quick deployment steps plus link to canonical guide. |
| `.env.production.example` | Copyable production env template | Existing `.env.production.example` and Compose files | Keep LAN defaults first; public-domain HTTPS variables remain optional and clearly separated. |

## Reusable Facts

- LAN Compose command: `docker compose --env-file .env.production -f docker-compose.local.yml up -d --build`
- LAN backend health: `curl -fsS http://localhost:8000/health`
- LAN frontend login check: `curl -fsSI http://localhost:3000/login`
- LAN frontend proxy health: `curl -fsS http://localhost:3000/health`
- Recommended LAN frontend URL: `http://SERVER_IP_OR_HOSTNAME:3000/login`
- Public-domain Compose command: `docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build`
- Required secrets: `BOKFOERING_API_KEY`, `JWT_SECRET`, `AUTH_PASSWORD`
- Unsafe fallback values exist in `docker-compose.local.yml`: `dev-key-change-in-production`, `admin`, `dev-jwt-secret-change-in-production`
- Same-origin frontend proxy depends on `NEXT_PUBLIC_API_URL=` and `BACKEND_URL=http://api:8000`

## Planning Notes

- `docs/local_network_deployment.md` is referenced by README but missing on disk.
- `DEPLOYMENT.md` currently duplicates Compose content and includes outdated broad infrastructure guidance.
- Terraform/Hetzner is out of scope for repair in Phase 4; do not present it as recommended.

