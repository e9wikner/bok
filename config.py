"""Application configuration."""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Database
    database_url: str = "sqlite:////tmp/bokfoering.db"
    database_check_same_thread: bool = False  # SQLite only

    # Multi-tenancy
    multi_tenant: bool = os.getenv("MULTI_TENANT", "False").lower() == "true"
    tenant_data_dir: str = os.getenv("TENANT_DATA_DIR", "/app/data/tenants")
    default_tenant_id: str = os.getenv("DEFAULT_TENANT_ID", "default")

    # API
    api_title: str = "Bokföringssystem API"
    api_version: str = "0.1.0"
    api_description: str = "REST API för bokföring enligt BFL och BFNAR 2013:2"

    # Authentication
    api_key: str = os.getenv("BOKFOERING_API_KEY", "dev-key-change-in-production")
    admin_api_key: str = os.getenv("ADMIN_API_KEY", "test-admin-key")

    # Security
    debug: bool = os.getenv("DEBUG", "False").lower() == "true"

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
    }


settings = Settings()
