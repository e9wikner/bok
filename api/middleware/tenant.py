"""Tenant middleware for multi-tenant request routing.

Extracts the tenant ID from the X-Tenant-Id header and sets it
in the contextvars context so the database proxy routes to the
correct SQLite file for the duration of the request.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from config import settings
from db.tenant_context import set_current_tenant, DEFAULT_TENANT


# Endpoints that don't require tenant context
TENANT_EXEMPT_PATHS = {"/", "/health", "/api/v1/health", "/docs", "/redoc", "/openapi.json"}


class TenantMiddleware(BaseHTTPMiddleware):
    """Middleware that extracts X-Tenant-Id header and sets tenant context."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip tenant resolution for exempt paths
        if path in TENANT_EXEMPT_PATHS:
            set_current_tenant(settings.default_tenant_id)
            return await call_next(request)

        # Admin tenant endpoints handle their own context
        if path.startswith("/api/v1/admin/tenants"):
            set_current_tenant(settings.default_tenant_id)
            return await call_next(request)

        # Extract tenant from header
        tenant_id = request.headers.get("x-tenant-id")

        if not tenant_id:
            # Backward compatibility: fall back to default tenant
            tenant_id = settings.default_tenant_id

        set_current_tenant(tenant_id)
        response = await call_next(request)
        return response
