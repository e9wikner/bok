"""Migrate an existing single-tenant deployment to multi-tenant structure.

Moves the existing database and attachments into a per-tenant directory
and registers it as the default tenant in the master registry.

Usage:
    MULTI_TENANT=true python scripts/migrate_to_multi_tenant.py

This is a non-destructive operation — the original files are moved (not
deleted) into the tenant directory. If the migration has already been
performed, the script will report that and exit.
"""

import os
import shutil
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings


def migrate():
    if not settings.multi_tenant:
        print("❌ MULTI_TENANT must be set to true to run this migration.")
        sys.exit(1)

    tenant_dir = Path(settings.tenant_data_dir) / settings.default_tenant_id
    tenant_db_path = tenant_dir / "bokfoering.db"

    # Check if already migrated
    if tenant_db_path.exists():
        print(f"✅ Tenant directory already exists: {tenant_dir}")
        print("   Migration appears to have already been performed.")
        return

    # Find the existing single-tenant database
    old_db_path = Path(settings.database_url.replace("sqlite:///", ""))
    if not old_db_path.exists():
        print(f"⚠️  No existing database found at {old_db_path}")
        print("   Nothing to migrate. A fresh database will be created on first run.")
        return

    print(f"📦 Migrating single-tenant data to multi-tenant structure...")
    print(f"   Source DB: {old_db_path}")
    print(f"   Target:    {tenant_db_path}")

    # Create tenant directory
    tenant_dir.mkdir(parents=True, exist_ok=True)

    # Move database file(s)
    shutil.move(str(old_db_path), str(tenant_db_path))
    print(f"   ✅ Moved database")

    # Move WAL and SHM files if they exist
    for suffix in ["-wal", "-shm"]:
        wal_path = old_db_path.parent / (old_db_path.name + suffix)
        if wal_path.exists():
            shutil.move(str(wal_path), str(tenant_dir / (tenant_db_path.name + suffix)))
            print(f"   ✅ Moved {suffix} file")

    # Move attachments if they exist
    old_attachments = old_db_path.parent / "attachments"
    if old_attachments.exists() and old_attachments.is_dir():
        tenant_attachments = tenant_dir / "attachments"
        shutil.move(str(old_attachments), str(tenant_attachments))
        print(f"   ✅ Moved attachments directory")

    # Register default tenant in master registry
    from db.tenant_registry import TenantRegistry
    registry = TenantRegistry()
    if not registry.tenant_exists(settings.default_tenant_id):
        registry.create_tenant(
            tenant_id=settings.default_tenant_id,
            name="Default Company (migrated)",
            api_key=settings.api_key,
        )
        print(f"   ✅ Registered default tenant in master registry")

    print(f"\n✅ Migration complete!")
    print(f"   Tenant ID: {settings.default_tenant_id}")
    print(f"   Database:  {tenant_db_path}")
    print(f"\n   You can now start the server with MULTI_TENANT=true")


if __name__ == "__main__":
    migrate()
