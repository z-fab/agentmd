import re
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator

HISTORY_LIMITS = {"low": 10, "medium": 50, "high": 200}

RESERVED_ALIASES = {"workspace", "skill_dir", "today", "now", "agents", "tools", "skills"}

ALIAS_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class PathEntry(BaseModel):
    """A named path entry in an agent's `paths` dict.

    Accepts either a plain string (treated as `path` with no description)
    or a dict with `path` and optional `description`.
    """

    path: str
    description: str | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_string(cls, data):
        """Allow `paths.alias: "/abs/path"` shorthand."""
        if isinstance(data, str):
            return {"path": data}
        return data


class TriggerConfig(BaseModel):
    """Configuration for agent triggers."""

    type: Optional[str] = "manual"  # 'manual', 'schedule', 'watch'
    every: Optional[str] = None  # e.g. '30m', '2h', '1d' (for schedule)
    cron: Optional[str] = None  # cron expression (for schedule)
    paths: list[str] = []  # paths to watch (for watch)

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = ("manual", "schedule", "watch")
        if v not in allowed:
            raise ValueError(f"Trigger type must be one of {allowed}, got '{v}'")
        return v

    @field_validator("paths", mode="before")
    @classmethod
    def normalize_paths(cls, v):
        """Accept a single string or a list of strings."""
        if isinstance(v, str):
            return [v]
        return v

    @model_validator(mode="after")
    def validate_trigger_fields(self):
        if self.type == "schedule":
            if not self.every and not self.cron:
                raise ValueError("Trigger type 'schedule' requires 'every' or 'cron' field")
            if self.every and self.cron:
                raise ValueError("Trigger type 'schedule' cannot have both 'every' and 'cron'")
            if self.every and not re.match(r"^\d+[smhd]$", self.every):
                raise ValueError(f"Invalid 'every' format: '{self.every}'. Use e.g. '30s', '5m', '2h', '1d'")
        if self.type == "watch":
            if not self.paths:
                raise ValueError("Trigger type 'watch' requires 'paths' field")
        return self


def _get_global_limit_defaults() -> dict:
    """Read limit defaults from config.yaml via the global Settings singleton."""
    try:
        from agent_md.config.settings import settings

        defaults = {}
        if settings.defaults_max_tool_calls is not None:
            defaults["max_tool_calls"] = settings.defaults_max_tool_calls
        if settings.defaults_max_execution_tokens is not None:
            defaults["max_execution_tokens"] = settings.defaults_max_execution_tokens
        if settings.defaults_max_cost_usd is not None:
            defaults["max_cost_usd"] = settings.defaults_max_cost_usd
        if settings.defaults_loop_detection is not None:
            defaults["loop_detection"] = settings.defaults_loop_detection
        return defaults
    except Exception:
        return {}


class SettingsConfig(BaseModel):
    """LLM and runtime settings for an agent."""

    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 300  # seconds
    # Execution limits (Spec 2)
    max_tool_calls: int | None = 50
    max_execution_tokens: int | None = 500_000
    max_cost_usd: float | None = None
    loop_detection: bool = True

    @model_validator(mode="before")
    @classmethod
    def apply_global_defaults(cls, data):
        """Apply config.yaml limit defaults (frontmatter overrides)."""
        if not isinstance(data, dict):
            data = {}

        global_defaults = _get_global_limit_defaults()
        for field, value in global_defaults.items():
            if field not in data:
                data[field] = value

        return data


class ModelConfig(BaseModel):
    """LLM model configuration."""

    provider: str
    name: str
    base_url: str | None = None
    url: str | None = None  # alias for base_url

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        allowed = ("google", "openai", "anthropic", "ollama", "local")
        if v not in allowed:
            raise ValueError(f"Provider must be one of {allowed}, got '{v}'")
        return v

    @model_validator(mode="after")
    def normalize_url(self):
        # Accept both 'url' and 'base_url', prefer base_url
        resolved = self.base_url or self.url
        if resolved:
            # Auto-append /v1 if not present
            if not resolved.rstrip("/").endswith("/v1"):
                resolved = resolved.rstrip("/") + "/v1"
            self.base_url = resolved
        self.url = None  # clear alias after normalization
        return self


class AgentConfig(BaseModel):
    """Complete validated configuration for a single agent."""

    name: str
    description: str = ""
    model: ModelConfig | None = None
    trigger: TriggerConfig = TriggerConfig()
    custom_tools: list[str] = []
    mcp: list[str] = []
    skills: list[str] = []
    settings: SettingsConfig = SettingsConfig()
    enabled: bool = True
    history: str = "low"  # 'low', 'medium', 'high', 'off'
    paths: dict[str, PathEntry] = {}

    @field_validator("history", mode="before")
    @classmethod
    def validate_history(cls, v):
        # YAML 1.1 parses `off` as False — accept it.
        if v is False:
            return "off"
        if v is True:
            raise ValueError(
                "history: true is not valid. "
                "Note: YAML parses `on` as True and `off` as False — "
                'quote string values: history: "low" / "medium" / "high" / "off"'
            )
        allowed = ("low", "medium", "high", "off")
        if v not in allowed:
            raise ValueError(f"History level must be one of {allowed}, got '{v}'")
        return v

    # Computed fields (not from YAML)
    system_prompt: str = ""
    file_path: str = ""
    config_hash: str = ""

    @model_validator(mode="before")
    @classmethod
    def accept_tools_alias(cls, data):
        """Accept 'tools' in YAML frontmatter as alias for 'custom_tools'."""
        if isinstance(data, dict) and "tools" in data and "custom_tools" not in data:
            data["custom_tools"] = data.pop("tools")
        return data

    @field_validator("skills", mode="before")
    @classmethod
    def normalize_skills(cls, v):
        """Accept a single string or a list of strings."""
        if isinstance(v, str):
            return [v]
        return v

    @field_validator("paths", mode="before")
    @classmethod
    def validate_paths_format(cls, v):
        """Accept dict only — reject the legacy list format with a helpful error."""
        if v is None:
            return {}
        if isinstance(v, list):
            raise ValueError(
                "paths must be a dict of named aliases (changed in v0.7.0).\n"
                "Migrate from:\n  paths:\n    - /a\n    - /b\n"
                "To:\n  paths:\n    alias_a: /a\n    alias_b: /b\n"
                "See docs/path-model.md for details."
            )
        if not isinstance(v, dict):
            raise ValueError(f"paths must be a dict, got {type(v).__name__}")
        for alias in v.keys():
            if not isinstance(alias, str):
                raise ValueError(f"path alias must be a string, got {type(alias).__name__}")
            if alias in RESERVED_ALIASES:
                raise ValueError(f"path alias '{alias}' is reserved. Reserved names: {sorted(RESERVED_ALIASES)}")
            if not ALIAS_PATTERN.match(alias):
                raise ValueError(f"path alias '{alias}' is invalid. Aliases must match [a-z][a-z0-9_]*.")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(f"Agent name must contain only alphanumeric, hyphens, and underscores. Got: '{v}'")
        return v
