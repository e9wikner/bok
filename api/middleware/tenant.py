"""Tenant middleware for multi-tenant request routing.

Extracts the tenant ID from the X-Tenant-Id header and sets it
in the contextvars context so the database proxy routes to the
correct SQLite file for the duration of the request.

Uses a raw ASGI middleware (not BaseHTTPMiddleware) to ensure
contextvars propagate correctly to route handlers.
"""

from starlette.types import ASGIApp, Receive, Scope, Send

from config import settings
from db.tenant_context import set_current_tenant, DEFAULT_TENANT


# Endpoints that don't require tenant context
TENANT_EXEMPT_PATHS = {"/", "/health", "/api/v1/health", "/docs", "/redoc", "/openapi.json"}


class TenantMiddleware:
    """ASGI middleware that extracts X-Tenant-Id header and sets tenant context."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # Determine tenant ID
        if path in TENANT_EXEMPT_PATHS:
            tenant_id = settings.default_tenant_id
        elif path.startswith("/api/v1/admin/tenants") or path.startswith("/api/v1/tenants"):
            tenant_id = settings.default_tenant_id
        else:
            # Extract tenant from headers
            tenant_id = settings.default_tenant_id
            for header_name, header_value in scope.get("headers", []):
                if header_name == b"x-tenant-id":
                    tenant_id = header_value.decode("latin-1")
                    break

        # Set tenant context — this works in raw ASGI middleware because
        # we're in the same async context as the route handler
        set_current_tenant(tenant_id)
        await self.app(scope, receive, send)
