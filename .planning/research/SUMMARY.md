# Project Research Summary

**Project:** Bok v1.3 Agent Usability & Feedback Loop
**Domain:** Self-hosted Swedish bookkeeping with AI-agent automation
**Researched:** 2026-06-05
**Confidence:** HIGH

## Executive Summary

Bok v1.3 is a brownfield milestone that enriches the agent's context model so a non-expert user can run compliant bookkeeping with minimal manual interaction. The five features—intake deduplication/linking, bank transaction matchability, per-source agent guidance, simplified correction flow, and agent instruction persistence—are all additive extensions to the existing FastAPI/Next.js/SQLite stack. No new core technologies or external dependencies are required. The dominant architectural pattern is "schema-first, then repository/service layer, then agent-facing routes, then frontend work surfaces," with the existing layered monolith (routes → services → repositories → SQLite) accommodating every change without subsystem proliferation.

The recommended approach is to build in strict dependency order: schema migrations first, then repository and service extensions, then backend routes (agent-facing before human-facing), then frontend UI surfaces. The primary risk is violating Swedish Bookkeeping Act (BFL §5 kap 6) immutability requirements—specifically the temptation to let the "simplified correction flow" bypass the B-series voucher mechanism. Every correction must still produce a proper immutable B-series correction voucher; the text note is only a user-friendly input layer. Secondary risks include race conditions on intake linking (SQLite thread-local connections), unbounded growth of instruction version history, and the agent entrypoint drifting out of sync with new capabilities. All of these are preventable with transaction-level guards, size limits, and a strict "update entrypoint in the same PR" rule.

## Key Findings

### Recommended Stack

The existing stack fully covers v1.3. All features are relational, low-volume CRUD and linking operations that fit naturally into FastAPI `APIRouter` + Pydantic v2 + raw SQL migrations + Next.js App Router + TanStack Query. There is no justification for adding PostgreSQL, Redis, message queues, GraphQL, or LLM frameworks.

**Core technologies (no changes):**
- **FastAPI (>=0.109.0)** — New agent and frontend endpoints fit the existing router/service/repository pattern without architectural changes.
- **Pydantic (>=2.6.0)** — New request/response models for correction notes, agent messages, and instruction versions use existing v2 patterns.
- **SQLite (stdlib)** — v1.3 features are relational and low-volume; indexed foreign keys already support the required query patterns.
- **Next.js (^16.2.6) + React (^18)** — New operational work surfaces (linking UI, agent guidance textarea, simplified correction dialog) are standard App Router pages.
- **TanStack Query (^5.94.5)** — New endpoints integrate into the existing `QueryClientProvider` and `useQuery`/`useMutation` hooks.
- **Tailwind CSS (^3.4.1)** — New components follow the existing Tailwind + Radix UI primitive pattern.

**What NOT to add:** Redis, PostgreSQL, message queues, LangChain/OpenAI SDK, Elasticsearch/FTS, GraphQL, workflow engines, or new frontend libraries. The existing stack is sufficient.

### Expected Features

**Must have (table stakes — P1):**
- **Intake deduplication/linking (DEDUP-01)** — Prevents stale agent queue; reuses existing `voucher_intake_sources` linkage.
- **Bank transaction matchability (MATCH-01)** — Makes existing bank CSV import useful for the agent by exposing unmatched transactions as matchable entities.
- **Per-source agent guidance (GUIDE-01)** — Lets users give the agent plain-text hints about a specific receipt without editing global instructions.
- **Simplified correction flow (CORR-01)** — Non-expert users leave a text note; the agent proposes a formal B-series correction; user approves. This is the core feedback loop.

**Should have (competitive differentiator — P2):**
- **Agent instruction persistence (INSTR-01)** — Agent appends learned rules to a dedicated "Inlärda regler" section. The PUT endpoint already exists; the work is mainly agent awareness and workflow documentation.
- **Agent-suggested instruction approval gate** — UX polish on top of INSTR-01; requires user review before agent rules go live.

**Defer (v2+):**
- OCR/text extraction for uploaded PDFs/images — large standalone effort, deferred as v2 candidate.
- Persistent per-agent API keys — deferred to v1.4.
- MCP adapter — deferred to v1.4+.
- Full Open Banking connection — manual CSV upload is sufficient for the target user.

### Architecture Approach

