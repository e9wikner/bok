---
phase: 9
slug: corr-simplified-correction-flow
status: validated
nyquist_compliant: false
wave_0_complete: true
created: 2026-06-05
updated: 2026-06-05
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Reconstructed from plan artifacts (State B). One gap marked manual-only.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.4.3 |
| **Config file** | none |
| **Quick run command** | `.venv/bin/pytest tests/test_correction_notes.py tests/test_agent_entrypoint.py` |
| **Full suite command** | `.venv/bin/pytest tests/test_correction_notes.py tests/test_agent_entrypoint.py tests/test_bank_input_agent.py tests/test_agent_accounting_workflow.py` |
| **Estimated runtime** | ~2 seconds |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/pytest tests/test_correction_notes.py`
- **After every plan wave:** Run full suite command above
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 09-01-T01 | 09-01 | 1 | CORR-01 | T-09-03 / T-09-04 | Auth-gated note creation; duplicate active blocked | unit | `.venv/bin/pytest tests/test_correction_notes.py::test_posted_voucher_can_receive_pending_correction_note` | ✅ | ✅ green |
| 09-01-T02 | 09-01 | 1 | CORR-03 / CORR-04 / CORR-05 / CORR-06 | T-09-01 / T-09-02 | Draft B-series created; original untouched; history written | unit | `.venv/bin/pytest tests/test_correction_notes.py` | ✅ | ✅ green |
| 09-01-T03 | 09-01 | 1 | CORR-01 / CORR-03 / CORR-04 / CORR-05 / CORR-06 | T-09-02 / T-09-03 | Status 409 on active conflict; routes auth-protected | unit+integration | `.venv/bin/pytest tests/test_correction_notes.py` | ✅ | ✅ green |
| 09-01-T04 | 09-01 | 1 | CORR-01 / CORR-03 / CORR-04 / CORR-05 / CORR-06 | — | All lifecycle states pass; pytest exits 0 | unit | `.venv/bin/pytest tests/test_correction_notes.py` | ✅ | ✅ green |
| 09-02-T01 | 09-02 | 2 | CORR-02 | T-09-05 / T-09-06 | Correction notes appear in agent queue with action URLs | manual-only | — | — | manual-only |
| 09-02-T02 | 09-02 | 2 | CORR-02 / CORR-03 | T-09-05 | Entrypoint documents correction-note workflow | unit | `.venv/bin/pytest tests/test_agent_entrypoint.py` | ✅ | ✅ green |
| 09-02-T03 | 09-02 | 2 | CORR-06 | T-09-07 | Dismissed/rejected visible in accounting corrections | unit | `.venv/bin/pytest tests/test_correction_notes.py tests/test_agent_accounting_workflow.py` | ✅ | ✅ green |
| 09-03-T01 | 09-03 | 3 | CORR-01 / CORR-04 / CORR-06 | T-09-08 / T-09-09 / T-09-10 | Frontend API types and hook compile | build | `cd frontend-v3 && npm run build` | ✅ | ✅ green |
| 09-03-T02 | 09-03 | 3 | CORR-01 / CORR-06 | T-09-08 / T-09-09 | Note entry and status badges render with correct IDs | static | `rg "Korrigeringsnotering|correction-note-text|Skicka till agent|Väntar på agent|Förslag klart|Tillämpad|Avfärdad|Ingen lösning|correction-notes|voucher-source-context" frontend-v3/app/vouchers/\[id\]/page.tsx` | ✅ | ✅ green |
| 09-03-T03 | 09-03 | 3 | CORR-04 / CORR-06 | T-09-08 / T-09-09 | Suggested correction card renders with editable rows | static | `rg "Föreslagen korrigering|Bokför korrigering|Avfärda förslag|Förslaget måste balansera innan det kan bokföras|accounting-corrections|overflow-x-auto" frontend-v3/app/vouchers/\[id\]/page.tsx` | ✅ | ✅ green |
| 09-03-T04 | 09-03 | 3 | CORR-01 / CORR-04 / CORR-06 | T-09-10 | No new route added; mobile-safe classes present | build | `cd frontend-v3 && npm run build` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_correction_notes.py` — covers CORR-01, CORR-03, CORR-04, CORR-05, CORR-06
- [x] `tests/test_agent_entrypoint.py` — covers CORR-02 (docs), CORR-03 (workflow)
- [x] `tests/test_agent_accounting_workflow.py` — covers CORR-06 (history)
- [x] `tests/conftest.py` — shared fixtures

*Existing infrastructure covers all phase requirements except one manual-only gap below.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Agent pending queue returns correction-note items with correct action URLs | CORR-02 | No automated test creates a correction note and asserts it appears in the mixed agent queue response with `kind="correction_note"`, `source_context_url`, `correction_draft_url`, and `suggest_url`. | 1. Create a posted voucher via API.<br>2. Create a correction note on it.<br>3. Call `GET /api/v1/agent/intake/pending`.<br>4. Assert queue contains an item with `kind="correction_note"` and the three action URLs.<br>5. Assert `/api/v1/intake/workspace` does **not** contain correction-note items. |

*All other phase behaviors have automated verification.*

---

## Validation Audit 2026-06-05

| Metric | Count |
|--------|-------|
| Gaps found | 1 |
| Resolved | 0 |
| Escalated | 1 |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter — blocked by CORR-02 manual-only gap

**Approval:** pending
