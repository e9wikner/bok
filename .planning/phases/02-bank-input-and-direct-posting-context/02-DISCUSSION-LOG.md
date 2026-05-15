# Phase 2: Bank Input and Direct Posting Context - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-05-15T08:27:28+02:00
**Phase:** 2-Bank Input and Direct Posting Context
**Areas discussed:** Bank input shape and lifecycle, CSV import behavior, Agent context package, Duplicate and matching safeguards, Traceability for bank-created vouchers

---

## Bank Input Shape and Lifecycle

### One Bank Input Record

| Option | Description | Selected |
|--------|-------------|----------|
| One upload | Each uploaded statement/status file becomes one immutable bank input, matching Phase 1 intake simplicity. | x |
| One statement period | Multiple files could be grouped under a period, but that adds batch semantics now. | |
| Agent decides | Planner chooses the simplest model that satisfies traceability and CSV import. | |

**User's choice:** One upload.
**Notes:** One bank input record equals one uploaded file.

### Accepted File Types

| Option | Description | Selected |
|--------|-------------|----------|
| CSV plus statement/status documents | Accept CSV for parsing and PDF/images for statement or account-status evidence. | |
| CSV only | Narrowest implementation, but it interprets Phase 2 bank statements/statuses as CSV exports. | x |
| Any file as opaque evidence | Flexible, but weaker validation and less useful for agent automation. | |

**User's choice:** CSV only.
**Notes:** Phase 2 should not include PDF/image/screenshot bank statements.

### Lifecycle Statuses

| Option | Description | Selected |
|--------|-------------|----------|
| Same statuses | Reuse `pending`, `processing`, `processed`, `skipped`, `failed`, `needs_attention`. | |
| Bank-specific statuses | Use statuses such as `uploaded`, `parsed`, `imported`, `partially_imported`, `failed`. | |
| Minimal statuses | Use only `pending`, `processed`, and `failed`. | x |

**User's choice:** Minimal statuses.
**Notes:** Keep bank input state compact.

### Duplicate CSV Rows

| Option | Description | Selected |
|--------|-------------|----------|
| Skip duplicates and process the rest | Preserve upload record with imported/skipped counts. | x |
| Reject whole upload on any duplicate | Stricter, but annoying for overlapping statement exports. | |
| Import duplicates as separate rows | Preserves raw input but risks double posting. | |

**User's choice:** Skip duplicates and process the rest.
**Notes:** Import result counts should be preserved.

---

## CSV Import Behavior

### Bank Account Association

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-create/reuse a manual connection | Use a default manual bank connection when no explicit account is provided. | |
| Require bank connection ID | Caller must choose an existing bank connection before upload. | x |
| Store account fields on bank input only | Avoid `bank_connections`, but duplicate existing bank model. | |

**User's choice:** The user selects from a list of relevant accounts to get the connection.
**Notes:** No silent default connection.

### CSV Format Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Configurable column mapping per upload | Caller can specify date, amount, description, delimiter, etc. | |
| Auto-detect common Swedish columns only | Simpler UI/API, but brittle when banks vary. | x |
| Strict fixed format | Easiest to test, but users must normalize files manually. | |

**User's choice:** Try to autodetect the format from a list of previously known formats.
**Notes:** Known-format detection is the primary path, not manual column mapping.

### Unknown CSV Format

| Option | Description | Selected |
|--------|-------------|----------|
| Fail the bank input with a clear error | Preserves automation simplicity and lets the frontend show what went wrong. | x |
| Fall back to manual mapping fields | More flexible, but likely belongs with the Phase 3 frontend workspace. | |
| Store as pending for agent interpretation | Keeps the file around, but CSV-only Phase 2 would not import transactions. | |

**User's choice:** Fail with a clear error.
**Notes:** Unrecognized CSVs should become failed bank inputs with parse details.

### Import Timing

| Option | Description | Selected |
|--------|-------------|----------|
| Immediate import | Upload parses and imports transactions right away, preserving imported/skipped counts. | x |
| Store first, agent imports later | Gives the agent more control, but delays bank transaction context. | |
| Two-step API | Upload first, separate process/import call; explicit but more workflow surface. | |

**User's choice:** Immediate import.
**Notes:** Successful CSV upload should update bank transactions immediately.

---

## Agent Context Package

### Context Delivery

| Option | Description | Selected |
|--------|-------------|----------|
| One focused bank context endpoint | Returns bank inputs, imported pending transactions, relevant matches, and correction hints in one response. | |
| Separate narrow endpoints | Agent calls bank inputs, transactions, invoices, corrections, etc. separately. | |
| Extend existing pending intake queue | Mix bank inputs into the same queue as voucher sources. | x |

**User's choice:** Extend the existing agent pending intake queue.
**Notes:** Preserve separate type/model underneath.

### Shared Queue Shape

| Option | Description | Selected |
|--------|-------------|----------|
| Typed queue items | One queue response with `kind: voucher_source | bank_input`, and fields specific to each kind. | x |
| Bank inputs as source_type values | Reuse `source_type` like `bank_csv`; simpler response, but weaker separation. | |
| Separate sections in one response | `{voucher_sources: [...], bank_inputs: [...]}`; clear, but less like a unified queue. | |

