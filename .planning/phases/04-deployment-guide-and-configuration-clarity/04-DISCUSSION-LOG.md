# Phase 4: Deployment Guide and Configuration Clarity - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-18
**Phase:** 4-Deployment Guide and Configuration Clarity
**Areas discussed:** Recommended Path Shape, Owner Skill Level and Tone, Configuration Defaults and Warnings, README and Doc Routing

---

## Recommended Path Shape

| Option | Description | Selected |
|--------|-------------|----------|
| LAN/local server first | Recommended default for a self-hosted owner; public-domain HTTPS is a separate optional section. | ✓ |
| Public-domain HTTPS first | Treats Traefik/domain deployment as the production path; LAN is secondary. | |
| Equal chooser | Starts with a choose-your-path table, then sends the owner to either LAN or public-domain steps. | |

**User's choice:** LAN/local server first.
**Notes:** Public-domain HTTPS should be optional, not the primary path.

| Option | Description | Selected |
|--------|-------------|----------|
| GitHub clone/pull | Simplest normal path when the repo is reachable from the server. | |
| Local git bundle over SSH | Matches the existing Home Assistant/local repository workflow already in `DEPLOYMENT.md`. | |
| Present both | Make GitHub clone/pull normal and bundle-over-SSH an advanced/local-repo variant. | ✓ |

**User's choice:** Present both, with GitHub clone/pull as normal.
**Notes:** Bundle-over-SSH remains useful but should not be the first path.

| Option | Description | Selected |
|--------|-------------|----------|
| One ordered LAN checklist first | Prerequisites, `.env.production`, build/start, verify, first login. Best fit for DEPL-02. | ✓ |
| Keep sectioned guide | Less disruptive, but risks preserving the current maze of paths. | |
| Hybrid | Short top-level checklist that links into detailed sections below. | |

**User's choice:** One ordered LAN checklist first.
**Notes:** `DEPLOYMENT.md` should be rewritten around this flow.

---

## Owner Skill Level and Tone

| Option | Description | Selected |
|--------|-------------|----------|
| Can SSH and paste commands | Explain what each block is for, but do not teach Linux/Docker from scratch. | |
| Docker beginner | Explain Docker Compose concepts and command meanings in more detail. | |
| Comfortable operator | Concise commands and warnings, minimal explanation. | ✓ |

**User's choice:** Comfortable operator.
**Notes:** Keep docs concise and practical.

| Option | Description | Selected |
|--------|-------------|----------|
| English | Matches current `DEPLOYMENT.md` and most config/tooling terms. | |
| Swedish | Matches README and the target company owner context. | ✓ |
| Mixed | English commands/headings, Swedish explanatory notes. | |

**User's choice:** Swedish.
**Notes:** Owner-facing explanatory text should be Swedish.

| Option | Description | Selected |
|--------|-------------|----------|
| Copy-paste with placeholders | Faster, but users must notice every placeholder. | ✓ |
| Split commands and edit steps | Safer for secrets/domains, but longer. | |
| Mostly copy-paste | Commands for most steps, explicit edit/check steps for secrets/domains. | |

**User's choice:** Copy-paste with placeholders.
**Notes:** Use clear placeholders in command blocks.

| Option | Description | Selected |
|--------|-------------|----------|
| Very blunt | Clearly say this is self-hosted Docker, not managed hosting or validated Terraform. | ✓ |
| Moderate | Warn where needed, but keep the guide focused on successful setup. | |
| Minimal | Avoid discouraging language; only mark concrete unsafe settings. | |

**User's choice:** Very blunt.
**Notes:** Make scope limits explicit.

---

## Configuration Defaults and Warnings

| Option | Description | Selected |
|--------|-------------|----------|
| Hard warning before startup | Say real deployments must set `.env.production`; show a preflight check command. | |
| Warn in env section only | Less noisy, but easier to miss. | ✓ |
| Recommend changing Compose defaults too | Broader change, but reduces risk if env loading is skipped. | |

**User's choice:** Warn in env section only.
**Notes:** Do not add a separate startup preflight gate unless planner finds it necessary for clarity.

| Option | Description | Selected |
|--------|-------------|----------|
| OpenSSL commands | Use commands such as `openssl rand -hex 32`. | |
| Manual guidance | Use a password manager/random generator; no commands. | ✓ |
| Both | Commands for API/JWT secrets, password-manager guidance for login password. | |

**User's choice:** Manual guidance.
**Notes:** Avoid secret-generation command snippets.

| Option | Description | Selected |
|--------|-------------|----------|
| Leave empty by default | Frontend uses same-origin `/api` proxy to `BACKEND_URL`; recommended LAN setup. | ✓ |
| Set to `http://SERVER_IP:8000` | Browser calls API directly; easier to reason about but CORS-sensitive. | |
| Explain both equally | Documents both proxy and direct API modes as peers. | |

**User's choice:** Leave empty by default.
**Notes:** This matches `frontend-v3/next.config.mjs` rewrite behavior.

| Option | Description | Selected |
|--------|-------------|----------|
| Keep placeholders in env example | Label public-domain variables optional and only for `docker-compose.prod.yml`. | |
| Separate optional docs block | Move public-domain variables into an optional example block in docs. | ✓ |
| Remove from env example only | Mention public-domain setup only in `DEPLOYMENT.md`. | |

**User's choice:** Separate optional docs block.
**Notes:** Main LAN env example should stay focused.

---

## README and Doc Routing

| Option | Description | Selected |
|--------|-------------|----------|
| Point real deployment users to `DEPLOYMENT.md` only | Short warning not to use dev quick start for production. | |
| Keep both quick deployment steps and `DEPLOYMENT.md` | Preserves a fast path plus the full guide. | ✓ |
| Split local dev and real deployment links | Clear separation between development quick start and production deployment. | |

**User's choice:** Keep both quick deployment steps and `DEPLOYMENT.md`.
**Notes:** README should still be useful without opening the full guide.

| Option | Description | Selected |
|--------|-------------|----------|
| Replace with current v1.1 status | Updates status in place. | |
| Remove detailed phase status entirely | Avoids future staleness. | ✓ |
| Keep historical feature status | Rename so it is not confused with current roadmap phases. | |

**User's choice:** Remove detailed phase status entirely.
**Notes:** The current README status block is stale and should not be carried forward.

| Option | Description | Selected |
|--------|-------------|----------|
| No | Fold relevant content into `DEPLOYMENT.md` and stop pointing deployment users there. | ✓ |
| Yes | Keep it as the detailed LAN guide, with README/DEPLOYMENT.md pointing to it. | |
| Legacy/reference only | Keep clearly secondary to `DEPLOYMENT.md`. | |

**User's choice:** No.
**Notes:** `DEPLOYMENT.md` becomes the recommended deployment guide.

---

## the agent's Discretion

- Exact headings, table shapes, command ordering details, and whether the old LAN doc is removed or converted to a non-recommended reference are left to implementation judgment.

## Deferred Ideas

- Phase 5 handles update, backup, restore, rollback, and deeper troubleshooting.
- Terraform/Hetzner repair or validation remains future infrastructure work.
