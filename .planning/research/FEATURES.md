# Feature Research: Agent Usability Improvements

**Domain:** Agent-driven bookkeeping automation (brownfield additions)
**Researched:** 2026-06-05
**Confidence:** HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist in an agent-driven bookkeeping system. Missing these creates visible gaps between agent processing and backend state.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Intake deduplication/linking** | Users upload receipts, then the agent or manual workflow creates a voucher. The intake item must leave the pending queue. Currently items stay pending if voucher was created outside the intake flow. | LOW | Add `linked_to_existing_voucher` status transition and `link_reason` values. Reuse existing `voucher_intake_sources` link table. Frontend needs a "Link to existing voucher" action on intake workspace items. |
| **Bank transaction matchability** | Bank CSVs import individual transactions. The agent needs to see unmatched transactions as concrete entities it can match to vouchers, not just as bank_input containers. | MEDIUM | Expose `bank_transactions` rows via agent API with `status=unmatched`. Add agent endpoint to match a transaction to a voucher (or create voucher from it). `matched_voucher_id` field already exists. |
| **Agent instruction persistence** | The default instructions say "Uppdatera instruktionerna med generell vägledning när mänskliga korrigeringar visar återkommande mönster." The agent needs a way to actually do this. | LOW | Company instructions already have PUT endpoints and version history. Gap is agent awareness + structured update API. Agent can already auth; may just need documented workflow and explicit permission to call PUT /accounting. |
| **Per-source agent guidance** | Users often know more about a specific receipt than the general instructions capture (e.g., "This is a software subscription — book to 6540"). | LOW | Add `agent_guidance` text column to `intake_sources`. Expose it in agent queue payloads. Frontend adds a textarea on upload or review surfaces. |
| **Simplified correction flow** | Non-expert users cannot construct B-series correction vouchers with proper debit/credit rows. They need a way to say "this was wrong, here's why" in plain text. | MEDIUM | New `correction_notes` table linked to posted vouchers. Agent reads notes, proposes a correction voucher (B-series), user approves/denies. Backend still posts the actual B-series voucher to preserve BFL immutability. |

### Differentiators (Competitive Advantage)

Features that make Bok's agent integration notably better than conventional bookkeeping tools.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Text-note corrections with agent-generated B-series vouchers** | Most systems force users to manually create correction vouchers or abandon immutability. Bok can let users write plain text while the agent handles the formal B-series mechanics — preserving compliance without requiring expertise. | MEDIUM | Requires careful UX: user writes note → agent suggests rows → user approves → backend posts B-series. Must expose "proposed correction" state before posting. |
| **Agent-updated company instructions** | Most agent systems are read-only from the agent's perspective. Letting the agent write back learned rules ("Always book Spotify to 6540") creates a self-improving system. | LOW | Reuse existing instruction version history. Add audit trail distinguishing `created_by="agent"` vs `created_by="user"`. Consider requiring user approval for agent-suggested instruction updates. |
| **Unified matchability for bank transactions** | Many systems separate bank reconciliation from voucher creation. Bok can treat unmatched bank transactions as first-class intake items the agent creates vouchers from directly. | MEDIUM | Bank transactions become part of agent queue alongside receipt/invoice sources. Agent sees amount, description, date, counterpart — enough to suggest a voucher. |
| **Per-source guidance feeding into instruction learning** | A user saying "book this to 6540" on one receipt should not require repeating. The agent can distill per-source guidance into general instruction updates. | LOW-MEDIUM | Requires the agent to correlate guidance → instruction update. System can surface recurring guidance patterns to the agent as update suggestions. |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Direct editing of posted vouchers** | Users want to "fix a typo" quickly. | Violates BFL immutability and audit trail. Breaks Swedish bookkeeping compliance. | Simplified correction flow: user leaves text note, agent suggests B-series correction, user approves. |
| **Pre-approval for every agent-posted voucher** | Users worry about agent mistakes. | Conflicts with automation-first product goal. Adds friction that defeats the purpose of an agent. | Post-directly by default; use review + correction loop as feedback mechanism. |
| **Agent creating its own API keys** | Agents discovering and managing credentials. | Key lifecycle is complex, high-security surface, and unnecessary for a single-tenant self-hosted app. | Single configured bearer token (current model). Defer per-agent keys to v1.4+ (KEYS-01). |
| **Full two-way Open Banking sync** | Automatic daily bank transaction import. | High external dependency complexity, OAuth flows, bank API fragmentation. Out of scope for self-hosted v1. | Manual CSV upload (existing) with matchability improvements (MATCH-01). |
| **Agent deleting or modifying intake sources** | Agent "cleaning up" after itself. | Risk of data loss; user uploads are evidence. Soft-delete already exists but should be user-initiated. | Agent marks items `processed`/`failed`/`skipped`. User decides to delete. |

