"""Application configuration."""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Database
    database_url: str = "sqlite:////tmp/bokfoering.db"
    database_check_same_thread: bool = False  # SQLite only

    # API
    api_title: str = "Bokföringssystem API"
    api_version: str = "0.1.0"
    api_description: str = "REST API för bokföring enligt BFL och BFNAR 2013:2"

    # Internal API URL (used by SIE4 importer for sub-requests)
    api_url: str = os.getenv("API_URL", "http://localhost:8000")

    # Authentication
    api_key: str = os.getenv("BOKFOERING_API_KEY", "dev-key-change-in-production")
    auth_username: str = os.getenv("AUTH_USERNAME", "admin")
    auth_password: str = os.getenv("AUTH_PASSWORD", "admin")

    # JWT
    jwt_secret: str = os.getenv("JWT_SECRET", "dev-jwt-secret-change-in-production")
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 7

    # Security
    debug: bool = os.getenv("DEBUG", "False").lower() == "true"
    cors_origins: str = os.getenv("CORS_ORIGINS", "*")

    @property
    def cors_origins_list(self) -> list[str]:
        """Return configured CORS origins as a list."""
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
    }


settings = Settings()
