import re
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator

HISTORY_LIMITS = {"low": 10, "medium": 50, "high": 200}


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


class SettingsConfig(BaseModel):
    """LLM and runtime settings for an agent."""

    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 300  # seconds


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
    paths: list[str] = []

    @field_validator("history")
    @classmethod
    def validate_history(cls, v: str) -> str:
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

    @field_validator("paths", "skills", mode="before")
    @classmethod
    def normalize_to_list(cls, v):
        """Accept a single string or a list of strings."""
        if isinstance(v, str):
            return [v]
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(f"Agent name must contain only alphanumeric, hyphens, and underscores. Got: '{v}'")
        return v
