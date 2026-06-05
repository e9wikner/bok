# Bok

## What This Is

Bok is a self-hosted bookkeeping application for small Swedish limited companies that want to run accounting without external accountants and without needing deep bookkeeping knowledge. It combines a FastAPI backend, a Next.js frontend, Swedish accounting compliance rules, and an AI-agent-facing API so bookkeeping decisions can be automated while the backend enforces formal accounting constraints.

Bok now includes an intake system for source material: users upload receipts, invoices, and bank statements/statuses through the frontend, and the agent uses that material to decide which vouchers to post. The intended workflow favors automation over pre-approval: the agent posts vouchers directly, and user review plus B-series correction vouchers become the feedback loop the agent learns from.

## Current State

v1.0 Intake Automation shipped on 2026-05-18. The codebase now supports durable voucher-source intake, separate bank CSV input intake, agent direct posting with source traceability, and frontend work surfaces for upload, status scanning, voucher source review, and correction-learning context.

v1.1 Clear Instructions for Deployment shipped on 2026-06-04. `README.md`,
`DEPLOYMENT.md`, `.env.production.example`, and `terraform/README.md` now
present a LAN-first Docker deployment path with brief secret-generation guidance,
verification commands, safe updates, backup/restore, rollback, troubleshooting,
support diagnostics, and explicit warnings that Terraform/Hetzner is not the
current validated path.

v1.2 Agent Onboarding shipped on 2026-06-05. The deployed Bok instance now exposes a public-safe agent instruction entrypoint (`/api/v1/agent-instructions/entrypoint`) with service identity, auth guidance, ordered startup workflow, and guardrails. Placeholder agent routes have been removed. `DEPLOYMENT.md` now includes a post-deploy OpenClaw/HTTP-agent setup section with shell-variable `curl` verification commands, frontend/backend URL separation notes, and a setup-only starter agent prompt. Deterministic pytest tests verify the documentation content and route behavior against the live FastAPI app.

Known closeout debt: the v1.0 milestone audit was accepted with `gaps_found` because Phase 1 lacks aggregate `01-VERIFICATION.md`, even though its plan summaries record focused implementation checks. The v1.1 milestone closed without a dedicated `v1.1-MILESTONE-AUDIT.md` and without running `$gsd-secure-phase 5`. The v1.2 milestone closed without a dedicated `v1.2-MILESTONE-AUDIT.md`.

## Current Milestone: v1.2 Agent Onboarding (Shipped)

**Goal:** Make a deployed Bok instance understandable and connectable for an OpenClaw-style HTTP agent so it can begin bookkeeping through the existing agent API.

**Shipped:**
- REST-style agent onboarding endpoint that tells an agent how to connect, authenticate, discover available agent endpoints, and start the bookkeeping workflow.
- Post-deploy OpenClaw/HTTP-agent setup instructions in `DEPLOYMENT.md`.
- Revised agent API behavior: startup, context scanning, direct posting, and correction feedback are coherent for an external agent.

## Next Milestone Goals

- Persistent, revocable per-agent API keys with audit metadata (KEYS-01)
- MCP adapter for selected agent workflow operations (MCP-01)
- Durable idempotency keys for retry-safe agent posting (IDEM-01)
- Continued refinement of agent context and correction-learning surfaces

## Core Value

The system should let a small Swedish company keep compliant books with minimal manual interaction by giving an agent enough source material, history, and correction feedback to post accurate vouchers.

## Requirements

### Validated

