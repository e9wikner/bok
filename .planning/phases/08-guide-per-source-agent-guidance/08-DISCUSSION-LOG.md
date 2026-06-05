# Phase 8: GUIDE — Per-Source Agent Guidance - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-05
**Phase:** 08-GUIDE — Per-Source Agent Guidance
**Areas discussed:** Field naming, Frontend discoverability, Edit lifecycle, Scope

---

## Field naming

| Option | Description | Selected |
|--------|-------------|----------|
| agent_guidance | More directive — implies 'how to book this'. The research uses this term slightly more often. | ✓ |
| agent_message | More conversational — implies 'a note for the agent'. The requirements (GUIDE-01) use 'agent message' in the text. | |
| agent_instruction | More formal — implies a command. Might be too strong. | |

**User's choice:** `agent_guidance`
**Notes:** Canonical name chosen for DB column, API field, and code references. The user preferred the more directive term over the softer "agent_message" or the too-formal "agent_instruction".

---

| Option | Description | Selected |
|--------|-------------|----------|
| PUT /api/v1/intake/{id}/guidance | Short, matches the field name. | |
| PUT /api/v1/intake/{id}/agent-guidance | More explicit — avoids ambiguity with other types of guidance. | ✓ |
| PATCH /api/v1/intake/{id} | Generic update — reuses the existing intake source resource. | |

**User's choice:** `PUT /api/v1/intake/{id}/agent-guidance`
**Notes:** Preferred explicit path over generic PATCH to make intent clear.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Agentinstruktion | Swedish — clear and directive. | |
| Meddelande till agent | Swedish — softer, matches the requirements' wording. | ✓ |
| Agent guidance | English — matches the field name exactly. | |

**User's choice:** `Meddelande till agent`
**Notes:** Preferred Swedish label that matches the requirements text, keeping the UI consistent with other Swedish labels.

---

| Option | Description | Selected |
|--------|-------------|----------|
| agent_guidance | Matches the canonical API/frontend field name. | ✓ |
| agent_message | Different from the API field name — creates a mapping layer. | |

**User's choice:** `agent_guidance`
**Notes:** Aligned DB column with the canonical field name.

---

## Frontend discoverability

| Option | Description | Selected |
|--------|-------------|----------|
| Collapsed behind an accordion | Hidden by default. Reduces cognitive load for non-expert users. | |
| Always visible below the explanation field | Shown as a standard textarea. No extra clicks. | ✓ |
| Visible only when a toggle is enabled in settings | User opts in via a settings toggle. | |

**User's choice:** Always visible below the explanation field
**Notes:** User preferred immediate visibility over hiding the field, even though the research recommended collapsing it for non-expert users.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — editable on the detail page | Users can review and edit the guidance after upload. | ✓ |
| Yes — read-only on the detail page | Users can see what they wrote, but can't edit it. | |
| No — only on the upload form | The detail page doesn't show the guidance field at all. | |

**User's choice:** Yes — editable on the detail page
**Notes:** User wanted the ability to refine guidance after upload, not just set it once.

---

| Option | Description | Selected |
|--------|-------------|----------|
| 'Exempel: bokför på konto 6540, moms 25%' | Concrete example that teaches the user what to write. | |
| 'Instruktion till agenten om hur detta underlag ska bokföras' | Descriptive — explains the purpose without prescribing content. | |
| 'Valfritt — beskriv hur agenten ska bokföra detta underlag' | Emphasizes that it's optional. | ✓ |

**User's choice:** `Valfritt — beskriv hur agenten ska bokföra detta underlag`
**Notes:** User wanted to emphasize that the field is optional, reducing pressure on users.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — short helper text | e.g., 'Agenten läser detta när den bearbetar underlaget.' | |
| No — keep the form minimal | The placeholder text is enough. | ✓ |

**User's choice:** No — keep the form minimal
**Notes:** User preferred minimal forms over extra explanatory text.

---

## Edit lifecycle

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — anytime before the source is processed | Users can add guidance to pending sources. Once processed, locked. | ✓ |
| Yes — anytime, even after processing | Users can edit guidance on processed sources too. | |
| No — guidance must be set at upload time | If you forgot to add guidance, you can't add it later. | |

**User's choice:** Yes — anytime before the source is processed
**Notes:** User wanted flexibility to add guidance later, but with a clear boundary at processing time.

---

| Option | Description | Selected |
|--------|-------------|----------|
| No — processed sources are locked | Guidance is immutable once processed. Use correction flow instead. | ✓ |
| Yes — but it doesn't affect the already-posted voucher | Users can edit guidance for documentation/review purposes. | |
| Yes — and it triggers a reprocessing suggestion | Editing guidance creates a 'needs_attention' flag. | |

**User's choice:** No — processed sources are locked
**Notes:** User wanted clean lifecycle separation. Corrections should go through the correction flow (Phase 9), not by editing guidance.

---

| Option | Description | Selected |
|--------|-------------|----------|
| 409 Conflict with clear error message | Explicit failure — frontend shows clear error. | ✓ |
| 200 OK but no-op | Backend accepts request but doesn't change processed source. | |
| 400 Bad Request | Generic client error. | |

**User's choice:** 409 Conflict with clear error message
**Notes:** User preferred explicit error over silent ignore or generic error.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Optional — most users won't need it | The field is nullable. Matches automation-first goal. | ✓ |
| Required — users must explicitly confirm no guidance | Forces users to think about the agent. | |

**User's choice:** Optional — most users won't need it
**Notes:** User strongly aligned with automation-first goal — guidance is an override, not a requirement.

---

## Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — both voucher sources and bank inputs | Agent guidance applies to all intake items. | |
| No — only voucher sources (receipts/invoices) | Strictly follow the requirements. | ✓ |
| Defer — only voucher sources now, add bank inputs later | Keep scope minimal for Phase 8. | |

**User's choice:** No — only voucher sources (receipts/invoices)
**Notes:** User wanted to strictly follow the requirements. Bank inputs have their own metadata.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Include null — uniform schema for all items | Every item in the agent queue has a `guidance` field. | ✓ |
| Omit the field for bank inputs | Only voucher sources include `guidance`. | |

**User's choice:** Include null — uniform schema for all items
**Notes:** User preferred predictable API schema over minimal payload.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Hide it entirely | The bank input detail page doesn't show the guidance field at all. | ✓ |
| Show as read-only '-' | Shows a disabled/empty field with a dash. | |

**User's choice:** Hide it entirely
**Notes:** User wanted the bank input detail page focused on bank-specific metadata.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — a small badge or icon | e.g., a 'message' icon in the workspace table. | |
| No — only visible on detail page and upload form | Keep the workspace list clean. | ✓ |

**User's choice:** No — only visible on detail page and upload form
**Notes:** User preferred a clean workspace table over extra indicators.

---

## Agent's Discretion

- Component styling (textarea height, spacing) — left to planner/executor to match existing Tailwind patterns.
- Exact error message text for the 409 response — left to implementation, should be clear per existing conventions.

## Deferred Ideas

- **Bank input guidance:** Adding `agent_guidance` to bank inputs was discussed and deferred. Can be added later if users request it.
- **Workspace list guidance indicator:** A badge/icon in the workspace table showing which sources have guidance was deferred.
