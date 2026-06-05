---
phase: 8
plan: 08-02
subsystem: frontend
duration: 12 min
completed: "2026-06-05T14:22:00Z"
---

# Phase 8 Plan 08-02: Per-Source Agent Guidance — Frontend Summary

Added frontend surfaces for per-source agent guidance: upload form field and detail page editor.

## What Changed

- **API types** `frontend-v3/lib/api.ts`: `VoucherSourceWorkspaceItem` and `IntakeSourceUploadResponse` now include `agent_guidance`. `uploadIntakeSource` accepts and forwards `agent_guidance` via `FormData`. New `updateIntakeGuidance` PUT method.
- **Upload page** `frontend-v3/app/vouchers/intake/page.tsx`: Added `agentGuidance` state, textarea labeled `Meddelande till agent` below `Kort förklaring`, placeholder `Valfritt — beskriv hur agenten ska bokföra detta underlag`. Value is forwarded in upload payload and reset on success.
- **Detail page** `frontend-v3/app/vouchers/intake/[kind]/[id]/page.tsx`: Added `GuidanceEditor` component rendered only for `voucher_source` items. Shows read-only guidance (or `Inget meddelande angivet.`). Edit mode available only when status is `pending` or `processing`. Save calls `updateIntakeGuidance`, invalidates `intake-detail` and `intake-workspace` queries. Surfaces 409 conflict error (`Meddelandet kan inte ändras eftersom underlaget redan har behandlats.`) and generic save error.

## Tasks Completed

| Task | Title | Files |
|------|-------|-------|
| T01 | Extend frontend API types and methods | frontend-v3/lib/api.ts |
| T02 | Add guidance field to voucher-source upload | frontend-v3/app/vouchers/intake/page.tsx |
| T03 | Add voucher-source detail guidance editor | frontend-v3/app/vouchers/intake/[kind]/[id]/page.tsx |

## Verification

- `npx tsc --noEmit` from `frontend-v3` passes with zero errors.
- Acceptance criteria verified via `rg` for field names, labels, placeholder, and error messages.

## Deviations from Plan

- `npm run build` could not be executed because the pre-existing `.next/trace-build` file has restrictive permissions (EACCES). TypeScript type-check (`tsc --noEmit`) passed successfully and serves as the build verification substitute for this environment.

## Next Up

Ready for **08-03** (tests and verification).
