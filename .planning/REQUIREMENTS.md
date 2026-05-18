# Requirements: Bok

**Defined:** 2026-05-18
**Core Value:** The system should let a small Swedish company keep compliant books with minimal manual interaction by giving an agent enough source material, history, and correction feedback to post accurate vouchers.

## v1.1 Requirements

Requirements for the clear deployment instructions milestone. Each maps to roadmap phases.

### Deployment Guide

- [ ] **DEPL-01**: Owner can identify the recommended deployment path for their situation: LAN/local server or public-domain Docker deployment.
- [ ] **DEPL-02**: Owner can follow a single ordered deployment checklist from prerequisites through first login without needing to infer missing steps.
- [ ] **DEPL-03**: Owner can understand what each required deployment file does: `.env.production`, `docker-compose.local.yml`, `docker-compose.prod.yml`, and `DEPLOYMENT.md`.
- [ ] **DEPL-04**: Owner can verify a deployment with explicit health checks for backend, frontend, login page, and container status.

### Configuration and Secrets

- [ ] **CONF-01**: Owner can create `.env.production` from the example and replace every required secret safely.
- [ ] **CONF-02**: Owner can configure LAN/direct access without public DNS.
- [ ] **CONF-03**: Owner can configure optional public-domain HTTPS deployment when they have domain names and email for Let's Encrypt.
- [ ] **CONF-04**: Owner can understand which default credentials or placeholder secrets are unsafe for real use.

### Operations

- [ ] **OPS-01**: Owner can update an existing deployment without deleting bookkeeping data.
- [ ] **OPS-02**: Owner can back up and restore the SQLite/data volume using documented commands and warnings.
- [ ] **OPS-03**: Owner can roll back to a previous deployed version when an update fails.
- [ ] **OPS-04**: Owner can inspect logs and container health enough to report or diagnose deployment problems.

### Documentation Alignment

- [ ] **DOCS-01**: `README.md` points users to the correct deployment guide and does not advertise stale or conflicting deployment paths.
- [ ] **DOCS-02**: `DEPLOYMENT.md` is structured for a non-expert owner and avoids contradictory compose/env instructions.
- [ ] **DOCS-03**: `.env.production.example` comments match the deployment guide's recommended settings.
- [ ] **DOCS-04**: Terraform/Hetzner documentation is clearly marked outdated and excluded from the current recommended deployment path.

## Future Requirements

Deferred to future releases. Tracked but not in current roadmap.

### Infrastructure

- **INFRA-01**: Owner can use validated Terraform/Hetzner provisioning instructions for public cloud deployment.
- **INFRA-02**: Owner can configure S3-compatible off-site backups through a fully documented and verified path.
- **INFRA-03**: Owner can complete an in-app deployment/setup checklist or environment health wizard.

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Repairing or validating Terraform/Hetzner provisioning | User explicitly deferred this path; current docs should mark it outdated instead. |
| Adding new deployment infrastructure or changing production hosting architecture | The milestone is documentation and operational clarity over existing Docker-based paths. |
| Building an in-app setup wizard or deployment UI | The requested outcome is clear deployment instructions, not product UI changes. |
| Changing authentication or persistent API-key management | Deployment docs can warn about current secrets, but auth implementation is outside this milestone. |
| Adding S3/object-storage backup support | Existing optional placeholders may be documented cautiously, but implementation and validation are future work. |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DEPL-01 | — | Pending |
| DEPL-02 | — | Pending |
| DEPL-03 | — | Pending |
| DEPL-04 | — | Pending |
| CONF-01 | — | Pending |
| CONF-02 | — | Pending |
| CONF-03 | — | Pending |
| CONF-04 | — | Pending |
| OPS-01 | — | Pending |
| OPS-02 | — | Pending |
| OPS-03 | — | Pending |
| OPS-04 | — | Pending |
| DOCS-01 | — | Pending |
| DOCS-02 | — | Pending |
| DOCS-03 | — | Pending |
| DOCS-04 | — | Pending |

**Coverage:**
- v1.1 requirements: 16 total
- Mapped to phases: 0
- Unmapped: 16

---
*Requirements defined: 2026-05-18*
*Last updated: 2026-05-18 after requirements definition*
