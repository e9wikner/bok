# Feature Research

**Domain:** Swedish small-company bookkeeping source-material intake for AI-agent posting
**Researched:** 2026-05-14
**Confidence:** HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Voucher source upload | Users need to drop receipts, supplier invoices, and reimbursement evidence before a voucher exists | MEDIUM | Accept PDF and common image formats; preserve original file and hash. |
| User explanation/hint | Source files often do not contain context such as "employee paid, reimburse later" | LOW | Store short text, source type, date hint, amount hint if available. |
| Separate bank statement/status upload | Bank data has different semantics from voucher evidence | MEDIUM | Keep separate intake type or table; can feed voucher creation and later reconciliation. |
| Agent-readable pending queue | The agent needs to know what new material exists when it checks status | MEDIUM | API should return pending source items, metadata, secure file URLs, and prior attempts. |
| Direct posting from intake | Product goal is minimal user interaction | MEDIUM | Agent should call existing posting APIs and then mark intake processed with voucher links. |
| Source-to-voucher traceability | Required for review, audit, and later correction learning | MEDIUM | Link each intake file/item to posted voucher ID(s), correction history, and processing log. |
| Duplicate detection | Receipts and statements are easy to upload twice | LOW | SHA-256 per file plus optional duplicate warnings by amount/date/counterparty. |
| Intake lifecycle status | Users need to see whether uploads were processed, posted, skipped, failed, or need attention | MEDIUM | Use explicit statuses and timestamps; avoid implicit "missing from queue means done." |
| File security and retention behavior | Accounting source material may be sensitive and compliance-relevant | MEDIUM | Auth-gated downloads, root-path enforcement, deletion rules, and backup compatibility. |

### Differentiators (Competitive Advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Correction-informed learning loop | Mistakes become future agent context without manual rule authoring | MEDIUM | Ensure corrections can be traced back to source material and original agent rationale. |
| Agent processing notes | Makes autonomous posting reviewable after the fact | MEDIUM | Store summary, confidence, warnings, selected source material, and assumptions. |
| Bank-statement-driven voucher creation | Lets the agent infer missing expense/payment vouchers from bank data | HIGH | Needs careful duplicate checks against existing vouchers and invoice payment flows. |
| Matched evidence bundles | One voucher can be supported by receipt plus bank transaction plus user hint | HIGH | Useful but can follow after basic intake links exist. |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Mandatory approval before posting | Feels safer | Conflicts with the core automation goal and recreates accountant-like manual workload | Post directly, then review/correct with B-series corrections. |
| Destructive reprocessing | Seems convenient after agent mistakes | Can erase audit trail and confuse source-to-voucher links | Add immutable processing attempts and correction records. |
| Treating bank statement rows as automatically correct accounting categories | Speeds implementation | Bank text rarely contains enough accounting context; VAT/reimbursement/invoice-payment distinctions need context | Let the agent use statements as one input with history and source documents. |
| Deleting source files after posting | Saves disk | Accounting records and traceability can require preservation | Retain source files under managed storage; allow only policy-driven deletion if legally safe. |

## Feature Dependencies

```text
Intake storage + metadata
    ├──requires──> Secure upload/download
    ├──requires──> Lifecycle statuses
    └──enables──> Agent pending queue
                       └──enables──> Direct posting from intake
                                         └──requires──> Source-to-voucher links
                                                           └──enables──> Review/correction learning

Bank statement upload
    └──enables──> Bank-driven voucher creation
                       └──requires──> Duplicate/match checks
```

### Dependency Notes

- **Agent pending queue requires intake storage:** The agent needs stable IDs, metadata, and file URLs rather than ad hoc uploads.
- **Direct posting requires traceability:** Once the agent posts immediately, later review depends on being able to inspect the exact source material and assumptions.
- **Bank-driven voucher creation requires duplicate checks:** Bank rows may correspond to existing invoice payments, payroll runs, reimbursements, or already-posted vouchers.

## MVP Definition

### Launch With (v1)

- [ ] Voucher source upload before voucher creation — essential intake path.
- [ ] Bank statement/status upload as separate input — user explicitly requested it and wants it used for voucher creation.
- [ ] Agent-readable pending intake API — required for the agent to consume uploads.
- [ ] Direct agent posting with processed status and voucher links — core automation behavior.
- [ ] Source file retention and download from posted voucher review — required for traceability.
- [ ] Correction-to-source learning context — preserves the existing agent learning model.

### Add After Validation (v1.x)

- [ ] Rich matching between bank transactions and source files — add after basic direct-post flow works.
- [ ] Agent confidence/warnings surfaced in dashboard — add when processing notes are stable.
- [ ] Reprocessing controls for failed/skipped items — add once failure modes are known.

### Future Consideration (v2+)

- [ ] OCR/text extraction index — defer until proven necessary.
- [ ] Open Banking connection — defer because uploaded statements/statuses are enough for this milestone.
- [ ] Multi-user approval policies — defer because the target workflow is automation-first.
- [ ] Object storage backend — defer until local filesystem storage becomes operationally limiting.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Voucher source upload | HIGH | MEDIUM | P1 |
| Bank statement/status upload | HIGH | MEDIUM | P1 |
| Agent pending queue | HIGH | MEDIUM | P1 |
| Direct posting and source-to-voucher linking | HIGH | MEDIUM | P1 |
| Intake status dashboard | MEDIUM | MEDIUM | P1 |
| Correction learning context | HIGH | MEDIUM | P1 |
| Bank/source matching bundles | MEDIUM | HIGH | P2 |
| OCR/extraction | MEDIUM | HIGH | P3 |
| Open Banking | MEDIUM | HIGH | P3 |

## Competitor Feature Analysis

| Feature | Common accounting apps | Our Approach |
|---------|------------------------|--------------|
| Receipt upload | Usually creates a review queue or suggested bookkeeping entry | Create agent-readable intake and allow direct posting by default. |
| Bank statement import | Often used for reconciliation and categorization | Use as source material for missing vouchers as requested. |
| Human approval | Common default for accountant-led products | Keep review after posting through correction vouchers. |
| Audit trail | Expected in accounting products | Preserve original file, processing attempt, posted voucher, and correction linkage. |

## Sources

- Existing README/API/frontend docs — current system capabilities and requested next step.
- Sveriges Riksdag, Bokföringslag (1999:1078), 5 kap. 6-7 §§ and 7 kap. 1-2 §§ — source material must support verifications and retention.
- BFNAR 2013:2, Chapter 5 — verification contents, supplementation, and link to original information.
- Bokföringsnämnden Limited companies page — Swedish ABs must record transactions, have supporting vouchers, archive accounting information, and prepare annual reports.

---
*Feature research for: Swedish bookkeeping intake*
*Researched: 2026-05-14*
