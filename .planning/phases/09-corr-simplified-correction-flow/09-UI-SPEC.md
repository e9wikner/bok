---
phase: 09
slug: corr-simplified-correction-flow
status: approved
shadcn_initialized: false
preset: bok-existing
created: 2026-06-05
---

# Phase 09 — UI Design Contract

> Visual and interaction contract for the simplified correction-note and suggested-correction flow on voucher detail pages.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none |
| Preset | bok-existing |
| Component library | local `components/ui` primitives |
| Icon library | lucide-react |
| Font | `var(--font-geist-sans)`, fallback `system-ui`, `sans-serif` |

Use the existing operational voucher detail UI. Do not introduce a new visual direction, third-party UI package, custom animation system, or new global CSS variables for this phase.

---

## Surfaces In Scope

| Surface | Path | Required Change |
|---------|------|-----------------|
| Posted voucher detail header area | `frontend-v3/app/vouchers/[id]/page.tsx` | Add a compact correction-note entry surface for posted vouchers |
| Voucher detail content stack | `frontend-v3/app/vouchers/[id]/page.tsx` | Add a conditional suggested-correction card for notes with `status: "suggested"` |
| Existing manual correction table | `frontend-v3/app/vouchers/[id]/page.tsx` | Reuse row editing controls for suggested correction rows |
| Voucher source context / correction history | `frontend-v3/app/vouchers/[id]/page.tsx` | Keep source material, processing notes, and correction chain visible below the correction workflow |
| Intake workspace | `frontend-v3/app/vouchers/intake/page.tsx` | No UI change; correction notes must not appear in this workspace |

---

## Layout Contract

### Correction Note Entry

- Render only when `voucher.status === "posted"` and the current voucher is not itself a correction draft awaiting approval.
- Place the note entry surface directly below the existing save-result banner and above the `Konteringsrader` card.
- Use one full-width `Card`; do not place it inside another card.
- Card title: `Korrigeringsnotering`.
- Card icon: `MessageSquareText` or `PencilLine` with `h-5 w-5 text-primary`.
- Card description: `Skriv vad som behöver rättas så kan agenten föreslå en B-serie-korrigering.`
- Card content uses `space-y-4`.
- The textarea must be full-width and use the same visual family as the existing correction reason textarea:
  - `w-full rounded-lg border bg-background px-3 py-2 text-sm min-h-[88px] focus:outline-none focus:ring-2 focus:ring-ring`
- Action row uses `flex flex-wrap items-center gap-3`.
- If an active note exists, replace the empty editor with a read-only note panel and status actions; do not show two separate note cards.

### Suggested Correction Card

- Render only when the active note has `status: "suggested"` and `suggested_voucher_id` is present.
- Place it directly below the correction-note card and above the main `Konteringsrader` card.
- Use one full-width `Card`.
- Card title: `Föreslagen korrigering`.
- Card icon: `Sparkles` or `Brain` with `h-5 w-5 text-primary`; use `Brain` if keeping consistency with existing agent labels is simpler.
- Card description: `Granska raderna innan korrigeringen bokförs. Originalverifikationen ändras inte.`
- Card header includes a compact `Badge` for note status:
  - `pending` → `Väntar på agent`
  - `suggested` → `Förslag klart`
  - `applied` → `Tillämpad`
  - `dismissed` → `Avfärdad`
  - `rejected` → `Ingen lösning`
- Suggested rows use the same table structure and input classes as the existing editable rows table.
- Include totals below the editable rows while in suggested-correction mode:
  - label `Summa`
  - debit and credit formatted with `formatCurrency`
  - if unbalanced, show inline error text `Förslaget måste balansera innan det kan bokföras.`
- The approve/dismiss controls must remain inside the suggested-correction card, not in the page header.

### Terminal Note States

- `applied`, `dismissed`, and `rejected` notes render as compact history rows inside the correction-note card only if the API returns them for the current voucher.
- Terminal states must not show editable row controls.
- Terminal note rows use `rounded-md border bg-muted/30 p-3`.

---

## Interaction Contract

### Create Correction Note