The work is brownfield: every feature extends existing tables, repositories, services, and routes rather than introducing new subsystems. The dominant theme is **enriching the agent context model** — every feature adds data the agent reads before posting vouchers, while the backend continues enforcing BFL/BFNAR immutability.

**Major components:**
1. **IntakeService** — Source lifecycle (upload, dedup, link, skip, agent guidance). Communicates with `IntakeRepository`, `VoucherRepository`, `LedgerService`.
2. **BankInputService** — Bank CSV import, transaction matching, matchable exposure. Communicates with `BankInputRepository`.
3. **CorrectionNoteService** — Text note CRUD, agent suggestion validation, apply via `LedgerService`. Communicates with `CorrectionNoteRepository`, `AccountingCorrectionRepository`.
4. **AgentInstructionService** — Append-only instruction updates, version tracking. Communicates with `AgentInstructionRepository`.
5. **LedgerService** — Core posting, correction, balance validation. Communicates with `VoucherRepository`, `PeriodRepository`, `AccountRepository`.

**Key pattern:** Schema changes → Repository extensions → Service methods → Backend routes (agent-facing first) → Frontend surfaces → Agent entrypoint update → Integration tests.

### Critical Pitfalls

1. **BFL Immutability Violation in Simplified Correction Flow (CORR-01)** — Developers might store the text note and skip the B-series voucher. **Avoid:** The backend must still call `LedgerService.create_posted_correction()` to produce an immutable B-series voucher. The text note is only the UX input layer. Watch for `sqlite3.OperationalError: posted vouchers are immutable` in logs.
2. **Race-Condition on Intake Source Linking (DEDUP-01)** — The check-then-link pattern in `IntakeService._ensure_can_record_outcome` is not atomic in SQLite with thread-local connections. **Avoid:** Make the check-and-link atomic using `INSERT` with `ON CONFLICT` or wrap in `db.transaction()` with immediate mode. Return the existing voucher ID in the error response so the agent can review.
3. **Unbounded Growth of Agent Instruction Versions (INSTR-01)** — `AgentInstructionRepository.update()` always inserts a new version. If the agent appends after every correction, the table grows without bound. **Avoid:** Cap at 100 versions, add a `content_markdown` length limit (e.g., 50KB), and deduplicate (skip insert if content is identical to last version).
4. **Conflating "Explanation" with "Agent Guidance" (GUIDE-01)** — Reusing the existing `explanation` field blurs user intent. **Avoid:** Add a dedicated `agent_guidance` / `agent_message` column to `intake_sources`. Keep explanation as general description and guidance as a collapsible "Agent instructions" textarea.
5. **Bank Transaction Matchability Exposing Already-Booked Items (MATCH-01)** — Including `booked` or already-matched transactions in the agent queue causes duplicate vouchers. **Avoid:** Split the API into `all` vs `matchable` endpoints; filter by `status = 'pending' AND matched_voucher_id IS NULL`.
6. **Agent Entrypoint Drift** — New agent routes are added but the hardcoded entrypoint in `api/routes/agent_instructions.py` is not updated. **Avoid:** Treat entrypoint updates as part of every feature's definition of done. Extend `tests/test_agent_entrypoint.py` with assertions for every new workflow endpoint.

## Implications for Roadmap

Based on research, the suggested phase structure follows the dependency chain: schema → repository/service → backend routes → frontend → integration/entrypoint.

### Phase 1: Schema Foundation & Repository Layer
**Rationale:** All other work depends on these tables. Brownfield schema additions are low-risk and must be in place before route or frontend development.
**Delivers:**
- Migration: Add `agent_guidance` / `agent_message` to `intake_sources` (GUIDE-01)
- Migration: Create `correction_notes` table (CORR-01)
- Migration: Add `link_reason` enum expansion if needed (DEDUP-01)
- Repository extensions: `IntakeRepository.update_agent_message()`, `mark_skipped()`, `link_to_existing_voucher()`
- Repository extensions: `BankInputRepository.list_unmatched_transactions()`, `get_transaction_detail()`
- New repository: `CorrectionNoteRepository` (CRUD + list_by_voucher + list_pending)
**Addresses:** DEDUP-01, GUIDE-01, CORR-01, MATCH-01 (backend prep)
**Avoids:** Conflating explanation/guidance fields; missing schema for correction notes.
**Research flags:** LOW — schema patterns are already well-established in migrations 001–019.

