from __future__ import annotations

import locale
import logging
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
        config_path.write_text(
            yaml.dump(default_config, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
    return config_path


def _find_env_files() -> list[str]:
    """Find .env files — global first, workspace-specific second (wins)."""
    files = []

    # Global: ~/.config/agentmd/.env
    global_env = _get_config_dir() / ".env"
    if global_env.is_file():
        files.append(str(global_env))

    # Workspace: {workspace}/{agents_dir}/_config/.env (or configured workspace)
    # Try to read workspace + agents_dir from config.yaml to find the workspace .env
    config_path = _get_config_path()
    workspace_path = _get_default_workspace()
    agents_subdir = "agents"
    if config_path.is_file():
        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            if raw.get("workspace"):
                workspace_path = Path(raw["workspace"]).expanduser()
            if raw.get("agents_dir"):
                agents_subdir = str(raw["agents_dir"])
        except Exception:
            pass

    ws_env = workspace_path / agents_subdir / "_config" / ".env"
    if ws_env.is_file():
        files.append(str(ws_env))

    # Legacy fallback: ~/agentmd/.env (old location)
    legacy_env = workspace_path / ".env"
    if legacy_env.is_file() and str(legacy_env) not in files:
        files.append(str(legacy_env))

    return files


def _load_env_file(path: str | None = None, *, override: bool = False) -> str | None:
    """Load one .env into ``os.environ``, tolerating a file that is not UTF-8.

    python-dotenv reads .env as UTF-8. Setup wizards up to 0.17.2 wrote it with
    the platform's locale encoding, so on a Windows console (cp1252) agentmd
    produced a file it then refused to read. Since this module is imported by
    every command, that surfaced as a traceback on *any* invocation, and
    repairing the writer alone would leave those installs broken forever — the
    bad file is already on disk and nothing rewrites it.

    So: decode with the locale encoding as a fallback, which is precisely the
    inverse of how such a file was created, and if even that fails, warn and
    move on. A .env we cannot parse is a missing API key, not a dead CLI.

    Returns the encoding that worked, or ``None`` if the file was unreadable.
    Callers need this because pydantic-settings reads the same file a second
    time, through its own ``env_file`` source, and has to be told the same
    answer — otherwise it raises the very error we just absorbed.
    """
    args = () if path is None else (path,)
    try:
        load_dotenv(*args, override=override)
        return "utf-8"
    except UnicodeDecodeError:
        pass

    log = logging.getLogger(__name__)
    label = path or ".env"
    # getencoding() ignores UTF-8 mode, unlike getpreferredencoding(): we want
    # the ANSI codepage that wrote the file, not what this interpreter prefers.
    fallback = locale.getencoding()
    if fallback.lower().replace("-", "").replace("_", "") != "utf8":
        try:
            load_dotenv(*args, override=override, encoding=fallback)
        except (UnicodeDecodeError, LookupError):
            pass
        else:
            log.warning(
                "%s is not valid UTF-8; read it as %s instead. Re-save it as UTF-8.",
                label,
                fallback,
            )
            return fallback

    log.warning(
        "%s could not be decoded and was skipped; any API keys in it were not loaded.",
        label,
    )
    return None


# Load secrets into os.environ so third-party libs (e.g. LangChain) can find the keys.
_env_files = _find_env_files()
_readable_env_files: list[str] = []
_env_file_encoding = "utf-8"
for ef in _env_files:
    _used = _load_env_file(ef, override=True)  # later files override earlier ones
    if _used:
        _readable_env_files.append(ef)
        _env_file_encoding = _used
if not _env_files:
    _load_env_file()  # fallback to default behavior


class Settings(BaseSettings):
    """Application settings loaded from config.yaml + .env."""

    # Only files _load_env_file could actually decode, paired with the encoding
    # that worked for the last of them: pydantic-settings re-reads this file
    # itself, so pointing it at an undecodable one resurrects the crash.
    model_config = SettingsConfigDict(
        env_file=_readable_env_files[-1] if _readable_env_files else ".env",
        env_file_encoding=_env_file_encoding,
        extra="ignore",
    )

    # --- App config (from config.yaml) ---
    # API keys are not Settings fields: they live in os.environ (loaded from
    # .env by python-dotenv) and are resolved via providers.keys.api_key_env_for.
    workspace: str = ""
    agents_dir: str = "agents"
    db_path: str = ""
    # Empty by default → derived from agents_dir as {agents_dir}/_config/... in bootstrap.
    # Set explicitly in config.yaml to override.
    mcp_config: str = ""
    tools_dir: str = ""
    skills_dir: str = ""
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
    defaults_confirm_tools: list[str] | None = None
    defaults_on_pending: str | None = None
    defaults_confirm_timeout: str | None = None
    defaults_checkpoint_retention_days: int = 30
    defaults_max_agent_depth: int = 3
    log_level: str = "INFO"

    # --- Internal ---
    config_yaml_path: str | None = None

    @model_validator(mode="before")
    @classmethod
    def load_yaml_config(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Load config.yaml and merge (lower priority than env vars).

        Read-only: if the file is missing, leave ``data`` unchanged so field
        defaults apply in memory. Creating ``config.yaml`` is an explicit
        action of setup (and ``info``), not a side effect of importing Settings.
        """
        # Do not call ``_get_config_dir()`` here — it mkdir's. Absence must
        # mean absence, with zero filesystem writes on the read path.
        config_path = Path.home() / ".config" / "agentmd" / "config.yaml"
        if not config_path.is_file():
            return data

        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return data

        if not isinstance(raw, dict):
            return data

        # Flatten nested 'defaults' key
        defaults = raw.pop("defaults", {})
        known_defaults = {
            "provider": "defaults_provider",
            "model": "defaults_model",
            "max_tool_calls": "defaults_max_tool_calls",
            "max_execution_tokens": "defaults_max_execution_tokens",
            "max_cost_usd": "defaults_max_cost_usd",
            "loop_detection": "defaults_loop_detection",
            "temperature": "defaults_temperature",
            "max_tokens": "defaults_max_tokens",
            "timeout": "defaults_timeout",
            "history": "defaults_history",
            "confirm_tools": "defaults_confirm_tools",
            "on_pending": "defaults_on_pending",
            "confirm_timeout": "defaults_confirm_timeout",
            "checkpoint_retention_days": "defaults_checkpoint_retention_days",
            "max_agent_depth": "defaults_max_agent_depth",
        }
        if isinstance(defaults, dict):
            for key, flat_key in known_defaults.items():
                if key in defaults:
                    raw.setdefault(flat_key, defaults[key])
            unknown_default_keys = sorted(set(defaults) - set(known_defaults))
            if unknown_default_keys:
                import logging

                logging.getLogger(__name__).warning(
                    "Unknown key(s) under defaults in config.yaml: %s",
                    ", ".join(unknown_default_keys),
                )

        known_top_level = {
            "workspace",
            "agents_dir",
            "db_path",
            "mcp_config",
            "tools_dir",
            "skills_dir",
            "log_level",
            "defaults",
        } | set(known_defaults.values())
        # Also accept the flattened defaults_* keys written above
        known_top_level |= {
            "defaults_provider",
            "defaults_model",
            "defaults_max_tool_calls",
            "defaults_max_execution_tokens",
            "defaults_max_cost_usd",
            "defaults_loop_detection",
            "defaults_temperature",
            "defaults_max_tokens",
            "defaults_timeout",
            "defaults_history",
            "defaults_confirm_tools",
            "defaults_on_pending",
            "defaults_confirm_timeout",
            "defaults_checkpoint_retention_days",
            "defaults_max_agent_depth",
        }
        unknown_top = sorted(k for k in raw if k not in known_top_level)
        if unknown_top:
            import logging

            logging.getLogger(__name__).warning(
                "Unknown key(s) in config.yaml: %s",
                ", ".join(unknown_top),
            )

        # YAML values are low priority — only fill in what's missing
        for k, v in raw.items():
            if v is not None and (k not in data or data.get(k) is None):
                data[k] = v

        data["config_yaml_path"] = str(config_path)
        return data


settings = Settings()
