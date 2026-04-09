from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _get_config_dir() -> Path:
    """Get the config directory (~/.config/agentmd)."""
    config_dir = Path.home() / ".config" / "agentmd"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def _get_config_path() -> Path:
    """Get the config.yaml path (always ~/.config/agentmd/config.yaml)."""
    return _get_config_dir() / "config.yaml"


def _get_default_workspace() -> Path:
    """Get the default workspace path (always ~/agentmd)."""
    return Path.home() / "agentmd"


def _ensure_default_config() -> Path:
    """Ensure config.yaml exists with defaults, create if missing."""
    config_path = _get_config_path()
    if not config_path.is_file():
        default_workspace = _get_default_workspace()
        default_config = {
            "workspace": str(default_workspace),
            "agents_dir": "agents",
            "db_path": "data/agentmd.db",
            "mcp_config": "agents/mcp-servers.json",
            "defaults": {
                "provider": "google",
                "model": "gemini-2.5-flash",
            },
            "log_level": "INFO",
        }
        config_path.write_text(yaml.dump(default_config, default_flow_style=False, sort_keys=False))
    return config_path


def _find_env_file() -> str | None:
    """Find .env for secrets in workspace (~/agentmd/.env)."""
    env_path = _get_default_workspace() / ".env"
    if env_path.is_file():
        return str(env_path)
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
        config_path = _ensure_default_config()

        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return data

        if not isinstance(raw, dict):
            return data

        # Flatten nested 'defaults' key
        defaults = raw.pop("defaults", {})
        if isinstance(defaults, dict):
            for key, flat_key in (("provider", "defaults_provider"), ("model", "defaults_model")):
                if key in defaults:
                    raw.setdefault(flat_key, defaults[key])

        # YAML values are low priority — only fill in what's missing
        for k, v in raw.items():
            if v is not None and (k not in data or data.get(k) is None):
                data[k] = v

        data["config_yaml_path"] = str(config_path)
        return data


settings = Settings()
