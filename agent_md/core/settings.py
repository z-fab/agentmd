from __future__ import annotations

from pathlib import Path

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

    # --- Database ---
    DB_PATH: Path | str = Path("data/agentmd.db").resolve()

    OUTPUT_DIR: Path | str = Path("output").resolve()

    # --- MCP ---
    MCP_CONFIG_PATH: Path | str | None = None

    # --- Runtime ---
    log_level: str = "INFO"


settings = Settings()
