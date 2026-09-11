# AGENTS.md

Guidance for coding agents working in this repository.

## Project

**Bok** — a Swedish bookkeeping system for small limited companies: FastAPI
backend, Next.js frontend, double-entry ledger with an immutable audit trail.
It is built to satisfy Bokföringslagen (BFL) and BFNAR 2013:2, and exposes an
agent-facing API so an LLM agent can post vouchers while the backend enforces
the formal accounting constraints.

## Commands

```bash
# Backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py --init-db --seed        # one-time DB init + test data
python main.py                         # serve on 127.0.0.1:8000

pytest tests/ -v
pytest tests/test_ledger.py::test_name
black . && isort . && flake8 && mypy . # flake8 ignores E203, E266, E501, W503

# Frontend (port 3000)
cd frontend-v3 && npm install && npm run dev
npm run build && npm run lint

# Both, in containers
docker compose up --build
```

Interactive API reference: `http://localhost:8000/docs`, schema at
`/openapi.json`. There is no hand-maintained endpoint document — the generated
schema is the reference.

## Append-only storage — the rule to not break

Posted vouchers are **never** modified or deleted. Enforced in three places, on
purpose, so that no single layer's bug can violate BFL:

1. SQL triggers reject UPDATE/DELETE on posted vouchers.
2. `VoucherValidator` (service layer) checks before posting.
3. No PATCH/PUT endpoints exist for posted resources.

Corrections go through B-series reversal vouchers only. Period locking is
irreversible. `draft` is editable; `posted` is not.

Do not add an "edit posted voucher" path, relax a trigger, or delete rows to fix
test data — reverse and re-post instead.

## Layering

- `api/routes/` — HTTP only: parse, authenticate, map domain errors to status codes.
- `services/` + `domain/` — all business rules; services orchestrate, domain models validate.
- `repositories/` + `db/` — all SQL. No SQL anywhere else; no HTTP concerns here.

Service-to-service imports are deferred inside methods to avoid import cycles.

## Non-obvious constraints

- **SQLite connections are thread-local, with WAL mode** (`db/database.py`).
  Required for FastAPI/uvicorn thread safety — do not cache a connection across
  threads or share one between requests.
- **Migrations are plain numbered SQL files** in `db/migrations/`, applied in
  order at startup. Add a new file; never edit an applied one.
- **Invoice auto-booking** produces a balanced voucher: debit 1510 (kundfordringar)
  incl. VAT, credit 3011 (försäljning) excl. VAT, credit 2610 (utgående moms).
  Payment registration creates a second voucher: debit 1010 (bank), credit 1510.
- **`docs/to_agent/*.md` is runtime content, not documentation.** It is read and
  served to agents by `repositories/system_instructions.py` and asserted on by
  `tests/test_agent_entrypoint.py`. Editing it changes system behaviour.

## Configuration

All settings come from environment variables via `config.py`. Notable:
`DATABASE_URL`, `BOKFOERING_API_KEY`, `AUTH_USERNAME` / `AUTH_PASSWORD`,
`JWT_SECRET`, `DEBUG`.

To call the API as an agent, use `scripts/bok-curl` — it resolves the host from
`BOK_API_URL` and sets the bearer header without the key entering the transcript.

## Deployment

Two supported paths:

- **hubbabubba (live)** — rootless Podman quadlets `bok-api` and `bok-frontend`
  under the `e9wikner` user's systemd, LAN HTTP, no reverse proxy. Deploy by
  running `deploy/hubbabubba/deploy.sh` **on the box**; details, one-time setup,
  folder intake and rollback are in `deploy/hubbabubba/README.md`. Deploys are
  explicit — there is no auto-update.
- **Docker Compose** — `docker-compose.yml`, for local and dev use.

Remote deployment from a workstation is deliberately unsupported; write your own
script if you need it.

Verifying the live instance:

```bash
curl -fsS http://hubbabubba:8000/health        # {"status":"ok","commit":"<sha>"}
systemctl --user status bok-api.service bok-frontend.service
journalctl --user -u bok-api -f
```

`GET /api/v1/intake/dropzone/status` (bearer auth) reports the folder-intake
scanner. Server state lives in `/srv/appdata/bok/{data,dropzone,bok.env}`.

## CI

`.github/workflows/tests.yml` (pytest + black + isort + flake8 + mypy) and
`docker-build.yml` (build, health check, Trivy scan). Every step is
`continue-on-error: true`, so a green tick does not mean the checks passed —
read the job output.
