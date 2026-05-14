# Pitfalls Research

**Domain:** Swedish small-company bookkeeping source-material intake for AI-agent posting
**Researched:** 2026-05-14
**Confidence:** HIGH

## Critical Pitfalls

### Pitfall 1: Losing the Link Between Source Material and Posted Voucher

**What goes wrong:**
The agent posts a voucher but later review cannot show which receipt, invoice, bank row, and user explanation drove the decision.

**Why it happens:**
Teams treat uploads as transient agent input rather than accounting evidence.

**How to avoid:**
Persist intake source records, processing attempts, and source-to-voucher links before marking anything processed.

**Warning signs:**
Voucher detail pages show accounting rows but no original uploaded source or agent rationale.

**Phase to address:**
Phase 1.

---

### Pitfall 2: Changing or Discarding Original Accounting Information

**What goes wrong:**
The system stores only extracted text, thumbnails, or transformed files, making the original source hard to prove.

**Why it happens:**
OCR/extraction is treated as the product instead of a derived convenience.

**How to avoid:**
Preserve the original file bytes, SHA-256 hash, filename, content type, and upload metadata. Store extraction only as supplemental metadata.

**Warning signs:**
No stable download endpoint for the original upload, or no file hash in the database.

**Phase to address:**
Phase 1.

---

### Pitfall 3: Duplicate Posting From Re-Uploads or Bank Rows

**What goes wrong:**
The same receipt or bank transaction creates multiple posted vouchers.

**Why it happens:**
Direct posting removes a manual checkpoint, so duplicate detection must happen before and during agent processing.

**How to avoid:**
Use file hashes, bank external IDs, source statuses, and agent duplicate checks against existing vouchers, invoices, payroll, and bank transactions.

**Warning signs:**
Repeated uploads are accepted silently, or the agent queue includes already-processed source IDs.

**Phase to address:**
Phase 1 and Phase 2.

---

### Pitfall 4: Bank Statements Treated as Complete Bookkeeping Context

**What goes wrong:**
The agent posts expense or income vouchers from bank text alone and misses VAT, reimbursement treatment, invoice settlement, or payroll semantics.

**Why it happens:**
Bank data looks structured but is often only payment evidence, not the full business event.

**How to avoid:**
Expose bank statements as one input alongside receipts, invoice records, payroll, existing vouchers, and user hints. Store uncertainty in processing notes.

**Warning signs:**
Agent code path only reads `bank_transactions` and does not inspect source documents or historical context.

**Phase to address:**
Phase 2.

---

### Pitfall 5: Unsafe File Serving

**What goes wrong:**
An attachment/intake record with a manipulated `stored_path` can serve files outside the intended storage root.

**Why it happens:**
File paths are trusted after reading them from the database.

**How to avoid:**
Resolve paths and enforce that they remain under the configured intake/attachment root before download/delete. Add regression tests.

**Warning signs:**
`FileResponse` is built directly from a DB path without `resolve()` and root containment checks.

**Phase to address:**
Phase 1.

---

### Pitfall 6: Review UI Shows Outcomes But Not Why

**What goes wrong:**
The user sees a posted voucher but cannot understand why the agent chose those accounts or whether a source item was skipped/failed.

**Why it happens:**
Processing status is collapsed to a boolean "done" state.

**How to avoid:**
Store processing attempts with summary, warnings, confidence if available, errors, and linked sources/vouchers.

**Warning signs:**
The intake page can only display "pending" and "processed" with no details.