- Append-only voucher storage with immutable posted vouchers and B-series corrections — existing
- Period and fiscal-year handling with irreversible period locking — existing
- Double-entry voucher validation with active-account and period checks — existing
- BAS-based account model and Swedish VAT handling — existing
- Invoice, payment, and credit invoice workflows with auto-booking — existing
- Report generation for income statement, balance sheet, ledger, K2 data, VAT, and related exports — existing
- SIE4 import/export for interoperability with other bookkeeping tools — existing
- PDF export for invoices and accounting reports — existing
- Agent-facing API endpoints for instructions, direct voucher posting, invoice drafts, and correction history — existing
- Agent-readable Markdown instruction documents with version history — existing
- Frontend review surfaces for vouchers, invoices, reports, payroll, settings, and agent instructions — existing
- Voucher attachments for already-created vouchers, including PDF and image files — existing
- Manual CSV bank transaction import and bank transaction storage/deduplication — existing
- User correction of posted vouchers through linked correction vouchers that preserve original records — existing
- Uploaded bank CSV inputs are modeled separately from voucher source material — validated in Phase 02
- Bank CSV uploads preserve original file metadata and import transaction rows with source linkage — validated in Phase 02
- Agent context exposes typed bank input queue items plus correction-history discovery — validated in Phase 02
- Bank-driven direct posting rejects explicit reuse of booked or matched transactions — validated in Phase 02
- Bank-driven vouchers preserve traceability to uploaded bank input rows and exact bank transactions — validated in Phase 02
- User can upload source material before a voucher exists, including receipt/invoice PDFs and images — shipped in v1.0
- User can add a short explanation to each uploaded voucher source — shipped in v1.0
- Uploaded voucher source material is visible to the agent as pending work during status/context checks — shipped in v1.0
- Agent can create and post vouchers directly from uploaded source material without requiring user approval first — shipped in v1.0
- Posted vouchers created from intake material preserve traceability back to source files and user explanation — shipped in v1.0
- User can review agent-posted vouchers after the fact and correct mistakes through existing B-series correction flows — shipped in v1.0
- Intake items have lifecycle state to avoid duplicate processing and show posted, skipped, failed, or attention-needed outcomes — shipped in v1.0
- Frontend provides an operational intake workspace for voucher source uploads, bank CSV uploads, scan status, and review/correction loops — shipped in v1.0
- Deployment instructions are clear enough for a non-expert small-company owner to deploy Bok using the existing Docker-based LAN path — validated in Phase 04
- Terraform/Hetzner documentation is excluded from the recommended deployment path and treated as outside the current validated route — validated in Phase 04
- Operational deployment instructions now cover updates, backup, restore, rollback, troubleshooting, and support diagnostics — shipped in v1.1
- Secret setup guidance now briefly explains required values, where they are used, and how to generate example values — shipped in v1.1
- Agent can discover how to connect to a deployed Bok instance via a stable unauthenticated entrypoint — shipped in v1.2, Phase 6
- Agent API startup flow is coherent enough for an external HTTP agent to begin bookkeeping without manual reverse engineering — shipped in v1.2, Phase 6
- Deployment documentation explains how to configure an OpenClaw-style agent for Bok — shipped in v1.2, Phase 7
- Documentation examples are checked against actual route paths and auth behavior with deterministic tests — shipped in v1.2, Phase 7

### Active

- [ ] Persistent, revocable per-agent API keys with audit metadata (KEYS-01)
- [ ] MCP adapter for selected agent workflow operations (MCP-01)
- [ ] Durable idempotency keys for retry-safe agent posting (IDEM-01)

### Out of Scope

- Pre-posting approval as the default workflow — the product goal is automation with as little user interaction as possible.
- External accountant workflow management — the app is meant to reduce dependency on accountants, not coordinate handoff to them.
- Full Open Banking integration as a prerequisite for intake — v1 can use uploaded bank statements/status files.
- Replacing append-only correction semantics with direct edits to posted vouchers — BFL-aligned immutability remains central.
- Backend-only bookkeeping judgement — the backend validates formal constraints, while the agent makes the accounting decision from instructions, history, source material, and corrections.

## Context

The repository contains a layered monolith: FastAPI routes in `api/routes`, business services in `services`, SQL repositories in `repositories`, migrations in `db/migrations`, and a Next.js frontend under `frontend-v3`. SQLite is the active persistence engine, with local filesystem storage for voucher attachments, intake source material, and bank input files.

The existing architecture is intentionally agent-friendly. The agent reads accounting and invoicing instructions, historical posted vouchers, invoices, and correction history, then posts vouchers through the agent API. This means intake should extend the agent context model rather than create a separate bookkeeping path.

Known codebase concerns relevant to this work:

- File retrieval should enforce that persisted paths remain under their configured storage roots before download/delete.
- API key lifecycle endpoints are placeholder-like; production agent authentication currently relies on `BOKFOERING_API_KEY` or JWT.
- Several route handlers use broad exception conversion, so new intake APIs should prefer typed errors and stable response payloads.
- SQLite and local filesystem storage are acceptable for the small-company/self-hosted target but should keep file lifecycle and backup behavior explicit.
- The main worktree frontend build is still affected by a pre-existing ignored `.next` ownership issue; clean-copy builds passed during v1.0 verification.
- Phase 1 is missing aggregate verification documentation and should be repaired before relying on milestone audit scores for historical reporting.

## Constraints

