"""Dependency injection for FastAPI."""

from fastapi import Depends, Header, HTTPException, status
from typing import Optional
from config import settings
from services.ledger import LedgerService


def verify_api_key(authorization: Optional[str] = Header(None)) -> str:
    """Verify API key from Authorization header.

    In multi-tenant mode, also validates that the API key belongs to
    the tenant specified in the X-Tenant-Id header.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Expect: "Bearer <api-key>"
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    api_key = parts[1]

    if settings.multi_tenant:
        # Look up API key in tenant registry
        from db.tenant_registry import TenantRegistry
        registry = TenantRegistry()
        tenant = registry.get_tenant_by_api_key(api_key)

        if not tenant:
            # Fall back to legacy single api_key check for default tenant
            if api_key != settings.api_key:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid API key",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            # Legacy key — tenant context already set by middleware, leave it
        else:
            # Key belongs to a specific tenant — trust the key, not the header.
            # This fixes the case where internal sub-requests (e.g. from SIE4
            # importer) may carry a stale or default X-Tenant-Id header while
            # providing a valid tenant-specific API key. The key IS the
            # credential; set the context to match it.
            from db.tenant_context import set_current_tenant
            set_current_tenant(tenant["id"])
    else:
        # Single-tenant mode: simple key check
        if api_key != settings.api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return api_key


def get_ledger_service() -> LedgerService:
    """Get ledger service instance."""
    return LedgerService()


def get_current_actor(api_key: str = Depends(verify_api_key)) -> str:
    """Get current actor (user) from API key."""
    if settings.multi_tenant:
        from db.tenant_context import get_current_tenant
        tenant_id = get_current_tenant()
        return f"{tenant_id}:api"
    return "api"