**Phase to address:**
Phase 3.

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Nullable `voucher_id` on source only | Quick linking | Fails for bank batches, multiple receipts per voucher, and one receipt split across vouchers | Only for throwaway prototype; not recommended here. |
| Reusing voucher attachments table for pre-voucher files | Less schema | Forces fake vouchers or nullable voucher references | Never for final intake. |
| No processing attempt table | Less work | No audit/debug trail for autonomous posting | Never for direct-posting automation. |
| MIME-only validation | Simple upload validation | Spoofed content types and unsafe downloads | Acceptable only with auth, size limits, and later content sniffing. |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Agent API | Return only text metadata, not file access | Return authenticated file download URLs or IDs the agent can fetch. |
| Bank import | Import transactions but lose source batch identity | Link every imported transaction to its uploaded bank source/batch. |
| Voucher posting | Create a separate intake-specific posting path | Use existing LedgerService/agent voucher API so validation stays consistent. |
| Corrections | Learn only from corrected voucher rows | Link correction back to original source and agent processing notes. |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Loading full file bytes for list APIs | Slow intake page | List metadata only; download files separately | Dozens of PDFs/images. |
| Recomputing duplicate candidates by scanning all vouchers | Slow agent checks | Store hashes, external IDs, and indexed dates/amounts | Hundreds/thousands of vouchers. |
| Storing bank rows without indexes | Slow pending queue and matching | Index status, date, external ID, source batch | Large statement imports. |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Trusting DB file paths | Arbitrary readable file disclosure | Root-path enforcement before serving/deleting. |
| Letting agents delete source material | Loss of accounting evidence | Agents can mark skipped/processed, not delete originals. |
| No actor/audit on intake actions | Weak accountability for sensitive financial data | Log upload, download, processing, and link operations with actor identity. |
| Permissive file types | Malware/content handling risk | Allow only PDF/images/known bank file types; size limits and safe content disposition. |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Hiding processed intake | User cannot verify what happened | Keep searchable processed history with voucher links. |
| Mixing bank statements and receipt uploads in one undifferentiated list | Confusing workflows | Separate upload affordances and filters while allowing unified status overview. |
| Asking for too much metadata | Automation value disappears | Require only file and optional explanation; derive or let agent infer the rest. |
| No failed-state recovery | User cannot fix upload/agent issues | Show failed/needs-attention states with retry or clarification path. |

## "Looks Done But Isn't" Checklist

- [ ] **Upload works:** Verify source can be consumed before voucher exists.
- [ ] **Agent sees queue:** Verify pending API includes metadata, hints, and file references.
- [ ] **Posting works:** Verify posted voucher links back to all source IDs.
- [ ] **Review works:** Verify voucher detail shows original source and agent attempt notes.
- [ ] **Correction learning works:** Verify corrected voucher remains linked to source and available to agent context.
- [ ] **File safety works:** Verify path traversal/manipulated stored path cannot escape storage root.
- [ ] **Bank input works:** Verify bank statement uploads can create missing vouchers without duplicating existing vouchers.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Duplicate posting | MEDIUM | Detect duplicate, create correction voucher if posted, mark duplicate intake item skipped with reason. |
| Wrong account/VAT | LOW-MEDIUM | User creates correction voucher; agent reads correction history before next run. |
| Lost source link | HIGH | Re-link manually if file exists; otherwise source traceability may be permanently weakened. |
| Failed bank parse | LOW | Keep original file, mark needs_attention, let user upload CSV or agent inspect original. |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Lost source-voucher link | Phase 1 | Unit/API test: processed intake has voucher link and voucher detail references source. |
| Original file not preserved | Phase 1 | Test file hash/download after processing. |
| Unsafe file serving | Phase 1 | Security regression test with malicious stored path. |
| Duplicate posting | Phase 1/2 | Tests for duplicate file upload and duplicate bank transaction handling. |
| Bank context overconfidence | Phase 2 | Agent context includes source docs, bank rows, vouchers, invoices, and correction history. |
| Opaque review | Phase 3 | UI shows processing attempts and source material from posted voucher. |

## Sources

- Existing codebase concerns for attachment path safety and auth/audit limitations.
- Sveriges Riksdag, Bokföringslag (1999:1078), especially 5 kap. 6-7 §§ and 7 kap. 1-2, 6 §§.
- BFNAR 2013:2, Chapter 5 verification guidance.
- Bokföringsnämnden Arkivering FAQ.

---
*Pitfalls research for: Swedish bookkeeping intake*
*Researched: 2026-05-14*
