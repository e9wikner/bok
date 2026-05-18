# Phase 4: Deployment Guide and Configuration Clarity - Research

**Researched:** 2026-05-18
**Phase:** 04 - Deployment Guide and Configuration Clarity
**Status:** Ready for planning

## Research Question

What do we need to know to plan Phase 4 well?

## Phase Scope Summary

Phase 4 is a documentation and configuration-alignment phase. It should make the existing Docker deployment path understandable for a non-expert owner from prerequisites through first login.

The phase should not repair infrastructure, add new deployment systems, or expand operational runbooks beyond first-deployment safety notes. Updates, backup, restore, rollback, deeper troubleshooting, and Terraform/Hetzner warnings are Phase 5 unless a minimal warning is required to prevent first-deployment confusion.

## Current State Findings

### README.md

- `README.md` currently starts with a developer-style `docker-compose up --build` quick start and `admin / admin` login credentials.
- It contains a stale phase-status block that claims older product phases and a different "Fas 5" are current.
- It routes LAN deployment users to `docs/local_network_deployment.md`, but that file does not exist in the repo.
- It also lists `DEPLOYMENT.md` as a broad guide covering on-premise, Hetzner, Terraform, monitoring, backup, and production Compose, which conflicts with the desired owner-facing first-deployment route.

### DEPLOYMENT.md

- `DEPLOYMENT.md` is currently a broad deployment guide for on-premise and Hetzner Cloud.
- The first main path is "Docker Deployment (On-Premise)", but it immediately mixes production-domain assumptions with instructions to create a `docker-compose.prod.yml` file even though the repo already has `docker-compose.prod.yml`.
- LAN deployment exists as a later section and is framed around a local repository bundle transfer workflow for a specific Home Assistant user/host.
- Public-domain HTTPS, Hetzner Cloud, Terraform, monitoring, backup, restore, troubleshooting, and maintenance all appear in the same guide, making the first deployment path hard to follow.
- Some operational warnings are already useful, especially the warning not to use `down -v` for normal deployments because it removes the SQLite data volume.

### .env.production.example

- The env example already includes the required backend secrets:
  - `BOKFOERING_API_KEY`
  - `JWT_SECRET`
  - `AUTH_USERNAME`
  - `AUTH_PASSWORD`
- It already sets the desired LAN default:
  - `NEXT_PUBLIC_API_URL=`
  - `BACKEND_URL=http://api:8000`
- Public-domain variables are present in the same file:
  - `APP_DOMAIN=app.localhost`
  - `API_DOMAIN=api.localhost`
  - `LETSENCRYPT_EMAIL=admin@example.com`
- The file should keep LAN defaults clear and move public-domain settings into an optional clearly labeled block, matching the deployment guide.

### docker-compose.local.yml

- This is the correct recommended LAN Compose file.
- It exposes:
  - backend on port `8000`
  - frontend on port `3000`
- It persists data in the `bokfoering-data` volume.
- It has unsafe fallback values for `BOKFOERING_API_KEY`, `AUTH_PASSWORD`, and `JWT_SECRET` if `.env.production` does not provide them.
- It builds frontend with `NEXT_PUBLIC_API_URL` defaulting to empty, which matches the same-origin proxy path.
- It hard-codes `BACKEND_URL` in frontend runtime environment to `http://api:8000`, matching the Compose service name.

### docker-compose.prod.yml

- This is the optional public-domain HTTPS path.
- It includes Traefik and expects:
  - `APP_DOMAIN`
  - `API_DOMAIN`
  - `LETSENCRYPT_EMAIL`
- It uses `docker-compose.prod.yml` plus `.env.production`.
- It includes backup service settings, monitoring placeholders, and Traefik configuration. Phase 4 should mention only what is needed to distinguish this optional path and reach first login.

### frontend-v3/next.config.mjs

- When `NEXT_PUBLIC_API_URL` is empty, Next.js rewrites:
  - `/api/:path*` to `${BACKEND_URL}/api/:path*`
  - `/health` to `${BACKEND_URL}/health`
