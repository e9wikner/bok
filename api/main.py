"""FastAPI application setup."""

import os
import sys

sys.setrecursionlimit(3000)  # Increase for Pydantic v2 schema generation

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import routers
from api.routes import (
    accounting_corrections,
    accounts,
    agent,
    agent_instructions,
    articles,
    attachments,
    audit,
    auth,
    bank_inputs,
    company_info,
    compliance,
    customers,
    export_pdf,
    export_sie4,
    export_sru,
    import_csv,
    import_sie4,
    intake,
    invoice_drafts,
    invoices,
    k2_reports,
    overview,
    payroll,
    periods,
    reports,
    sru_mappings,
    tax_ink2,
    threads,
    vat,
    vouchers,
)
from config import settings
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

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers (organized by phase)
# Fas 1: Grundbokföring
app.include_router(vouchers.router)
app.include_router(accounts.router)
app.include_router(periods.router)
app.include_router(reports.router)

# Fas 2: Fakturering & Moms
app.include_router(invoices.router)
app.include_router(customers.router)
app.include_router(articles.router)
app.include_router(invoice_drafts.router)

# Fas 3: Rapporter & K2
app.include_router(k2_reports.router)

# Fas 4: Agent Integration
app.include_router(agent.router)
app.include_router(agent_instructions.router)

# Import/Export
app.include_router(import_sie4.router)
app.include_router(import_csv.router)
app.include_router(export_sie4.router)

# PDF Export
app.include_router(export_pdf.router)

# SRU Export (INK2 Tax Declaration)
app.include_router(export_sru.router)

# Fas 5: BFL Compliance Checking
app.include_router(compliance.router)

# Fas 5: VAT Declarations
app.include_router(vat.router)

# Agent-readable corrections
app.include_router(accounting_corrections.router)

# Intake source material
app.include_router(intake.router)
app.include_router(bank_inputs.router)

# Attachments
app.include_router(attachments.router)

# Auth (JWT-based user authentication — additive, does not replace API key auth)
app.include_router(auth.router)

# Audit Log
app.include_router(audit.router)

# SRU Mappings (INK2 Tax Declaration)
app.include_router(sru_mappings.router)
app.include_router(sru_mappings.sru_fields_router)

# Company metadata
app.include_router(company_info.router)

# Tax declaration presentation data
app.include_router(tax_ink2.router)

# Payroll
app.include_router(payroll.router)

# Sidöversikt (header counters for the three pages)
app.include_router(overview.router)

# Tråd per vy (chatten hör till vyn, inte till appen)
app.include_router(threads.router)


@app.get("/health", tags=["health"])
@app.get("/api/v1/health", tags=["health"])
async def health_check():
    """Health check endpoint with build info."""
    import subprocess

    try:
        commit = (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )
    except Exception:
        commit = os.environ.get("GIT_COMMIT", "unknown")

    return {
        "status": "ok",
        "service": "bokfoering-api",
        "version": settings.api_version,
        "commit": commit,
    }


@app.get("/", tags=["root"])
async def root():
    """API root."""
    return {
        "title": settings.api_title,
        "version": settings.api_version,
        "docs": "/docs",
        "openapi": "/openapi.json",
    }
