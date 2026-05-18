# Roadmap: Bok

## Milestones

- ✅ **v1.0 Intake Automation** — Phases 1-3 (shipped 2026-05-18). Full archive: [v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)
- ◆ **v1.1 Clear Instructions for Deployment** — Phases 4-5 (planned). Scope: owner-friendly Docker deployment documentation; Terraform/Hetzner marked outdated.

## Phases

<details>
<summary>✅ v1.0 Intake Automation (Phases 1-3) — SHIPPED 2026-05-18</summary>

- [x] Phase 1: Intake Foundation and Agent Queue (3/3 plans) — completed 2026-05-15
- [x] Phase 2: Bank Input and Direct Posting Context (3/3 plans) — completed 2026-05-15
- [x] Phase 3: Frontend Intake Workspace and Review Loop (3/3 plans) — completed 2026-05-15

Archive:
- Roadmap: [v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)
- Requirements: [v1.0-REQUIREMENTS.md](milestones/v1.0-REQUIREMENTS.md)
- Audit: [v1.0-MILESTONE-AUDIT.md](milestones/v1.0-MILESTONE-AUDIT.md)

</details>

<details open>
<summary>◆ v1.1 Clear Instructions for Deployment (Phases 4-5) — PLANNED</summary>

### Phase 4: Deployment Guide and Configuration Clarity

**Goal:** Make the primary deployment path understandable and executable for a non-expert owner from prerequisites through first login.

**Requirements:** DEPL-01, DEPL-02, DEPL-03, DEPL-04, CONF-01, CONF-02, CONF-03, CONF-04, DOCS-01, DOCS-02, DOCS-03

**Success criteria:**
1. README directs deployment users to the correct guide and no longer presents stale deployment status or conflicting first steps.
2. DEPLOYMENT.md presents a single ordered checklist for LAN/local server deployment and a separate optional public-domain HTTPS path.
3. The guide explains `.env.production`, required secrets, unsafe placeholders, LAN URLs, public-domain settings, and Compose file selection in owner-friendly language.
4. Verification commands cover container status, backend health, frontend availability, and first login.

### Phase 5: Operations, Troubleshooting, and Outdated Infra Warnings

**Goal:** Give owners enough operational instructions to update, back up, restore, roll back, and troubleshoot deployments without risking bookkeeping data.

**Requirements:** OPS-01, OPS-02, OPS-03, OPS-04, DOCS-04

**Success criteria:**
1. Deployment docs explain safe update flow and explicitly warn against data-destructive commands such as removing volumes during normal deployments.
2. Backup and restore instructions cover the SQLite/data volume and local backup directory with practical verification steps.
3. Rollback instructions describe returning to a previous deployed version and restarting without wiping data.
4. Troubleshooting sections cover unhealthy containers, frontend/backend connection failures, missing env vars, DNS/HTTPS issues, logs, and support-ready diagnostic output.
5. Terraform/Hetzner docs are clearly marked outdated and excluded from the recommended deployment path.

</details>

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Intake Foundation and Agent Queue | v1.0 | 3/3 | Complete | 2026-05-15 |
| 2. Bank Input and Direct Posting Context | v1.0 | 3/3 | Complete | 2026-05-15 |
| 3. Frontend Intake Workspace and Review Loop | v1.0 | 3/3 | Complete | 2026-05-15 |
| 4. Deployment Guide and Configuration Clarity | v1.1 | 0/0 | Planned | — |
| 5. Operations, Troubleshooting, and Outdated Infra Warnings | v1.1 | 0/0 | Planned | — |

## Next

Start Phase 4 with `$gsd-discuss-phase 4` or `$gsd-plan-phase 4`.
