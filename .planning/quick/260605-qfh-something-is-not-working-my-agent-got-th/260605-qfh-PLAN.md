---
quick_id: 260605-qfh
status: in_progress
created: 2026-06-05
mode: quick
---

# Quick Task 260605-qfh: Intake source status remains pending after agent voucher creation

## Goal

Analyze why uploaded Verifikationsunderlag can remain listed as `Väntar` after an agent successfully creates vouchers from them, then propose a concrete solution.

## Tasks

### T1 - Trace voucher creation APIs

Files:
- `api/routes/agent.py`
- `api/routes/vouchers.py`
- `services/ledger.py`
- `services/intake.py`
- `repositories/intake_repo.py`

Action:
- Identify which endpoints can create posted vouchers.
- Verify whether those endpoints require or preserve `intake_source_ids`.
- Check how `intake_sources.status` is moved out of `pending`.

Verify:
- Cite exact route/service/repository locations in the summary.

Done:
- The root cause is identified with file references.

### T2 - Propose contract and implementation fix

Files:
- `api/routes/agent.py`
- `api/schemas.py`
- `services/intake.py`
- `tests/test_intake_api.py`
- `tests/test_bank_input_agent.py`

Action:
- Propose the smallest API/service change that makes agent-created vouchers traceable to their Verifikationsunderlag and prevents them from staying pending.
- Include compatibility and test recommendations.

Verify:
- Proposal explains behavior for missing, invalid, already-linked, and successful source IDs.

Done:
- User receives an actionable solution plan.