- Default state for a posted voucher with no active note: textarea plus primary CTA.
- Primary CTA copy: `Skicka till agent`.
- Secondary action: none.
- Button disabled while saving or when the textarea is empty after trimming.
- Successful create:
  - clears textarea
  - invalidates `["correction-notes", voucher.id]`
  - invalidates `["voucher-source-context", voucher.id]`
  - shows success message `Noteringen har skickats till agenten.`
- `409 Conflict` when an active note already exists:
  - show `Det finns redan en aktiv korrigeringsnotering för verifikationen.`
  - refetch correction notes
- Generic failure:
  - show `Korrigeringsnoteringen kunde inte sparas. Försök igen.`

### Pending Note

- Show note text in a bordered panel using `whitespace-pre-wrap break-words`.
- Show status badge `Väntar på agent`.
- Provide destructive secondary action `Avfärda notering`.
- Dismiss confirmation copy: `Avfärda notering: agenten kommer inte att föreslå någon korrigering för denna notering.`
- Dismiss success message: `Noteringen har avfärdats.`

### Suggested Correction Review

- Suggested row fields are editable before approval.
- The user can change account, debit, credit, and row description.
- Primary CTA copy: `Bokför korrigering`.
- Secondary CTA copy: `Avfärda förslag`.
- If rows are unbalanced, disable `Bokför korrigering` and show the unbalanced message.
- Approval flow:
  - saves edited draft rows if they changed
  - posts the draft B-series voucher
  - marks the note `applied`
  - invalidates `["voucher", id]`, `["voucher", suggested_voucher_id]`, `["correction-notes", id]`, `["voucher-source-context", id]`, `["vouchers"]`, and `["accounting-corrections"]`
  - success message: `Korrigeringen bokfördes som B-serie.`
- Dismiss flow:
  - asks for confirmation using the destructive confirmation copy
  - deletes the draft if present
  - marks note `dismissed`
  - logs correction history for agent learning
  - success message: `Förslaget har avfärdats och sparats i historiken.`

### Rejected Note

- If the agent marks a note `rejected`, show a non-editable panel with title text `Agenten kunde inte föreslå en korrigering`.
- Include the note text and any API-provided error/summary.
- Primary CTA for user: `Skapa ny notering` if there is no active pending/suggested note.
- Do not use red destructive styling for rejected notes unless the user action failed; use muted/warning styling.

---

## Spacing Scale

Declared values use the existing Tailwind spacing scale and are multiples of 4.

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4px | Icon-to-label gaps in badges and compact links |
| sm | 8px | Button/icon gaps and table cell compact spacing |
| md | 16px | Card content rhythm, field grouping, status panels |
| lg | 24px | Card header/content padding via existing primitives |
| xl | 32px | Separation between major voucher detail sections only if already present |
| 2xl | 48px | Not needed for this phase |
| 3xl | 64px | Not needed for this phase |

Exceptions: none.

Required classes:

- Page frame remains `p-4 lg:p-8 space-y-6 max-w-[1000px] mx-auto`.
- New correction-note and suggested-correction cards use existing `Card`, `CardHeader`, `CardContent`.
- Action rows use `flex flex-wrap items-center gap-3`.
- Editable suggested rows reuse existing row input/select classes from the voucher detail page.

---

## Typography

| Role | Size | Weight | Line Height |
|------|------|--------|-------------|
| Body | 14px (`text-sm`) | 400 | Tailwind default |
| Label | 14px (`text-sm`) | 500 (`font-medium`) | Tailwind default |
| Metadata label | 12px (`text-xs`) | 500-600 | Tailwind default |
| Card title | 18px (`text-lg`) | 600 (`font-semibold`) | `leading-none` from existing component |
| Page heading | Existing `text-2xl lg:text-3xl` | 700 (`font-bold`) | Tailwind default |

Do not add display typography for this phase.

---

## Color

