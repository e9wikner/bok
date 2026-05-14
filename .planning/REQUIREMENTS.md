# Requirements: Bok

**Defined:** 2026-05-14
**Core Value:** The system should let a small Swedish company keep compliant books with minimal manual interaction by giving an agent enough source material, history, and correction feedback to post accurate vouchers.

## v1 Requirements

Requirements for the intake milestone. Each maps to roadmap phases.

### Intake Sources

- [x] **INTK-01**: User can upload voucher source material before a voucher exists.
- [x] **INTK-02**: User can upload PDF and common image files as voucher source material.
- [x] **INTK-03**: User can add an optional short explanation to uploaded voucher source material.
- [x] **INTK-04**: Uploaded source material preserves original filename, MIME type, size, SHA-256 hash, upload timestamp, and actor.
- [x] **INTK-05**: System detects duplicate source file uploads by hash and prevents duplicate pending work.
- [x] **INTK-06**: Intake source files can be downloaded only through authenticated APIs that enforce storage-root containment.
- [x] **INTK-07**: Intake source records have explicit lifecycle status: pending, processing, processed, skipped, failed, or needs_attention.

### Agent Processing

- [x] **AGNT-01**: Agent can list pending intake source material with metadata, user explanations, and file download references.
- [x] **AGNT-02**: Agent can mark an intake source as processing, processed, skipped, failed, or needs_attention.
- [x] **AGNT-03**: Agent can post vouchers directly from intake material using the existing voucher posting path and backend validation.
- [x] **AGNT-04**: A voucher posted from intake material is linked back to all source items used for the decision.
- [x] **AGNT-05**: Agent processing attempts store summary, warnings or error details, linked voucher IDs, timestamps, and actor identity.
- [ ] **AGNT-06**: Agent context includes relevant correction history so user corrections can inform future intake processing.

### Bank Inputs

- [ ] **BANK-01**: User can upload bank statements/statuses separately from voucher source material.
- [ ] **BANK-02**: Bank statement/status uploads preserve the original uploaded file and source metadata.
- [ ] **BANK-03**: Parseable bank CSV uploads create or update bank transaction records through the existing bank import logic.
- [ ] **BANK-04**: Agent can use uploaded bank statements/statuses and imported bank transactions as source input for creating missing vouchers.
- [ ] **BANK-05**: Bank-driven voucher creation checks for duplicate source items, bank transactions, invoices, payroll entries, and existing vouchers before posting.
- [ ] **BANK-06**: Vouchers created from bank inputs are linked back to the bank statement/status source and any imported bank transaction rows used.

### Review and Frontend

- [ ] **FRNT-01**: User can upload voucher sources and bank statements/statuses from a frontend intake workspace.
- [ ] **FRNT-02**: User can view intake items grouped or filtered by lifecycle status.
- [ ] **FRNT-03**: User can open processed intake items and navigate to linked posted vouchers.
- [ ] **FRNT-04**: Voucher detail view shows intake source material and agent processing notes for vouchers created from intake.
- [ ] **FRNT-05**: Failed or needs_attention intake items show enough detail for the user to understand what went wrong.
- [ ] **FRNT-06**: User corrections to agent-posted vouchers remain visible as part of the agent learning/review loop.

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Extraction

- **EXTR-01**: System can extract text from PDFs and images for indexing or agent fallback.
- **EXTR-02**: System can display extracted text beside the original source file.

### Bank Automation

- **OPEN-01**: System can connect to an Open Banking provider for automatic transaction import.
- **OPEN-02**: System can periodically synchronize bank transactions without manual file upload.

### Storage

- **STOR-01**: System can store source files in S3-compatible object storage.
- **STOR-02**: System can enforce configurable retention/deletion policies for source material.

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Mandatory pre-posting approval queue | Conflicts with the automation-first product goal. |
| OCR/text extraction as a v1 dependency | The first milestone should prove source intake and agent direct-posting before adding extraction complexity. |
| Full Open Banking integration | Uploaded statements/statuses are sufficient for this milestone. |
| Replacing B-series corrections with direct edits | Posted voucher immutability is a core compliance and audit constraint. |
| Separate intake microservice | Existing monolith is appropriate for the current scale and deployment model. |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INTK-01 | Phase 1 | Complete |
| INTK-02 | Phase 1 | Complete |
| INTK-03 | Phase 1 | Complete |
| INTK-04 | Phase 1 | Complete |
| INTK-05 | Phase 1 | Complete |
| INTK-06 | Phase 1 | Complete |
| INTK-07 | Phase 1 | Complete |
| AGNT-01 | Phase 1 | Complete |
| AGNT-02 | Phase 1 | Complete |
| AGNT-03 | Phase 1 | Complete |
| AGNT-04 | Phase 1 | Complete |
| AGNT-05 | Phase 1 | Complete |
| AGNT-06 | Phase 2 | Pending |
| BANK-01 | Phase 2 | Pending |
| BANK-02 | Phase 2 | Pending |
| BANK-03 | Phase 2 | Pending |
| BANK-04 | Phase 2 | Pending |
| BANK-05 | Phase 2 | Pending |
| BANK-06 | Phase 2 | Pending |
| FRNT-01 | Phase 3 | Pending |
| FRNT-02 | Phase 3 | Pending |
| FRNT-03 | Phase 3 | Pending |
| FRNT-04 | Phase 3 | Pending |
| FRNT-05 | Phase 3 | Pending |
| FRNT-06 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 25 total
- Mapped to phases: 25
- Unmapped: 0

---
*Requirements defined: 2026-05-14*
*Last updated: 2026-05-14 after roadmap creation*
