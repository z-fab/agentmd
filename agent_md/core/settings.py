from __future__ import annotations

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env into os.environ so third-party libs (e.g. LangChain) can find the keys.
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Provider credentials ---
    GOOGLE_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None

    # --- Paths (overridable via env vars) ---
    AGENTMD_WORKSPACE: str | None = None
    AGENTMD_AGENTS_DIR: str | None = None
    AGENTMD_OUTPUT_DIR: str | None = None
    AGENTMD_DB_PATH: str | None = None
    AGENTMD_MCP_CONFIG: str | None = None

    # --- Runtime ---
    log_level: str = "INFO"


settings = Settings()