## Feature Dependencies

```
Intake deduplication/linking (DEDUP-01)
    └──requires──> Existing voucher linking (already built)
    └──enables──>  Clean agent queue (no false positives)

Per-source agent guidance (GUIDE-01)
    └──requires──> Intake source schema extension
    └──enhances──> Agent decision quality for edge cases

Bank transaction matchability (MATCH-01)
    └──requires──> Bank transaction query API
    └──requires──> Agent voucher creation from bank transactions
    └──enhances──> Automated bank-driven posting
    └──conflicts──> None; but should reuse existing bank_input link tables

Agent instruction persistence (INSTR-01)
    └──requires──> Existing PUT endpoint (already built)
    └──requires──> Agent awareness in startup sequence
    └──enhances──> Simplified correction flow (agent learns from notes)
    └──enhances──> Per-source guidance (agent distills patterns into instructions)

Simplified correction flow (CORR-01)
    └──requires──> Correction note storage
    └──requires──> Agent instruction persistence (to learn from corrections)
    └──requires──> B-series posting already works (already built)
    └──requires──> Agent-generated correction proposal + user approval flow
    └──enables──>  Non-expert users to participate in feedback loop
```

### Dependency Notes

- **DEDUP-01 reuses existing linking:** The `voucher_intake_sources` table and `link_existing_voucher` service method already exist. DEDUP-01 mainly adds the "user links an already-posted voucher to an existing intake item" path and ensures the status transitions correctly.

- **CORR-01 requires INSTR-01 for learning loop:** If the agent suggests corrections but never updates instructions, the same mistakes repeat. The learning loop closes when corrections → instruction updates.

- **MATCH-01 should not duplicate bank_input link tables:** `voucher_bank_inputs` and `voucher_bank_transactions` already exist. The new API surface should read from existing tables, not create parallel structures.

- **GUIDE-01 is low-risk and can ship independently:** Adding a text column to `intake_sources` and exposing it in the agent queue has minimal blast radius.

## MVP Definition (v1.3 Scope)

### Launch With (v1.3)

Minimum viable agent usability improvement — what's needed to close the real-world gaps identified in v1.2 usage.

- [ ] **Intake deduplication/linking (DEDUP-01)** — Essential. Without this, the agent keeps re-processing items that already have vouchers, or the queue fills with stale items.
- [ ] **Bank transaction matchability (MATCH-01)** — Essential. Bank CSV import is already built, but the agent cannot actually act on individual transactions. This makes bank import useful.
- [ ] **Per-source agent guidance (GUIDE-01)** — Essential. Low complexity, high user value. Users need a way to tell the agent specifics about a receipt without editing global instructions.
- [ ] **Simplified correction flow (CORR-01)** — Essential. The existing B-series correction flow is too heavy for non-expert users. Without simplification, the feedback loop breaks.

### Add After Validation (v1.3.x)

Features to add once the core v1.3 features are working and user-tested.

- [ ] **Agent instruction persistence (INSTR-01)** — Trigger: Correction notes and per-source guidance are flowing in. Now the agent needs to write back distilled rules. Can technically ship with v1.3 since PUT endpoints exist, but the real value emerges after correction volume exists.
- [ ] **Agent-suggested instruction updates with user approval** — Trigger: Agent has updated instructions at least once and user wants oversight.

### Future Consideration (v2+)

Features to defer until the v1.3 agent usability improvements prove their value.

