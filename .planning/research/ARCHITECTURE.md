# Architecture Research

**Domain:** Swedish small-company bookkeeping source-material intake for AI-agent posting
**Researched:** 2026-05-14
**Confidence:** HIGH

## Standard Architecture

### System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│                        Frontend                              │
│  Intake upload  │  Intake status  │  Voucher review          │
└────────────┬──────────────┬──────────────┬───────────────────┘
             │              │              │
             ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────┐
│                       FastAPI Routes                         │
│  /intake/sources  │  /intake/bank-statements  │  /agent/intake │
└────────────┬──────────────┬──────────────────────┬─────────────┘
             │              │                      │
             ▼              ▼                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    Domain Services                           │
│  IntakeService  │  BankIntegrationService  │  LedgerService    │
└────────────┬──────────────┬──────────────────────┬─────────────┘
             │              │                      │
             ▼              ▼                      ▼
┌─────────────────────────────────────────────────────────────┐
│                  Persistence + File Storage                   │
│  SQLite intake tables  │  bank_transactions  │  source files    │
└─────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| Intake source routes | Upload/list/download source files and metadata | New `api/routes/intake.py` with multipart upload and typed schemas. |
| Intake service | Validate file type/size, store files, hash content, manage lifecycle | New `services/intake.py` with repository calls and storage helpers. |
| Intake repository | Persist source records, processing attempts, source-voucher links | New `repositories/intake_repo.py` and migration. |
| Agent intake route | Return pending work and allow marking processed/skipped/failed | Extend `api/routes/agent.py` or add dedicated `api/routes/agent_intake.py`. |
| Bank statement intake | Store uploaded bank files and import parseable CSV rows | Integrate with existing `services/bank_integration.py`. |
| Voucher linkage | Connect posted vouchers to intake source IDs | Add link table or nullable source reference depending on many-to-many needs. |
| Review UI | Show uploaded source material on intake and voucher pages | New frontend intake page plus extension of voucher detail attachments/source panel. |

## Recommended Project Structure

```text
api/
├── routes/
│   ├── intake.py              # Human upload/list/download APIs
│   └── agent_intake.py        # Agent pending queue and processing status APIs
services/
├── intake.py                  # Intake lifecycle and storage orchestration
repositories/
├── intake_repo.py             # SQLite persistence for intake records and links
db/
├── migrations/
│   └── 018_add_intake_sources.sql
frontend-v3/
├── app/
│   └── intake/
│       └── page.tsx           # Upload and status workspace
├── lib/
│   └── api.ts                 # Intake client functions/types
└── hooks/
    └── useData.ts             # React Query hooks if following existing pattern
```

### Structure Rationale

- **`services/intake.py`:** Intake has business lifecycle rules; keep them out of route handlers.
- **`repositories/intake_repo.py`:** Existing backend uses repository-by-convention over handwritten SQL.
- **Separate human and agent routes:** Human upload APIs and agent work-queue APIs have different consumers and response shapes.
- **Migration-first schema:** Intake state must survive restarts and be auditable.

## Architectural Patterns

### Pattern 1: Source Record Plus Immutable Original File

**What:** Store file metadata in SQLite and original bytes on disk, keyed by source ID and SHA-256.
**When to use:** All uploaded receipts, invoices, and bank statements.
**Trade-offs:** Simple and compatible with current storage; requires backup discipline and path safety.

### Pattern 2: Processing Attempt Log

**What:** Each agent processing pass creates an attempt record with status, notes, errors, voucher IDs, and timestamps.
**When to use:** Direct posting from autonomous agent.
**Trade-offs:** More schema up front, but essential for review and debugging.

### Pattern 3: Many-to-Many Source/Voucher Links

**What:** Link intake source IDs to voucher IDs through a join table.
**When to use:** A voucher may be based on receipt plus bank statement row, or one bank statement may produce many vouchers.
**Trade-offs:** Slightly more complex than a nullable `voucher_id`, but much safer for bank statement batches and evidence bundles.

## Data Flow

### Voucher Source Intake Flow

```text
User uploads receipt/invoice + explanation
    ↓
POST /api/v1/intake/sources
    ↓
IntakeService validates type/size, hashes, stores original file
    ↓
intake_sources row created with status=pending
    ↓
Agent calls /api/v1/agent/intake/pending
    ↓
Agent downloads source file, reads hint/history/instructions
    ↓
Agent posts voucher via existing agent voucher API
    ↓
Agent marks intake processed with voucher link and processing notes
    ↓
User reviews posted voucher; correction flow remains existing B-series path
```

### Bank Statement Intake Flow

```text
User uploads bank statement/status file
    ↓
POST /api/v1/intake/bank-statements
    ↓
Store original statement file and metadata
    ↓
If CSV parseable, import transactions through BankIntegrationService
    ↓
Agent sees bank statement batch and/or imported transactions in pending context
    ↓
Agent creates missing vouchers and links outputs to bank source/transactions
```

### State Management

```text
pending -> processing -> processed
                    ├── failed
                    ├── skipped
                    └── needs_attention
```

Use explicit statuses instead of deleting processed rows from the queue.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Single small company | SQLite plus local filesystem is acceptable. |
| Many companies/tenants | Add tenant scoping to intake records and storage paths; audit actor identity becomes more important. |
| Large file volume | Move files to object storage and keep content-addressed metadata in DB. |

### Scaling Priorities

1. **First bottleneck:** File lifecycle/backup discipline. Fix with storage root organization, hashes, and retention policy.
2. **Second bottleneck:** Bank statement duplicate matching. Fix with stronger transaction identity and source batch links.
3. **Third bottleneck:** SQLite write contention. Fix with PostgreSQL only when actual write concurrency requires it.

## Anti-Patterns

### Anti-Pattern 1: Attachment-Only Intake

**What people do:** Force users to create a voucher before they can upload evidence.
**Why it's wrong:** The agent needs evidence before a voucher exists.
**Do this instead:** Add intake sources as first-class records and link them to vouchers after posting.

### Anti-Pattern 2: No Original File Preservation

**What people do:** Extract text and discard the source file.
**Why it's wrong:** Swedish accounting records and review workflows depend on original source traceability.
**Do this instead:** Preserve original files and store derived text/notes only as supplemental metadata.

### Anti-Pattern 3: One Bank Statement Equals One Voucher

**What people do:** Model a statement upload as if it maps directly to one accounting entry.
**Why it's wrong:** One statement contains many transactions, and some match existing invoices/payroll/vouchers.
**Do this instead:** Model statement batches, imported rows, and many-to-many voucher links.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| External AI agent/Openclaw | Authenticated API polling and downloads | Keep binary source access explicit and audit logged. |
| Future Open Banking provider | Optional later bank connection | Not required for v1 because user selected uploaded statements/statuses. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Intake -> Agent | Dedicated pending queue API | Include source metadata, file URLs, user hints, and prior attempts. |
| Intake -> Ledger | Agent posts through existing voucher API | Preserve backend validation boundaries. |
| Intake -> BankIntegration | Service call for CSV statements | Reuse existing import/dedup logic; link imported transactions to source batch. |
| Intake -> Corrections | Read correction history and source links | Use corrections as learning context. |

## Sources

- Existing codebase architecture map and README/API docs.
- Sveriges Riksdag, Bokföringslag (1999:1078), 5 kap. and 7 kap.
- BFNAR 2013:2, Chapter 5 verification guidance.

---
*Architecture research for: Swedish bookkeeping intake*
*Researched: 2026-05-14*
