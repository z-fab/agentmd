import re
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator


class TriggerConfig(BaseModel):
    """Configuration for agent triggers."""

    type: str  # 'cron', 'interval', 'manual'
    schedule: Optional[str] = None  # cron expression
    interval: Optional[str] = None  # e.g. '30m', '2h', '1d'

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = ("cron", "interval", "manual")
        if v not in allowed:
            raise ValueError(f"Trigger type must be one of {allowed}, got '{v}'")
        return v

    @model_validator(mode="after")
    def validate_trigger_fields(self):
        if self.type == "cron" and not self.schedule:
            raise ValueError("Trigger type 'cron' requires 'schedule' field")
        if self.type == "interval" and not self.interval:
            raise ValueError("Trigger type 'interval' requires 'interval' field")
        if self.type == "interval" and self.interval:
            if not re.match(r"^\d+[smhd]$", self.interval):
                raise ValueError(f"Invalid interval format: '{self.interval}'. Use e.g. '30s', '5m', '2h', '1d'")
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
    model: ModelConfig
    trigger: TriggerConfig
    tools: list[str] = []
    mcp: list[str] = []
    settings: SettingsConfig = SettingsConfig()
    enabled: bool = True

    # Computed fields (not from YAML)
    system_prompt: str = ""
    file_path: str = ""
    config_hash: str = ""

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(f"Agent name must contain only alphanumeric, hyphens, and underscores. Got: '{v}'")
        return v