- This confirms the Phase 4 decision to leave `NEXT_PUBLIC_API_URL` empty for LAN deployment.
- The first-deployment guide can verify backend health through both `http://SERVER:8000/health` and the frontend proxy at `http://SERVER:3000/health`.

### Missing LAN Doc

- `docs/local_network_deployment.md` is referenced in README and Phase 4 context, but the file is not present.
- The plan should not depend on reading or editing that file.
- The implementation should remove README routing to that missing path and fold the relevant LAN guidance from the existing `DEPLOYMENT.md` LAN section into the new primary checklist.

## Recommended Planning Approach

Use three plans:

1. README deployment routing and stale-status cleanup.
2. Rewrite `DEPLOYMENT.md` around a LAN-first ordered checklist plus optional public-domain HTTPS path.
3. Align `.env.production.example` comments/default grouping with the guide and add doc consistency verification.

This split keeps the work reviewable and lets the main deployment guide be edited without also mixing README cleanup or env-comment refinements into the same plan.

## Required Plan Coverage

Every Phase 4 plan set must cover these requirement IDs:

- `DEPL-01`
- `DEPL-02`
- `DEPL-03`
- `DEPL-04`
- `CONF-01`
- `CONF-02`
- `CONF-03`
- `CONF-04`
- `DOCS-01`
- `DOCS-02`
- `DOCS-03`

## Implementation Constraints

- Owner-facing deployment explanation should be Swedish.
- Commands, filenames, environment variable names, and URLs should remain literal.
- The recommended default path is LAN/local server deployment with `docker-compose.local.yml`.
- Public-domain HTTPS with `docker-compose.prod.yml` and Traefik is optional and separate.
- Do not make Terraform/Hetzner look like the recommended path.
- Do not add new deployment infrastructure or change the Docker architecture.
- Do not add secret-generation command snippets; use manual guidance such as password manager or random generator.
- Warn in the configuration section that Compose fallbacks and placeholder secrets are unsafe for real use.
- Include verification commands for:
  - container status
  - backend health
  - frontend availability
  - first login URL

## Files To Modify

- `README.md`
- `DEPLOYMENT.md`
- `.env.production.example`

## Files To Read Before Editing

- `.planning/phases/04-deployment-guide-and-configuration-clarity/04-CONTEXT.md`
- `.planning/ROADMAP.md`
- `.planning/REQUIREMENTS.md`
- `README.md`
- `DEPLOYMENT.md`
- `.env.production.example`
- `docker-compose.local.yml`
- `docker-compose.prod.yml`
- `frontend-v3/next.config.mjs`

## Verification Commands

Documentation-only changes do not need backend or frontend test suites by default. Verification should focus on source assertions and command validity:

- `rg -n "docs/local_network_deployment|ALLA FASER KLARA|Fas 5|Hetzner Cloud-deployment \\(Console, API, Terraform\\)" README.md`
- `rg -n "docker compose --env-file \\.env\\.production -f docker-compose\\.local\\.yml up -d --build|curl -fsS http://localhost:8000/health|curl -fsSI http://localhost:3000/login|NEXT_PUBLIC_API_URL=|BACKEND_URL=http://api:8000" DEPLOYMENT.md .env.production.example`
- `rg -n "BOKFOERING_API_KEY|JWT_SECRET|AUTH_PASSWORD|docker-compose.local.yml|docker-compose.prod.yml|APP_DOMAIN|API_DOMAIN|LETSENCRYPT_EMAIL" DEPLOYMENT.md .env.production.example`

## Planning Risks

- If the plan asks the executor to "make docs consistent" without exact target strings and files, the implementation will likely be too shallow.
- The old `DEPLOYMENT.md` has useful commands, but its structure is the problem. The plan should require a restructure, not just adding a new section at the top.
- Phase 5 owns updates, backup, restore, rollback, and deeper troubleshooting. Phase 4 should avoid expanding those sections except to prevent dangerous first-deployment mistakes.
- The missing `docs/local_network_deployment.md` should be treated as a broken reference to remove from the recommended route.

## Research Complete

Phase 4 can be planned against the current repo without additional external research.

## RESEARCH COMPLETE
