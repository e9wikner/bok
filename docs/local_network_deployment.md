# Local Network Production Deployment

This guide is for running BokAi on a server inside your own network and letting
a local AI agent, such as Openclaw, call the API.

## Recommended Topology

- Frontend: `http://SERVER_IP:3000`
- Backend/API: `http://SERVER_IP:8000`
- Database: SQLite file in the Docker volume `bok_bokfoering-data`
- Agent auth: `Authorization: Bearer <BOKFOERING_API_KEY>`

For a LAN-only setup, start without public TLS. Put the server behind your
router/firewall and do not port-forward `3000` or `8000` to the internet.

## 1. Prepare The Server

Install Docker and Docker Compose v2, then clone the repo:

```bash
git clone https://github.com/e9wikner/bok.git
cd bok
```

Create production settings:

```bash
cp .env.production.example .env.production
```

Edit `.env.production`:

- replace `BOKFOERING_API_KEY` with a long random value
- replace `JWT_SECRET` with a different long random value
- replace `AUTH_PASSWORD` with a strong password
- replace `SERVER_IP` in `CORS_ORIGINS` with the server's LAN IP
- keep `NEXT_PUBLIC_API_URL=` empty for the recommended same-origin frontend proxy

Generate secrets with:

```bash
openssl rand -hex 32
```

## 2. Start The App

```bash
docker compose --env-file .env.production -f docker-compose.local.yml up -d --build
```

Check health:

```bash
docker compose -f docker-compose.local.yml ps
curl http://localhost:8000/health
curl http://localhost:3000/login
```

Open the frontend from another computer on the same network:

```text
http://SERVER_IP:3000
```

## 3. Attach Openclaw Or Another Agent

Use the backend URL directly:

```text
http://SERVER_IP:8000
```

Authentication header:

```http
Authorization: Bearer <BOKFOERING_API_KEY>
```

Useful discovery URLs:

- `GET http://SERVER_IP:8000/openapi.json` - complete FastAPI OpenAPI schema
- `GET http://SERVER_IP:8000/docs` - Swagger UI
- `GET http://SERVER_IP:8000/api/v1/agent/spec/openapi` - small agent-focused spec
- `POST http://SERVER_IP:8000/api/v1/agent/spec/tools` - tool definitions

Recommended initial agent read sequence:

1. `GET /api/v1/agent-instructions/accounting`
2. `GET /api/v1/fiscal-years`
3. `GET /api/v1/accounts`
4. `GET /api/v1/vouchers?status=posted`
5. `GET /api/v1/accounting-corrections`

Recommended posting endpoint:

```http
POST /api/v1/agent/vouchers
Authorization: Bearer <BOKFOERING_API_KEY>
Content-Type: application/json

{
  "series": "A",
  "date": "2026-05-10",
  "period_id": "<open-period-id>",
  "description": "Example posting",
  "reasoning_summary": "Short explanation for audit/review.",
  "rows": [
    { "account": "1930", "debit": 10000, "credit": 0, "description": "Bank" },
    { "account": "3010", "debit": 0, "credit": 10000, "description": "Revenue" }
  ]
}
```

Amounts are always in öre in the API.

## 4. Human Review Workflow

The agent can post directly, but posted vouchers are immutable. Review in the
frontend and correct mistakes with:

```http
POST /api/v1/vouchers/{id}/correct
```

Corrections are stored as B-series vouchers and exposed through:

```http
GET /api/v1/accounting-corrections
```

The agent should read that endpoint before future bookkeeping so human
corrections become reusable guidance.

## 5. Backups

SQLite lives in the Docker volume. Create a manual backup with:

```bash
mkdir -p backups
docker compose --env-file .env.production -f docker-compose.local.yml exec -T api \
  python -c "import shutil, datetime; shutil.copy('/app/data/bokfoering.db', f'/app/data/bokfoering-{datetime.datetime.now():%Y%m%d-%H%M%S}.db')"
```

For scheduled backups, use `docker-compose.prod.yml`'s `backup` service or add a
host cron job that archives the Docker volume. Keep backups for the retention
period required by Swedish bookkeeping rules.

## Production Readiness Notes

- The `/api/v1/agent/keys/*` endpoints are currently placeholders and do not
  persist separate keys. Use `BOKFOERING_API_KEY` for Openclaw until persistent
  agent keys are implemented.
- Use `docker-compose.prod.yml` plus a real DNS name if you later need HTTPS
  with Traefik/Let's Encrypt.
- Do not keep `admin/admin`, `dev-key-change-in-production`, or the development
  JWT secret on a real network.
