# Phase 7: OpenClaw Deployment Instructions and Verification - Pattern Map

**Mapped:** 2026-06-05
**Files analyzed:** 4 new/modified files
**Analogs found:** 4 / 4

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `DEPLOYMENT.md` | documentation | request-response + operational shell verification | `DEPLOYMENT.md` | exact |
| `README.md` | documentation | reference / cross-link consistency | `README.md` | exact |
| `tests/test_agent_entrypoint.py` | test | request-response | `tests/test_agent_entrypoint.py` | exact |
| `tests/test_deployment_docs.py` | test | documentation source assertions + request-response | `tests/test_agent_entrypoint.py`, `tests/conftest.py` | role-match |

## Pattern Assignments

### `DEPLOYMENT.md` (documentation, request-response + operational shell verification)

**Analog:** `DEPLOYMENT.md`

**Placement pattern** (lines 142-152):
````markdown
### 9. Första inloggning

Öppna från en annan dator på samma LAN:

```text
http://SERVER_IP_OR_HOSTNAME:3000/login
```

Logga in med användarnamnet från `AUTH_USERNAME` och lösenordet du satte i
`AUTH_PASSWORD`.
````

Add the OpenClaw/HTTP-agent checklist immediately after this first-login block, before `## Uppdatera säkert på LAN`.

**LAN command style** (lines 127-140):
````markdown
### 7. Verifiera backend

```bash
curl -fsS http://localhost:8000/health
```

Kommandot ska skriva ett lyckat hälsosvar.

### 8. Verifiera frontend

```bash
curl -fsSI http://localhost:3000/login
curl -fsS http://localhost:3000/health
```
````

Use short Swedish explanatory text plus copy-pasteable shell blocks. For the agent section, prefer variables such as `BOK_API_URL="http://SERVER_IP_OR_HOSTNAME:8000"` and `API_KEY="..."`, then curl paths from those variables.

**Docker-internal URL warning pattern** (lines 94-107):
````markdown
```env
NEXT_PUBLIC_API_URL=
BACKEND_URL=http://api:8000
```

`NEXT_PUBLIC_API_URL=` ska vara tom. Då anropar webbläsaren samma origin via
`/api`, och Next.js-proxyn skickar vidare till `BACKEND_URL`.

`BACKEND_URL=http://api:8000` är den interna backend-adressen inne i Docker
Compose-nätverket. Ändra inte den för LAN-drift.
````

Reuse this wording style when warning that OpenClaw outside Docker must not receive `BACKEND_URL=http://api:8000`; it needs the backend API URL reachable from the agent.

**Optional public HTTPS pattern** (lines 311-340):
````markdown
## Valfritt: publik domän och HTTPS

Det här spåret är bara för en server som ska exponeras publikt och där du redan
har DNS och en e-postadress för Let's Encrypt. Blanda inte ihop detta med
LAN-checklistan ovan.

```env
APP_DOMAIN=app.example.com
API_DOMAIN=api.example.com
LETSENCRYPT_EMAIL=admin@example.com
```

```bash
curl -fsS "https://${API_DOMAIN}/health"
curl -fsSI "https://${APP_DOMAIN}/login"
```
````

Keep the public OpenClaw note separate from the LAN checklist. Use `https://${API_DOMAIN}` for OpenClaw and `https://${APP_DOMAIN}` for humans.

**Troubleshooting pattern** (lines 342-421):
````markdown
## Felsökning

### Backend svarar inte

```bash
curl -fsS http://localhost:8000/health
```

Om kommandot fallerar:

- kontrollera `docker compose ... ps`
- läs `docker compose ... logs --tail=100 api`
- bekräfta att `.env.production` finns
- kontrollera att inga placeholders används i hemlighetsfälten
````

Put auth failures, wrong base URL/port, and Docker-internal URL confusion under troubleshooting, not inline with the setup checklist.

---

### `README.md` (documentation, reference / cross-link consistency)

**Analog:** `README.md`

**Deployment cross-link pattern** (lines 19-37):
```markdown
## Lokal produktionsdrift

Rekommenderad ägardrift är LAN/lokal server med Docker Compose. Börja i
[DEPLOYMENT.md](DEPLOYMENT.md); den guiden täcker `.env.production`, starka
hemligheter, `docker-compose.local.yml`, uppdateringar, säkerhetskopiering,
återställning, rollback, felsökning och valfri publik domän med HTTPS.

För agentintegration används tills vidare `BOKFOERING_API_KEY`. Skicka
entrypoint-länken `GET /api/v1/agent-instructions/entrypoint` till agenten så
hämtar den själv startup-instruktioner, auth-check och workflow-länkar.
```