Use existing semantic CSS variables from `frontend-v3/app/globals.css`.

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | `hsl(var(--background))` | Page background and form controls |
| Secondary (30%) | `hsl(var(--card))`, `hsl(var(--muted))` | Cards, note panels, table headers |
| Accent (10%) | `hsl(var(--primary))` | Card icons, primary CTAs, focus rings |
| Success | Existing success badge/banner style | Applied note and approval success |
| Warning | Existing warning badge/banner style | Pending/rejected-but-not-failed note states |
| Destructive | `hsl(var(--destructive))` | Dismiss action errors and destructive confirmation only |

Accent reserved for:

- Correction-note and suggested-correction card icons
- Primary CTA buttons
- Focus rings on textarea and row inputs

Do not introduce a purple/blue gradient, decorative background, or new one-off status palette.

---

## Copywriting Contract

| Element | Copy |
|---------|------|
| Note card title | `Korrigeringsnotering` |
| Note card description | `Skriv vad som behöver rättas så kan agenten föreslå en B-serie-korrigering.` |
| Note textarea label | `Notering` |
| Note textarea placeholder | `Exempel: Bankavgiften ska bokföras på 6570 utan moms.` |
| Create note CTA | `Skicka till agent` |
| Create note success | `Noteringen har skickats till agenten.` |
| Active-note conflict | `Det finns redan en aktiv korrigeringsnotering för verifikationen.` |
| Create note error | `Korrigeringsnoteringen kunde inte sparas. Försök igen.` |
| Pending badge | `Väntar på agent` |
| Suggested badge | `Förslag klart` |
| Applied badge | `Tillämpad` |
| Dismissed badge | `Avfärdad` |
| Rejected badge | `Ingen lösning` |
| Dismiss note CTA | `Avfärda notering` |
| Dismiss suggestion CTA | `Avfärda förslag` |
| Dismiss note confirmation | `Avfärda notering: agenten kommer inte att föreslå någon korrigering för denna notering.` |
| Dismiss suggestion confirmation | `Avfärda förslag: utkastet tas bort och förslaget sparas i historiken för agentens lärande.` |
| Suggested card title | `Föreslagen korrigering` |
| Suggested card description | `Granska raderna innan korrigeringen bokförs. Originalverifikationen ändras inte.` |
| Approve CTA | `Bokför korrigering` |
| Approving CTA | `Bokför...` |
| Approval success | `Korrigeringen bokfördes som B-serie.` |
| Dismiss success | `Förslaget har avfärdats och sparats i historiken.` |
| Unbalanced rows | `Förslaget måste balansera innan det kan bokföras.` |
| Rejected heading | `Agenten kunde inte föreslå en korrigering` |
| New note after rejected CTA | `Skapa ny notering` |

Do not mention implementation details such as endpoint names in visible UI copy.

---

## Accessibility Contract

- Note textarea must have a visible label and `id="correction-note-text"`.
- Suggested correction row table must preserve column headers for account, account name, debit, and credit.
- Status badges must be accompanied by visible text, not color alone.
- Confirmation dialogs must include the action name in the message.
- Dismiss controls may use destructive styling but must include visible text; no icon-only destructive actions.
- Error text must be visible near the relevant editor and use `text-destructive`.
- Native buttons, inputs, textarea, and select elements must remain keyboard reachable.
- Long note text uses `whitespace-pre-wrap break-words`.

---

## Responsive Contract

- New cards remain full-width in the existing `max-w-[1000px]` voucher detail frame.
- Action rows wrap on mobile and never force horizontal scroll.
- The suggested correction table may use the existing `overflow-x-auto` wrapper.
- Textarea and note panels are `w-full`.
- Badge/action clusters use `flex flex-wrap` so long Swedish labels do not overlap.
- Do not add fixed pixel widths to the cards, table, or CTA groups.

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| shadcn official | none | not required |
| third-party | none | not allowed |

Do not install or copy external UI components for this phase.

---

## Checker Sign-Off

- [x] Dimension 1 Copywriting: PASS
- [x] Dimension 2 Visuals: PASS
- [x] Dimension 3 Color: PASS
- [x] Dimension 4 Typography: PASS
- [x] Dimension 5 Spacing: PASS
- [x] Dimension 6 Registry Safety: PASS

**Approval:** approved 2026-06-05

## UI-SPEC VERIFIED
