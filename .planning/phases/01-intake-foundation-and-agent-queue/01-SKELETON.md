# Walking Skeleton - Bok

**Phase:** 1
**Generated:** 2026-05-14
**Mode:** Brownfield MVP skeleton

## Capability Proven End-to-End

A signed-in/API-key-authenticated caller can upload one voucher source file, have the backend persist its metadata and original file, let the agent post a voucher from that source through the existing ledger validation path, and later prove the posted voucher is linked back to the source material.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Backend framework | FastAPI route modules under `api/routes` | Existing API stack and tests already use FastAPI and `TestClient`. |
| Data layer | SQLite with handwritten migrations and repository classes | Existing deployment and backup model are SQLite-first; repositories already isolate SQL. |
| File storage | Local filesystem under `INTAKE_DIR` | Matches current local-volume architecture while separating intake source material from voucher attachments. |
| Auth | Existing bearer API key/JWT dependency via `get_current_actor` | Keeps Phase 1 additive and compatible with current agent calls. |
| Agent path | Extend `POST /api/v1/agent/vouchers` and add queue endpoints under `/api/v1/agent/intake` | Preserves the current direct-posting workflow and avoids a separate approval queue. |
| Traceability | `voucher_intake_sources` plus `intake_processing_attempts` | Keeps posted vouchers immutable while preserving source-to-voucher and processing-history evidence. |
| Frontend | Deferred to Phase 3 | Phase 1 is backend foundation; frontend workspace is explicitly later roadmap scope. |

## Stack Touched in Phase 1

- [x] Project scaffold already exists: FastAPI backend, Next.js frontend, SQLite migrations, pytest.
- [x] Routing already exists: `api/main.py` registers route modules.
- [ ] Database: add intake source, processing attempt, and voucher link tables.
- [ ] API: add human intake upload/download and agent queue/outcome endpoints.
- [ ] Agent workflow: post a voucher through `LedgerService` and link it to intake source material.
- [ ] Deployment/local run: existing `pytest` and app startup paths remain valid after router/migration additions.

## Out of Scope

- Bank statement/status intake.
- Frontend intake workspace.
- OCR or text extraction from source files.
- Multi-file intake batches.
- Pre-posting approval queue.
- DB-backed agent API key lifecycle.
- Object storage or retention policies.

## Subsequent Slice Plan

- Phase 2: add bank statement/status intake and bank-aware direct posting context.
- Phase 3: add frontend intake workspace and review loop.
