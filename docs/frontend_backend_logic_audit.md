# Frontend/Backend Logic Audit

Goal: keep the frontend as a thin human UI for review and correction, while backend APIs contain the business logic, data selection and agent-operable workflows.

## Summary

The backend already owns the most important accounting operations: vouchers, posting, invoices, payments, SIE import/export, SRU export and reports. The new agent model also requires the backend to own versioned Markdown accounting instructions, direct agent posting, and correction history. The main remaining drift is that several frontend pages still derive domain views from lower-level API data. Those derivations should move server-side so an AI agent can call the same endpoints and get the same interpretation as the human UI.

## Agent Workflow Target

- Agent reads `GET /api/v1/agent-instructions/accounting`.
- Agent reads posted vouchers and `GET /api/v1/accounting-corrections`.
- Agent posts directly with `POST /api/v1/agent/vouchers`.
- Frontend correction of a posted voucher must call `POST /api/v1/vouchers/{id}/correct`, not edit posted rows in place.
- Corrections become agent-readable history; frontend remains a human review/correction surface.

## Move First

1. Agent instructions, direct posting and posted correction flow
   - Current frontend: `frontend-v3/app/learning/page.tsx`, `frontend-v3/app/vouchers/[id]/page.tsx`
   - Problem: voucher correction can look like direct editing unless the UI makes the B-series correction flow explicit.
   - Backend target: versioned instruction document, `POST /api/v1/agent/vouchers`, `POST /api/v1/vouchers/{id}/correct`, `GET /api/v1/accounting-corrections`.
   - Agent value: agent can operate from persistent instructions, and human corrections are available as structured feedback.

2. INK2 declaration layout and row calculations
   - Current frontend: `frontend-v3/app/bokslut/ink2/page.tsx`
   - Problem: INK2/INK2R/INK2S sections, row labels, SRU-to-form-field mapping, taxable result fallback and source-account display are encoded in the frontend.
   - Backend target: `GET /api/v1/tax/ink2/{fiscal_year_id}` returning company, fiscal year, tabs, sections, rows, values, source accounts, warnings and export status.
   - Agent value: an agent can inspect and validate the complete declaration without rendering React.

3. Report period selection and export resolution
   - Current frontend: `frontend-v3/app/reports/page.tsx`
   - Problem: frontend resolves available years, month labels, matching period IDs, PDF endpoints and SRU export year matching.
   - Backend target: `GET /api/v1/reports/options` and export endpoints that accept `fiscal_year_id` plus optional month instead of requiring frontend period lookup.
   - Agent value: an agent can ask for “income statement 2026 March” directly.

4. Invoice totals and VAT preview before create
   - Current frontend: `frontend-v3/app/invoices/new/page.tsx`
   - Problem: row totals, VAT, totals and VAT breakdown are calculated in the form before submit.
   - Backend target: `POST /api/v1/invoices/preview` with rows, returning normalized rows, VAT summary and totals. `POST /api/v1/invoices` should remain authoritative.
   - Agent value: an agent can validate an invoice draft before creating it.

5. Voucher list row totals
   - Current frontend: `frontend-v3/app/vouchers/page.tsx`
   - Problem: visible debit total is calculated from voucher rows client-side.
   - Backend target: include `total_debit`, `total_credit`, `balanced`, and maybe `row_count` in voucher list responses.
   - Agent value: list responses become self-contained and cheaper to reason about.

6. Invoice dashboard summaries
   - Current frontend: `frontend-v3/app/invoices/page.tsx`
   - Problem: total amount, paid count, overdue count, outstanding amount and page totals are derived client-side from the currently loaded set.
   - Backend target: `GET /api/v1/invoices/summary` or include `summary` next to paginated invoice results.
   - Agent value: avoids inconsistent summaries when pagination/filtering changes.

## Lower Priority

1. Audit grouping and relative time labels
   - Current frontend: `frontend-v3/app/audit/page.tsx`
   - Keep relative time formatting in frontend, but backend could expose event categories and human-readable summaries.

2. Account grouping for display
   - Current frontend: `frontend-v3/app/accounts/page.tsx`
   - Grouping by account type is mostly presentation. Backend can optionally expose account groups, but this is not urgent.

3. SRU settings inheritance
   - Current frontend: `frontend-v3/app/settings/sru-mappings/page.tsx`
   - Problem: “inherit previous year” finds previous year client-side and copies mappings locally before save.
   - Backend target: `POST /api/v1/fiscal-years/{id}/sru-mappings/inherit-previous` and `POST /api/v1/fiscal-years/{id}/sru-mappings/reset-default`.
   - Agent value: explicit agent-operable commands for year-to-year setup.

## What Should Stay Frontend

- Visual layout, tab state, sorting controls, mobile/desktop responsive layout.
- Formatting for humans: currency strings, date display, badges, colors.
- Temporary unsaved form state and inline validation hints.
- Manual correction UI interactions, as long as the submitted operation is fully validated by backend.

## Suggested Migration Order

1. Add agent instruction APIs, direct-post endpoint and posted-correction endpoint.
2. Convert voucher correction UI to use B-series correction for posted vouchers.
3. Add backend INK2 declaration endpoint and convert frontend to render returned sections.
4. Add invoice preview endpoint and use it from invoice creation/edit views.
5. Add server-side summaries/totals to voucher and invoice list endpoints.
6. Add report option/export helper endpoints so frontend stops resolving period IDs.
7. Add SRU mapping command endpoints for inherit/reset.

Each step should keep existing endpoints working while frontend gradually becomes a renderer over backend-authored view models.