Only update README if needed to avoid contradiction with `DEPLOYMENT.md`. Keep it high-level and point owners to the deployment guide instead of duplicating the checklist.

**Agent endpoint reference pattern** (lines 80-86, 154-165):
```markdown
- Publik, maskinläsbar agent-entrypoint för startup-instruktioner
- Auth-check via `POST /api/v1/agent/test/ping` med `BOKFOERING_API_KEY`
- FastAPI-genererad schema via `/openapi.json`

- `GET /api/v1/agent-instructions/entrypoint` – Publik startup-instruktion för agenten
- `POST /api/v1/agent/vouchers` – Agenten skapar och postar verifikation direkt
```

If README is touched, keep exact route names aligned with the entrypoint route and avoid adding unsupported MCP, key lifecycle, generated tool-schema, or idempotency claims.

---

### `tests/test_agent_entrypoint.py` (test, request-response)

**Analog:** `tests/test_agent_entrypoint.py`

**Imports and constants pattern** (lines 1-16):
```python
"""Tests for the public agent instruction entrypoint."""

import json
from collections.abc import Iterator
from datetime import datetime

import httpx
import pytest
import pytest_asyncio

from api.main import app
from config import settings

ENTRYPOINT_PATH = "/api/v1/agent-instructions/entrypoint"
```

For new checks in this file, add constants near `ENTRYPOINT_PATH` and keep the file focused on route contract behavior.

**Async FastAPI client pattern** (lines 32-42):
```python
@pytest_asyncio.fixture
async def async_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _entrypoint(async_client: httpx.AsyncClient) -> dict:
    response = await async_client.get(ENTRYPOINT_PATH)
    assert response.status_code == 200
    return response.json()
```

Use this same in-process ASGI pattern for verifying documented route paths; no live server or Docker runtime is needed.

**Bearer auth helper pattern** (lines 45-46):
```python
def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.api_key}"}
```

Use the configured test settings API key for authenticated ping checks. Do not hard-code or inline real secrets in tests or docs.

**Public entrypoint assertions** (lines 60-69):
```python
@pytest.mark.asyncio
async def test_agent_entrypoint_is_public_without_auth(async_client):
    response = await async_client.get(ENTRYPOINT_PATH)

    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "bokfoering-api"
    assert "version" in data
    assert data["auth"]["value_format"] == "Bearer <BOKFOERING_API_KEY>"
```

Follow this direct status/body assertion style for public entrypoint and health route examples.

**Authenticated ping assertions** (lines 145-166):
```python
@pytest.mark.asyncio
async def test_agent_ping_requires_auth(async_client):
    response = await async_client.post("/api/v1/agent/test/ping")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_agent_ping_returns_dynamic_bounded_auth_data(async_client):
    response = await async_client.post(
        "/api/v1/agent/test/ping",
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
```

Use this as the source pattern for verifying that the documented ping command needs `Authorization: Bearer ...` and succeeds with the configured key.

**Unsupported feature guard pattern** (lines 119-128, 170-186):
```python
@pytest.mark.asyncio
async def test_agent_entrypoint_discloses_unsupported_features(async_client):
    data = await _entrypoint(async_client)
    unsupported = " ".join(data["unsupported_features"]).lower()

    assert "persistent" in unsupported
    assert "credential lifecycle" in unsupported
    assert "generated tool-schema discovery" in unsupported
    assert "durable idempotency" in unsupported
```

If documentation tests include scope honesty checks, assert absence of unsupported feature claims in the OpenClaw setup section rather than adding runtime features.

---

### `tests/test_deployment_docs.py` (test, documentation source assertions + request-response)

**Analogs:** `tests/test_agent_entrypoint.py`, `tests/conftest.py`

**Fixture/import pattern from existing tests** (from `tests/conftest.py` lines 13-16):
```python
@pytest.fixture
def auth_headers():
    """Return bearer auth headers for protected API endpoints."""
    return {"Authorization": f"Bearer {settings.api_key}"}
```

If a new docs test file is created, it can import `Path` and read `DEPLOYMENT.md` directly, while using the existing auth fixture if synchronous `TestClient` tests are preferred. For async route checks, copy the `httpx.ASGITransport` fixture from `tests/test_agent_entrypoint.py`.

**Route registration source of truth** (from `api/main.py` lines 129-131):
```python
@app.get("/health", tags=["health"])
@app.get("/api/v1/health", tags=["health"])
async def health_check():
```

Documentation assertions should allow the documented health route chosen by the implementation. Current docs use `/health`; the agent entrypoint also exposes `/api/v1/health`.

