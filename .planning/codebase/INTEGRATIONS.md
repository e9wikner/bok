# External Integrations

**Analysis Date:** 2026-05-14

## APIs & External Services

**Internal Service-to-Service:**
- Bokföring Backend API - Primary service consumed by frontend and scripts
  - SDK/Client: `axios` client in `frontend-v3/lib/api.ts`, `fetch` in `frontend-v3/hooks/useAuth.ts`, `requests` in `scripts/demo_runner.py`
  - Auth: `BOKFOERING_API_KEY` and JWT bearer token flow defined in `config.py`, `api/routes/auth.py`, `services/auth.py`

**Infrastructure/Edge:**
- Traefik reverse proxy - TLS termination and host routing in `docker-compose.prod.yml`
  - SDK/Client: Not applicable (container service integration)
  - Auth: Environment/domain/TLS config via `.env.production` referenced by `docker-compose.prod.yml`

**Cloud Provider (optional):**
- Hetzner Cloud - Provisioning target via Terraform in `terraform/main.tf`
  - SDK/Client: Terraform provider `hetznercloud/hcloud`
  - Auth: `hcloud_token` variable in `terraform/main.tf` and `terraform/variables.tf`

## Data Storage

**Databases:**
- SQLite (default and actively used)
  - Connection: `DATABASE_URL` from `config.py` and compose files (`docker-compose.yml`, `docker-compose.local.yml`)
  - Client: Native `sqlite3` wrapper in `db/database.py` (thread-local connection manager)

**File Storage:**
- Local filesystem for attachments in `api/routes/attachments.py` (`ATTACHMENTS_DIR`, default `/app/data/attachments`)
- Local filesystem for PDF templates in `templates/pdf/`
- Docker volume persistence (`bokfoering-data`) in `docker-compose.yml` and `docker-compose.prod.yml`

**Caching:**
- None detected

## Authentication & Identity

**Auth Provider:**
- Custom auth (no external IdP detected)
  - Implementation: API key gate in `api/deps.py` plus JWT login/session endpoints in `api/routes/auth.py` using `services/auth.py`

## Monitoring & Observability

**Error Tracking:**
- None detected (no Sentry/Bugsnag integration found)

**Logs:**
- Container/stdout logging from app and services (`print`/process logs in `main.py`, `db/database.py`, compose-managed logs)
- Optional monitoring stack is scaffolded but commented out in `docker-compose.prod.yml` (Loki/Prometheus/Grafana)

## CI/CD & Deployment

**Hosting:**
- Docker Compose deployment with API + Next.js frontend + Traefik in `docker-compose.prod.yml`
- Optional Hetzner Cloud IaC deployment in `terraform/main.tf`

**CI Pipeline:**
- GitHub Actions in `.github/workflows/tests.yml` and `.github/workflows/docker-build.yml`
- External CI services: Codecov upload action in `.github/workflows/tests.yml`; Trivy security scan in `.github/workflows/docker-build.yml`

## Environment Configuration

**Required env vars:**
- Backend/auth/security: `BOKFOERING_API_KEY`, `AUTH_USERNAME`, `AUTH_PASSWORD`, `JWT_SECRET`, `CORS_ORIGINS`, `DEBUG` from `config.py`
- Data/storage/runtime: `DATABASE_URL`, `ATTACHMENTS_DIR`, `API_URL`, `GIT_COMMIT` from `config.py`, `api/routes/attachments.py`, `api/main.py`
- Frontend connectivity: `NEXT_PUBLIC_API_URL`, `BACKEND_URL` from `frontend-v3/next.config.mjs`, `frontend-v3/lib/api.ts`
- Infra/domain/TLS: `APP_DOMAIN`, `API_DOMAIN`, `LETSENCRYPT_EMAIL` from `docker-compose.prod.yml` and deployment docs
- Optional backup object storage: `AWS_S3_BUCKET_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_ENDPOINT`, `AWS_S3_PATH` (commented optional config in `docker-compose.prod.yml`)

**Secrets location:**
- Environment files and runtime env injection via `.env.production` (`docker-compose.prod.yml`) and `.env` model config in `config.py`
- CI secrets through GitHub Actions secrets usage in `.github/workflows/tests.yml` and docs in `CICD.md`

## Webhooks & Callbacks

**Incoming:**
- None detected (no webhook receiver endpoints identified)

**Outgoing:**
- None detected for business webhooks/callbacks
- Optional outbound object storage transfer path via backup container S3-compatible config in `docker-compose.prod.yml`

---

*Integration audit: 2026-05-14*
