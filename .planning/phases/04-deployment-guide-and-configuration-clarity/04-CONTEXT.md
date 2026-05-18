# Phase 4: Deployment Guide and Configuration Clarity - Context

**Gathered:** 2026-05-18
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers clear owner-facing deployment documentation for the existing Docker-based setup, from prerequisites through first login. It should align `README.md`, `DEPLOYMENT.md`, `.env.production.example`, and the Compose file guidance so a non-expert owner can identify the recommended path, configure secrets, start the app, and verify that it works.

Phase 4 is about first deployment and configuration clarity. Updates, backup, restore, rollback, deeper troubleshooting, and Terraform/Hetzner warnings are Phase 5 unless a minimal note is needed to prevent confusion in Phase 4 docs.

</domain>

<decisions>
## Implementation Decisions

### Recommended Deployment Path
- **D-01:** Make LAN/local server deployment the recommended default path.
- **D-02:** Treat public-domain HTTPS deployment as a separate optional path, not the primary flow.
- **D-03:** For LAN deployment, present GitHub clone/pull as the normal code transfer path.
- **D-04:** Keep git bundle over SSH as an advanced/local-repository variant because it matches the current local/Home Assistant workflow.
- **D-05:** Rewrite `DEPLOYMENT.md` around one ordered LAN checklist first: prerequisites, `.env.production`, build/start, verification, and first login.

### Owner Skill Level and Tone
- **D-06:** Target a comfortable operator: concise commands, direct warnings, and minimal explanation.
- **D-07:** Use Swedish for owner-facing explanatory deployment text.
- **D-08:** Favor copy-paste command blocks with placeholders.
- **D-09:** Be very blunt about deployment limits: this is a self-hosted Docker path, not managed hosting, and Terraform/Hetzner is not validated in this milestone.

### Configuration Defaults and Warnings
- **D-10:** Warn about unsafe Compose fallbacks and placeholder secrets in the environment/configuration section only, rather than adding a separate preflight warning before startup.
- **D-11:** Use manual secret guidance, such as password manager or random generator instructions, instead of secret-generation command snippets.
- **D-12:** For LAN deployment, leave `NEXT_PUBLIC_API_URL` empty by default so the frontend uses same-origin `/api` rewrites through `BACKEND_URL`.
- **D-13:** Move public-domain variables into a separate optional docs block instead of mixing them into the main LAN `.env.production.example` path.

### README and Documentation Routing
- **D-14:** Keep both quick deployment steps and a link to `DEPLOYMENT.md` in `README.md`.
- **D-15:** Remove the detailed stale phase-status block from `README.md`.
- **D-16:** Fold relevant `docs/local_network_deployment.md` content into `DEPLOYMENT.md` and stop routing deployment users to the separate LAN doc.

### the agent's Discretion
- The agent may decide exact section headings, command ordering details, and table formatting as long as the LAN checklist remains the first and clearest path.
- The agent may decide whether `docs/local_network_deployment.md` should be removed, shortened into a legacy pointer, or left as non-recommended reference, provided README and deployment users are no longer routed there as the recommended path.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Planning
- `.planning/ROADMAP.md` — Phase 4 goal, requirements, and success criteria.
- `.planning/REQUIREMENTS.md` — v1.1 deployment, configuration, and documentation alignment requirements.
- `.planning/PROJECT.md` — current milestone context, scope constraints, and Docker-first deployment decision.
- `.planning/STATE.md` — current project position and recent decisions.

### Deployment Documentation and Config
- `README.md` — current quick start, stale status block, deployment links, and docs routing to align.
- `DEPLOYMENT.md` — primary deployment guide to restructure around the LAN checklist.
- `.env.production.example` — environment example to align with LAN defaults and optional public-domain variables.
- `docker-compose.local.yml` — recommended LAN Compose file and default environment behavior.
- `docker-compose.prod.yml` — optional public-domain HTTPS Compose path using Traefik.
- `frontend-v3/next.config.mjs` — rewrite behavior when `NEXT_PUBLIC_API_URL` is empty.
- `docs/local_network_deployment.md` — existing LAN guidance to fold into `DEPLOYMENT.md` if present.

### Outdated Infrastructure
- `terraform/README.md` — Terraform/Hetzner documentation to exclude from the current recommended path.
- `terraform/main.tf` — existing Terraform implementation, out of scope for repair in this milestone.
- `terraform/variables.tf` — Terraform variables, out of scope for repair in this milestone.
- `terraform/terraform.tfvars.example` — Terraform example variables, out of scope for repair in this milestone.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `docker-compose.local.yml`: Existing LAN deployment file exposes frontend on `3000` and backend on `8000`, sets `BACKEND_URL` to the internal API service, and lets `NEXT_PUBLIC_API_URL` default empty.
- `docker-compose.prod.yml`: Existing optional public-domain deployment file includes Traefik, HTTPS labels, `APP_DOMAIN`, `API_DOMAIN`, and `LETSENCRYPT_EMAIL`.
- `.env.production.example`: Already includes core backend/auth secrets and frontend connectivity settings, but public-domain settings should be separated from the main LAN path.
- `frontend-v3/next.config.mjs`: Supports the intended LAN default by proxying `/api/:path*` and `/health` to `BACKEND_URL` when `NEXT_PUBLIC_API_URL` is empty.

### Established Patterns
- Deployment is Compose-based with a persistent `bokfoering-data` volume for SQLite/data storage.
- Backend health is available at `/health`; frontend availability can be checked through `/login` and `/health` depending on proxy mode.
- Current docs mix developer quick start, LAN/local-repo deployment, public-domain HTTPS, Hetzner, Terraform, monitoring, backup, and troubleshooting, which conflicts with the Phase 4 goal of a single first-deployment checklist.

### Integration Points
- `README.md` should route users consistently and remove stale phase-status claims.
- `DEPLOYMENT.md` is the canonical deployment guide for Phase 4.
- `.env.production.example` comments must match `DEPLOYMENT.md` recommended LAN settings.
- Terraform docs should not be repaired in Phase 4, but references must not make them look like the recommended deployment path.

</code_context>

<specifics>
## Specific Ideas

- LAN/local server deployment should be the first path users see.
- Public-domain HTTPS should be explicitly optional.
- GitHub clone/pull should be the normal deployment source flow; bundle-over-SSH should remain available for local-repo workflows.
- Swedish explanatory text is preferred for owner-facing deployment docs, while commands, file paths, variables, and code terms remain literal.

</specifics>

<deferred>
## Deferred Ideas

- Full update, backup, restore, rollback, and operational troubleshooting instructions belong to Phase 5.
- Repairing or validating Terraform/Hetzner provisioning remains out of scope for v1.1 and is tracked as future infrastructure work.

</deferred>

---

*Phase: 4-Deployment Guide and Configuration Clarity*
*Context gathered: 2026-05-18*
