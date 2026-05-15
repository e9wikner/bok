---
phase: 03-frontend-intake-workspace-and-review-loop
plan: 03-02
subsystem: frontend-ui
tags: [nextjs, react-query, intake, uploads, responsive-ui]

requires:
  - phase: 03-01
    provides: typed intake workspace APIs, upload client methods, bank connection hook, and React Query workspace hooks
provides:
  - Operational `/vouchers/intake` workspace for voucher source and bank CSV uploads
  - Unified lifecycle/type filtered intake table with status details and counts
  - Primary posted-voucher row actions for processed linked intake items
  - Responsive upload/table workspace verified at desktop and mobile widths
affects: [03-03, intake-detail-ui, voucher-review]

tech-stack:
  added: []
  patterns:
    - React Query invalidation after multipart upload success
    - Fixed-layout horizontally scrollable operational tables inside flex app shells
    - Longest-prefix sidebar active route matching for nested workspace routes

key-files:
  created:
    - frontend-v3/app/vouchers/intake/page.tsx
    - .planning/phases/03-frontend-intake-workspace-and-review-loop/03-02-SUMMARY.md
  modified:
    - frontend-v3/components/Sidebar.tsx
    - frontend-v3/components/AppShellClient.tsx

key-decisions:
  - "The intake workspace uses two separate upload panels above one unified intake table."
  - "Processed intake rows with linked vouchers make the posted voucher the primary action."
  - "The app shell now allows main content to shrink so operational tables scroll internally instead of widening the page."

patterns-established:
  - "Upload feedback: successful uploads clear only the submitted form and invalidate `intake-workspace`; failed uploads preserve selected fields."
  - "Row action hierarchy: posted voucher first for processed linked rows, intake detail first for failed or needs_attention rows."
  - "Responsive shell: `min-w-0` main content plus non-shrinking sidebar keeps table overflow local to the table scroller."

requirements-completed: [FRNT-01, FRNT-02, FRNT-03, FRNT-05]

duration: 31 min
completed: 2026-05-15
---

# Phase 03 Plan 03-02: Intake Upload and Status Workspace Summary

**Operational intake workspace with separate voucher-source and bank CSV uploads, lifecycle/type filters, status details, and linked-voucher row actions.**

## Performance

- **Duration:** 31 min
- **Started:** 2026-05-15T13:01:32Z
- **Completed:** 2026-05-15T13:32:05Z
- **Tasks:** 4
- **Files modified:** 4

## Accomplishments

- Added `/vouchers/intake` under the voucher area with adjacent `Intag` sidebar navigation.
- Added separate `Verifikationsunderlag` and `Bankfil` upload panels with source type, explanation, bank account selection, success/error feedback, and workspace query invalidation.
- Added compact lifecycle and type filter chips, status counts, skeleton loading rows, empty state, and a unified intake table.
- Added row action hierarchy so processed linked rows open posted vouchers first, while failed and needs_attention rows open detail review.
- Verified desktop and mobile rendering with mocked API data and screenshots at `/tmp/intake-desktop.png` and `/tmp/intake-mobile.png`.

## Task Commits

1. **Task 1: Create the intake workspace route and navigation placement** - `4d61ec6` (feat)
2. **Task 2: Build separate voucher-source and bank CSV upload panels** - `0c04e60` (feat)
3. **Task 3: Render filters, counts, and unified intake table** - `73e514f` (feat)
4. **Task 4: Implement row actions and responsive workspace behavior** - `d3b7029` (feat)

## Files Created/Modified

- `frontend-v3/app/vouchers/intake/page.tsx` - Intake workspace route, upload forms, filters, table, status details, row actions, and pagination.
- `frontend-v3/components/Sidebar.tsx` - Added `Intag` navigation adjacent to `Verifikationer`, longest-route active matching, and non-shrinking desktop sidebar.
- `frontend-v3/components/AppShellClient.tsx` - Added `min-w-0` to the main flex region so wide operational tables scroll inside their container.

## Decisions Made

