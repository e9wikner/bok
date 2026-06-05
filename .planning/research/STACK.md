# Stack Research: v1.3 Agent Usability & Feedback Loop

**Domain:** Brownfield self-hosted bookkeeping (FastAPI backend, Next.js frontend, SQLite persistence)
**Researched:** 2026-06-05
**Confidence:** HIGH

## Executive Summary

The v1.3 milestone features—intake deduplication/linking, bank transaction matchability, agent instruction persistence, per-source agent guidance, and simplified correction flow—require **no new core technologies or libraries**. All capabilities are additive within the existing validated stack. The work is scoped to:

- SQLite schema extensions (new columns and linking tables via raw SQL migrations)
- New FastAPI routes with Pydantic request/response models
- New React/Next.js UI components and data hooks
- Extended agent API contract over existing HTTP transport

## Recommended Stack for v1.3

### Core Technologies (Existing — No Changes)

| Technology | Version | Purpose | Why It Covers v1.3 |
|------------|---------|---------|-------------------|
| FastAPI | >=0.109.0 | HTTP API framework | New agent-facing endpoints (bank matchability, instruction CRUD, correction notes) and frontend endpoints (intake linking, per-source guidance) fit the existing router/service/repository pattern without architectural changes. |
| Pydantic | >=2.6.0 | API schema validation | New request/response models for correction notes, agent messages, instruction versions, and bank transaction exposure use existing Pydantic v2 patterns. |
| SQLAlchemy | >=2.0.23 | DB connectivity/ORM | Schema additions (e.g., `intake_sources` status expansion, `agent_instruction_versions` mutation support, `correction_notes` concept) are handled via the existing raw SQL migration strategy. |
| SQLite | (bundled) | Persistence engine | The v1.3 features are relational and low-volume; SQLite with indexed foreign keys already supports the required query patterns. |
| Next.js | ^16.2.6 | Frontend framework | New operational work surfaces (linking UI, agent message fields, simplified correction flows) are standard App Router pages/components. |
| React | ^18 | UI runtime | Form state, modals, and review surfaces for new features use existing React patterns. |
| TanStack Query | ^5.94.5 | Server state/cache | New endpoints integrate into the existing `QueryClientProvider` and `useQuery`/`useMutation` hooks. |
| Tailwind CSS | ^3.4.1 | Styling | New components follow the existing Tailwind + Radix UI primitive pattern. |

### Supporting Libraries (Existing — No Changes)

| Library | Version | Purpose | Why It Covers v1.3 |
|---------|---------|---------|-------------------|
| python-multipart | >=0.0.6 | Form data parsing | Already used for file uploads; no new file upload features in v1.3. |
| python-dateutil | 2.8.2 | Date parsing | Bank transaction matchability and intake timestamps already rely on this. |
| PyJWT | >=2.8.0 | JWT auth | Agent and user auth remain unchanged. |
| axios | ^1.13.6 | Frontend HTTP client | Existing API client in `frontend-v3/lib/api.ts` handles new endpoints. |

### Optional Considerations (Not Required)

| Library | Version | Purpose | When to Consider |
|---------|---------|---------|-------------------|
| `react-markdown` | ^9.x | Markdown rendering | If the frontend needs to render agent instruction diffs or markdown guidance notes. **Not needed for MVP**—a `<pre>` or `<textarea>` is sufficient. |
| `difflib` (stdlib) | — | Text diffing | If instruction version history needs a unified diff view. Already available in Python standard library. |

## Installation

No new packages to install for v1.3.

```bash
# Existing backend (already in requirements.txt)
pip install fastapi>=0.109.0 uvicorn>=0.27.0 pydantic>=2.6.0 pydantic-settings>=2.1.0 sqlalchemy>=2.0.23 python-multipart>=0.0.6 PyJWT>=2.8.0

# Existing frontend (already in package.json)
npm install next@^16.2.6 react@^18 react-dom@^18 @tanstack/react-query@^5.94.5 axios@^1.13.6
```

## Alternatives Considered

