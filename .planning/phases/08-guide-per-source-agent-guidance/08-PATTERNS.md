# Phase 08 - Pattern Map

**Mapped:** 2026-06-05

## Existing Patterns To Reuse

### Backend Intake Layering

| Role | Existing File | Pattern |
|------|---------------|---------|
| HTTP routes | `api/routes/intake.py` | FastAPI route catches `IntakeError` and maps to `_http_error`. |
| Service | `services/intake.py` | `IntakeService` owns validation, state checks, and repository orchestration. |
| Repository | `repositories/intake_repo.py` | Static SQL methods plus `_row_to_source` hydration. |
| Domain | `domain/models.py` | `IntakeSource` dataclass represents source material. |
| Migration | `db/migrations/*.sql` | Numbered SQL files update SQLite schema and insert `schema_version`. |

### Agent Queue

| Role | Existing File | Pattern |
|------|---------------|---------|
| Mixed queue | `api/routes/agent.py` | Build voucher-source items, merge with `BankInputService().agent_queue_items`, sort by `uploaded_at`, slice by offset/limit. |
| Bank item shape | `services/bank_inputs.py` | Agent-facing bank items are dicts with safe signal fields and no raw storage paths. |
| Entrypoint docs | `api/routes/agent_instructions.py` | Public-safe static route contract, relative paths only, no company state. |

### Frontend Intake UI

| Role | Existing File | Pattern |
|------|---------------|---------|
| Upload form | `frontend-v3/app/vouchers/intake/page.tsx` | Local state, standard labels, textarea classes, `api.uploadIntakeSource`, query invalidation through `refreshWorkspace`. |
| Detail page | `frontend-v3/app/vouchers/intake/[kind]/[id]/page.tsx` | Branches by `item.kind`, uses `Card`, `SummaryField`, `StatusBadge`, authenticated blob opener. |
| API client | `frontend-v3/lib/api.ts` | Typed interfaces plus `api` methods returning `data` from axios. |
| Data hooks | `frontend-v3/hooks/useData.ts` | React Query keys: `["intake-workspace", ...]` and `["intake-detail", kind, id]`. |

## Concrete Implementation Targets

- `db/migrations/020_add_agent_guidance_to_intake_sources.sql`
- `domain/models.py`
- `repositories/intake_repo.py`
- `services/intake.py`
- `api/routes/intake.py`
- `api/routes/agent.py`
- `services/bank_inputs.py`
- `api/routes/agent_instructions.py`
- `frontend-v3/lib/api.ts`
- `frontend-v3/app/vouchers/intake/page.tsx`
- `frontend-v3/app/vouchers/intake/[kind]/[id]/page.tsx`
- `tests/test_intake_api.py`
- `tests/test_bank_input_agent.py`
- `tests/test_agent_entrypoint.py`

## Landmines

- Do not store guidance in `explanation`.
- Do not add guidance storage or UI to bank inputs.
- Do not omit `guidance: null` from bank queue items.
- Do not allow edits outside `pending` and `processing`.
- Do not leave frontend cache stale after detail-page saves.

## PATTERN MAPPING COMPLETE
