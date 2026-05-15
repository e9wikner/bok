# Phase 03: Frontend Intake Workspace and Review Loop - Research

**Researched:** 2026-05-15
**Status:** Complete

## Research Question

What does the executor need to know to plan Phase 03 well: a frontend intake work surface that uploads voucher sources and bank inputs, scans statuses, opens intake details, links to posted vouchers, and shows source/correction learning context on voucher detail pages?

## Current Backend Surface

Phase 1 and 2 already delivered the core storage and agent posting paths:

- `POST /api/v1/intake` uploads ordinary voucher source material with `file`, optional `explanation`, and optional `source_type`.
- `GET /api/v1/intake/{source_id}` returns ordinary source metadata.
- `GET /api/v1/intake/{source_id}/file` safely downloads the original file through `IntakeService.resolve_source_file`.
- `POST /api/v1/bank-inputs` uploads CSV bank input with `file` and `bank_connection_id`.
- `GET /api/v1/bank-inputs/{bank_input_id}` returns bank input metadata.
- `GET /api/v1/bank-inputs/{bank_input_id}/file` safely downloads the original CSV through `BankInputService.resolve_input_file`.
- `GET /api/v1/agent/intake/pending` returns a typed mixed agent queue with `kind: "voucher_source"` and `kind: "bank_input"`, plus `correction_history_url`.
- `POST /api/v1/agent/vouchers` creates and posts vouchers through `LedgerService`, then links ordinary intake sources, bank inputs, and bank transaction rows.

The existing human/frontend read surface is incomplete for Phase 03. It has upload and item-by-id endpoints, but not a unified human workspace list across lifecycle statuses, detail history, bank connection selection data, or voucher source context. The frontend should not call agent-only endpoints as its primary review API because the agent queue is optimized for automation context, not user review and filtering.

## Required API Additions

Plan 03 should add a thin human review/read layer over existing services and repositories:

- `GET /api/v1/intake/workspace` before `/{source_id}` in `api/routes/intake.py`.
  - Query params: `status`, `kind`, `limit`, `offset`.
  - Return: `items`, `total`, `limit`, `offset`, `status_counts`.
  - Items need stable `kind` discriminators: `voucher_source` and `bank_input`.
  - Ordinary source fields should include `source_type`, `status`, filename, MIME, size, explanation, upload actor/time, `download_url`, latest processing summary/error, and linked voucher IDs.
  - Bank input fields should include `bank_connection_id`, optional display account fields, status, filename, MIME, size, upload actor/time, `download_url`, imported/skipped counts, detected format, parse error, transaction IDs/counts, match signals, and linked voucher IDs.
- `GET /api/v1/intake/workspace/{kind}/{item_id}` for detail review.
  - Ordinary source detail should include metadata, `processing_attempts`, `voucher_links`, and `download_url`.
  - Bank input detail should include metadata, transaction IDs/signals, voucher links, parse result fields, and `download_url`.
- `GET /api/v1/bank-inputs/connections` in `api/routes/bank_inputs.py`, registered before `/{bank_input_id}`.
  - Return active bank connections with `id`, `bank_name`, `account_number`, `iban`, `currency`, and `status`.
  - The frontend will display account number/name while submitting the backend `bank_connection_id`.
- `GET /api/v1/vouchers/{voucher_id}/source-context` in `api/routes/vouchers.py`.
  - Return source material separate from manual attachments: ordinary intake sources and bank inputs.
  - Return agent processing attempts/notes relevant to the voucher.
  - Return correction chain/history enough to show original/correction voucher IDs, correction reason, actor, and timestamps.

These endpoints can be implemented without new schema. Existing repositories already expose much of the data but need list helpers:

- `IntakeRepository.list_by_status`, `count_by_status`, `list_links_for_source`.
- `BankInputRepository.list_by_status` exists; add `count_by_status`, `list_voucher_links_for_input`, and join helpers where needed.
- `BankIntegrationService.get_connections` already returns bank connection display data.
- `IntakeService.list_attempts_for_source`, `IntakeService.list_links_for_voucher`, `BankInputRepository.list_inputs_for_voucher`, and `BankInputRepository.list_transactions_for_voucher` are the anchors for voucher source context.