**Entrypoint source of truth** (from `api/routes/agent_instructions.py` lines 32-58):
```python
@router.get("/entrypoint", response_model=dict)
async def get_agent_instruction_entrypoint():
    """Return the public-safe startup contract for external bookkeeping agents."""
    return {
        "service": "bokfoering-api",
        "version": settings.api_version,
        "auth": {
            "type": "bearer",
            "header": "Authorization",
            "value_format": "Bearer <BOKFOERING_API_KEY>",
            "check": {
                "method": "POST",
                "path": "/api/v1/agent/test/ping",
                "expected_status": 200,
            },
        },
        "links": {
            "health": "/api/v1/health",
            "docs": "/docs",
            "redoc": "/redoc",
            "openapi": "/openapi.json",
        },
```

Use these exact strings when checking that docs point OpenClaw to `/api/v1/agent-instructions/entrypoint`, describe bearer auth, and verify ping.

**Auth dependency source of truth** (from `api/deps.py` lines 10-25, 30-45):
```python
async def verify_api_key(authorization: Optional[str] = Header(None)) -> str:
    """Verify API key or JWT token from Authorization header."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Expect: "Bearer <api-key-or-jwt>"
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )
```

Docs should show `Authorization: Bearer ${API_KEY}` or equivalent. Tests can assert the string `Authorization: Bearer` exists in the documented ping command and that repeated inline secret placeholders are avoided.

**Suggested docs assertion shape**:
```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT = (ROOT / "DEPLOYMENT.md").read_text()


def test_openclaw_docs_distinguish_frontend_backend_and_docker_internal_urls():
    assert "http://SERVER_IP_OR_HOSTNAME:3000" in DEPLOYMENT
    assert "http://SERVER_IP_OR_HOSTNAME:8000" in DEPLOYMENT
    assert "BACKEND_URL=http://api:8000" in DEPLOYMENT
    assert "Docker" in DEPLOYMENT
```

Keep docs tests deterministic source assertions plus in-process route checks. Do not use curl, Docker, network, browser automation, or an AI evaluator in pytest.

## Shared Patterns

### Documentation Tone and Structure

**Source:** `DEPLOYMENT.md`

Apply Swedish, owner-facing, LAN-first operational language. Use short checklists, explicit command blocks, and troubleshooting sections. Avoid long OpenClaw UI walkthroughs because Phase 7 decided OpenClaw must be described generically as an HTTP agent.

### Agent URL Separation

**Sources:** `DEPLOYMENT.md` lines 94-107, `README.md` lines 35-37, `api/routes/agent_instructions.py` lines 53-58

Apply to `DEPLOYMENT.md` and docs tests:
- Humans use frontend URL `http://SERVER_IP_OR_HOSTNAME:3000/login`.
- OpenClaw uses backend API base URL `http://SERVER_IP_OR_HOSTNAME:8000`.
- Optional public deployment uses `https://${API_DOMAIN}` for OpenClaw and `https://${APP_DOMAIN}` for humans.
- `BACKEND_URL=http://api:8000` is Docker-internal and must not be given to OpenClaw outside Docker.

### Auth and Ping Verification

**Sources:** `api/deps.py` lines 10-45, `tests/test_agent_entrypoint.py` lines 145-166

Apply to docs and tests:
```bash
BOK_API_URL="http://SERVER_IP_OR_HOSTNAME:8000"
API_KEY="hamta-fran-BOKFOERING_API_KEY"
curl -fsS "${BOK_API_URL}/api/v1/agent-instructions/entrypoint"
curl -fsS -X POST "${BOK_API_URL}/api/v1/agent/test/ping" \
  -H "Authorization: Bearer ${API_KEY}"
```

Keep secrets in variables, not repeated inline command text.

### No AI Runtime Implementation

**Sources:** `07-AI-SPEC.md`, `api/routes/agent_instructions.py` lines 151-160, `tests/test_agent_entrypoint.py` lines 119-128

Phase 7 must not add model providers, MCP, generated tool-schema discovery, persistent per-agent key lifecycle, durable idempotency, RAG, LangGraph, CrewAI, LlamaIndex, OpenAI Agents SDK, or any other in-app AI runtime. The first OpenClaw starter instruction should delegate to the existing public entrypoint and verify setup only.

### Verification Boundary

**Sources:** `tests/test_agent_entrypoint.py`, `api/main.py`

Use `pytest` with in-process FastAPI/httpx route checks and Markdown source assertions. The verification target is command/path correctness and documentation scope honesty, not live deployment, Docker networking, OpenClaw UI behavior, or AI output quality.
