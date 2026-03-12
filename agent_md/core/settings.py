from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_config_yaml() -> Path | None:
    """Find config.yaml in priority order: AGENTMD_WORKSPACE > ~/agentmd > CWD."""
    ws = os.environ.get("AGENTMD_WORKSPACE", "")
    candidates: list[Path] = []
    if ws:
        candidates.append(Path(ws) / "config.yaml")
    candidates.append(Path.home() / "agentmd" / "config.yaml")
    # Dev/CWD fallback
    candidates.append(Path("config.yaml"))
    for p in candidates:
        if p.is_file():
            return p.resolve()
    return None


def _find_env_file() -> str | None:
    """Find .env for secrets (API keys only)."""
    ws = os.environ.get("AGENTMD_WORKSPACE", "")
    candidates: list[Path] = [Path(".env")]
    if ws:
        candidates.append(Path(ws) / ".env")
    candidates.append(Path.home() / "agentmd" / ".env")
    for p in candidates:
        if p.is_file():
            return str(p)
    return None


# Load secrets into os.environ so third-party libs (e.g. LangChain) can find the keys.
_env_file = _find_env_file()
if _env_file:
    load_dotenv(_env_file)
else:
    load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from config.yaml + .env."""

    model_config = SettingsConfigDict(
        env_file=_find_env_file() or ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Secrets (from .env) ---
    GOOGLE_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None

    # --- App config (from config.yaml) ---
    workspace: str = ""
    agents_dir: str = "agents"
    output_dir: str = "output"
    db_path: str = "data/agentmd.db"
    mcp_config: str = "agents/mcp-servers.json"
    defaults_provider: str = "google"
    defaults_model: str = "gemini-2.5-flash"
    log_level: str = "INFO"

    # --- Internal ---
    config_yaml_path: str | None = None

    @model_validator(mode="before")
    @classmethod
    def load_yaml_config(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Load config.yaml and merge (lower priority than env vars)."""
        config_path = _find_config_yaml()
        if not config_path:
            return data

        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return data

        if not isinstance(raw, dict):
            return data

        # Flatten nested 'defaults' key
        defaults = raw.pop("defaults", {})
        if isinstance(defaults, dict):
            if "provider" in defaults:
                raw.setdefault("defaults_provider", defaults["provider"])
            if "model" in defaults:
                raw.setdefault("defaults_model", defaults["model"])

        # YAML values are low priority — only fill in what's missing
        for k, v in raw.items():
            if v is not None and (k not in data or data.get(k) is None):
                data[k] = v

        data["config_yaml_path"] = str(config_path)
        return data


settings = Settings()
