# Project Research Summary

**Project:** Bok
**Domain:** Swedish small-company bookkeeping source-material intake for AI-agent posting
**Researched:** 2026-05-14
**Confidence:** HIGH

## Executive Summary

Bok is already a capable Swedish bookkeeping system with agent-facing APIs, immutable voucher posting, correction vouchers, invoice workflows, bank transaction import, and frontend review surfaces. The next milestone should not rebuild accounting logic. It should add a first-class intake layer that stores source material before a voucher exists and exposes it to the agent as pending work.

The recommended approach is to keep the existing FastAPI/SQLite/local-filesystem/Next.js stack and add intake metadata tables, secure file storage, agent queue endpoints, source-to-voucher linking, and frontend upload/status views. Swedish bookkeeping rules make traceability and preservation central: source material should be treated as accounting evidence, not temporary agent prompt content.

The main risk is that direct posting removes a human pre-approval checkpoint. The mitigation is not to add mandatory approval, because that conflicts with the product goal. Instead, preserve original files, processing attempts, source-voucher links, duplicate checks, and correction feedback so the user can review after posting and the agent can learn from corrections.

## Key Findings

### Recommended Stack

Keep the current stack. The first intake slice does not need new infrastructure or OCR dependencies.

**Core technologies:**
- FastAPI: intake and agent APIs — already used and fits multipart uploads plus typed schemas.
- SQLite: intake metadata and links — appropriate for the self-hosted small-company target.
- Local filesystem: original source files — matches existing attachment storage and deployment model.
- Next.js/React Query: upload and status UI — consistent with the current frontend.
- Pytest/Playwright: verification — needed for lifecycle, security, and upload workflows.

### Expected Features

**Must have (table stakes):**
- Voucher source upload before voucher creation — users need to drop receipts and invoices without creating vouchers manually.
- Bank statement/status upload as a separate input type — bank data has distinct semantics and should be used for voucher creation.
- Agent-readable pending queue — the agent must discover uploaded work during status/context checks.
- Direct posting from intake — matches the automation-first product goal.
- Source-to-voucher traceability — required for review, audit, and learning from corrections.
- Lifecycle status and duplicate detection — prevents silent loss and repeated posting.

**Should have (competitive):**
- Processing attempts with agent summaries/warnings — makes autonomous posting understandable.
- Correction-informed learning context — turns user review into future guidance.
- Evidence bundles across receipts, bank rows, and vouchers — improves review and duplicate detection.

**Defer (v2+):**
- OCR/text extraction index — useful only if the agent cannot inspect original files reliably.
- Open Banking — not needed for the selected v1 path because uploaded statements/statuses are acceptable.
- Object storage — defer until local storage is operationally limiting.

### Architecture Approach

Add intake as a domain slice in the existing monolith. Use new routes/services/repositories for intake sources and agent queue behavior, plus a migration for source records, processing attempts, and source-voucher links. Keep posting through existing ledger/agent voucher APIs so backend validation and BFL-aligned immutability remain unchanged.

**Major components:**
1. IntakeService — validates uploads, stores original files, hashes content, manages lifecycle.
2. IntakeRepository — persists source metadata, attempts, and source-voucher links.
3. Agent intake API — returns pending source material and accepts processing outcomes.
4. Frontend intake workspace — supports upload, status scanning, and links to posted vouchers.
5. Voucher review extension — shows source files and agent processing notes on posted vouchers.

### Critical Pitfalls

1. **Lost source-voucher link** — prevent with a link table and processed-attempt records.
2. **Original file not preserved** — store original bytes and SHA-256; treat extraction as derived metadata only.
3. **Duplicate posting** — use file hashes, bank external IDs, lifecycle state, and agent duplicate checks.
4. **Bank data overconfidence** — expose bank statements as one input among receipts, invoices, payroll, history, and corrections.
5. **Unsafe file serving** — enforce storage-root containment before serving or deleting files.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Intake Foundation and Source Traceability
**Rationale:** The agent cannot safely post from source material until uploads, storage, lifecycle state, and source-voucher links exist.
**Delivers:** Intake schema, upload APIs, secure file storage/download, pending queue, direct posting outcome linkage, backend tests.
**Addresses:** Voucher source upload, lifecycle state, duplicate file detection, source-to-voucher traceability.
**Avoids:** Lost source-voucher links, original file loss, unsafe file serving.

### Phase 2: Bank Statement Intake and Agent Posting Context
**Rationale:** Bank statements/statuses are a separate source type and the user wants them used for creating missing vouchers.
**Delivers:** Bank statement upload path, integration with existing bank transaction import where parseable, agent context that combines bank rows with source material/history, duplicate/match safeguards.
**Uses:** Existing `BankIntegrationService`, bank transaction tables, agent instruction/correction APIs.
**Implements:** Bank-driven voucher creation input without making bank text the only evidence.

### Phase 3: Frontend Intake Workspace and Review Loop
**Rationale:** Automation still needs a human review surface after posting.
**Delivers:** Upload/status UI, processed history, failed/needs-attention states, voucher detail source display, processing notes, correction-learning visibility.
**Implements:** Operational frontend workflow for minimal interaction plus review after the fact.

### Phase Ordering Rationale

- Storage, lifecycle, and traceability must precede agent behavior because direct posting needs auditability from day one.
- Bank input follows basic intake because bank statement rows have more matching and duplicate risks.
- Frontend review follows core APIs, but should be included before the milestone is considered usable.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2:** Bank statement formats and duplicate matching need targeted tests against real Swedish bank CSV/PDF examples.
- **Phase 3:** Review UX needs screenshots/browser checks because this is an operational workflow with dense financial state.

Phases with standard patterns:
- **Phase 1:** File upload, metadata persistence, and lifecycle APIs follow established project patterns.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Existing stack fits; no new core technology is required. |
| Features | HIGH | User direction and compliance constraints are clear. |
| Architecture | HIGH | Existing layered monolith maps cleanly to an intake slice. |
| Pitfalls | HIGH | Risks are grounded in current codebase concerns and accounting record requirements. |

**Overall confidence:** HIGH

### Gaps to Address

- **Exact bank statement formats:** Collect representative files during Phase 2 planning/testing.
- **Agent binary-file access model:** Confirm whether the connected agent can download/read PDFs and images directly; add extraction later only if needed.
- **Retention/deletion policy UI:** Keep deletion conservative until policy is explicitly defined.

## Sources

### Primary (HIGH confidence)

- Existing repository README, API docs, frontend code, and `.planning/codebase/*` — current app capabilities and architecture.
- Sveriges Riksdag, Bokföringslag (1999:1078) — legal basis for verifications, supporting information, and retention: https://www.riksdagen.se/sv/dokument-och-lagar/dokument/svensk-forfattningssamling/bokforingslag-19991078_sfs-1999-1078/
- Bokföringsnämnden, BFNAR 2013:2 — verification content, supplementation, and original information linkage: https://www.bfn.se/wp-content/uploads/2020/06/bfnar13-2-grund.pdf
- Bokföringsnämnden, Limited companies — Swedish AB bookkeeping obligations: https://www.bfn.se/english/what-applies-to/limited-companies/
- Bokföringsnämnden, Arkivering FAQ — preservation/transfer guidance: https://www.bfn.se/fragor-och-svar/arkivering/

### Secondary (MEDIUM confidence)

- Existing codebase concerns audit — attachment path-safety and auth/audit limitations relevant to intake.

---
*Research completed: 2026-05-14*
*Ready for roadmap: yes*
