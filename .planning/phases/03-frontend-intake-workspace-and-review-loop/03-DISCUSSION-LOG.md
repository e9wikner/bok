# Phase 3: Frontend Intake Workspace and Review Loop - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-05-15
**Phase:** 3-Frontend Intake Workspace and Review Loop
**Areas discussed:** Workspace shape, Upload flow, Status and failure review, Voucher review context

---

## Workspace Shape

| Option | Description | Selected |
|--------|-------------|----------|
| Unified table | One operational queue with a type column; matches the typed agent queue and is fastest to scan/filter. | ✓ |
| Two sections | Voucher sources and bank inputs appear in separate panels; clearer separation but more switching. | |
| Status lanes | Kanban-style columns by lifecycle status; more visual, less dense for bookkeeping work. | |

**User's choice:** Unified table
**Notes:** The unified table must still make voucher sources and bank inputs visibly typed.

| Option | Description | Selected |
|--------|-------------|----------|
| Status tabs | Top tabs for pending, processing, processed, skipped, failed, needs_attention, plus all. | |
| Filter chips only | Compact chips for status and type, closer to the current voucher list pattern. | ✓ |
| Grouped rows | One table, but rows are grouped under status headings. | |

**User's choice:** Filter chips only
**Notes:** Keep the workspace close to the existing voucher list pattern.

| Option | Description | Selected |
|--------|-------------|----------|
| Own sidebar item | Add Intag as a main workspace next to Verifikationer. | |
| Under Verifikationer | Make it a secondary route near vouchers; keeps navigation smaller. | ✓ |
| Dashboard entry only | Link from overview only; lightest navigation change. | |

**User's choice:** Under Verifikationer
**Notes:** Intake should not become a new top-level sidebar item in this phase.

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated detail page | `/intake/{id}` for full metadata, files, attempts, and linked vouchers. | ✓ |
| Inline expansion | Expand a row in the table. | |
| Side panel | Drawer-style detail without leaving the table. | |

**User's choice:** Dedicated detail page
**Notes:** The detail page is the proper surface for metadata, files, processing attempts, and linked vouchers.

---

## Upload Flow

| Option | Description | Selected |
|--------|-------------|----------|
| Two upload panels | One panel for receipt/invoice PDFs/images, one for bank CSV with bank selection. | ✓ |
| Single upload dropzone | User drops any supported file and then chooses type. | |
| Upload buttons in toolbar | Compact commands above the table. | |

**User's choice:** Two upload panels
**Notes:** Keeps voucher source material and bank CSV inputs visibly separate.

| Option | Description | Selected |
|--------|-------------|----------|
| Source type + explanation | Choose receipt/supplier invoice/customer invoice/reimbursement/other and add optional short explanation. | ✓ |
| Explanation only | Keep upload very fast and leave classification to the agent. | |
| Source type required | Force a type before upload. | |

**User's choice:** Source type + explanation
**Notes:** Source type is collected at upload time, with explanation remaining optional.

| Option | Description | Selected |
|--------|-------------|----------|
| Required dropdown in bank panel | User selects an existing bank connection before upload. | |
| Remember last used | Preselect the last connection but still show it. | |
| Create connection shortcut | Add a link/button to settings if no connection exists. | |

**User's choice:** User selects account number associated with the CSV upload.
**Notes:** The visible choice should be a bank account number. The frontend should map that to the backend bank connection/account ID.

| Option | Description | Selected |
|--------|-------------|----------|
| Stay on workspace and refresh table | Show a compact success message and update the queue/status counts. | ✓ |
| Open intake detail page | Immediately navigate to the uploaded item's detail page. | |
| Keep upload panel focused | Clear the form for another upload and refresh in the background. | |

**User's choice:** Stay on workspace and refresh table
**Notes:** Successful upload should not navigate away from the workspace.

---

## Status and Failure Review

| Option | Description | Selected |
|--------|-------------|----------|
| Badge + short detail column | Status badge plus one compact status/detail text such as imported count, linked voucher, or error summary. | ✓ |
| Badge only | Cleanest table, but failures require opening detail to understand anything. | |
| Expanded status cards above table | Visible counts and summaries, but more page weight. | |

**User's choice:** Badge + short detail column
**Notes:** The table should show enough context to scan without opening every item.

| Option | Description | Selected |
|--------|-------------|----------|
| Actionable error summary | Show parse/processing error or agent summary directly in the detail column, truncated if needed. | ✓ |
| Generic failure label | Keep the table tidy and require opening detail. | |
| Warning emphasis | Visually highlight failed/needs_attention rows with stronger color treatment. | |

**User's choice:** Actionable error summary
**Notes:** Failed and needs_attention rows should expose useful error context directly.

| Option | Description | Selected |
|--------|-------------|----------|
| Primary link to voucher | Processed rows link straight to the posted voucher, with detail page secondary. | ✓ |
| Primary link to intake detail | Always open intake detail first. | |
| Show both actions | Separate Open source and Open voucher actions in the row. | |

**User's choice:** Primary link to voucher
**Notes:** Processed items optimize for voucher review.

| Option | Description | Selected |
|--------|-------------|----------|
| What happened + next correction path | Show status, processing notes/errors, source file, and expected fix path. | |
| Raw processing history | Show attempts and errors as an audit log. | ✓ |
| Minimal metadata | File details, status, and timestamps only. | |

**User's choice:** Raw processing history
**Notes:** Failed/needs_attention detail pages should prefer audit-style history over guided remediation.

---

## Voucher Review Context

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated source-material section | Separate from manual voucher attachments, showing original intake files and upload explanations. | ✓ |
| Merged with attachments | One Bilagor/Underlag section containing manual attachments and intake sources. | |
| Compact provenance row | Small source summary near the voucher header. | |

**User's choice:** Dedicated source-material section
**Notes:** Intake evidence should not be merged with manual voucher attachments.

| Option | Description | Selected |
|--------|-------------|----------|
| Audit-style processing section | Show summaries, warnings, errors, actor, and timestamps for source attempts. | ✓ |
| Compact agent note block | One short summary near the AI badge/header. | |
| Only on intake detail | Voucher page links back to intake detail for processing notes. | |

**User's choice:** Audit-style processing section
**Notes:** Voucher review needs the processing notes directly on the voucher detail page.

| Option | Description | Selected |
|--------|-------------|----------|
| Separate bank source subsection | Show bank input file, imported transaction rows/signals, and link/download. | |
| Same source-material section | Show bank inputs beside voucher-source files under one source section. | ✓ |
| Only transaction summary | Show account/date/amount/reference rows, but not original CSV context. | |

**User's choice:** Same source-material section
**Notes:** Bank inputs should be clearly typed but live in the same dedicated source-material section.

| Option | Description | Selected |
|--------|-------------|----------|
| Correction chain section | Show original voucher, correction voucher(s), correction reason, and note that history is agent-readable. | ✓ |
| Only audit history | Rely on the existing change history section. | |
| Header badge + link | Compact Corrected badge with link to correction voucher. | |

**User's choice:** Correction chain section
**Notes:** Corrections are part of the agent learning/review loop and should be visible as a chain.

---

## the agent's Discretion

None.

## Deferred Ideas

None.