- Kept voucher-source and bank CSV uploads as two sibling panels to preserve the source/bank separation required by the phase contract.
- Used filter chips instead of tabs/lanes so status and type filtering stay compact on the operational surface.
- Kept detail routes as `/vouchers/intake/{kind}/{id}` links even though the detail pages are delivered by the following plan.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed shell-level horizontal overflow caused by the intake table**
- **Found during:** Task 4 (viewport verification)
- **Issue:** At 1280px desktop width, the app shell flex row widened beyond the viewport because the new operational table contributed a large min-content width.
- **Fix:** Added `min-w-0` to `AppShellClient` main content, made the desktop sidebar non-shrinking, and changed the intake table to fixed layout inside its horizontal scroller.
- **Files modified:** `frontend-v3/components/AppShellClient.tsx`, `frontend-v3/components/Sidebar.tsx`, `frontend-v3/app/vouchers/intake/page.tsx`
- **Verification:** Playwright viewport check at 1280 and 390 returned `bodyFits`, `buttonsFit`, `tableScrollsInternally`, and `uploadCardsDoNotOverlap` all true.
- **Committed in:** `d3b7029`

---

**Total deviations:** 1 auto-fixed (Rule 1)
**Impact on plan:** The fix was necessary for the plan's responsive workspace criteria and does not change product scope.

## Issues Encountered

- `cd frontend-v3 && npm run build` remains blocked in the main worktree by the pre-existing ignored `frontend-v3/.next` ownership problem (`EACCES` on `.next/trace-build`), already recorded in Plan 03-01.
- Clean temporary copies without `.next` built successfully. Turbopack and Chromium verification needed sandbox escalation because both bind local worker/debug ports.

## Verification

- `test -f frontend-v3/app/vouchers/intake/page.tsx` - PASS
- `rg "Intag" frontend-v3/app/vouchers/intake/page.tsx frontend-v3/components/Sidebar.tsx` - PASS
- `rg "Verifikationsunderlag" frontend-v3/app/vouchers/intake/page.tsx` - PASS
- `rg "Bankfil" frontend-v3/app/vouchers/intake/page.tsx` - PASS
- `rg "source_type" frontend-v3/app/vouchers/intake/page.tsx` - PASS
- `rg "useBankInputConnections" frontend-v3/app/vouchers/intake/page.tsx` - PASS
- `rg "pending" frontend-v3/app/vouchers/intake/page.tsx` - PASS
- `rg "needs_attention" frontend-v3/app/vouchers/intake/page.tsx` - PASS
- `rg "Underlag" frontend-v3/app/vouchers/intake/page.tsx` - PASS
- `rg "Bankfil" frontend-v3/app/vouchers/intake/page.tsx` - PASS
- `rg "Öppna verifikation" frontend-v3/app/vouchers/intake/page.tsx` - PASS
- `rg "Granska fel" frontend-v3/app/vouchers/intake/page.tsx` - PASS
- `rg "Visa intagspost" frontend-v3/app/vouchers/intake/page.tsx` - PASS
- `cd frontend-v3 && npm run lint` - PASS
- `cd frontend-v3 && npm run build` - BLOCKED by pre-existing ignored `.next` ownership (`EACCES` on `.next/trace-build`)
- `npm run build` from clean `/tmp/bok-frontend-build-*` copy without `.next` - PASS
- Playwright viewport check at 1280 and 390 with mocked auth/API data - PASS
- `git diff --check` - PASS

## Known Stubs

None. Stub-pattern scan found only intentional input placeholder copy and Tailwind `placeholder:` classes.

## Threat Flags

None. This plan added no new backend endpoints, file-serving paths, or trust-boundary storage access.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Ready for Plan 03-03. The workspace now links to intake detail routes and posted voucher routes, so the next plan can fill the detail/review surfaces behind those links.

## Self-Check: PASSED

- Summary file created at `.planning/phases/03-frontend-intake-workspace-and-review-loop/03-02-SUMMARY.md`.
- Task commits present: `4d61ec6`, `0c04e60`, `73e514f`, `d3b7029`.
- Key created/modified files exist and plan-level verification results are recorded above.

---
*Phase: 03-frontend-intake-workspace-and-review-loop*
*Completed: 2026-05-15*
