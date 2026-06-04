# Milestones

## v1.1 Clear Instructions for Deployment (Shipped: 2026-06-04)

**Phases completed:** 2 phases, 6 plans, 18 tasks

**Delivered:** Owner-facing Docker deployment and operations documentation for
LAN/local installs, with optional public-domain guidance, safe secret setup,
updates, backup/restore, rollback, troubleshooting, and explicit Terraform
deprecation warnings.

**Key accomplishments:**

- LAN-first Swedish deployment guide with required secrets, Docker Compose verification, first login, and optional public HTTPS separated.
- Production environment template now mirrors the LAN deployment defaults and clearly separates optional public-domain and backup settings.
- README now sends deployment users to the canonical LAN-first guide and removes stale status, broken LAN-doc routing, and default credential guidance.
- `DEPLOYMENT.md` now covers safe updates, concrete rollback steps, and blunt data-loss warnings around Docker volume deletion.
- `DEPLOYMENT.md` now covers backup scope, manual LAN backup commands, restore steps, optional backup-sidecar context, and troubleshooting/support diagnostics.
- `terraform/README.md` is now marked outdated, not validated in v1.1, and excluded from the recommended deployment path.

**Known deferred items at close:** Milestone closed without a dedicated
`v1.1-MILESTONE-AUDIT.md`, and Phase 5 security review (`$gsd-secure-phase 5`)
was acknowledged but not run before close. See `.planning/STATE.md` Deferred
Items.

**What's next:** Define fresh requirements for the next milestone with
`$gsd-new-milestone`.

---

## v1.0 Intake Automation (Shipped: 2026-05-18)

**Phases completed:** 3 phases, 9 plans, 36 tasks

**Delivered:** Automation-first source intake for voucher evidence and bank CSV inputs, with agent posting traceability and frontend review/correction surfaces.

**Key accomplishments:**

- SQLite-backed intake source storage with duplicate hash rejection and root-contained local file resolution
- Authenticated intake upload/download routes plus agent pending queue and failed-processing attempt APIs
- Agent-posted vouchers can now consume one intake source and leave durable source, link, and processing history
- CSV bank input uploads with separate SQLite source records, active bank connection validation, and safe original-file downloads
- Supported Swedish bank CSV uploads now import transactions immediately, store lifecycle counts, and link imported rows to their source file
- Agent context now exposes typed bank input work and bank-driven voucher posting is guarded against transaction reuse with durable source links
- Typed intake review APIs and React Query hooks now support unified source/bank intake listing, uploads, voucher source context, and correction-chain review.
- Operational intake workspace with separate voucher-source and bank CSV uploads, lifecycle/type filters, status details, and linked-voucher row actions.
- Dedicated intake detail and voucher review surfaces now expose source files, processing history, agent notes, and correction-learning context.

**Known deferred items at close:** Milestone audit status was `gaps_found` because Phase 1 lacks aggregate `01-VERIFICATION.md`; user chose to proceed and accept this verification gap as deferred tech debt. See `.planning/milestones/v1.0-MILESTONE-AUDIT.md`.

**What's next:** Define fresh requirements for v1.1 with `$gsd-new-milestone`.

---
