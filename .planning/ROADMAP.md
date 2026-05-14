# Roadmap: Bok

## Overview

This milestone turns Bok's existing agent-capable bookkeeping system into an automation-first source intake workflow. The roadmap first establishes durable source storage and traceability, then expands bank statement/status input for voucher creation, and finally gives the user a frontend workspace for upload, status scanning, and post-fact review.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Intake Foundation and Agent Queue** - Store voucher source material before vouchers exist and expose it safely to the agent.
- [ ] **Phase 2: Bank Input and Direct Posting Context** - Add bank statement/status intake and let the agent use it to create missing vouchers without duplicating existing accounting.
- [ ] **Phase 3: Frontend Intake Workspace and Review Loop** - Provide the operational UI for upload, status, linked voucher review, and correction learning.

## Phase Details

### Phase 1: Intake Foundation and Agent Queue
**Goal**: Users can upload voucher source material before a voucher exists, and the agent can consume a pending queue with durable source-to-voucher traceability.
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: [INTK-01, INTK-02, INTK-03, INTK-04, INTK-05, INTK-06, INTK-07, AGNT-01, AGNT-02, AGNT-03, AGNT-04, AGNT-05]
**Success Criteria** (what must be TRUE):
  1. User can upload a receipt or invoice PDF/image with an optional explanation before any voucher exists.
  2. Agent can list pending intake items, download source files, and mark processing outcomes.
  3. Agent can post a voucher through the existing validation path and link it back to every source item used.
  4. Intake downloads reject paths outside the configured storage root and duplicate file uploads do not create duplicate pending work.
  5. Processing attempts preserve summary, warnings/errors, voucher IDs, timestamps, and actor identity for later review.
**Plans**: 3 plans

Plans:
- [ ] 01-01: Add intake schema, repository, service, and secure source file storage.
- [ ] 01-02: Add human upload APIs and agent pending/processing APIs.
- [ ] 01-03: Link agent-posted vouchers to intake sources and test traceability, duplicate detection, and path safety.

### Phase 2: Bank Input and Direct Posting Context
**Goal**: Users can upload bank statements/statuses separately, and the agent can use bank input plus source/history context to create missing vouchers safely.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: [BANK-01, BANK-02, BANK-03, BANK-04, BANK-05, BANK-06, AGNT-06]
**Success Criteria** (what must be TRUE):
  1. User can upload a bank statement/status file as bank input, separate from voucher source uploads.
  2. Parseable bank CSV uploads reuse existing bank import logic while preserving the original uploaded statement/status file.
  3. Agent context includes uploaded bank inputs, imported transactions, relevant source material, existing vouchers, invoices, payroll references, and correction history.
  4. Bank-driven voucher creation performs duplicate/match checks before posting.
  5. Vouchers created from bank input link back to the bank source and any imported transaction rows used.
**Plans**: 3 plans

Plans:
- [ ] 02-01: Add bank statement/status intake records and upload API.
- [ ] 02-02: Integrate parseable bank uploads with existing bank transaction import and source batch linkage.
- [ ] 02-03: Extend agent context and posting safeguards for bank-driven voucher creation.

### Phase 3: Frontend Intake Workspace and Review Loop
**Goal**: Users can manage intake through the frontend, inspect outcomes, and review agent-posted vouchers with source material and correction-learning context.
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: [FRNT-01, FRNT-02, FRNT-03, FRNT-04, FRNT-05, FRNT-06]
**Success Criteria** (what must be TRUE):
  1. User can upload voucher sources and bank statements/statuses from a frontend intake workspace.
  2. User can filter intake items by pending, processing, processed, skipped, failed, and needs_attention.
  3. User can open a processed intake item and navigate to linked posted vouchers.
  4. Voucher detail pages show linked intake source files and agent processing notes.
  5. Failed or needs_attention items display actionable details, and corrected agent-posted vouchers remain visible in the learning/review loop.
**Plans**: 3 plans

Plans:
- [ ] 03-01: Add frontend API client/types/hooks for intake and bank input.
- [ ] 03-02: Build the intake upload and status workspace.
- [ ] 03-03: Extend voucher review pages with linked source material, processing notes, and correction-learning context.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Intake Foundation and Agent Queue | 0/3 | Not started | - |
| 2. Bank Input and Direct Posting Context | 0/3 | Not started | - |
| 3. Frontend Intake Workspace and Review Loop | 0/3 | Not started | - |