## Frontend Implementation Findings

The frontend is a Next.js app router UI with client pages, React Query, axios, local UI primitives, and lucide icons.

Closest analogs:

- `frontend-v3/app/vouchers/page.tsx` has the dense operational list pattern: header, filter card, table card, badges, search/filter controls, pagination, and skeleton rows.
- `frontend-v3/app/vouchers/[id]/page.tsx` already contains voucher metadata, correction UI, manual attachments, and audit history. Phase 03 should add separate `Kallmaterial`, `Agentbearbetning`, and `Korrigeringskedja` sections without merging intake material into manual attachments.
- `frontend-v3/app/settings/page.tsx` has a small file import card pattern, but the intake workspace needs richer upload panels because the voucher source upload collects `source_type` and explanation, while bank upload requires bank account selection.
- `frontend-v3/lib/api.ts` is the central API client and already handles auth headers and multipart upload for voucher attachments.
- `frontend-v3/hooks/useData.ts` centralizes React Query hooks with 1-10 minute stale times.
- `frontend-v3/components/Sidebar.tsx` is the only navigation surface. Context and UI spec say intake belongs under/near `Verifikationer`; use `/vouchers/intake` and add a compact sidebar item adjacent to `Verifikationer` only if route discoverability requires it.

## UI Contract Implications

The UI spec is approved and should be treated as a design contract:

- Swedish operational copy.
- Page title `Intag`.
- Two sibling upload panels: `Verifikationsunderlag` and `Bankfil`.
- Unified table with type indicator column, lifecycle status badge, compact status detail column, and row action hierarchy.
- Compact filter chips for lifecycle status and type, not tabs or lanes.
- Dedicated intake detail page with status summary first and raw processing history as audit record.
- Voucher detail source material appears in a dedicated section separate from manual attachments.
- Correction learning sentence must appear exactly: `Den här historiken kan användas av agenten vid framtida bokföring.`

## Testing Strategy

Backend:

- Extend `tests/test_bank_input_agent.py` or add a focused API test file for the new human review endpoints.
- Direct route-function tests are established in intake/bank tests and avoid ASGI transport issues noted by previous plans.
- Cover listing filters/status counts, detail attempts, bank connections selector payload, voucher source context, and root-contained download URLs (do not expose stored paths).

Frontend:

- There is no React component test setup in `frontend-v3/package.json`.
- Verification should use `npm run lint` and `npm run build` from `frontend-v3`.
- For UI work, run a local dev server and inspect with Playwright if execution workflow allows it. At minimum, plans must require responsive behavior checks for desktop and mobile widths.

## Risks and Mitigations

- Risk: route ordering conflict in `api/routes/intake.py` and `api/routes/bank_inputs.py`. Static routes like `/workspace` and `/connections` must be declared before `/{id}` routes.
- Risk: frontend cannot select bank account by account number because only `bank_connection_id` is currently accepted. Add a display endpoint rather than exposing opaque IDs directly.
- Risk: source material gets visually merged with manual attachments on voucher detail. Keep the intake sections separate from the existing `Bilagor` card.
- Risk: bank input statuses only include `pending`, `processed`, and `failed`; ordinary intake includes `processing`, `skipped`, and `needs_attention`. The unified UI must handle the union without implying bank inputs can enter unsupported states.
- Risk: processing history for bank inputs differs from ordinary intake attempts. Render bank parse/import fields as source processing metadata, and ordinary intake attempts as chronological agent processing attempts.
- Risk: correction chain may require composing audit/correction repository data rather than a single current endpoint. Keep the endpoint thin and reuse `AccountingCorrectionRepository`/audit history rather than inferring from UI-only data.

## Recommended Plan Shape

Keep the roadmap's three plans:

1. `03-01`: Add backend human review/read endpoints plus frontend API client/types/hooks. This is the dependency for all UI rendering.
2. `03-02`: Build `/vouchers/intake` upload and status workspace with separate upload panels and unified table.
3. `03-03`: Build intake detail and extend voucher detail with source material, processing notes, and correction-learning context.

## RESEARCH COMPLETE
