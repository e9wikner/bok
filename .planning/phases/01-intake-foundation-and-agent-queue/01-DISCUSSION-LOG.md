# Phase 1: Intake Foundation and Agent Queue - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-05-14
**Phase:** 1-Intake Foundation and Agent Queue
**Areas discussed:** Intake item shape, Agent queue flow, Source file access, Voucher traceability

---

## Intake Item Shape

| Question | Options Presented | User's Choice |
|----------|-------------------|---------------|
| What should one pending queue item represent? | One file; Multi-file batch; You decide | One file |
| If a real-world voucher uses multiple source files, how should Phase 1 handle that? | Link many items to one voucher; Ask user to combine files first; Defer multi-source vouchers | Ask user to combine files first |
| When the same file is uploaded again, what should the API do? | Return existing item; Reject with conflict; Create a note only | Reject with conflict |
| What metadata is essential beyond required file metadata? | Explanation only; Explanation + source type; Explanation + bookkeeping hints | Explanation + source type |
| How strict should `source_type` be? | Small enum; Free text; Optional enum plus explanation | Small enum |
| Should uploaded intake items be editable before processing? | Metadata editable only; No edits; File replacement allowed | No edits |
| Should Phase 1 allow deleting an intake item before processing? | No delete; Delete pending only; Soft-delete pending only | Soft-delete pending only |

**Notes:** Each uploaded file is the durable unit of work. Phase 1 intentionally avoids batches, edits, and replacement semantics.

---

## Agent Queue Flow

| Question | Options Presented | User's Choice |
|----------|-------------------|---------------|
| How should the agent claim work? | Explicit claim endpoint; Implicit claim on outcome; Lease with timeout | Implicit claim on outcome |
| If two agent runs pick up the same pending item, how should duplicates be prevented? | Outcome-time guard; Agent responsibility; No guard beyond duplicate file hash | Outcome-time guard |
| Which processing statuses should the agent be allowed to set directly? | Final statuses only; All lifecycle statuses; Processed or failed only | Processed or failed only |
| For failed processing attempts, what detail should be required? | Summary + error text; Free-form notes only; Structured error code | Summary + error text |

**Notes:** The queue should remain simple in Phase 1. Concurrency protection happens when recording the outcome, not through a claim/lease model.

---

## Source File Access

| Question | Options Presented | User's Choice |
|----------|-------------------|---------------|
| Should the agent receive authenticated download references to original files? | Yes, direct download URLs; Metadata only; Embedded file content | Yes, direct download URLs |
| How should download URLs behave? | Stable authenticated endpoint; Short-lived signed URL; Agent-only route | Stable authenticated endpoint |
| Should storage use `ATTACHMENTS_DIR` or a separate intake storage root? | Separate intake root; Reuse attachments root; Planner decides | Separate intake root |
| How strict should path safety be? | Resolve-and-check root every time; Trust generated paths; Store relative paths only | Resolve-and-check root every time |

**Notes:** Agent file access is part of Phase 1. The endpoint must be authenticated and must enforce storage-root containment every time.

---

## Voucher Traceability

| Question | Options Presented | User's Choice |
|----------|-------------------|---------------|
| How should source linkage happen when the agent posts a voucher? | Required in posting call; Link after posting; Both allowed | Both allowed |
| Should Phase 1 allow multiple intake items to link to one voucher? | One intake item per voucher; Many intake items per voucher; Schema supports many, API enforces one | One intake item per voucher |
| What happens when the linked voucher posts successfully? | Auto-mark processed; Agent marks processed separately; Keep status pending until review | Auto-mark processed |
| What traceability detail should be stored on the processing attempt? | Summary + voucher id + actor/time; Full reasoning text; Summary + warnings + voucher id + actor/time | Summary + voucher id + actor/time |

**Notes:** Source linkage should be easiest in the posting call, but post-linking is allowed for repair/manual cases. Phase 1 keeps the source-to-voucher model one-to-one.

---

## the agent's Discretion

None.

## Deferred Ideas

None.