### Phase 2: Service Layer & Agent-Facing API Routes
**Rationale:** The agent is the primary consumer of matchability, instruction updates, and correction notes. Agent-facing routes must be built and tested before the frontend depends on them. This also closes the core automation loop.
**Delivers:**
- `BankInputService.agent_matchable_transactions()` → `GET /api/v1/agent/bank-transactions/matchable` (MATCH-01)
- `POST /api/v1/agent/instructions/learn` (INSTR-01)
- `POST /api/v1/vouchers/{id}/correction-notes`, `GET /api/v1/agent/correction-notes/pending`, `POST /api/v1/agent/correction-notes/{id}/apply` (CORR-01)
- `POST /api/v1/intake/{id}/link-to-voucher`, `POST /api/v1/intake/{id}/skip` (DEDUP-01)
- `PUT /api/v1/intake/{id}/agent-message` (GUIDE-01)
**Addresses:** All five features' backend contracts.
**Avoids:** Race conditions on intake linking (atomic repo methods); BFL immutability violation (backend still calls `LedgerService.create_posted_correction`); bank transaction mismatch (explicit `matchable` filter); instruction version bloat (size caps and deduplication in service layer).
**Research flags:** LOW — well-documented, established patterns in existing codebase.

### Phase 3: Frontend Work Surfaces & Human-Facing Routes
**Rationale:** Once the backend contracts are stable, the frontend can build the operational UI. This phase is human-facing and depends on the agent-facing routes being tested.
**Delivers:**
- Intake workspace: "Länka till verifikation" and "Markera som hanterad" actions (DEDUP-01)
- Intake upload form: "Agentinstruktion" textarea (GUIDE-01)
- Intake detail page: Show `agent_message` prominently (GUIDE-01)
- Voucher detail page: "Lämna korrigeringsnot" button + dialog; show pending correction notes (CORR-01)
- Human-facing route: `GET /api/v1/vouchers/{id}/correction-notes` (rich metadata for UI, separate from agent endpoint)
- Agent instructions page: "Visa inlärda regler" section (INSTR-01)
**Addresses:** DEDUP-01, GUIDE-01, CORR-01 frontend surfaces.
**Avoids:** Frontend calling agent-only endpoints (create separate human-facing routes); agent guidance field overwhelming non-expert users (collapse behind accordion); simplified correction showing no preview (show proposed B-series rows before approval).
**Research flags:** LOW — standard Next.js App Router + TanStack Query + Tailwind patterns.

### Phase 4: Integration, Entrypoint & End-to-End Validation
**Rationale:** The agent relies on the entrypoint to discover capabilities. This phase ties everything together and ensures the automation loop works end-to-end.
**Delivers:**
- Update `GET /api/v1/agent-instructions/entrypoint` to include new endpoints, workflow steps, and guardrails.
- Extend `tests/test_agent_entrypoint.py` with assertions for every new route.
- Integration test: Agent reads correction note → suggests fix → applies → voucher gets B-series correction.
- Integration test: Agent reads matchable bank transactions → creates voucher → transaction status becomes `booked`.
- Integration test: Concurrent intake linking attempts produce clear, deterministic responses.
**Addresses:** All features' end-to-end contracts and agent discoverability.
**Avoids:** Agent entrypoint drift (strict "same PR" rule); untested race conditions.
**Research flags:** MEDIUM — integration tests across agent + backend + frontend benefit from validation during planning, but the patterns are standard.

### Phase Ordering Rationale

- **Schema first** because all repository, service, route, and frontend work depends on the new `correction_notes` table and `agent_guidance` column.
- **Agent-facing routes before frontend** because the automation loop is the core value proposition. The frontend is a review/feedback surface, not a blocking prerequisite.
- **Human-facing routes separate from agent-facing routes** to avoid the anti-pattern of exposing machine-optimized shapes to human UI (Pitfall 4 in ARCHITECTURE.md).
- **Entrypoint update as a dedicated phase** to enforce the "definition of done" rule and prevent drift, while also allowing integration tests to validate the full agent startup sequence.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 4 (Integration & Entrypoint):** The exact shape of the agent startup sequence and how the external agent (e.g., OpenClaw) consumes the entrypoint may need a brief spike if the entrypoint format changes significantly.
- **Phase 2 (Agent-Facing Routes — CORR-01):** The agent-generated correction proposal and user approval flow is a novel UX pattern. A brief UI spike or mockup may be useful to confirm the approval step before backend implementation.

