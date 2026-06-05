---
phase: 8
plan: 08-01
subsystem: backend
requirements-completed: [GUIDE-01, GUIDE-02, GUIDE-03]
duration: 15 min
completed: "2026-06-05T14:10:00Z"
---

# Phase 8 Plan 08-01: Per-Source Agent Guidance — Backend Summary

Added backend storage, API, and agent queue support for optional per-source agent guidance.

## What Changed

- **Migration 020** added `agent_guidance TEXT` to `intake_sources`.
- **Domain model** `IntakeSource` now carries `agent_guidance: Optional[str]`.
- **Repository** `IntakeRepository.create_source` accepts and persists `agent_guidance`, and `_row_to_source` hydrates it. New `update_agent_guidance` method supports targeted updates.
- **Service** `IntakeService.create_source_from_upload_content` accepts `agent_guidance` and normalizes whitespace-only values to `None`. New `update_agent_guidance` enforces status lock (`pending`/`processing` only) and raises `IntakeConflictError` with code `intake_guidance_locked` for non-editable sources.
- **API** `POST /api/v1/intake` accepts optional `agent_guidance` form field. New `PUT /api/v1/intake/{id}/agent-guidance` returns updated source or `409 Conflict`.
- **Agent queue** voucher sources expose `"guidance": source.agent_guidance`; bank inputs expose `"guidance": null` for uniform field presence.

## Tasks Completed

| Task | Title | Files |
|------|-------|-------|
| T01 | Add guidance schema and domain hydration | db/migrations/020_add_agent_guidance_to_intake_sources.sql, domain/models.py, repositories/intake_repo.py |
| T02 | Add service and intake route guidance update | services/intake.py, api/routes/intake.py |
| T03 | Expose guidance to the agent queue | api/routes/agent.py, services/bank_inputs.py |

## Verification

- `pytest tests/test_intake_api.py tests/test_bank_input_agent.py` — 52/52 passed.
- Acceptance criteria verified via `rg` for `agent_guidance`, `agent-guidance`, `guidance`, and status checks.

## Deviations from Plan

- **Form object handling:** Direct Python tests calling `upload_intake_source` without the `agent_guidance` argument received the FastAPI `Form(None)` default object instead of `None`, causing a SQLite binding error. Added an early guard in `IntakeService.create_source_from_upload_content` to coerce non-string `agent_guidance` values to `None`. No functional change for real HTTP requests.

## Next Up

Ready for **08-02** (frontend guidance UI).
