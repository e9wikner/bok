"""FastAPI application setup."""

import os
import sys

sys.setrecursionlimit(3000)  # Increase for Pydantic v2 schema generation

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import settings

# Import routers
from api.routes import (
    vouchers,
    accounts,
    periods,
    reports,
    invoices,
    customers,
    articles,
    invoice_drafts,
    k2_reports,
    agent,
    import_sie4,
    import_csv,
    export_sie4,
    export_pdf,
    export_sru,
    compliance,
    vat,
    learning,
    accounting_patterns,
    attachments,
    auth,
    audit,
    sru_mappings,
    company_info,
    tax_ink2,
)

# Create app
app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

# AI Learning & Corrections
app.include_router(learning.router)
app.include_router(accounting_patterns.router)

# Attachments
app.include_router(attachments.router)

# Auth (JWT-based user authentication — additive, does not replace API key auth)
app.include_router(auth.router)

# Audit Log
app.include_router(audit.router)

# SRU Mappings (INK2 Tax Declaration)
app.include_router(sru_mappings.router)

# Company metadata
app.include_router(company_info.router)

# Tax declaration presentation data
app.include_router(tax_ink2.router)


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
