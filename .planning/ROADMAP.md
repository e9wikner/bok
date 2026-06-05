# Roadmap: Bok

## Milestones

- ✅ **v1.0 Intake Automation** — Phases 1-3 (shipped 2026-05-18). Full archive: [v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 Clear Instructions for Deployment** — Phases 4-5 (shipped 2026-06-04). Full archive: [v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md)
- ✅ **v1.2 Agent Onboarding** — Phases 6-7 (shipped 2026-06-05). Full archive: [v1.2-ROADMAP.md](milestones/v1.2-ROADMAP.md)
- 📋 **v1.3** — Phases 8+ (planned)

## Phases

<details>
<summary>✅ v1.0 Intake Automation (Phases 1-3) — SHIPPED 2026-05-18</summary>

- [x] Phase 1: Foundation (3/3 plans) — completed 2026-05-18
- [x] Phase 2: Bank Input Intake (3/3 plans) — completed 2026-05-18
- [x] Phase 3: Frontend Review Surfaces (3/3 plans) — completed 2026-05-18

</details>

<details>
<summary>✅ v1.1 Clear Instructions for Deployment (Phases 4-5) — SHIPPED 2026-06-04</summary>

- [x] Phase 4: Deployment Instructions (3/3 plans) — completed 2026-06-04
- [x] Phase 5: Intake Agent Traceability (3/3 plans) — completed 2026-06-04

</details>

<details>
<summary>✅ v1.2 Agent Onboarding (Phases 6-7) — SHIPPED 2026-06-05</summary>

- [x] Phase 6: Agent Instruction Entrypoint and API Discovery (2/2 plans) — completed 2026-06-05
- [x] Phase 7: OpenClaw Deployment Instructions and Verification (2/2 plans) — completed 2026-06-05

</details>

### 📋 v1.3 (Planned)

- [ ] **Phase 8: GUIDE — Per-Source Agent Guidance** — Schema, agent-facing routes, and frontend for attaching per-source messages
- [ ] **Phase 9: CORR — Simplified Correction Flow** — Correction notes, agent suggestion, user approval, and B-series voucher production
- [ ] **Phase 10: INSTR — Agent Instruction Persistence** — Versioned, deduplicated, capped instruction append with user-visible history
- [ ] **Phase 11: Integration & Entrypoint Update** — Update agent entrypoint, integration tests, and end-to-end validation

## Phase Details

### Phase 8: GUIDE — Per-Source Agent Guidance
**Goal**: Users can attach guidance messages to individual uploaded receipts/invoices, and agents see those messages during processing.
**Depends on**: Phase 7
**Requirements**: GUIDE-01, GUIDE-02, GUIDE-03
**Success Criteria** (what must be TRUE):
  1. User can type and save an agent message when uploading or editing a receipt/invoice
  2. Agent message appears on the intake detail page for human review
  3. Agent receives the per-source message when fetching the intake item for processing
**Plans**:
  - 08-01: Backend schema, intake API, and agent queue guidance
  - 08-02: Frontend upload and detail guidance surfaces
  - 08-03: Guidance tests and agent entrypoint documentation
**UI hint**: yes

### Phase 9: CORR — Simplified Correction Flow
**Goal**: Users can leave text correction notes on posted vouchers; agents read them, suggest B-series corrections, and get user approval before posting.
**Depends on**: Phase 8
**Requirements**: CORR-01, CORR-02, CORR-03, CORR-04, CORR-05, CORR-06
**Success Criteria** (what must be TRUE):
  1. User can leave a text correction note on any posted voucher
  2. Agent can query pending correction notes and propose a B-series correction
  3. User can review proposed correction rows and approve or dismiss them
  4. Approved corrections produce an immutable B-series voucher linked to the original
  5. Correction notes display their lifecycle status (pending, suggested, applied, dismissed)
**Plans**: TBD
**UI hint**: yes

### Phase 10: INSTR — Agent Instruction Persistence
**Goal**: Agents can append learned rules to a dedicated instruction section, with versioned, auditable, and capped history visible to users.
**Depends on**: Phase 9
**Requirements**: INSTR-01, INSTR-02, INSTR-03, INSTR-04
**Success Criteria** (what must be TRUE):
  1. Agent can append a learned rule to a dedicated instruction section via API
  2. Each instruction append creates a new auditable version with timestamp
  3. Identical or redundant appends are deduplicated and version count stays capped
  4. User can view the history of agent-learned rules in the instruction UI
**Plans**: TBD
**UI hint**: yes

### Phase 11: Integration & Entrypoint Update
**Goal**: Agent can discover all new v1.3 capabilities through the updated entrypoint, and end-to-end workflows are validated.
**Depends on**: Phase 10
**Requirements**: — (validates all v1.3 requirements)
**Success Criteria** (what must be TRUE):
  1. Agent entrypoint lists all new v1.3 workflow endpoints and guardrails
  2. Integration tests verify: agent reads correction note → suggests fix → applies → B-series voucher created
  3. Integration tests verify: agent sees per-source guidance and uses it in voucher creation
  4. Integration tests verify: agent appends instruction → new version visible in frontend history
**Plans**: TBD

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
| ----- | --------- | -------------- | ------ | --------- |
| 1. Foundation | v1.0 | 3/3 | Complete | 2026-05-18 |
| 2. Bank Input Intake | v1.0 | 3/3 | Complete | 2026-05-18 |
| 3. Frontend Review Surfaces | v1.0 | 3/3 | Complete | 2026-05-18 |
| 4. Deployment Instructions | v1.1 | 3/3 | Complete | 2026-06-04 |
| 5. Intake Agent Traceability | v1.1 | 3/3 | Complete | 2026-06-04 |
| 6. Agent Instruction Entrypoint | v1.2 | 2/2 | Complete | 2026-06-05 |
| 7. OpenClaw Deployment | v1.2 | 2/2 | Complete | 2026-06-05 |
| 8. GUIDE — Per-Source Agent Guidance | v1.3 | 0/3 | Ready to execute | - |
| 9. CORR — Simplified Correction Flow | v1.3 | 0/0 | Not started | - |
| 10. INSTR — Agent Instruction Persistence | v1.3 | 0/0 | Not started | - |
| 11. Integration & Entrypoint Update | v1.3 | 0/0 | Not started | - |
