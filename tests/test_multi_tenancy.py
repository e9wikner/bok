"""Tests for multi-tenant database isolation."""

import pytest
import tempfile
import os
from db.tenant_context import _current_tenant, get_current_tenant, set_current_tenant, DEFAULT_TENANT
from db.database import Database, TenantAwareDatabaseProxy, db
from db.tenant_db_manager import TenantDbManager


class TestTenantContext:
    """Test the context variable mechanism."""

    def test_default_tenant(self):
        """Default tenant should be 'default'."""
        assert DEFAULT_TENANT == "default"

    def test_set_and_get_tenant(self):
        token = set_current_tenant("acme-ab")
        assert get_current_tenant() == "acme-ab"
        _current_tenant.reset(token)

    def test_reset_restores_default(self):
        token = set_current_tenant("acme-ab")
        _current_tenant.reset(token)
        assert get_current_tenant() == DEFAULT_TENANT


class TestTenantDbManager:
    """Test the tenant database pool."""

    def test_creates_separate_databases(self, tmp_path):
        """Each tenant should get its own Database instance."""
        from unittest.mock import patch

        with patch("db.tenant_db_manager.settings") as mock_settings:
            mock_settings.multi_tenant = True
            mock_settings.tenant_data_dir = str(tmp_path)
            mock_settings.database_url = f"sqlite:///{tmp_path}/fallback.db"

            manager = TenantDbManager()
            db_a = manager.get_database("tenant-a")
            db_b = manager.get_database("tenant-b")

            assert db_a is not db_b
            assert "tenant-a" in db_a.db_path
            assert "tenant-b" in db_b.db_path

            manager.close_all()

    def test_same_tenant_returns_same_instance(self, tmp_path):
        """Same tenant ID should return the cached instance."""
        from unittest.mock import patch

        with patch("db.tenant_db_manager.settings") as mock_settings:
            mock_settings.multi_tenant = True
            mock_settings.tenant_data_dir = str(tmp_path)

            manager = TenantDbManager()
            db1 = manager.get_database("tenant-x")
            db2 = manager.get_database("tenant-x")

            assert db1 is db2
            manager.close_all()


class TestDataIsolation:
    """Test that data is fully isolated between tenants."""

    def test_vouchers_isolated_between_tenants(self, tmp_path):
        """Vouchers written to tenant A should not be visible in tenant B."""
        from unittest.mock import patch

        with patch("db.tenant_db_manager.settings") as mock_settings:
            mock_settings.multi_tenant = True
            mock_settings.tenant_data_dir = str(tmp_path)

            manager = TenantDbManager()
            proxy = TenantAwareDatabaseProxy()
            proxy._manager = manager

            # Write to tenant-a
            token_a = set_current_tenant("tenant-a")
            proxy.execute(
                "INSERT INTO accounts (code, name, account_type, active) VALUES (?, ?, ?, ?)",
                ("1000", "Kassa A", "asset", 1),
            )
            proxy.commit()

            # Write to tenant-b
            _current_tenant.reset(token_a)
            token_b = set_current_tenant("tenant-b")
            proxy.execute(
                "INSERT INTO accounts (code, name, account_type, active) VALUES (?, ?, ?, ?)",
                ("1000", "Kassa B", "asset", 1),
            )
            proxy.commit()

            # Verify tenant-b sees only its own data
            row = proxy.execute(
                "SELECT name FROM accounts WHERE code = '1000'"
            ).fetchone()
            assert row["name"] == "Kassa B"

            # Switch to tenant-a and verify it sees its own data
            _current_tenant.reset(token_b)
            token_a2 = set_current_tenant("tenant-a")
            row = proxy.execute(
                "SELECT name FROM accounts WHERE code = '1000'"
            ).fetchone()
            assert row["name"] == "Kassa A"

            _current_tenant.reset(token_a2)
            manager.close_all()


class TestTenantRegistry:
    """Test the master tenant registry."""

    def test_create_and_lookup_tenant(self, tmp_path):
        from db.tenant_registry import TenantRegistry

        registry = TenantRegistry(master_db_path=str(tmp_path / "_master.db"))

        tenant = registry.create_tenant(
            tenant_id="acme",
            name="Acme AB",
            api_key="key-acme-123",
            org_number="556123-4567",
        )

        assert tenant["id"] == "acme"
        assert tenant["name"] == "Acme AB"

        # Lookup by API key
        found = registry.get_tenant_by_api_key("key-acme-123")
        assert found is not None
        assert found["id"] == "acme"

        # Lookup unknown key returns None
        assert registry.get_tenant_by_api_key("unknown-key") is None

    def test_list_tenants(self, tmp_path):
        from db.tenant_registry import TenantRegistry

        registry = TenantRegistry(master_db_path=str(tmp_path / "_master.db"))
        registry.create_tenant("t1", "Tenant One", "key1")
        registry.create_tenant("t2", "Tenant Two", "key2")

        tenants = registry.list_tenants()
        assert len(tenants) == 2

    def test_deactivate_tenant(self, tmp_path):
        from db.tenant_registry import TenantRegistry

        registry = TenantRegistry(master_db_path=str(tmp_path / "_master.db"))
        registry.create_tenant("t1", "Tenant One", "key1")
        registry.deactivate_tenant("t1")

        # Should not appear in active-only list
        assert len(registry.list_tenants(active_only=True)) == 0
        assert len(registry.list_tenants(active_only=False)) == 1

        # API key lookup should not find deactivated tenant
        assert registry.get_tenant_by_api_key("key1") is None
