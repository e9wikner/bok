# Codebase Concerns

**Analysis Date:** 2026-05-14

## Tech Debt

**Error handling across API routes and services:**
- Issue: Broad `except Exception` handlers convert domain failures to generic HTTP errors and hide root causes.
- Files: `api/routes/periods.py`, `api/routes/vouchers.py`, `api/routes/invoices.py`, `api/routes/export_pdf.py`, `api/routes/import_sie4.py`, `services/sie4_import.py`
- Impact: Hard-to-diagnose production issues, inconsistent status codes, and fragile client behavior.
- Fix approach: Replace broad catches with typed exception mapping (`ValidationError`, repository errors, parse errors), and add structured error payloads with stable error codes.

**Monolithic accounting import/export services:**
- Issue: Very large service files contain parsing, validation, transformation, and persistence logic in single modules.
- Files: `services/sie4_import.py`, `services/sru_export.py`, `services/pdf_export.py`, `services/ledger.py`
- Impact: High change risk, poor test targeting, and regression-prone refactors.
- Fix approach: Split into submodules by responsibility (parser, validators, mappers, persistence coordinator) and add interface-level tests per module boundary.

**Non-atomic repository updates in multi-step flows:**
- Issue: Repository methods commit repeatedly inside loops and staged operations.
- Files: `repositories/invoice_draft_repo.py`
- Impact: Partial writes on mid-operation failure (rows deleted but not fully recreated), inconsistent draft totals, and repair burden.
- Fix approach: Wrap `replace_rows` and related update paths in `db.transaction()` and move commit responsibility to service-layer operation boundaries.

## Known Bugs

**Agent API key lifecycle endpoints return mock data and do not persist state:**
- Symptoms: API key creation/list/revoke responses look successful, but keys are not stored or enforced.
- Files: `api/routes/agent.py`
- Trigger: Calling `/api/v1/agent/keys/create`, `/api/v1/agent/keys`, or `/api/v1/agent/keys/{key_id}/revoke`.
- Workaround: Use static `BOKFOERING_API_KEY` or JWT auth from `api/routes/auth.py` and avoid these endpoints for real credential management.

**K2 PDF export intentionally unimplemented at runtime:**
- Symptoms: `NotImplementedError` when requesting PDF generation for K2 reports.
- Files: `services/k2_report.py`
- Trigger: Any call path that invokes `generate_k2_pdf`.
- Workaround: Use JSON export path (`export_k2_json`) until PDF generation is implemented.

## Security Considerations

**Unsafe default credentials and wildcard CORS:**
- Risk: Default auth and API secrets can be used if env config is missed; permissive CORS allows any origin.
- Files: `config.py`, `api/main.py`, `docker-compose.local.yml`
- Current mitigation: Environment-variable overrides exist.
- Recommendations: Fail fast on insecure defaults outside local dev, require strong secrets at startup, and restrict `CORS_ORIGINS` to explicit allowlists.

**Single shared actor identity weakens auditability:**
- Risk: Most authenticated requests are logged as `"api"` regardless of caller identity.
- Files: `api/deps.py`
- Current mitigation: JWT validation is supported.
- Recommendations: Extract and propagate JWT subject in `get_current_actor` and include key/user identifiers in audit events.

**Attachment retrieval trusts persisted path without root-path enforcement:**
- Risk: If `stored_path` is manipulated in DB, file responses can serve arbitrary filesystem paths readable by the process.
- Files: `api/routes/attachments.py`
- Current mitigation: Attachment records are looked up by `voucher_id` and `attachment_id`.
- Recommendations: Enforce that resolved `stored_path` is under `ATTACHMENTS_DIR` before serving/deleting; reject paths outside storage root.

## Performance Bottlenecks

**N+1 draft loading and row lookups:**
- Problem: Listing drafts queries IDs first, then loads each draft and rows individually.
- Files: `repositories/invoice_draft_repo.py`
- Cause: `list_all()` calls `get()` for each result (`SELECT id ...` followed by per-draft queries).
- Improvement path: Use a single joined query for list responses or batched row fetch with in-memory grouping.