- **Compliance**: Posted vouchers must remain immutable and corrections must happen through correction vouchers — required for Swedish bookkeeping durability and auditability.
- **Automation first**: Intake should support direct agent posting by default — the project exists to minimize user interaction.
- **Traceability**: Every agent-posted voucher created from intake must remain linked to its source files and user explanation — necessary for review, audit, and correction learning.
- **Input separation**: Voucher source material and bank statements/statuses should be uploaded and modeled separately — they play different roles in the agent's decision process.
- **Storage**: Initial implementation should fit the existing SQLite plus local filesystem architecture — consistent with current deployment and backup model.
- **Frontend**: The UI should be an operational work surface, not a landing page — users need to upload, scan status, and review outcomes efficiently.
- **Security**: File-serving paths must be constrained to the configured attachment/intake storage root — existing codebase concern and high-risk surface.
- **Deployment scope**: Docker-based deployment remains the validated path; agent setup documentation should build on the existing LAN-first deployment guide.
- **Agent integration scope**: v1.2 prioritizes HTTP/API-key agent connectivity; MCP is deferred unless implementation reveals a small compatibility or documentation-only path.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Treat this as a brownfield project | The app already has backend, frontend, agent integration, attachments, bank import, and core bookkeeping workflows | Good — all milestones built on validated foundations |
| Default agent behavior is direct posting from intake | The product goal is automated bookkeeping with as little user interaction as possible | Good — v1.0 shipped this; v1.2 extends agent connectivity without changing the core flow |
| Use corrections as the learning loop | Mistakes are expected to be corrected by the user through B-series correction vouchers, and those corrections become future agent context | Good — correction history is exposed to agent context and used for learning |
| Bank statements/statuses are source input for voucher creation | Uploaded bank data should help the agent create missing vouchers, not only reconcile already-created ones | Validated in Phase 02 with bank CSV inputs and bank-driven agent posting safeguards |
| Keep voucher source uploads separate from bank statement uploads | Receipts/invoices and bank statements represent different evidence types and need different lifecycle handling | Validated in Phase 02 with `bank_inputs` separate from `intake_sources` |
| Preserve backend validation boundaries | The agent decides bookkeeping treatment; backend enforces balance, periods, accounts, immutability, and audit rules | Validated in Phase 02 by keeping bank-driven posting on `LedgerService` and adding transaction reuse guardrails |
| Keep source material review separate from manual voucher attachments | Intake evidence and manual attachments have different lifecycle and audit semantics | Validated in Phase 03 with voucher `source-context` sections distinct from `Bilagor` |
| Use dedicated human review endpoints instead of the agent queue for the frontend | The frontend needs status counts, details, and linked voucher navigation beyond agent work-queue shape | Validated in Phase 03 with `/api/v1/intake/workspace` and detail routes |
| Accept v1.0 with known verification debt | The implementation and integration checks were acceptable, but Phase 1 lacked aggregate verification evidence | Accepted at milestone close; tracked as deferred tech debt |
| Keep v1.1 deployment-focused and Docker-first | The immediate need is clear deployment instructions for a non-expert owner, not new infrastructure behavior | Validated in Phase 04 with LAN-first `DEPLOYMENT.md` |
| Mark Terraform/Hetzner docs outdated for now | The current milestone should prevent accidental reliance on stale infrastructure docs without spending scope on repairing them | Validated in Phase 04 by excluding Terraform/Hetzner from the recommended path |
| Close v1.1 with acknowledged process gaps | Milestone scope shipped, but the dedicated milestone audit and Phase 5 security review were skipped at close | Accepted as deferred process debt at v1.1 milestone close |
| Prioritize HTTP agent onboarding over MCP for v1.2 | The immediate need is connecting an OpenClaw-style agent that can call REST APIs with an API key or bearer token | Good — entrypoint, ping, and deployment docs now support this; MCP deferred |
| Entrypoint returns only static metadata and settings.api_version | Prevents unauthenticated company-state leakage | Good — no auth dependencies or repositories in the entrypoint route |
| Remove misleading placeholder routes instead of deprecating them | Prevents agents from discovering and attempting to use non-functional endpoints | Good — tests confirm routes are gone and README points to truthful paths |
| LAN-first agent setup with shell variables in docs | Avoids inline secrets and matches existing deployment doc tone | Good — `BOK_API_URL` and `API_KEY` pattern used throughout |
| Verify deployment docs with deterministic pytest assertions | Replaces manual doc review with automated regression detection | Good — 25 assertions in `tests/test_deployment_docs.py` cover content and routes |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `$gsd-transition`):
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to Active
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone** (via `$gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check -> still the right priority?
3. Audit Out of Scope -> reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-05 after v1.2 milestone completion*
