# Requirements: Bok v1.3 Agent Usability & Feedback Loop

**Defined:** 2026-06-05
**Core Value:** The system should let a small Swedish company keep compliant books with minimal manual interaction by giving an agent enough source material, history, and correction feedback to post accurate vouchers.

## v1.3 Requirements

### GUIDE — Per-Source Agent Guidance

- [ ] **GUIDE-01**: User can attach an agent message to an uploaded receipt/invoice
- [ ] **GUIDE-02**: Agent message is visible to the agent when processing the intake item
- [ ] **GUIDE-03**: Agent message is displayed on the intake detail page

### CORR — Simplified Correction Flow

- [ ] **CORR-01**: User can leave a text correction note on a posted voucher
- [ ] **CORR-02**: Agent can read pending correction notes
- [ ] **CORR-03**: Agent can suggest a B-series correction based on a correction note
- [ ] **CORR-04**: User can review and approve a suggested correction before posting
- [ ] **CORR-05**: Approved correction still produces an immutable B-series voucher
- [ ] **CORR-06**: Correction note lifecycle is tracked (pending, suggested, applied, dismissed)

### INSTR — Agent Instruction Persistence

- [ ] **INSTR-01**: Agent can append learned rules to a dedicated instruction section
- [ ] **INSTR-02**: Instruction updates are versioned and auditable
- [ ] **INSTR-03**: Instruction version growth is capped and deduplicated
- [ ] **INSTR-04**: User can view agent-learned rules in the instruction history

## v2+ Requirements

### DEDUP — Intake Deduplication & Linking (Deferred)

- **DEDUP-01**: User can link an already-posted intake item to an existing voucher
- **DEDUP-02**: User can mark an intake item as handled/skipped without creating a voucher
- **DEDUP-03**: Agent queue excludes intake items already linked to vouchers or marked skipped
- **DEDUP-04**: Intake linking is atomic to prevent race conditions

### MATCH — Bank Transaction Matchability (Deferred)

- **MATCH-01**: Agent can query unmatched/imported bank transactions as matchable entities
- **MATCH-02**: Bank transaction status transitions correctly when matched to a voucher
- **MATCH-03**: Agent can create a voucher from a matchable bank transaction
- **MATCH-04**: Matchable bank transactions exclude already-booked or matched items

## Out of Scope

| Feature | Reason |
|---------|--------|
| Pre-posting approval as default workflow | Product goal is automation with minimal user interaction |
| External accountant workflow management | App is meant to reduce dependency on accountants |
| Full Open Banking integration | Manual CSV upload is sufficient for v1 |
| MCP adapter | Deferred to v1.4+ — HTTP agent connectivity is the current validated path |
| Persistent per-agent API keys | Deferred to v1.4 — currently using shared API key or JWT |
| Durable idempotency keys | Deferred to v1.4 — retry-safe posting is not the current pain point |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| GUIDE-01 | Phase 8 | Pending |
| GUIDE-02 | Phase 8 | Pending |
| GUIDE-03 | Phase 8 | Pending |
| CORR-01 | Phase 9 | Pending |
| CORR-02 | Phase 9 | Pending |
| CORR-03 | Phase 9 | Pending |
| CORR-04 | Phase 9 | Pending |
| CORR-05 | Phase 9 | Pending |
| CORR-06 | Phase 9 | Pending |
| INSTR-01 | Phase 10 | Pending |
| INSTR-02 | Phase 10 | Pending |
| INSTR-03 | Phase 10 | Pending |
| INSTR-04 | Phase 10 | Pending |

**Coverage:**
- v1.3 requirements: 13 total
- Mapped to phases: 13 ✓
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-05*
*Last updated: 2026-06-05 after initial definition*
