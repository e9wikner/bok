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
        else:
            # Verify the API key matches the tenant in the header
            from db.tenant_context import get_current_tenant
            current_tenant = get_current_tenant()
            if current_tenant != settings.default_tenant_id and current_tenant != tenant["id"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="API key does not match the specified tenant",
                )
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
