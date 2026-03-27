"""Tenant registry backed by a small master SQLite database.

Stores tenant metadata and API key mappings.
Uses its own direct sqlite3 connection (not through the tenant-aware proxy).
"""

import sqlite3
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

from config import settings


class TenantRegistry:
    """Manages tenant registration in a master database."""

    def __init__(self, master_db_path: Optional[str] = None):
        if master_db_path is None:
            master_db_path = str(
                Path(settings.tenant_data_dir) / "_master.db"
            )
        self._db_path = master_db_path
        self._lock = threading.Lock()

        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(self._db_path)), exist_ok=True)
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a connection to the master database."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _init_schema(self) -> None:
        """Create the tenants table if it doesn't exist."""
        conn = self._get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tenants (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    org_number TEXT,
                    api_key TEXT NOT NULL UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active INTEGER DEFAULT 1
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def create_tenant(
        self,
        tenant_id: str,
        name: str,
        api_key: str,
        org_number: Optional[str] = None,
    ) -> Dict:
        """Create a new tenant."""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT INTO tenants (id, name, org_number, api_key)
                       VALUES (?, ?, ?, ?)""",
                    (tenant_id, name, org_number, api_key),
                )
                conn.commit()
                return self.get_tenant(tenant_id)
            finally:
                conn.close()

    def get_tenant(self, tenant_id: str) -> Optional[Dict]:
        """Get a tenant by ID."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM tenants WHERE id = ?", (tenant_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_tenant_by_api_key(self, api_key: str) -> Optional[Dict]:
        """Look up a tenant by API key."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM tenants WHERE api_key = ? AND is_active = 1",
                (api_key,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_tenants(self, active_only: bool = True) -> List[Dict]:
        """List all tenants."""
        conn = self._get_conn()
        try:
            if active_only:
                rows = conn.execute(
                    "SELECT * FROM tenants WHERE is_active = 1 ORDER BY name"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tenants ORDER BY name"
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def tenant_exists(self, tenant_id: str) -> bool:
        """Check if a tenant exists."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT 1 FROM tenants WHERE id = ?", (tenant_id,)
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    def deactivate_tenant(self, tenant_id: str) -> bool:
        """Deactivate a tenant (soft delete)."""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    "UPDATE tenants SET is_active = 0 WHERE id = ?",
                    (tenant_id,),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()
