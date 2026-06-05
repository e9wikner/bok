# Phase 09: CORR — Simplified Correction Flow - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-05
**Phase:** 09-CORR — Simplified Correction Flow
**Areas discussed:** Correction note data model, Agent suggestion mechanism, User approval surface, Note lifecycle and dismissal semantics

---

## Correction note data model

| Option | Description | Selected |
|--------|-------------|----------|
| Store suggestion JSON inline | The `correction_notes` table stores suggested rows directly in JSON. | |
| Reference a draft voucher | The note references a draft B-series voucher ID. | |
| Both — note stores text + refs draft | The note stores `note_text` and `status`, but the agent's suggestion is always a draft voucher referenced by `suggested_voucher_id`. | ✓ |

**User's choice:** Both — note stores text + refs draft
**Notes:** The user later clarified that correction notes should create entries under "Intag" (intake) so the agent discovers them via the intake queue. The note table is the source of truth for user intent; the draft voucher is the agent's proposal. Both are needed.

---

## Queue placement

| Option | Description | Selected |
|--------|-------------|----------|
| Agent queue only | Correction notes appear only in `/api/v1/agent/intake/pending` as `kind: 'correction_note'`. | ✓ |
| Both queues | Correction notes appear in both agent queue and frontend workspace. | |
| Frontend workspace only | Correction notes appear only in frontend workspace; agent uses separate endpoint. | |

**User's choice:** Agent queue only
**Notes:** The frontend workspace (`/api/v1/intake/workspace`) remains focused on source material. Correction notes are surfaced to users on the voucher detail page.

---

## Multiplicity and resolution

| Option | Description | Selected |
|--------|-------------|----------|
| One active note, kept after resolution | Each voucher has at most one active note. Resolved notes stay with terminal status. | ✓ |
| Multiple active notes, kept after resolution | A voucher can have many notes. | |
| One active note, deleted after resolution | Each voucher has at most one active note. Resolved notes are deleted. | |

**User's choice:** One active note, kept after resolution
**Notes:** Simple to reason about. Users must wait for one note to resolve before leaving another.

---

## Traceability

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, link to intake sources | The note stores `intake_source_ids` copied from the original voucher. | |
| No, voucher ID is enough | The note only stores `voucher_id`. Agent can fetch source context via existing endpoint if needed. | ✓ |

**User's choice:** No, voucher ID is enough
**Notes:** Simpler schema. Agent can call `GET /api/v1/vouchers/{id}/source-context` if it needs source material.

---

## Status transitions

| Option | Description | Selected |
|--------|-------------|----------|
| User can dismiss anytime | User can create and immediately dismiss a note. Agent never sees it. | ✓ |
| Agent must suggest first | User creates note (pending). Agent must suggest before user can approve or dismiss. | |

**User's choice:** User can dismiss anytime
**Notes:** Flexible for users who change their mind. If they want the agent to act, they wait.

---

## Agent suggestion mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| New agent-specific endpoint | `POST /api/v1/agent/correction-notes/{note_id}/suggest` creates draft and updates note in one call. | |
| Generic draft endpoint | `POST /api/v1/vouchers/{voucher_id}/correction-draft` creates draft; agent updates note separately. | ✓ |

**User's choice:** Generic draft endpoint
**Notes:** Reusable and RESTful. Agent may need two calls (create draft + update note status).

---

## Processing attempts

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, processing attempts | New table tracks every agent attempt with summary, warnings, errors. | |
| No, status only | The `status` field is sufficient. | ✓ |

**User's choice:** No, status only
**Notes:** Simpler. If the agent fails, the note stays pending and the agent retries.

---

## Draft lifecycle on dismissal

| Option | Description | Selected |
|--------|-------------|----------|
| Delete the draft | Draft is deleted when dismissed. | |
| Keep the draft | Draft stays as orphaned draft. | |
| Delete draft, log in history | Draft is deleted, but `correction_history` records the suggested rows in JSON. | ✓ |

**User's choice:** Delete draft, log in history
**Notes:** Clean, no orphaned drafts, but full audit trail preserved in `correction_history` with `corrected_voucher_id: null`.

---

## Approval model

| Option | Description | Selected |
|--------|-------------|----------|
| Agent posts directly | Correction notes are intake items; agent posts B-series correction immediately. | |
| User approves first | Agent creates draft, user reviews/approves before posting. | ✓ |

**User's choice:** User approves first
**Notes:** The user explicitly wants to keep CORR-04 intact despite initially suggesting intake-only flow.

---

## User approval surface

| Option | Description | Selected |
|--------|-------------|----------|
| On the voucher detail page | Suggested correction card on `/vouchers/{id}` with Approve/Dismiss. | ✓ |
| On a dedicated corrections page | New `/corrections/pending` page lists all suggested corrections. | |
| Both | Detail page for action + badge on vouchers list/dashboard. | |

**User's choice:** On the voucher detail page
**Notes:** Natural context. User is already reviewing the voucher.

---

## Edit before approve

| Option | Description | Selected |
|--------|-------------|----------|
| Approve or dismiss only | Binary approve/dismiss with no edits. | |
| Edit then approve | User can modify draft rows before approving. | ✓ |
| Dismiss-only with redirect to manual | User dismisses suggestion, then enters existing manual correction flow. | |

**User's choice:** Edit then approve
**Notes:** User wants flexibility to tweak the agent's suggestion before posting.

---

## Dismissal signal

| Option | Description | Selected |
|--------|-------------|----------|
| Visible in learning context | Dismissed notes appear in agent's correction history so it learns from bad suggestions. | ✓ |
| Invisible to agent | Dismissed notes are terminal states for humans only. | |

**User's choice:** Visible in learning context
**Notes:** Important for the feedback loop. Agent learns from both successful and unsuccessful suggestions.

---

## Agent inability

| Option | Description | Selected |
|--------|-------------|----------|
| Agent can reject | Add a 'rejected' status (or similar) for notes the agent cannot solve. | ✓ |
| Leave it pending | Agent does nothing; note stays pending. | |

**User's choice:** Agent can reject
**Notes:** Clearer communication. User sees when the agent gave up.

---

## Agent's Discretion

- Exact component styling for the "Suggested correction" card on the voucher detail page.
- Exact error message text for the `rejected` agent action.
- Whether the agent marks a note as `rejected` via a dedicated agent endpoint or by updating the note directly.
- Whether the frontend uses a single "approve" endpoint or two calls (update draft + post) when the user edits before approving.

## Deferred Ideas

- **Frontend workspace badge for pending corrections** — Deferred. Intake workspace remains source-material only.
- **Dedicated corrections inbox page** — Deferred in favor of inline approval on voucher detail page.
- **Agent auto-retry on rejected notes** — Not discussed; could be a future enhancement.
