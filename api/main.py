"""FastAPI application setup."""

import functools
import os
import sys

sys.setrecursionlimit(3000)  # Increase for Pydantic v2 schema generation

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Import routers
from api.deps import verify_api_key
from api.routes import (
    accounting_corrections,
    accounts,
    agent,
    agent_instructions,
    articles,
    audit,
    auth,
    bank_inputs,
    bokslut,
    company_info,
    compliance,
    customers,
    decisions,
    drafts,
    export_pdf,
    import_sie4,
    intake,
    invoice_drafts,
    invoices,
    overview,
    payroll,
    periods,
    reports,
    sru_mappings,
    threads,
    vouchers,
)
from config import settings
from domain.validation import ValidationError
from services import agent_runtime, dropzone


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run folder pickup and the agent runtime alongside the API when
    enabled.

    Both are threads in this process rather than a second container:
    `db.Database` already hands out thread-local SQLite connections with WAL on,
    so a worker thread needs no new infrastructure.
    """
    dropzone.start_background_scanner()
    agent_runtime.start_agent_runtime()
    try:
        yield
    finally:
        agent_runtime.stop_agent_runtime()
        dropzone.stop_background_scanner()


# Create app
app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError):
    """A domain rule the request broke: `400` with the error's code.

    A route maps a `ValidationError` itself only when the code means another
    status (`404`, `409`, `422`) or the body needs more than the error carries.
    Anything else that escapes a route is a bug and stays FastAPI's plain
    `500`, logged with its traceback, never `str(e)` in the response.
    """
    return JSONResponse(
        status_code=400,
        content={
            "detail": {
                "error": exc.message,
                "code": exc.code,
                "details": exc.details,
                **exc.payload,
            }
        },
    )


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Every route needs the bearer -- the agent's API key or a logged-in user's
# JWT -- reads too: the books hold salaries, personal numbers and invoices.
# Public are only `/`, `/health`, the auth router (login) and the agent
# entrypoint; those two routers authenticate their other routes themselves.
AUTHENTICATED = [Depends(verify_api_key)]

# Include routers (organized by phase)
# Fas 1: Grundbokföring
app.include_router(vouchers.router, dependencies=AUTHENTICATED)
app.include_router(accounts.router, dependencies=AUTHENTICATED)
app.include_router(periods.router, dependencies=AUTHENTICATED)
app.include_router(reports.router, dependencies=AUTHENTICATED)

# Fas 2: Fakturering & Moms
app.include_router(invoices.router, dependencies=AUTHENTICATED)
app.include_router(customers.router, dependencies=AUTHENTICATED)
app.include_router(articles.router, dependencies=AUTHENTICATED)
app.include_router(invoice_drafts.router, dependencies=AUTHENTICATED)

# Fas 4: Agent Integration
app.include_router(agent.router, dependencies=AUTHENTICATED)
app.include_router(agent_instructions.router)

# Import/Export
app.include_router(import_sie4.router, dependencies=AUTHENTICATED)

# PDF Export
app.include_router(export_pdf.router, dependencies=AUTHENTICATED)

# Fas 5: BFL Compliance Checking
app.include_router(compliance.router, dependencies=AUTHENTICATED)

# Agent-readable corrections
app.include_router(accounting_corrections.router, dependencies=AUTHENTICATED)

# Intake source material
app.include_router(intake.router, dependencies=AUTHENTICATED)
app.include_router(bank_inputs.router, dependencies=AUTHENTICATED)

# Auth (JWT-based user authentication — additive, does not replace API key auth)
app.include_router(auth.router)

# Audit Log
app.include_router(audit.router, dependencies=AUTHENTICATED)

# SRU Mappings (INK2 Tax Declaration)
app.include_router(sru_mappings.router, dependencies=AUTHENTICATED)
app.include_router(sru_mappings.sru_fields_router, dependencies=AUTHENTICATED)

# Company metadata
app.include_router(company_info.router, dependencies=AUTHENTICATED)

# Tax declaration presentation data
app.include_router(bokslut.router, dependencies=AUTHENTICATED)

# Payroll
app.include_router(payroll.router, dependencies=AUTHENTICATED)

# Sidöversikt (header counters for the three pages)
app.include_router(overview.router, dependencies=AUTHENTICATED)

# Tråd per vy (chatten hör till vyn, inte till appen)
app.include_router(threads.router, dependencies=AUTHENTICATED)

# Beslut: unionen av tre källor
app.include_router(decisions.router, dependencies=AUTHENTICATED)

# Trådens förslag och vad som hände med dem
app.include_router(drafts.router, dependencies=AUTHENTICATED)


@app.get("/health", tags=["health"])
@app.get("/api/v1/health", tags=["health"])
async def health_check():
    """Health check endpoint with build info."""
    return {
        "status": "ok",
        "service": "bokfoering-api",
        "version": settings.api_version,
        "commit": _build_commit(),
    }


@functools.lru_cache(maxsize=1)
def _build_commit() -> str:
    """The running commit, resolved once per process rather than per request."""
    import subprocess

    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )
    except Exception:
        return os.environ.get("GIT_COMMIT", "unknown")


@app.get("/", tags=["root"])
async def root():
    """API root."""
    return {
        "title": settings.api_title,
        "version": settings.api_version,
        "docs": "/docs",
        "openapi": "/openapi.json",
    }
