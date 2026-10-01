"""Application configuration."""

import os
from typing import Optional

from pydantic import Field, field_validator
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

    # Intake source file storage
    intake_dir: str = os.getenv("INTAKE_DIR", "/app/data/intake")
    bank_input_dir: str = os.getenv(
        "BANK_INPUT_DIR",
        os.path.join(intake_dir, "bank-inputs"),
    )

    # Dropzone (folder-based intake, e.g. a Syncthing-shared folder)
    dropzone_enabled: bool = os.getenv("DROPZONE_ENABLED", "False").lower() == "true"
    dropzone_dir: str = os.getenv("DROPZONE_DIR", "/app/data/dropzone")
    dropzone_scan_interval_seconds: int = int(
        os.getenv("DROPZONE_SCAN_INTERVAL_SECONDS", "60")
    )
    dropzone_quiet_seconds: int = int(os.getenv("DROPZONE_QUIET_SECONDS", "10"))
    dropzone_max_files_per_scan: int = int(
        os.getenv("DROPZONE_MAX_FILES_PER_SCAN", "25")
    )

    # Authentication
    api_key: str = Field(
        default=os.getenv("BOKFOERING_API_KEY", "dev-key-change-in-production"),
        alias="BOKFOERING_API_KEY",
    )
    auth_username: str = os.getenv("AUTH_USERNAME", "admin")
    auth_password: str = os.getenv("AUTH_PASSWORD", "admin")

    # JWT
    jwt_secret: str = os.getenv("JWT_SECRET", "dev-jwt-secret-change-in-production")
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 7

    # Security
    debug: bool = os.getenv("DEBUG", "False").lower() == "true"
    cors_origins: str = os.getenv("CORS_ORIGINS", "*")

    # Agent runtime (docs/redesign/SPEC-agentruntime.md) -- off by default, like
    # the dropzone: running `python main.py` should never accidentally start a
    # paid LLM loop against a developer's test database.
    agent_runtime_enabled: bool = (
        os.getenv("AGENT_RUNTIME_ENABLED", "False").lower() == "true"
    )
    # Never log, print, or otherwise surface this value -- see §12.6.
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://opencode.ai/zen/v1")
    # OpenCode Go, the subscription gateway. Picked per model by the
    # `opencode-go/` prefix (services/llm/__init__.py), so Zen and Go models
    # can be used side by side. The key comes from the same OpenCode
    # account; an empty `LLM_GO_API_KEY` falls back to `LLM_API_KEY`.
    llm_go_base_url: str = os.getenv("LLM_GO_BASE_URL", "https://opencode.ai/zen/go/v1")
    # Same rule as `llm_api_key`: never log, print, or surface it.
    llm_go_api_key: str = os.getenv("LLM_GO_API_KEY", "")
    llm_default_model: str = os.getenv("LLM_DEFAULT_MODEL", "opencode-go/glm-5.3")

    # The caps (SPEC §6.5). Checked between source documents and between
    # tool turns, never inside a `with db.transaction():`.
    agent_max_tool_turns_per_item: int = int(
        os.getenv("AGENT_MAX_TOOL_TURNS_PER_ITEM", "25")
    )
    # The token and cost caps are opt-in: unset or empty means no cap. Read
    # by pydantic from the environment under the field's own name.
    #
    # Cumulative output tokens per source document / thread turn.
    agent_max_output_tokens_per_item: Optional[int] = None
    # Output tokens per single model call. With none, a Chat model runs to
    # its own limit; the Messages protocol requires a value, see
    # `services/llm/messages.py`.
    agent_max_tokens_per_turn: Optional[int] = None
    # Daily spend in öre (this codebase's amount convention), e.g. 5000 for
    # 50 kr.
    agent_daily_budget_ore: Optional[int] = None
    agent_max_items_per_pass: int = int(os.getenv("AGENT_MAX_ITEMS_PER_PASS", "20"))

    # The thread window (SPEC-tradar.md §6.3, open question 1). A token
    # budget, not a number of posts: a `draft` post and an `agent_text`
    # differ by an order of magnitude in size, so counting posts would give
    # two very different context sizes the same name. What does not fit is
    # left out -- never summarized (§6.3: an LLM summary of earlier
    # bookkeeping conversation, used as the basis for a posting, is exactly
    # the second-hand text ANALYS.md §7 warns about).
    agent_thread_window_tokens: int = int(
        os.getenv("AGENT_THREAD_WINDOW_TOKENS", "12000")
    )

    @field_validator(
        "agent_max_output_tokens_per_item",
        "agent_max_tokens_per_turn",
        "agent_daily_budget_ore",
        mode="before",
    )
    @classmethod
    def _empty_means_no_cap(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    def gateway_for(self, provider: str) -> tuple[str, str]:
        """(base_url, api_key) for a model's gateway -- `ModelInfo.provider`."""
        if provider == "opencode-go":
            return self.llm_go_base_url, self.llm_go_api_key or self.llm_api_key
        return self.llm_base_url, self.llm_api_key

    @property
    def cors_origins_list(self) -> list[str]:
        """Return configured CORS origins as a list."""
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
        # .env.example documents some deploy-only/future keys (e.g.
        # DROPZONE_HOST_DIR, which only docker-compose.yml consumes) that have
        # no matching field here -- tolerate them instead of failing startup.
        "extra": "ignore",
    }


settings = Settings()