| Category | Recommended (Keep) | Alternative | Why Not Switch |
|----------|-------------------|-------------|----------------|
| Database | SQLite | PostgreSQL | v1.3 features do not exceed SQLite's relational capabilities. PostgreSQL is listed as optional in requirements.txt but switching databases mid-milestone adds unnecessary deployment complexity. |
| Agent transport | HTTP REST + API Key | MCP (Model Context Protocol) | MCP is explicitly deferred to a future milestone. The existing HTTP agent entrypoint and auth pattern already supports the new features. |
| Frontend state | TanStack Query | Redux/Zustand | Server state for new endpoints is naturally cacheable with TanStack Query; no global client state complexity is introduced by v1.3. |

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Redis / caching layer | v1.3 features do not introduce read-heavy or high-concurrency patterns that require caching. | SQLite indexes + existing TanStack Query client caching. |
| Message queue (RabbitMQ, Celery) | No asynchronous job processing is required; intake linking, bank matching, and correction notes are synchronous API operations. | FastAPI route handlers calling existing service layer. |
| LangChain / LlamaIndex / OpenAI SDK | The agent is an external HTTP caller (OpenClaw-style). The backend remains "agent-facing API" only and does not host LLM logic. | Existing FastAPI routes with structured request/response schemas. |
| Elasticsearch / SQLite FTS | No full-text search requirement exists for v1.3. Per-source guidance and correction notes are looked up by primary key. | Standard SQL `SELECT` with indexed foreign keys. |
| GraphQL | The existing REST pattern is sufficient for the new CRUD and linking operations. Adding GraphQL would introduce unnecessary schema and client complexity. | FastAPI `APIRouter` with Pydantic models. |
| Workflow engine (Temporal, Camunda) | The simplified correction flow is a lightweight state transition (note → suggestion → approval/post), not a long-running workflow. | Status fields in SQLite + route handlers. |
| New frontend component library | The project already uses Radix UI primitives + Tailwind via `class-variance-authority`. No new UI paradigm is needed. | Extend existing `frontend-v3/components/ui/` primitives. |

## Integration Points

### Database Layer
- **Migrations**: Add new SQL migration files in `db/migrations/` (e.g., `020_add_intake_linking.sql`, `021_add_agent_instruction_edits.sql`, `022_add_correction_notes.sql`).
- **Repositories**: Extend existing repository classes in `repositories/` to handle new columns/tables.
- **No ORM migration tool**: Continue using raw SQL migrations managed by `db/database.py` as established in migrations `001` through `019`.

### API Layer
- **Agent routes**: Extend existing agent-facing routers (or create new ones under `api/routes/`) for bank transaction exposure, instruction persistence, and correction suggestion retrieval.
- **Frontend routes**: Add standard FastAPI routes for intake linking and per-source agent guidance.
- **Auth**: Continue using JWT/API key dependency injection (`api/deps.py`).

### Frontend Layer
- **Pages**: Add new routes under `frontend-v3/app/` (e.g., `/intake/link`, `/corrections/review`).
- **Components**: Build new components using existing Radix UI primitives (`frontend-v3/components/ui/`).
- **Hooks**: Extend `frontend-v3/hooks/useData.ts` or add feature-specific hooks for new endpoints.

### Agent Contract
- **New endpoints**: `GET /api/v1/agent/bank-transactions` (matchable entities), `PUT /api/v1/agent/instructions/{scope}` (persistence), `POST /api/v1/agent/corrections/suggest` (simplified flow).
- **Auth**: Existing API key or JWT bearer token.
- **Format**: Continue using JSON request/response bodies with Pydantic schemas.

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| FastAPI >=0.109.0 | Pydantic >=2.6.0 | No compatibility issues expected; v1.3 does not use advanced FastAPI features. |
| SQLAlchemy >=2.0.23 | SQLite (stdlib) | Existing thread-local connection strategy remains valid. |
| Next.js ^16.2.6 | React ^18 | No upgrade needed for v1.3 features. |
| TanStack Query ^5.94.5 | React ^18 | Existing cache invalidation patterns apply to new endpoints. |

## Sources

- Existing `requirements.txt` and `frontend-v3/package.json` — verified current versions.
- Existing migrations `018_add_intake_sources.sql`, `019_add_bank_inputs.sql`, `013_add_agent_instructions.sql` — confirmed schema patterns for linking, bank transactions, and instruction versioning.
- `PROJECT.md` v1.3 milestone context — confirmed scope and constraints (SQLite-first, no external accountant workflow, no pre-posting approval).
- `ARCHITECTURE.md` — confirmed layered monolith pattern and integration points.

---
*Stack research for: Bok v1.3 Agent Usability & Feedback Loop*
*Researched: 2026-06-05*
