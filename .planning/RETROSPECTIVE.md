# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.2 — Agent Onboarding

**Shipped:** 2026-06-05
**Phases:** 2 | **Plans:** 4 | **Tasks:** 10

### What Was Built

- Public-safe unauthenticated agent instruction entrypoint at `/api/v1/agent-instructions/entrypoint` with service identity, auth guidance, ordered startup workflow, guardrails, and unsupported-feature disclosure.
- Removed placeholder agent routes (keys, spec/tools, idempotency) and made agent ping dynamic with version, actor, and UTC timestamp.
- `DEPLOYMENT.md` OpenClaw/HTTP-agent setup section with shell-variable `curl` verification, frontend/backend URL separation, and setup-only starter prompt.
- Deterministic pytest suite (`tests/test_deployment_docs.py`) with 25 assertions verifying DEPLOYMENT.md content and documented route/auth behavior against the live FastAPI app.

### What Worked

- Converting instruction tests to async ASGI transport resolved the local TestClient hang and gave reliable route verification.
- Removing placeholder routes entirely (rather than deprecating) prevented agents from discovering broken endpoints.
- Using `pathlib.Path` + pytest assertions for doc verification created automated regression detection without requiring external tools.
- Shell-variable documentation pattern (`BOK_API_URL`, `API_KEY`) kept deployment docs safe from secret leakage.

### What Was Inefficient

- REQUIREMENTS.md checkboxes were not updated during Phase 7 execution, creating a 6-item gap between the phase SUMMARY.md records and the top-level requirements document. This required manual reconciliation at milestone close.
- No dedicated milestone audit was run before close (same gap as v1.1), making it harder to assess cross-phase integration independently.
- The date-sensitive test-data issue (May period vs June correction) was caught during verification but required an unplanned fix within the phase.

### Patterns Established

- Public agent discovery endpoints should be static and unauthenticated unless they need company state.
- Agent API tests should use `httpx.ASGITransport` async clients in this environment.
- Unsupported future features are disclosed through the entrypoint rather than placeholder endpoints.
- Deployment docs verify with `pathlib.Path` + pytest assertions, not manual review.
- Route docs verify with `httpx.ASGITransport` + async pytest fixtures.

### Key Lessons

1. Requirements traceability needs a check-in step during phase execution — not only at milestone boundaries.
2. Milestone audits should be run before close, even when phase-level verification exists, to catch cross-phase gaps.
3. Date-sensitive tests should create periods for the current date rather than hardcoding past months.
4. Documentation verification via source assertions is fast, deterministic, and catches regressions that human review misses.

### Cost Observations

- Model mix: not tracked.
- Sessions: not tracked.
- Notable: Phase 7 documentation work was concise (15 min each plan) because the route behavior was already stable from Phase 6. The verification plan added the most value by creating permanent regression detection.

---

## Milestone: v1.1 — Clear Instructions for Deployment

**Shipped:** 2026-06-04
**Phases:** 2 | **Plans:** 6 | **Tasks:** 18

### What Was Built

- Owner-facing Docker deployment and operations documentation for LAN/local installs.
- Production environment template mirroring LAN deployment defaults.
- README routing users to canonical LAN-first guide.
- `DEPLOYMENT.md` covering updates, rollback, backup/restore, troubleshooting, and support diagnostics.
- `terraform/README.md` marked outdated and excluded from recommended path.

### What Worked

- Focusing on documentation-only changes for v1.1 avoided code churn while delivering high owner value.
- LAN-first approach aligned with the self-hosted small-company target.

### What Was Inefficient

- Milestone closed without running a dedicated milestone audit or Phase 5 security review.
- The decision to skip these was accepted as process debt, which then carried into v1.2.

### Patterns Established

- Swedish, pragmatic, LAN-first documentation tone.
- Explicit warnings when infrastructure docs are not the validated path.

### Key Lessons

1. Skipping audits creates compounding process debt. Each skipped audit makes the next milestone close harder to validate.

### Cost Observations

- Notable: The v1.1 scope was well-contained and shipped quickly, but process shortcuts created tracking overhead for future milestones.

---

## Milestone: v1.0 — Intake Automation

**Shipped:** 2026-05-18
**Phases:** 3 | **Plans:** 9 | **Sessions:** n/a

### What Was Built

- SQLite-backed intake source storage with duplicate hash rejection and root-contained local file resolution.
- Authenticated intake upload/download routes plus agent pending queue and processing outcome APIs.
- Agent-posted vouchers can consume intake sources and preserve durable source, link, and processing history.
- Separate bank CSV input storage imports supported Swedish bank formats and links imported rows to source files.
- Bank-driven agent posting rejects booked or matched transaction reuse before ledger posting.
- Frontend intake workspace, intake detail pages, and voucher review sections expose source files, processing notes, and correction-learning context.

### What Worked

- Keeping agent posting on `LedgerService` preserved existing accounting validation while adding intake traceability around it.
- Separating voucher source material from bank input records kept the domain model clear and matched the requirements.
- Clean-copy frontend builds avoided the local `.next` ownership issue without changing committed source behavior.

### What Was Inefficient

- Phase 1 did not get an aggregate `01-VERIFICATION.md`, which later blocked a clean milestone audit.
- The local Python 3.14 TestClient/AnyIO hang forced some route verification into direct route-function tests instead of full ASGI request tests.
- Frontend verification needed repeated clean-copy builds because the main worktree `.next` directory has stale ownership.

### Patterns Established

- Intake and bank file downloads resolve stored paths through service-owned root containment checks before `FileResponse`.
- Agent direct posting uses preflight checks, ledger posting, and post-success traceability linking in one transaction.
- Human review APIs use `kind` discriminators for unified voucher-source and bank-input views.

### Key Lessons

1. Phase-level verification artifacts need to be generated as part of closeout, even when plan-level summaries and tests exist.
2. File-source features should always pair metadata persistence, duplicate detection, and root-contained file serving in the same service boundary.
3. Operational frontend tables need shell-level `min-w-0` and local scrolling checks, not only route-level rendering checks.

### Cost Observations

- Model mix: not tracked.
- Sessions: not tracked.
- Notable: The milestone moved quickly once the source/bank separation was explicit, but missing verification artifacts created avoidable closeout overhead.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.0 | n/a | 3 | Established GSD milestone archival and highlighted the need for phase-level verification completeness. |
| v1.1 | n/a | 2 | Deployment-only milestone; skipped audit created process debt. |
| v1.2 | n/a | 2 | Added deterministic doc verification tests and async ASGI transport pattern for reliable route testing. |

### Cumulative Quality

| Milestone | Tests | Coverage | Zero-Dep Additions |
|-----------|-------|----------|-------------------|
| v1.0 | Focused backend tests, frontend lint/build, viewport smoke checks | Not measured | No new frontend runtime libraries for intake UI |
| v1.1 | Existing tests + doc verification | Not measured | No new dependencies |
| v1.2 | 25 doc assertions + 23 agent route tests | Entrypoint, ping, docs, auth | No new runtime dependencies |

### Top Lessons (Verified Across Milestones)

1. Keep future milestone audits strict about missing phase verification artifacts before allowing archive.
2. Requirements traceability needs check-ins during execution, not just at boundaries.
3. Async ASGI transport tests are the reliable pattern in this environment; avoid synchronous TestClient for new route tests.
4. Documentation verification via source assertions catches regressions that human review misses.
5. Skipping audits compounds process debt across milestones.
