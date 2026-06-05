---
phase: 08
slug: guide-per-source-agent-guidance
status: approved
shadcn_initialized: false
preset: bok-existing
created: 2026-06-05
---

# Phase 08 — UI Design Contract

> Visual and interaction contract for adding per-source agent guidance to voucher-source intake.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none |
| Preset | bok-existing |
| Component library | local `components/ui` primitives |
| Icon library | lucide-react |
| Font | `var(--font-geist-sans)`, fallback `system-ui`, `sans-serif` |

Use the existing operational intake UI. Do not introduce a new visual direction, third-party UI package, custom animation system, or new global CSS variables for this phase.

---

## Surfaces In Scope

| Surface | Path | Required Change |
|---------|------|-----------------|
| Voucher-source upload form | `frontend-v3/app/vouchers/intake/page.tsx` | Add optional guidance textarea directly below `Kort förklaring` |
| Voucher-source detail page | `frontend-v3/app/vouchers/intake/[kind]/[id]/page.tsx` | Add voucher-source-only guidance review/edit card |
| Bank input detail page | `frontend-v3/app/vouchers/intake/[kind]/[id]/page.tsx` | Hide guidance entirely |
| Intake workspace table | `frontend-v3/app/vouchers/intake/page.tsx` | No guidance badge or indicator |

---

## Layout Contract

### Upload Form

- Place the new textarea immediately after the existing `Kort förklaring` textarea and before the upload button row.
- Use the same label wrapper as explanation: `label.space-y-1.5.block`.
- Use the same textarea classes as explanation:
  - `w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:ring-2 focus:ring-ring`
- Use `rows={3}`.
- Do not add helper text below the field.
- Do not collapse the field behind an accordion or details element.
- Do not show this field in the bank upload card.

### Detail Page

- Render guidance only when `item.kind === "voucher_source"`.
- Prefer a full-width `Card` between the status card and the file/metadata grid so the user sees guidance before technical file metadata.
- Card title: `Meddelande till agent`.
- Card icon: `FileText` with `h-5 w-5 text-primary`.
- Card description: `Instruktioner som agenten ser när underlaget behandlas.`
- When editable, show a textarea and action row.
- When locked, show the saved value in a bordered muted panel and a short lock note.
- Empty read-only value should render `Inget meddelande angivet.`, not `-`.
- Bank input detail must not render an empty placeholder, disabled card, or lock note for guidance.

---

## Interaction Contract

### Editable Statuses

Guidance is editable only for voucher-source items with status:

- `pending`
- `processing`

Guidance is locked for:

- `processed`
- `skipped`
- `failed`
- `needs_attention`
- `deleted`

### Detail Editing Flow

- Default mode shows current guidance text and an `Redigera meddelande` button when editable.
- Clicking edit switches to textarea mode with current value loaded.
- Primary save button copy: `Spara meddelande`.
- Secondary cancel button copy: `Avbryt`.
- Save button is disabled while saving.
- Saving an empty or whitespace-only textarea is allowed and clears guidance.
- On success, leave edit mode and show the updated value.
- On `409 Conflict`, keep edit mode open and show a visible error message:
  - `Meddelandet kan inte ändras eftersom underlaget redan har behandlats.`
- On other save failure, show:
  - `Meddelandet kunde inte sparas. Försök igen.`

### Upload Flow

- Upload form should include guidance when the field contains non-whitespace text.
- A successful source upload resets the guidance field to empty with the rest of the source form.
- Existing upload success/error message placement stays unchanged.

---

## Spacing Scale

Declared values use the existing Tailwind spacing scale and are multiples of 4.

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4px | Icon gaps only when matching existing compact controls |
| sm | 8px | Label-to-field spacing and tight button gaps |
| md | 16px | Card body vertical rhythm and form section gaps |
| lg | 24px | Card padding via existing `CardHeader` / `CardContent` |
| xl | 32px | Page section grouping only if already present |
| 2xl | 48px | Not needed for this phase |
| 3xl | 64px | Not needed for this phase |

Exceptions: none.

Required classes:

- Upload card `CardContent` remains `space-y-4`.
- Detail page guidance card `CardContent` should use `space-y-4`.
- Action rows should use `flex flex-wrap items-center gap-3`.

---

## Typography

| Role | Size | Weight | Line Height |
|------|------|--------|-------------|
| Body | 14px (`text-sm`) | 400 | Tailwind default |
| Label | 14px (`text-sm`) | 500 (`font-medium`) | Tailwind default |
| Metadata label | 12px (`text-xs`) | 600 (`font-semibold`) | Tailwind default |
| Card title | 18px (`text-lg`) | 600 (`font-semibold`) | `leading-none` |
| Page heading | Existing `text-2xl lg:text-3xl` | 700 (`font-bold`) | Tailwind default |

Do not add display typography for this phase.

---

## Color

Use existing semantic CSS variables from `frontend-v3/app/globals.css`.

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | `hsl(var(--background))` | Page background and textarea background |
| Secondary (30%) | `hsl(var(--card))`, `hsl(var(--muted))` | Cards, read-only guidance panel, metadata blocks |
| Accent (10%) | `hsl(var(--primary))` | Card icon, primary save button, focus ring |
| Destructive | `hsl(var(--destructive))` | Save errors only |

Accent reserved for:

- `FileText` icon in guidance card title
- Primary CTA button
- Focus ring on textarea

Do not add a new highlight color for guidance. Do not use warning/amber unless showing an actual warning from processing history.

---

## Copywriting Contract

| Element | Copy |
|---------|------|
| Upload field label | `Meddelande till agent` |
| Upload placeholder | `Valfritt — beskriv hur agenten ska bokföra detta underlag` |
| Detail card title | `Meddelande till agent` |
| Detail card description | `Instruktioner som agenten ser när underlaget behandlas.` |
| Empty guidance text | `Inget meddelande angivet.` |
| Edit CTA | `Redigera meddelande` |
| Save CTA | `Spara meddelande` |
| Saving CTA | `Sparar...` |
| Cancel CTA | `Avbryt` |
| Locked note | `Meddelandet är låst eftersom underlaget inte längre väntar på behandling.` |
| Conflict error | `Meddelandet kan inte ändras eftersom underlaget redan har behandlats.` |
| Generic save error | `Meddelandet kunde inte sparas. Försök igen.` |

No additional helper text is allowed under the upload field.

---

## Accessibility Contract

- Textarea must have an `id` and visible label.
- Suggested upload textarea id: `source-agent-guidance`.
- Suggested detail textarea id: `intake-agent-guidance`.
- Save error text must be visible near the guidance editor and use `text-destructive`.
- Save/cancel controls must be keyboard reachable native buttons.
- Do not rely on icon-only buttons for guidance editing.
- Preserve existing responsive behavior; no new fixed-width containers.

---

## Responsive Contract

- Upload form remains in the existing two-column `lg:grid-cols-2` page layout.
- The new upload textarea must not increase the minimum width of the card.
- Detail page guidance card is full-width in the `max-w-[1100px]` detail frame.
- Text areas must be `w-full`.
- Long guidance content must use `whitespace-pre-wrap break-words`.

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