Phases with standard patterns (skip dedicated research):
- **Phase 1 (Schema Foundation):** Raw SQL migrations 001–019 establish a clear, repeatable pattern.
- **Phase 2 (Repository + Service + Routes):** The existing layered monolith pattern (`api/routes/` → `services/` → `repositories/` → `db/`) is well-established and covers all new features.
- **Phase 3 (Frontend Work Surfaces):** Next.js App Router + TanStack Query + Tailwind + Radix UI is the established frontend stack.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Based on direct verification of `requirements.txt`, `package.json`, and existing codebase. No external sources needed. |
| Features | HIGH | Based on direct codebase analysis (`repositories/intake_repo.py`, `services/ledger.py`, etc.) and PROJECT.md v1.3 requirements. Feature gaps are well-documented. |
| Architecture | HIGH | Based on direct codebase analysis (migrations 013, 018, 019; `services/ledger.py`; `api/routes/`). The layered monolith pattern is explicit and consistent. |
| Pitfalls | HIGH | Based on direct codebase analysis (existing triggers, `UNIQUE` constraints, entrypoint tests) and Swedish BFL compliance requirements. |

**Overall confidence:** HIGH

### Gaps to Address

The following gaps should be resolved during phase planning or execution, but they are not blockers:

- **Agent instruction approval gate UX:** The research notes that INSTR-01 should ideally include a user approval gate, but the exact UX (notification vs inline review vs batch approval) is not specified. This should be decided during Phase 2 planning.
- **Correction note approval preview:** The frontend must show proposed B-series rows before the user confirms. The exact component design (modal vs inline vs new page) should be sketched during Phase 3 planning.
- **Agent guidance vs. explanation field naming:** The research uses both `agent_guidance` and `agent_message` interchangeably. The exact column name should be settled in the Phase 1 migration to avoid frontend/API drift.
- **Version limit / pruning strategy for instructions:** The research recommends capping at 100 versions and deduplicating, but the exact cleanup policy (soft-delete vs hard-delete vs compression) should be defined during Phase 2.

## Sources

### Primary (HIGH confidence)
- Bok codebase: `requirements.txt`, `frontend-v3/package.json` — verified current versions and lockfiles.
- Bok codebase: `repositories/intake_repo.py`, `services/intake.py`, `api/routes/intake.py`, `api/routes/agent.py`, `repositories/agent_instruction_repo.py`, `api/routes/agent_instructions.py`, `repositories/bank_input_repo.py`, `services/bank_inputs.py`, `services/ledger.py` — direct analysis of existing patterns and extension points.
- Bok codebase: `db/migrations/018_add_intake_sources.sql`, `db/migrations/019_add_bank_inputs.sql`, `db/migrations/013_add_agent_instructions.sql`, `db/migrations/014_add_posted_voucher_immutability_triggers.sql` — confirmed schema patterns for linking, bank transactions, instruction versioning, and immutability enforcement.
- Bok codebase: `tests/test_intake_api.py`, `tests/test_bank_input_agent.py`, `tests/test_agent_entrypoint.py`, `tests/test_agent_accounting_workflow.py` — existing test coverage and patterns.
- Bok codebase: `frontend-v3/app/vouchers/intake/page.tsx`, `frontend-v3/app/vouchers/intake/[kind]/[id]/page.tsx`, `frontend-v3/app/vouchers/[id]/page.tsx` — existing frontend surfaces and patterns.
- `PROJECT.md` v1.3 milestone context — confirmed scope and constraints (SQLite-first, no external accountant workflow, no pre-posting approval, BFL immutability).
- Swedish Bookkeeping Act (BFL) §5 kap 6 (varaktighet) and §5 kap 7 (rättelseverifikation) — compliance constraints for immutability and B-series corrections.

### Secondary (MEDIUM confidence)
- `STATE.md` — v1.2 real-world agent usage gaps and deferred features (OCR, Open Banking, MCP).
- `AGENTS.md` — project conventions and GSD workflow rules.

### Tertiary (LOW confidence)
- External agent integration patterns (OpenClaw-style) — the agent is an external HTTP caller; the exact agent behavior depends on its own prompt engineering, which is outside the backend's control.

---
*Research completed: 2026-06-05*
*Ready for roadmap: yes*
