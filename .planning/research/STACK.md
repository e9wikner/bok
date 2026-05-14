# Stack Research

**Domain:** Swedish small-company bookkeeping source-material intake for AI-agent posting
**Researched:** 2026-05-14
**Confidence:** HIGH

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.11 | Backend runtime | Already used by the FastAPI accounting backend and compatible with the current Docker/CI setup. |
| FastAPI | >=0.109.0 | Intake, file upload, and agent context APIs | Existing API framework; supports `UploadFile`/multipart flows and typed route schemas without adding a second backend surface. |
| SQLite | Current project DB | Intake metadata, lifecycle state, source-to-voucher links | Matches the self-hosted small-company target and the existing repository/migration pattern. |
| Local filesystem storage | Existing `ATTACHMENTS_DIR` pattern | Original PDF/image/bank-statement file storage | Fits current deployments and backup model; Swedish accounting records must remain available and preserved. |
| Next.js | 16.x | Upload/review frontend | Existing frontend stack; lets intake become part of the operational app instead of a separate tool. |
| React Query | Existing frontend dependency | Intake status and polling/caching | Existing data-fetching pattern in `frontend-v3/hooks/useData.ts`. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `hashlib` | stdlib | SHA-256 deduplication and file integrity | Always for uploaded source files and bank files. |
| `pathlib` | stdlib | Safe storage path construction | Always for file paths; combine with root-path enforcement before serving/deleting files. |
| `csv` | stdlib | Swedish bank CSV parsing | Continue using for bank statement/status uploads when the input is CSV. |
| `python-multipart` | Existing transitive/runtime dependency | Multipart file upload support | Needed by FastAPI `UploadFile` endpoints. |
| `pydantic` | Existing dependency | Intake request/response schemas | Keep all API contracts typed and documented. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| Pytest | Backend tests | Add tests for intake lifecycle, file safety, agent queue consumption, and source-to-voucher linking. |
| Playwright | Frontend/E2E tests | Useful for upload workflow and review/status pages. |
| Alembic-style SQL migrations | Schema changes | Follow existing `db/migrations/*.sql` convention. |

## Installation

No new core dependency is required for the first intake slice. The safest v1 is metadata plus file storage plus agent-readable APIs.

```bash
# Backend: keep existing requirements.txt unless implementation adds OCR/parsing.
# Frontend: keep existing frontend-v3 package set unless UI needs a new upload widget library.
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Local filesystem source storage | S3-compatible object storage | Use object storage after storage volume growth, multi-node deployment, or retention lifecycle needs exceed local disk. |
| Agent reads original files via API | Backend OCR/extraction pipeline | Add OCR only if the external agent cannot inspect PDFs/images reliably or if offline indexing becomes required. |
| SQLite intake tables | PostgreSQL | Move when concurrent writes, larger attachment indexing, or multi-user production scale exceed SQLite's write limits. |
| Direct agent posting from intake | Human approval queue | Use approval only for high-risk workflows if automation accuracy proves insufficient. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Storing uploaded file bytes in SQLite | Bloats DB backups, complicates streaming/download, and differs from existing attachment storage | Store files on disk and metadata in SQLite. |
| Treating uploaded source files as temporary prompts | Source material can be accounting information and must remain traceable and retainable | Persist original files with hashes and voucher links. |
| A separate intake microservice | Adds deployment/auth complexity for a small self-hosted monolith | Add an intake domain/service/routes within the existing backend. |
| OCR as mandatory v1 behavior | Adds dependency and accuracy risk before the agent workflow is proven | Expose original files and user hints to the agent first. |

## Stack Patterns by Variant

**If the agent can read files directly from the API:**
- Store original files and metadata only.
- Provide authenticated download URLs and a concise pending-intake API.
- Let the agent inspect PDFs/images and decide voucher rows.

**If the agent cannot read binary files:**
- Add optional backend extraction later.
- Store extracted text as derived metadata while preserving the original file unchanged.

**If bank statement uploads are CSV:**
- Reuse and harden the existing bank CSV import path.
- Link imported transactions to intake batches and eventual vouchers.

**If bank statement uploads are PDF/images:**
- Store as bank statement intake source files first.
- Defer parsing to the agent or a later extraction phase.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| FastAPI >=0.109.0 | Pydantic existing project version | Use existing schemas and route style. |
| Next.js 16.x | React 18 | Existing frontend stack; no version change needed. |
| SQLite | Local filesystem storage | Store metadata and file paths; keep file path safety checks at API boundary. |

## Sources

- Existing repository docs and codebase map — stack, architecture, attachment, bank import, and agent integration status.
- Sveriges Riksdag, Bokföringslag (1999:1078) — current legal requirements for verifications and retention: https://www.riksdagen.se/sv/dokument-och-lagar/dokument/svensk-forfattningssamling/bokforingslag-19991078_sfs-1999-1078/
- Bokföringsnämnden, Limited companies — confirms Swedish AB bookkeeping, supporting voucher, archiving, and annual-report duties: https://www.bfn.se/english/what-applies-to/limited-companies/
- Bokföringsnämnden, Arkivering FAQ — practical guidance on preserving/transferring accounting information: https://www.bfn.se/fragor-och-svar/arkivering/

---
*Stack research for: Swedish bookkeeping intake*
*Researched: 2026-05-14*
