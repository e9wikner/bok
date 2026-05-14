# Technology Stack

**Analysis Date:** 2026-05-14

## Languages

**Primary:**
- Python 3.11 - Backend API and business logic in `main.py`, `api/`, `services/`, `repositories/`, `db/`
- TypeScript - Frontend app and UI logic in `frontend-v3/app/`, `frontend-v3/components/`, `frontend-v3/lib/`

**Secondary:**
- SQL - Schema and migrations in `db/migrations/*.sql`
- HCL (Terraform) - Infrastructure definitions in `terraform/main.tf`, `terraform/variables.tf`

## Runtime

**Environment:**
- Python runtime via `python:3.11-slim` in `Dockerfile`
- Node.js runtime via `node:20-alpine` in `frontend-v3/Dockerfile`

**Package Manager:**
- `pip` (requirements-based) for backend dependencies from `requirements.txt`
- `npm` for frontend dependencies in `frontend-v3/package.json`
- Lockfile: present for frontend (`frontend-v3/package-lock.json`), missing for backend (no `poetry.lock`/`Pipfile.lock`)

## Frameworks

**Core:**
- FastAPI (>=0.109.0) - HTTP API framework in `api/main.py`, declared in `requirements.txt`
- Next.js (^16.2.6) - Frontend framework in `frontend-v3/package.json` with app router in `frontend-v3/app/`
- React (^18) - UI runtime in `frontend-v3/package.json`

**Testing:**
- Pytest (`pytest==7.4.3`) - Backend test runner in `tests/` and `.github/workflows/tests.yml`
- Playwright (`^1.59.1`) - Frontend/E2E dependency in `frontend-v3/package.json`

**Build/Dev:**
- Uvicorn (>=0.27.0) - ASGI server launched from `main.py`
- Tailwind CSS (`^3.4.1`) - Styling pipeline in `frontend-v3/tailwind.config.ts`
- PostCSS (`8.5.14`) - CSS transform config in `frontend-v3/postcss.config.mjs`
- ESLint (`^9`) - Frontend linting in `frontend-v3/eslint.config.mjs`

## Key Dependencies

**Critical:**
- `pydantic` / `pydantic-settings` - API schemas/settings in `api/schemas.py`, `config.py`
- `PyJWT` - JWT signing/verification in `services/auth.py`
- `weasyprint`, `jinja2`, `qrcode`, `pillow` - PDF and QR rendering in `services/pdf_export.py`, templates in `templates/pdf/`
- `axios` - Frontend API client in `frontend-v3/lib/api.ts`

**Infrastructure:**
- `docker-compose` service definitions in `docker-compose.yml`, `docker-compose.local.yml`, `docker-compose.prod.yml`
- Traefik (`traefik:v3.0`) as reverse proxy/TLS in `docker-compose.prod.yml`
- Terraform Hetzner provider (`hetznercloud/hcloud ~> 1.45`) in `terraform/main.tf`

## Configuration

**Environment:**
- Backend settings centralized in `config.py` (`BaseSettings`, `.env` support)
- Frontend API routing config via `NEXT_PUBLIC_API_URL` and `BACKEND_URL` in `frontend-v3/next.config.mjs`
- Environment files detected: `.env.example`, `.env.production`, `.env.production.example`

**Build:**
- Backend container build in `Dockerfile`
- Frontend multi-stage build in `frontend-v3/Dockerfile`
- Frontend TS config in `frontend-v3/tsconfig.json`
- Frontend Next config in `frontend-v3/next.config.mjs`
- CI workflows in `.github/workflows/tests.yml`, `.github/workflows/docker-build.yml`

## Platform Requirements

**Development:**
- Python 3.11-compatible environment for backend (`requirements.txt`, CI in `.github/workflows/tests.yml`)
- Node.js 20-compatible environment for frontend (`frontend-v3/Dockerfile`)
- Docker and Docker Compose for local/full-stack runs (`docker-compose.yml`, `docker-compose.local.yml`)

**Production:**
- Containerized deployment with Docker Compose and Traefik in `docker-compose.prod.yml`
- Persistent volume-backed SQLite storage (`bokfoering-data` volume) in `docker-compose*.yml`
- Optional Terraform-managed Hetzner Cloud infrastructure in `terraform/main.tf`

---

*Stack analysis: 2026-05-14*
