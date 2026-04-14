from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_state_dir() -> Path:
    """Return XDG state directory for agentmd runtime data."""
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "state"
    return base / "agentmd"


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
            "defaults": {
                "provider": "google",
                "model": "gemini-2.5-flash",
            },
            "log_level": "INFO",
        }
        config_path.write_text(yaml.dump(default_config, default_flow_style=False, sort_keys=False))
    return config_path


def _find_env_files() -> list[str]:
    """Find .env files — global first, workspace-specific second (wins)."""
    files = []

    # Global: ~/.config/agentmd/.env
    global_env = _get_config_dir() / ".env"
    if global_env.is_file():
        files.append(str(global_env))

    # Workspace: ~/agentmd/agents/_config/.env (or configured workspace)
    # Try to read workspace from config.yaml to find the workspace .env
    config_path = _get_config_path()
    workspace_path = _get_default_workspace()
    if config_path.is_file():
        try:
            raw = yaml.safe_load(config_path.read_text()) or {}
            if raw.get("workspace"):
                workspace_path = Path(raw["workspace"]).expanduser()
        except Exception:
            pass

    ws_env = workspace_path / "agents" / "_config" / ".env"
    if ws_env.is_file():
        files.append(str(ws_env))

    # Legacy fallback: ~/agentmd/.env (old location)
    legacy_env = workspace_path / ".env"
    if legacy_env.is_file() and str(legacy_env) not in files:
        files.append(str(legacy_env))

    return files


# Load secrets into os.environ so third-party libs (e.g. LangChain) can find the keys.
_env_files = _find_env_files()
for ef in _env_files:
    load_dotenv(ef, override=True)  # later files override earlier ones
if not _env_files:
    load_dotenv()  # fallback to default behavior


class Settings(BaseSettings):
    """Application settings loaded from config.yaml + .env."""

    model_config = SettingsConfigDict(
        env_file=_env_files[-1] if _env_files else ".env",
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
    db_path: str = ""
    mcp_config: str = "agents/_config/mcp-servers.json"
    tools_dir: str = "agents/_config/tools"
    skills_dir: str = "agents/_config/skills"
    defaults_provider: str = "google"
    defaults_model: str = "gemini-2.5-flash"
    defaults_max_tool_calls: int | None = None
    defaults_max_execution_tokens: int | None = None
    defaults_max_cost_usd: float | None = None
    defaults_loop_detection: bool | None = None
    defaults_temperature: float | None = None
    defaults_max_tokens: int | None = None
    defaults_timeout: int | None = None
    defaults_history: str | None = None
    defaults_max_agent_depth: int = 3
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
            for key, flat_key in (
                ("provider", "defaults_provider"),
                ("model", "defaults_model"),
                ("max_tool_calls", "defaults_max_tool_calls"),
                ("max_execution_tokens", "defaults_max_execution_tokens"),
                ("max_cost_usd", "defaults_max_cost_usd"),
                ("loop_detection", "defaults_loop_detection"),
                ("temperature", "defaults_temperature"),
                ("max_tokens", "defaults_max_tokens"),
                ("timeout", "defaults_timeout"),
                ("history", "defaults_history"),
                ("max_agent_depth", "defaults_max_agent_depth"),
            ):
                if key in defaults:
                    raw.setdefault(flat_key, defaults[key])

        # YAML values are low priority — only fill in what's missing
        for k, v in raw.items():
            if v is not None and (k not in data or data.get(k) is None):
                data[k] = v

        data["config_yaml_path"] = str(config_path)
        return data


settings = Settings()
