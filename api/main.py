"""FastAPI application setup."""

import sys
sys.setrecursionlimit(3000)  # Increase for Pydantic v2 schema generation

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import settings

# Import routers
from api.routes import vouchers, accounts, periods, reports, invoices, k2_reports, agent, import_sie4, export_sie4, bank, compliance, vat

# Create app
app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
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

# Fas 3: Rapporter & K2
app.include_router(k2_reports.router)

# Fas 4: Agent Integration
app.include_router(agent.router)

# Import/Export
app.include_router(import_sie4.router)
app.include_router(export_sie4.router)

# Fas 5: Bank Integration & Auto-Categorization
app.include_router(bank.router)

# Fas 5: BFL Compliance Checking
app.include_router(compliance.router)

# Fas 5: VAT Declarations
app.include_router(vat.router)


@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "bokfoering-api",
        "version": settings.api_version
    }


@app.get("/", tags=["root"])
async def root():
    """API root."""
    return {
        "title": settings.api_title,
        "version": settings.api_version,
        "docs": "/docs",
        "openapi": "/openapi.json"
    }
