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
black . && isort . && flake8 && mypy . # config i pyproject.toml och .flake8

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

Corrections go through B-series reversal vouchers only. `draft` is editable;
`posted` is not.

A period (a month) or a fiscal year can be locked so nothing new is posted in
it. The agent may lock (`stang_perioder`, or the API key); only a logged-in
human may unlock (JWT — the API key gets `403 human_only`). Unlocking never
touches posted vouchers, and both lock and unlock are audit-logged.

Do not add an "edit posted voucher" path, relax a trigger, or delete rows to fix
test data — reverse and re-post instead.

The link between an underlag (intake source) and a voucher follows the same
rule (migration 035). `voucher_intake_sources`, `intake_link_basis` and
`voucher_intake_unlinks` refuse UPDATE/DELETE. A wrong link is undone by an
unlink row (`IntakeLinkService.unlink`, the tool `koppla_bort_underlag`,
`POST /api/v1/intake/{id}/unlink`). The link row stays. A trigger allows at most
one *current* link per source, and "current" means the link has no unlink row.
Anything that asks "is this linked?" must read current links only.

A statement transaction's link to a voucher works the same way (migration
040). `voucher_bank_transactions` and `voucher_bank_transaction_unlinks` refuse
UPDATE/DELETE; a wrong link is undone by an unlink row
(`StatementMatchService.unlink`, the tool `koppla_bort_banktransaktion`,
`POST /api/v1/bank-inputs/transactions/{id}/unlink`). Read links through the
view `current_voucher_bank_transactions`. The server never automatically re-links
a transaction that has been unlinked.

An issued invoice is append-only too. An invoice comes into being only when a
logged-in human issues a draft (`POST /api/v1/invoice-drafts/{id}/issue`; the
API key gets `403 human_only`). Issuing creates the invoice, its posted voucher
and the stored PDF in one transaction (`services/invoice_issue.py`). Migration
038's triggers let only `status` and `paid_amount` change once `issued_at` is
set. The PDF is räkenskapsinformation: it is linked to the voucher as underlag
and served byte for byte (`GET /api/v1/invoices/{id}/pdf`), never re-rendered.
A wrong invoice is corrected with a credit note.

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
- **Opening balance (IB) is not a voucher** (`services/opening_balance.py`).
  The first fiscal year's is stated in `opening_balances`; every later year's
  is derived on read from the previous year (unclosed result on 2099). No
  `IB`-series voucher can be created; a posted one from before migration 033 is
  ignored as movement everywhere. Anything that sums balances must start from
  `OpeningBalanceService`, not from vouchers.
- **Issuing an invoice books it** in the same transaction: debit 1510
  (kundfordringar) incl. VAT, credit revenue excl. VAT and output VAT per VAT
  code (25 %: 3011/2610). Payment registration creates a second voucher:
  debit 1010 (bank), credit 1510.
- **`docs/to_agent/*.md` is runtime content, not documentation.** It is read and
  served to agents by `repositories/system_instructions.py` and asserted on by
  `tests/test_agent_entrypoint.py`. Editing it changes system behaviour.

## Design history

The `/v4` redesign was built module by module from specs (`docs/redesign/SPEC-*.md`)
and task lists (`tasks/*/`). Both were removed from the tree after the build. Code
comments still cite them as `SPEC-<module>.md §n`; read them in git history:

```bash
git show 1a7a7b7:docs/redesign/SPEC-flode-underlag.md
git show 1a7a7b7:tasks/flode-underlag/todo.md
git show e313c5f:docs/redesign/SPEC-fakturering.md   # fakturering F0
```

What still needs deciding is in `docs/oppna-beslut.md`. The design source (v10 and
the flow panels) is `BokAI App Redesign.zip`.

## Configuration

All settings come from environment variables via `config.py`. Notable:
`DATABASE_URL`, `BOKFOERING_API_KEY`, `AUTH_USERNAME` / `AUTH_PASSWORD`,
`JWT_SECRET`, `DEBUG`.

Every route needs the bearer (the API key or a logged-in user's JWT), reads
and files too; only `/`, `/health`, login and the agent entrypoint are public
(`api/main.py`, guarded by `tests/test_api.py`). The frontend fetches files as
blobs through `apiClient`, never as a plain `href` or `src`.

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
