# Phase 5: Operations, Troubleshooting, and Outdated Infra Warnings - Context

**Gathered:** 2026-06-04
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers owner-facing operations documentation for the existing
Docker-based deployment paths. It should explain safe updates, backup, restore,
rollback, troubleshooting, and outdated infrastructure warnings without changing
the deployment architecture or repairing Terraform/Hetzner provisioning.

Phase 5 extends the Phase 4 deployment guide after first login. The recommended
path remains LAN/local Docker first, with public-domain HTTPS as an optional
separate path. Owner-facing explanatory text should be Swedish; commands, file
paths, environment variables, and code terms remain literal.

</domain>

<decisions>
## Implementation Decisions

### Safe Updates and Rollback
- **D-01:** Normal LAN updates should use `git pull`, rebuild/restart, then
  verification as the primary path.
- **D-02:** The git bundle over SSH flow may remain as an advanced/secondary
  update path for local-repository deployments, but it should not be presented
  as the normal route.
- **D-03:** Every update flow should start by creating or confirming a backup.
  Backup is not optional in the owner-facing update checklist.
- **D-04:** Rollback instructions should include concrete previous-commit
  commands: find a commit, check it out, rebuild/restart, verify, and later
  return to the intended branch.
- **D-05:** Data-loss warnings should be blunt and repeated where relevant:
  `docker compose down -v`, deleting Docker volumes, or removing
  `bokfoering-data` can delete bookkeeping data.

### Carried Forward from Phase 4
- **D-06:** `DEPLOYMENT.md` remains the canonical deployment and operations
  guide for this milestone.
- **D-07:** LAN/local Docker is the recommended default route.
- **D-08:** Public-domain HTTPS remains optional and separate from the LAN
  route.
- **D-09:** Terraform/Hetzner documentation should be marked outdated and
  excluded from the recommended path, not repaired in this milestone.
- **D-10:** Owner-facing explanatory deployment and operations text should be
  Swedish, with concise commands and direct warnings.

### the agent's Discretion
- The agent may decide exact section order, headings, tables, and command block
  formatting as long as the update flow starts with backup, avoids data-
  destructive commands, and ends with verification.
- The agent may decide how much of the safe-update flow is duplicated for the
  optional public-domain Compose path, provided LAN remains first and clearest.
- Backup/restore, troubleshooting, and Terraform/Hetzner warning details were
  not discussed beyond the locked roadmap requirements and carried-forward
  Phase 4 decisions; downstream agents should use the requirements and existing
  docs to plan those sections conservatively.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Planning
- `.planning/ROADMAP.md` — Phase 5 goal, requirements, and success criteria.
- `.planning/REQUIREMENTS.md` — OPS-01 through OPS-04 and DOCS-04.
- `.planning/PROJECT.md` — milestone scope, Docker-first deployment decision,
  and out-of-scope infrastructure constraints.
- `.planning/STATE.md` — current project position and known verification debt.
- `.planning/phases/04-deployment-guide-and-configuration-clarity/04-CONTEXT.md`
  — carried-forward deployment path, owner tone, and Terraform/Hetzner
  decisions.

### Deployment Documentation and Config
- `DEPLOYMENT.md` — canonical guide to extend with operations, troubleshooting,
  backup, restore, rollback, and warnings.
- `README.md` — top-level routing should remain aligned with the canonical
  guide.
- `.env.production.example` — optional backup/S3 settings and operational
  environment comments.
- `docker-compose.local.yml` — recommended LAN Compose file and persistent
  `bokfoering-data` volume.
- `docker-compose.prod.yml` — optional public-domain HTTPS path, backup service,
  local backup directory, logs directory, and persistent data volume.
- `frontend-v3/next.config.mjs` — same-origin API rewrite behavior used by the
  LAN deployment path.

### Outdated Infrastructure
- `terraform/README.md` — currently presents Hetzner/Terraform as a deployment
  path and must be clearly marked outdated/excluded.
- `terraform/main.tf` — existing Terraform implementation, out of scope for
  repair.
- `terraform/variables.tf` — Terraform variables, out of scope for repair.
- `terraform/terraform.tfvars.example` — Terraform example variables, out of
  scope for repair.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `docker-compose.local.yml`: Recommended LAN deployment file with API,
  frontend, health checks, and persistent `bokfoering-data:/app/data`.
- `docker-compose.prod.yml`: Optional public-domain Compose file with Traefik,
  `bokfoering-data:/app/data`, `./backups:/app/backups`, `./logs:/app/logs`,
  and an `offen/docker-volume-backup` service archiving the data volume.
- `DEPLOYMENT.md`: Already contains LAN-first setup, verification, first login,
  optional public HTTPS, and a small troubleshooting section to expand.
- `.env.production.example`: Already includes required secrets and optional
  backup/S3 placeholders.

### Established Patterns
- Deployment is Docker Compose based.
- SQLite and local filesystem state live under `/app/data` inside the persistent
  `bokfoering-data` Docker volume.
- Backend health can be verified at `/health`; frontend availability and login
  can be verified through `/login` and `/health` on the frontend host.
- The public-domain path uses Traefik and Let's Encrypt through
  `docker-compose.prod.yml`; LAN should remain separate and simpler.

### Integration Points
- `DEPLOYMENT.md` should get the primary operations content.
- `README.md` should continue routing users to `DEPLOYMENT.md` without
  introducing a competing operations path.
- `terraform/README.md` needs a prominent outdated/excluded warning so owners do
  not treat it as the current recommended route.

</code_context>

<specifics>
## Specific Ideas

- The update checklist should be ordered roughly: backup or confirm backup,
  fetch code with `git pull`, rebuild/restart with the correct Compose file,
  run health checks, open the login page, and inspect logs if verification
  fails.
- Rollback should be practical enough for an owner following support guidance:
  inspect recent commits, check out the previous known-good commit, rebuild,
  verify, and later return to the intended branch.
- The wording around `docker compose down -v`, deleting Docker volumes, and
  deleting `bokfoering-data` should be intentionally blunt because the data is
  bookkeeping data.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 5-Operations, Troubleshooting, and Outdated Infra Warnings*
*Context gathered: 2026-06-04*
