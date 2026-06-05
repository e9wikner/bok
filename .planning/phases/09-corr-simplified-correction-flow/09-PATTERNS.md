# Phase 09 - Pattern Map

**Mapped:** 2026-06-05

## Existing Patterns To Reuse

### Backend Voucher and Correction Layering

| Role | Existing File | Pattern |
|------|---------------|---------|
| HTTP routes | `api/routes/vouchers.py` | FastAPI route catches `ValidationError` and maps to structured `400`; voucher-scoped correction endpoints already live here. |
| Service | `services/ledger.py` | Business validation, B-series correction creation, posting, audit logging, and best-effort correction history recording. |
| Repository | `repositories/voucher_repo.py` | Static SQL methods, draft correction creation, draft deletion, row replacement, and posting. |
| Domain | `domain/models.py` | Dataclasses for `Voucher`, `VoucherRow`, and `CorrectionHistory`. |
| History | `repositories/accounting_correction_repo.py` | Agent-readable history with optional `corrected_voucher_id` and JSON snapshots. |

### Agent Queue

| Role | Existing File | Pattern |
|------|---------------|---------|
| Mixed queue | `api/routes/agent.py` | Build typed item dicts, merge independent source streams, sort by timestamp, slice by offset/limit. |
| Agent contract docs | `api/routes/agent_instructions.py` | Static startup instructions and workflow endpoint contracts for external agents. |
| Tests | `tests/test_bank_input_agent.py`, `tests/test_agent_entrypoint.py` | Assert queue shape and agent-visible route guidance. |

### Frontend Voucher Detail

| Role | Existing File | Pattern |
|------|---------------|---------|
| Page | `frontend-v3/app/vouchers/[id]/page.tsx` | Operational card stack, local mutation state, React Query invalidation, and manual correction row editing. |
| API client | `frontend-v3/lib/api.ts` | Typed axios methods grouped under `api`. |
| Data hooks | `frontend-v3/hooks/useData.ts` | Small React Query hooks with stable query keys. |
| UI primitives | `frontend-v3/components/ui/card.tsx`, `frontend-v3/components/ui/button.tsx`, `frontend-v3/components/ui/badge.tsx` | Existing local primitives; no external component installation. |

## Concrete Implementation Targets

- `db/migrations/022_add_correction_notes.sql`
- `domain/models.py`
- `api/schemas.py`
- `repositories/correction_note_repo.py`
- `services/correction_notes.py`
- `services/ledger.py`
- `api/routes/vouchers.py`
- `api/routes/agent.py`
- `api/routes/agent_instructions.py`
- `frontend-v3/lib/api.ts`
- `frontend-v3/hooks/useData.ts`
- `frontend-v3/app/vouchers/[id]/page.tsx`
- `tests/test_correction_notes.py`
- `tests/test_agent_accounting_workflow.py`
- `tests/test_agent_entrypoint.py`

## Landmines

- Do not use `POST /api/v1/vouchers/{voucher_id}/correct` for suggestions; it posts immediately.
- Do not include correction notes in `/api/v1/intake/workspace`.
- Do not allow more than one `pending` or `suggested` note per voucher.
- Do not delete resolved notes.
- Do not leave draft correction vouchers behind after dismissal.
- Do not approve an unbalanced draft.
- Do not skip `correction_history` for dismissed or rejected suggestions; the agent learning loop depends on those records.
- Do not introduce a new frontend visual system for the voucher detail page.

## PATTERN MAPPING COMPLETE
