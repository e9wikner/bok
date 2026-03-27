"""Tenant context management using contextvars.

Provides async-safe tenant ID propagation through the request lifecycle.
Works with both sync and async code in FastAPI.
"""

import contextvars
from typing import Optional


DEFAULT_TENANT = "default"

# Context variable holding the current tenant ID for this request/task
_current_tenant: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_tenant", default=DEFAULT_TENANT
)


def get_current_tenant() -> str:
    """Get the tenant ID for the current request context.

    Returns DEFAULT_TENANT if no tenant has been set (backward compatibility).
    """
    return _current_tenant.get()


def set_current_tenant(tenant_id: str) -> contextvars.Token:
    """Set the tenant ID for the current request context.

    Returns a token that can be used to reset the context var.
    """
    return _current_tenant.set(tenant_id)