- [ ] **OCR/text extraction for uploaded PDFs/images** — Would reduce need for per-source guidance. Deferred as "v2 candidate" in STATE.md.
- [ ] **Persistent per-agent API keys** — Deferred to v1.4 (KEYS-01).
- [ ] **MCP adapter** — Deferred to v1.4+ (MCP-01).
- [ ] **Full Open Banking connection** — Manual CSV is sufficient for the target user.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority | Rationale |
|---------|------------|---------------------|----------|-----------|
| Intake deduplication/linking | HIGH | LOW | P1 | Unblocks agent queue; prevents duplicate work. Reuses existing tables. |
| Per-source agent guidance | HIGH | LOW | P1 | Immediate user value; trivial schema addition. |
| Bank transaction matchability | HIGH | MEDIUM | P1 | Makes existing bank CSV import functional for the agent. |
| Simplified correction flow | HIGH | MEDIUM | P1 | Closes the feedback loop for non-experts. Required for product goal. |
| Agent instruction persistence | MEDIUM | LOW | P2 | Endpoints exist; mainly documentation and workflow. Adds value after correction volume exists. |
| Agent instruction approval gate | MEDIUM | LOW | P2 | UX polish on top of INSTR-01. |
| OCR/text extraction | HIGH | HIGH | P3 | Would reduce guidance burden but is a large standalone effort. |

## Existing System Interactions

### How Each Feature Touches Current Architecture

| Feature | Backend Routes | Services | Repositories | Frontend | DB Migrations |
|---------|---------------|----------|--------------|----------|---------------|
| DEDUP-01 | `POST /intake/{id}/link-voucher` (new) | `IntakeService` — add `link_to_existing_voucher` | `IntakeRepository` — add `update_status` to `linked` | Intake workspace — add "Link to voucher" action | Add `linked` to `IntakeStatus` enum or reuse `processed` |
| MATCH-01 | `GET /agent/bank-transactions` (new), `POST /agent/bank-transactions/{id}/match` (new) | `BankInputService` — add match methods | `BankInputRepository` — query unmatched | Bank detail view — show match status | Add index on `bank_transactions.status` |
| GUIDE-01 | `PUT /intake/{id}/guidance` (new) | `IntakeService` — add `update_guidance` | `IntakeRepository` — add `update_guidance` | Upload form + review surface — add guidance textarea | Add `agent_guidance TEXT` to `intake_sources` |
| INSTR-01 | Reuse `PUT /agent-instructions/accounting` | No new service | No new repo | Optional: show agent-authored versions | No migration needed |
| CORR-01 | `POST /vouchers/{id}/correction-notes` (new), `GET /vouchers/{id}/correction-proposal` (new), `POST /vouchers/{id}/correction-proposal/approve` (new) | `LedgerService` — add `create_correction_proposal`, `approve_correction_proposal` | New `CorrectionNoteRepository` | Voucher review — add "Leave correction note" button, show proposal | Add `correction_notes` table |

## Competitor Feature Analysis

| Feature | Traditional Bookkeeping (Fortnox/Visma) | Modern AI Tools (Dooer/Rematch) | Our Approach |
|---------|----------------------------------------|--------------------------------|--------------|
| Intake deduplication | Manual review of uploaded files; no agent queue concept. | Automated but often hidden; user doesn't see queue. | Explicit queue with user-initiated linking for edge cases. |
| Bank matchability | Bank feed matching to existing vouchers; user manually clicks match. | Auto-matching with confidence scores. | Agent sees unmatched transactions and can create vouchers directly. |
| Per-source guidance | Memo fields on transactions; not agent-targeted. | Often relies on global rules only. | Plain-text guidance attached to source, visible to agent in queue. |
| Correction workflow | User creates B-series manually (expert required). | Some allow direct edit (non-compliant) or suggest corrections. | User writes text note; agent proposes formal B-series; user approves. Preserves immutability. |
| Instruction learning | Static chart of accounts and rules. | ML models trained on history; opaque to user. | Versioned Markdown instructions updated by agent, auditable by user. |

## Sources

- Existing codebase analysis: `repositories/intake_repo.py`, `services/intake.py`, `api/routes/intake.py`, `api/routes/agent.py`, `repositories/agent_instruction_repo.py`, `api/routes/agent_instructions.py`, `repositories/bank_input_repo.py`, `services/bank_inputs.py`
- PROJECT.md v1.3 requirements (Active: DEDUP-01, MATCH-01, INSTR-01, GUIDE-01, CORR-01)
- v1.2 real-world agent usage gaps documented in STATE.md and PROJECT.md
- BFL/BFNAR immutability constraints from PROJECT.md Constraints section

---
*Feature research for: Agent Usability Improvements (v1.3)*
*Researched: 2026-06-05*