**User's choice:** Typed queue items.
**Notes:** Include `kind` and type-specific fields.

### Transaction Detail Inline

| Option | Description | Selected |
|--------|-------------|----------|
| Summary plus linked transaction IDs | Counts, date range, account, imported/skipped counts, and references to transaction IDs. | x |
| Full transaction rows inline | Agent gets every imported row immediately; useful but heavier. | |
| Only file metadata | Agent must call a separate endpoint for all transaction details. | |

**User's choice:** Summary plus linked transaction IDs.
**Notes:** Keep the queue compact.

### Correction History

| Option | Description | Selected |
|--------|-------------|----------|
| Relevant correction summary in agent context | Include recent/related correction pairs and summaries. | |
| Full correction history every time | Complete but noisy and potentially large. | x |
| Separate correction endpoint only | Agent can fetch it, but Phase 2 may fail to surface it in bank decisions. | |

**User's choice:** Full correction history every time.
**Notes:** Prioritize complete learning context over compactness for Phase 2.

---

## Duplicate and Matching Safeguards

### Posting Blockers

| Option | Description | Selected |
|--------|-------------|----------|
| Any strong existing match | Block if transaction is already booked, linked, or clearly matches existing accounting. | |
| Only explicit links | Block only when `matched_voucher_id` or a source link already exists. | |
| Agent decides | Backend surfaces candidates, agent chooses whether to post. | x |

**User's choice:** Agent decides.
**Notes:** Inferred matches should inform the agent, not hard-block posting.

### Candidate Surface

| Option | Description | Selected |
|--------|-------------|----------|
| Broad candidate set | Existing bank status/link, vouchers, invoices/payments, payroll, and related intake sources. | |
| Accounting records only | Vouchers, invoices, payroll; skip softer source/intake hints. | |
| Bank transaction links only | Only current `bank_transactions` status and `matched_voucher_id`. | x |

**User's choice:** Bank transaction links only.
**Notes:** Keep Phase 2 duplicate signal narrow.

### Explicit Transaction Reuse

| Option | Description | Selected |
|--------|-------------|----------|
| Reject explicit duplicate transaction use | Backend blocks reuse of a transaction already marked booked or matched. | x |
| Allow with override reason | Agent may intentionally reuse it if it supplies a reason. | |
| Always allow | Trust the agent entirely. | |

**User's choice:** Reject explicit duplicate transaction use.
**Notes:** This is the hard backend guard.

### Successful Posting Transaction Update

| Option | Description | Selected |
|--------|-------------|----------|
| Mark booked and set matched_voucher_id | Direct state update on every used transaction. | x |
| Only create separate link records | Keep transaction status unchanged, derive status from links. | |
| Leave unchanged | Voucher traceability exists elsewhere, agent handles future duplicate checks. | |

**User's choice:** Mark booked and set `matched_voucher_id`.
**Notes:** Used transactions must no longer look pending.

---

## Traceability for Bank-Created Vouchers

### Required Voucher Links

| Option | Description | Selected |
|--------|-------------|----------|
| Bank input and transaction rows | Link to uploaded CSV bank input and every bank transaction row used. | x |
| Transaction rows only | Enough if transactions retain source metadata, but weaker direct file traceability. | |
| Bank input only | Simple, but hard to tell which rows caused the voucher. | |

**User's choice:** Bank input and transaction rows.
**Notes:** Preserve both file-level and row-level traceability.

### Multiple Rows per Voucher

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, multiple rows allowed | Supports grouped bank fees, split payments, and related transfers. | x |
| No, one transaction per voucher | Simpler and safer, but may force awkward duplicate voucher creation. | |
| Agent decides but planner may restrict | Allow implementation to choose based on schema risk. | |

**User's choice:** Yes, multiple rows allowed.
**Notes:** A single bank-driven voucher can consume multiple bank transaction rows.

### Multiple Vouchers per CSV

| Option | Description | Selected |
|--------|-------------|----------|
| Yes | One uploaded CSV can import many transactions and produce multiple linked vouchers over time. | x |
| No | One uploaded CSV should correspond to one posted voucher; too restrictive for bank statements. | |
| Only in same processing run | Multiple vouchers allowed, but all must be created at once. | |

**User's choice:** Yes.
**Notes:** One bank input can lead to multiple vouchers over time.

### Ordinary Intake Sources in Bank Posting

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, when available | Link bank input, bank transaction rows, and related voucher source item(s). | x |
| No, bank-only in Phase 2 | Keeps posting call simpler, voucher sources handled separately. | |
| Only post-linking later | Agent posts from bank first, then links receipt/invoice sources through repair flow. | |

**User's choice:** Yes, when available.
**Notes:** Bank-driven posting can also link ordinary receipt/invoice source items.

---

## the agent's Discretion

None. The user selected concrete behavior for every discussed area.

## Deferred Ideas

None. Discussion stayed within Phase 2 scope.
