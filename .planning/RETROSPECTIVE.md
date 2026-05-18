# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

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

### Cumulative Quality

| Milestone | Tests | Coverage | Zero-Dep Additions |
|-----------|-------|----------|-------------------|
| v1.0 | Focused backend tests, frontend lint/build, viewport smoke checks | Not measured | No new frontend runtime libraries for intake UI |

### Top Lessons (Verified Across Milestones)

1. Keep future milestone audits strict about missing phase verification artifacts before allowing archive.