**Per-row article lookups in response shaping:**
- Problem: Invoice draft serialization performs repeated article fetches.
- Files: `api/routes/invoice_drafts.py`
- Cause: `_draft_row_to_dict` calls `ArticleRepository.get(...)` per row.
- Improvement path: Preload article metadata per draft response and map by `article_id`.

**Heavy accounting computations run synchronously in request paths:**
- Problem: Export/report calculations perform wide scans and transformations during API request execution.
- Files: `services/sru_export.py`, `services/sie4_export.py`, `services/vat_report.py`, `api/routes/export_sru.py`, `api/routes/export_sie4.py`
- Cause: No caching/materialized summaries and limited pagination/chunking strategy for large fiscal years.
- Improvement path: Introduce precomputed period/fiscal aggregates and optional async job-based export for large datasets.

## Fragile Areas

**SIE4 import pipeline:**
- Files: `services/sie4_import.py`, `api/routes/import_sie4.py`, `tests/test_sie4_integration.py`, `tests/test_sie4_multi_period.py`
- Why fragile: Mixed responsibilities, permissive exception swallowing, and format/encoding edge cases increase regression risk.
- Safe modification: Change parser logic behind targeted fixture-based tests and preserve current validation contracts for voucher/account creation.
- Test coverage: Core flows are tested, but negative-path and partial-failure recovery coverage is still limited.

**Posting flow with best-effort opening-balance side effects:**
- Files: `services/ledger.py`, `services/opening_balance.py`
- Why fragile: Posting silently ignores exceptions from next-year opening-balance updates.
- Safe modification: Isolate side effects into explicit post hooks with structured failure logging and retry strategy.
- Test coverage: Ledger unit tests exist (`tests/test_ledger.py`), but resilience scenarios for failed post-hooks are not comprehensive.

## Scaling Limits

**SQLite write concurrency ceiling:**
- Current capacity: Single-node SQLite with WAL and thread-local connections.
- Limit: Write-heavy concurrent workloads will serialize on DB locks and degrade API latency.
- Scaling path: Migrate to PostgreSQL for multi-writer production traffic; keep repository interfaces DB-agnostic to support transition.

**Attachment storage on local filesystem:**
- Current capacity: Local disk under `ATTACHMENTS_DIR` with no lifecycle policy.
- Limit: Storage growth and backup/retention become operational bottlenecks at scale.
- Scaling path: Move attachment blobs to object storage with content-addressed keys and retention controls.

## Dependencies at Risk

**No persistence-backed auth provider despite expanded auth surface:**
- Risk: Auth/account management behavior relies on env variables and mock key endpoints instead of durable identity/key records.
- Impact: Operational auth workflows (rotation, revocation, scoped access) are unreliable.
- Migration plan: Implement DB-backed users/API keys with hashed secrets, rotation metadata, and revocation checks in `verify_api_key`.

## Missing Critical Features

**Real API key management and enforcement:**
- Problem: Agent key endpoints are placeholders and disconnected from request authentication.
- Blocks: Secure per-agent onboarding, key rotation, scoped permission enforcement, and trustworthy audit attribution.

**Consistent structured error contract:**
- Problem: Error responses vary across routes and often stringify exceptions directly.
- Blocks: Reliable client-side retry/error handling and stable observability dashboards.

## Test Coverage Gaps

**Attachment security and path-safety behavior:**
- What's not tested: Path-root enforcement and malicious/invalid stored-path handling during download/delete.
- Files: `api/routes/attachments.py`
- Risk: Path traversal-style file exposure can regress without detection.
- Priority: High

**Auth edge cases and actor propagation:**
- What's not tested: Distinguishing API-key vs JWT actor identity and ensuring audit actor fidelity.
- Files: `api/deps.py`, `services/auth.py`, `api/routes/auth.py`
- Risk: Authorization and audit regressions may ship undetected.
- Priority: High

**Failure recovery for multi-step draft mutation:**
- What's not tested: Mid-transaction failures during row replacement/update and rollback behavior.
- Files: `repositories/invoice_draft_repo.py`, `services/invoice_draft.py`
- Risk: Partial data persistence and inconsistent totals.
- Priority: Medium

---

*Concerns audit: 2026-05-14*
