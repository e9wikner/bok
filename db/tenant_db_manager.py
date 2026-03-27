"""Tenant database manager — pool of per-tenant Database instances.

Each tenant gets its own SQLite file at {tenant_data_dir}/{tenant_id}/bokfoering.db.
Database instances are created and initialized (migrations) on first access.
"""

import threading
from collections import OrderedDict
from pathlib import Path
from typing import Optional

from config import settings


class TenantDbManager:
    """Manages a pool of per-tenant Database instances."""

    def __init__(self, max_tenants: int = 50):
        self._databases: OrderedDict = OrderedDict()
        self._lock = threading.Lock()
        self._max_tenants = max_tenants

    def get_database(self, tenant_id: str):
        """Get (or create + initialize) the Database for a tenant.

        Thread-safe. Auto-runs migrations on first access.
        """
        # Fast path: already cached
        if tenant_id in self._databases:
            self._databases.move_to_end(tenant_id)
            return self._databases[tenant_id]

        # Slow path: create under lock
        with self._lock:
            # Double-check after acquiring lock
            if tenant_id in self._databases:
                self._databases.move_to_end(tenant_id)
                return self._databases[tenant_id]

            db_instance = self._create_database(tenant_id)

            # LRU eviction
            if len(self._databases) >= self._max_tenants:
                _evicted_id, evicted_db = self._databases.popitem(last=False)
                evicted_db.disconnect()

            self._databases[tenant_id] = db_instance
            return db_instance

    def _create_database(self, tenant_id: str):
        """Create a new Database instance for a tenant and run migrations."""
        from db.database import Database  # Local import to avoid circular

        if settings.multi_tenant:
            tenant_dir = Path(settings.tenant_data_dir) / tenant_id
            tenant_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(tenant_dir / "bokfoering.db")
        else:
            # Single-tenant mode: use the configured database_url
            db_path = settings.database_url.replace("sqlite:///", "")

        db_instance = Database(db_path)
        db_instance.init_db()
        return db_instance

    def remove_database(self, tenant_id: str) -> None:
        """Remove a tenant's Database from the pool."""
        with self._lock:
            db_instance = self._databases.pop(tenant_id, None)
            if db_instance:
                db_instance.disconnect()

    def close_all(self) -> None:
        """Close all tenant database connections."""
        with self._lock:
            for db_instance in self._databases.values():
                db_instance.disconnect()
            self._databases.clear()
