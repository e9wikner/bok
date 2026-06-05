# Architecture Research: Agent Usability & Feedback Loop

**Project:** Bok (v1.3 Agent Usability & Feedback Loop)
**Domain:** Self-hosted Swedish bookkeeping with AI-agent automation
**Researched:** 2026-06-05
**Confidence:** HIGH

## Executive Summary

The v1.3 milestone introduces five agent-usability features into an existing layered monolith (FastAPI routes, business services, SQL repositories, SQLite, Next.js frontend). All five features extend existing tables and workflows rather than requiring new subsystems. The dominant architectural theme is **enriching the agent context model** — every feature adds data that the agent reads before posting vouchers, while the backend continues to enforce BFL/BFNAR immutability constraints.

The work is brownfield: every feature touches existing migrations, repositories, services, routes, and frontend surfaces. The recommended build order follows dependency chains: schema changes first, then repository/service layers, then route handlers, then frontend work surfaces.

## System Overview (Target State)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Frontend (Next.js)                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐ │
│  │ Intake       │  │ Voucher      │  │ Agent        │  │ Correction       │ │
│  │ Workspace    │  │ Detail       │  │ Instructions │  │ Note Dialog      │ │
│  │ (upload +    │  │ (source      │  │ (read +      │  │ (text note →    │ │
│  │  review)      │  │  context +   │  │  update)     │  │  agent suggest)  │ │
│  │              │  │  correction) │  │              │  │                  │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘ │
│         │                 │                 │                   │           │
├─────────┴─────────────────┴─────────────────┴───────────────────┴───────────┤
│                         FastAPI Route Layer                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐ │
│  │ /intake/*    │  │ /agent/*     │  │ /vouchers/*  │  │ /agent-          │ │
│  │ (link, skip, │  │ (pending,    │  │ (correct,    │  │ instructions/*   │ │
│  │  update)      │  │  post)       │  │  source-ctx) │  │ (update by      │ │
│  │              │  │              │  │              │  │  agent or user)  │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘ │
│         │                 │                 │                   │           │
├─────────┴─────────────────┴─────────────────┴───────────────────┴───────────┤
│                         Service Layer                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐ │
│  │ IntakeService│  │ BankInput    │  │ LedgerService│  │ (new)            │ │
│  │ (dedup,      │  │ Service      │  │ (correction  │  │ CorrectionNote   │ │
│  │  link, skip)  │  │ (matchable   │  │  helper)     │  │ Service          │ │
│  │              │  │  tx exposure)│  │              │  │ (text note CRUD) │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘ │
│         │                 │                 │                   │           │
├─────────┴─────────────────┴─────────────────┴───────────────────┴───────────┤
│                         Repository Layer (SQLite)                           │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐ │
│  │ IntakeRepo   │  │ BankInputRepo│  │ VoucherRepo  │  │ AgentInstrRepo │ │
│  │ (existing +  │  │ (existing +  │  │ (existing)   │  │ (existing +    │ │
│  │  new methods) │  │  new methods)│  │              │  │  agent_writer)  │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────────┘ │
│  ┌──────────────────────────────────────────────────────────────────────────┐ │
│  │ (new) CorrectionNoteRepo                                               │ │
│  │  CRUD + list_by_voucher + list_pending_for_agent                       │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Feature Integration Points

### 1. Intake Deduplication / Linking (DEDUP-01)

**Current gap:** Already-posted intake items remain in `pending` state if the agent posted a voucher from them but the link wasn't recorded, or if the voucher was created outside the agent flow.

**Integration approach:**

| Layer | Change | New or Modified |
|-------|--------|-----------------|
| Schema | Add `intake_source_link` table (or extend `voucher_intake_sources` with a `manual_link` boolean) | Modified migration |
| Repository | `IntakeRepository.link_to_existing_voucher()`, `mark_skipped()`, `find_by_sha256_or_filename()` | Modified |
| Service | `IntakeService.link_existing_voucher()` already exists; add `skip_source()`, `find_duplicate_candidates()` | Modified |
| Routes | `POST /api/v1/intake/{id}/link-to-voucher`, `POST /api/v1/intake/{id}/skip` | New endpoints |
| Frontend | Intake detail page gets "Länka till verifikation" and "Markera som hanterad" actions | Modified |

**Data flow:**
```
User selects intake item → Frontend calls /link-to-voucher or /skip
    ↓
IntakeService.validate_source_is_pending() → IntakeRepository.update_status(processed/skipped)
    ↓
If link: IntakeRepository.create_voucher_link(intake_id, voucher_id, linked_by=user, link_reason="manual_dedup")
    ↓
Agent's pending queue no longer includes the item
```

**Key design decision:** Re-use the existing `voucher_intake_sources` linkage table. The `link_reason` column already distinguishes `agent_posted_voucher` from manual links. Add `link_reason="manual_dedup"` for user-initiated links.

### 2. Bank Transaction Matchability (MATCH-01)

**Current gap:** Imported bank transactions exist in `bank_transactions` but are not exposed as individually matchable entities through the agent API. The agent only sees `bank_input` files and their aggregate `transaction_ids`.

**Integration approach:**

| Layer | Change | New or Modified |
|-------|--------|-----------------|
| Schema | `bank_transactions` already has `status`, `matched_voucher_id`, `booked_at` | No schema change |
| Repository | `BankInputRepository.list_unmatched_transactions()`, `get_transaction_detail()` | Modified |
| Service | `BankInputService.agent_matchable_transactions()` — filters for `status != 'booked'` and `matched_voucher_id IS NULL` | Modified |
| Routes | `GET /api/v1/agent/bank-transactions/matchable` | New endpoint |
| Agent entrypoint | Add step 5b: read matchable bank transactions | Modified |

**Data flow:**
```
Agent startup sequence → reads matchable bank transactions
    ↓
BankInputService.agent_matchable_transactions(limit, offset)
    ↓
BankInputRepository.list_unmatched_transactions()
    ↓
Returns: transaction id, amount, date, description, bank_connection_id, bank_input_id
    ↓
Agent creates voucher with bank_transaction_ids included
    ↓
Existing BankInputService.link_posted_voucher() marks them booked
```

**Key design decision:** No new table needed. The existing `bank_transactions` table already tracks `status` and `matched_voucher_id`. The new endpoint is a filtered view.

### 3. Agent Instruction Persistence (INSTR-01)

**Current gap:** Agent instructions have versioned documents (`agent_instruction_documents` + `agent_instruction_versions`), but there is no endpoint for the *agent* to update instructions based on what it learns. Only human users can call `PUT /api/v1/agent-instructions/accounting`.

**Integration approach:**

| Layer | Change | New or Modified |
|-------|--------|-----------------|
| Schema | No change — existing `agent_instruction_versions` supports any `created_by` value | No schema change |
| Repository | `AgentInstructionRepository.update()` already accepts `created_by` | No change |
| Service | Add `AgentInstructionService.append_learned_rule(markdown_fragment, change_summary, actor)` | New service (thin wrapper) |
| Routes | `POST /api/v1/agent/instructions/learn` — agent-only endpoint that appends a rule to company instructions | New endpoint |
| Auth | Re-use existing `get_current_actor()` — agent calls with its API key, actor = "agent" or configured agent identity | Modified |

**Data flow:**
```
Agent detects pattern from corrections → calls POST /agent/instructions/learn
    ↓
AgentInstructionService fetches current active instructions
    ↓
Appends markdown fragment under a "## Inlärda regler" heading
    ↓
AgentInstructionRepository.update(scope="accounting_company", ...)
    ↓
New version persisted; future agent reads get the updated instructions
```

**Key design decision:** The agent does not overwrite instructions — it *appends* to them. This preserves human-authored guidance while letting the agent add learned rules. The `created_by` field records "agent" for audit.

### 4. Per-Source Agent Guidance (GUIDE-01)

**Current gap:** Users can add a short `explanation` to uploaded intake sources, but there is no dedicated `agent_message` field for explicit agent guidance (e.g., "Bokför detta på konton 5410 och 2610, moms 25%").

**Integration approach:**

| Layer | Change | New or Modified |
|-------|--------|-----------------|
| Schema | Add `agent_message TEXT` to `intake_sources` | New migration |
| Repository | `IntakeRepository.update_agent_message()` | Modified |
| Service | `IntakeService.add_agent_message(source_id, message, actor)` | Modified |
| Routes | `PUT /api/v1/intake/{id}/agent-message` | New endpoint |
| Frontend | Upload form gets "Agentinstruktion" textarea; intake detail shows it prominently | Modified |
| Agent context | `GET /api/v1/agent/intake/pending` includes `agent_message` in each item | Modified |

**Data flow:**
```
User uploads receipt → includes agent_message
    ↓
Stored in intake_sources.agent_message
    ↓
Agent reads pending queue → sees agent_message per source
    ↓
Agent uses message as strong signal for account/period decisions
```

**Key design decision:** The field lives on `intake_sources` because guidance is *per-source*, not global. It is separate from `explanation` (which is free-form user context) to make it explicit in agent prompts.

### 5. Simplified Correction Flow (CORR-01)

**Current gap:** Users must manually create B-series corrections (reverse rows + corrected rows). Non-expert users find this heavy. The desired flow: user leaves a text note → agent suggests the correction → user approves → agent posts it.

**Integration approach:**

| Layer | Change | New or Modified |
|-------|--------|-----------------|
| Schema | New `correction_notes` table | New migration |
| Repository | `CorrectionNoteRepository` — create, list by voucher, list pending for agent | New |
| Service | `CorrectionNoteService` — create note, get pending notes for agent, apply note as correction | New |
| Routes | `POST /api/v1/vouchers/{id}/correction-notes`, `GET /api/v1/agent/correction-notes/pending`, `POST /api/v1/agent/correction-notes/{id}/apply` | New endpoints |
| Frontend | Voucher detail gets "Lämna korrigeringsnot" button + dialog; shows pending notes | Modified |
| Ledger | Re-use existing `LedgerService.create_posted_correction()` | No change to core ledger |

**Schema for `correction_notes`:**
```sql
CREATE TABLE correction_notes (
    id TEXT PRIMARY KEY,
    voucher_id TEXT NOT NULL,
    note TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', -- pending, approved, rejected, applied
    suggested_rows TEXT, -- JSON array of {account, debit, credit, description}
    suggested_by TEXT,
    created_by TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    FOREIGN KEY(voucher_id) REFERENCES vouchers(id)
);
CREATE INDEX idx_correction_notes_voucher ON correction_notes(voucher_id);
CREATE INDEX idx_correction_notes_status ON correction_notes(status);
```

**Data flow:**
```
User reviews posted voucher → clicks "Lämna korrigeringsnot"
    ↓
POST /vouchers/{id}/correction-notes with free-text note
    ↓
CorrectionNoteRepository.create(status='pending')
    ↓
Agent scans GET /agent/correction-notes/pending
    ↓
Agent reads note + voucher context → suggests corrected rows
    ↓
Agent calls POST /agent/correction-notes/{id}/apply with suggested_rows
    ↓
Backend: CorrectionNoteService.validate_suggestion(suggested_rows)
    ↓
Backend calls LedgerService.create_posted_correction(...)
    ↓
Correction note status → 'applied', resolved_at set
    ↓
User sees applied correction on voucher detail
```

**Key design decision:** The correction note is *not* a replacement for B-series corrections. It is a **frontend convenience layer** that still results in a proper B-series correction voucher. BFL immutability is preserved.

## Recommended Build Order

The features have interdependencies. Build in this order:

### Phase A: Schema Foundation (all features)
1. **Migration:** Add `agent_message` to `intake_sources` (GUIDE-01)
2. **Migration:** Create `correction_notes` table (CORR-01)
3. **Migration:** Add `link_reason` enum expansion if needed (DEDUP-01)

*Why first:* All other work depends on these tables.

### Phase B: Repository + Service Layer
4. **IntakeRepository:** `update_agent_message()`, `mark_skipped()`, `link_to_existing_voucher()` (DEDUP-01, GUIDE-01)
5. **BankInputRepository:** `list_unmatched_transactions()`, `get_transaction_detail()` (MATCH-01)
6. **CorrectionNoteRepository:** full CRUD + list_by_voucher + list_pending (CORR-01)
7. **AgentInstructionService:** thin `append_learned_rule()` wrapper (INSTR-01)

*Why second:* Routes and frontend depend on service contracts.

### Phase C: Backend Routes (agent-facing first)
8. **`POST /api/v1/intake/{id}/link-to-voucher`** and **`POST /api/v1/intake/{id}/skip`** (DEDUP-01)
9. **`GET /api/v1/agent/bank-transactions/matchable`** (MATCH-01)
10. **`POST /api/v1/agent/instructions/learn`** (INSTR-01)
11. **`PUT /api/v1/intake/{id}/agent-message`** (GUIDE-01)
12. **`POST /api/v1/vouchers/{id}/correction-notes`**, **`GET /api/v1/agent/correction-notes/pending`**, **`POST /api/v1/agent/correction-notes/{id}/apply`** (CORR-01)

*Why agent-facing first:* The agent is the primary consumer of matchability, instruction updates, and correction notes. Human-facing routes can be added immediately after.

### Phase D: Frontend Work Surfaces
13. **Intake workspace:** Add "Länka till verifikation" and "Markera som hanterad" actions (DEDUP-01)
14. **Intake upload form:** Add "Agentinstruktion" textarea (GUIDE-01)
15. **Intake detail page:** Show `agent_message` prominently (GUIDE-01)
16. **Voucher detail page:** Add "Lämna korrigeringsnot" button + dialog (CORR-01)
17. **Voucher detail page:** Show pending correction notes (CORR-01)
18. **Agent instructions page:** Add "Visa inlärda regler" section (INSTR-01)

### Phase E: Agent Entrypoint + Integration Tests
19. **Update `/api/v1/agent-instructions/entrypoint`:** Add step for matchable bank transactions, correction notes workflow
20. **Integration tests:** Agent reads correction note → suggests fix → applies → voucher gets B-series correction

## Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `IntakeService` | Source lifecycle: upload, dedup, link, skip, agent_message | `IntakeRepository`, `VoucherRepository`, `LedgerService` |
| `BankInputService` | Bank CSV import, transaction matching, matchable exposure | `BankInputRepository`, `BankIntegrationService` |
| `CorrectionNoteService` | Text note CRUD, agent suggestion validation, apply via LedgerService | `CorrectionNoteRepository`, `LedgerService`, `AccountingCorrectionRepository` |
| `AgentInstructionService` | Append-only instruction updates, version tracking | `AgentInstructionRepository` |
| `LedgerService` | Core posting, correction, balance validation | `VoucherRepository`, `PeriodRepository`, `AccountRepository` |

## Data Flow: Agent Correction Note Workflow

```
User reviews posted voucher on frontend
    ↓
POST /vouchers/{id}/correction-notes { note: "Fel konto, ska vara 6570" }
    ↓
CorrectionNoteService.create() → status='pending'
    ↓
Agent polls GET /agent/correction-notes/pending
    ↓
Agent reads note + voucher source context + instructions
    ↓
Agent generates suggested_rows: [{account:"1920",debit:0,credit:12500}, {account:"6570",debit:12500,credit:0}]
    ↓
Agent calls POST /agent/correction-notes/{id}/apply { suggested_rows }
    ↓
CorrectionNoteService.validate_suggestion_balances(suggested_rows)
    ↓
CorrectionNoteService.call_ledger_create_posted_correction(voucher_id, suggested_rows, reason=note)
    ↓
LedgerService.create_posted_correction() → B-series voucher
    ↓
CorrectionNoteService.mark_applied(note_id, correction_voucher_id)
    ↓
Frontend sees correction note status='applied' + link to B-series voucher
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Letting the agent overwrite human instructions
**What people do:** Give the agent a `PUT` that replaces the entire instruction document.
**Why it's wrong:** Human-authored rules (e.g., "always use account 1920 for bank") could be clobbered by a bad agent learning cycle.
**Do this instead:** Agent appends to a dedicated "## Inlärda regler" section. Human instructions remain authoritative.

### Anti-Pattern 2: Storing correction notes as direct voucher edits
**What people do:** Treat correction notes as a way to bypass B-series corrections.
**Why it's wrong:** Violates BFL §5 kap 6 varaktighet — posted vouchers must never be edited in place.
**Do this instead:** Correction notes always result in `LedgerService.create_posted_correction()`, producing an immutable B-series voucher.

### Anti-Pattern 3: Exposing booked bank transactions as matchable
**What people do:** Filter only on `status != 'booked'` but forget `matched_voucher_id IS NULL`.
**Why it's wrong:** A transaction can be unbooked but already matched to a voucher (e.g., via `voucher_bank_transactions`). The agent would create duplicate vouchers.
**Do this instead:** Filter on both `status != 'booked'` AND `matched_voucher_id IS NULL`.

### Anti-Pattern 4: Frontend calling agent-only endpoints
**What people do:** Re-use `/agent/correction-notes/pending` for the human review surface.
**Why it's wrong:** Agent endpoints may return shapes optimized for machine consumption (compact, no UI labels). Human review needs richer context.
**Do this instead:** Create a separate `/api/v1/vouchers/{id}/correction-notes` (human-facing) that returns full metadata, audit trail, and UI-ready labels.

## Scalability Considerations

| Scale | Concern | Approach |
|-------|---------|----------|
| 1 company, ~100 intake items/month | SQLite is fine | No change needed |
| 1 company, ~10K bank transactions/month | `list_unmatched_transactions` scan | Add index on `bank_transactions(status, matched_voucher_id)` |
| Multi-company (future) | `agent_instruction_documents.scope` collision | Scope must include company_id prefix or separate schema per tenant |

## Sources

- Bok codebase: `repositories/intake_repo.py`, `repositories/bank_input_repo.py`, `repositories/agent_instruction_repo.py`, `services/ledger.py`, `api/routes/agent.py`
- Bok migrations: `018_add_intake_sources.sql`, `019_add_bank_inputs.sql`, `013_add_agent_instructions.sql`
- BFL/BFNAR: Bokföringslagen §5 kap 6 (varaktighet), §5 kap 7 (rättelseverifikation)
- Swedish BAS 2026 account model (existing in `domain/types.py`)

---
*Architecture research for: Bok v1.3 Agent Usability & Feedback Loop*
*Researched: 2026-06-05*
