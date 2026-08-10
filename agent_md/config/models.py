import difflib
import re
from types import UnionType
from typing import Literal, Optional, Union, get_args, get_origin

from pydantic import BaseModel, field_validator, model_validator

HISTORY_LIMITS = {"low": 10, "medium": 50, "high": 200}

DEFAULT_CONFIRM_TOOLS = ["file_delete", "file_write"]


def effective_confirm_tools(config, defaults: list[str] | None = None) -> set[str]:
    """Return the set of tool names that require confirmation for *config*.

    effective = (defaults ∪ config.confirm) − config.auto_approve
    auto_approve == "*"/"all" clears the set entirely.
    """
    base = set(defaults if defaults is not None else DEFAULT_CONFIRM_TOOLS)
    base |= set(config.confirm)
    aa = config.auto_approve
    if aa in ("*", "all"):
        return set()
    return base - set(aa)


RESERVED_ALIASES = {"workspace", "skill_dir", "today", "now", "agents", "tools", "skills"}

ALIAS_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

# Shared identity/display-name character rule (filename stem and name:).
AGENT_IDENTITY_PATTERN = re.compile(r"^[\w \-]+$", re.UNICODE)


def validate_agent_identity(value: str, *, field: str = "id") -> str:
    """Validate an agent id or display name against the shared character rule."""
    if not value or value != value.strip():
        raise ValueError(f"Agent {field} must be non-empty and have no leading/trailing spaces.")
    if not AGENT_IDENTITY_PATTERN.match(value):
        raise ValueError(
            f"Agent {field} may contain only letters, numbers, spaces, hyphens, and underscores. Got: '{value}'"
        )
    return value


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


class TriggerFilters(BaseModel):
    """Glob include/exclude filters for watch triggers.

    When ``include`` is non-empty, the event path must match at least one
    pattern. Any path matching an ``exclude`` pattern is dropped. Matching
    is applied in the watch handler before a trigger is scheduled — it is
    not an admission-gate concern.
    """

    include: list[str] = []
    exclude: list[str] = []

    @field_validator("include", "exclude", mode="before")
    @classmethod
    def normalize_globs(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v


class TriggerConfig(BaseModel):
    """Configuration for agent triggers."""

    type: Optional[str] = "manual"  # 'manual', 'schedule', 'watch'
    every: Optional[str] = None  # e.g. '30m', '2h', '1d' (for schedule)
    cron: Optional[str] = None  # cron expression (for schedule)
    paths: list[str] = []  # paths to watch (for watch)
    input: Optional[str] = None  # optional user-input template replacing hardcoded prompts
    filters: Optional[TriggerFilters] = None  # watch include/exclude globs
    debounce: float = 0.5  # watch debounce window in seconds (default 500ms)

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

    @field_validator("debounce", mode="before")
    @classmethod
    def normalize_debounce(cls, v):
        """Accept seconds as float/int, or a duration string like ``2s`` / ``500ms``."""
        if v is None:
            return 0.5
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            s = v.strip().lower()
            m = re.match(r"^(\d+(?:\.\d+)?)\s*(ms|s)?$", s)
            if not m:
                raise ValueError(f"Invalid debounce '{v}'. Use seconds (e.g. 2.0) or '500ms'/'2s'")
            amount = float(m.group(1))
            unit = m.group(2) or "s"
            return amount / 1000.0 if unit == "ms" else amount
        raise ValueError(f"Invalid debounce type: {type(v).__name__}")

    @field_validator("debounce")
    @classmethod
    def debounce_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("debounce must be >= 0")
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
    """Read global defaults from config.yaml via Settings singleton."""
    try:
        from agent_md.config.settings import settings

        defaults = {}
        mapping = {
            "defaults_max_tool_calls": "max_tool_calls",
            "defaults_max_execution_tokens": "max_execution_tokens",
            "defaults_max_cost_usd": "max_cost_usd",
            "defaults_loop_detection": "loop_detection",
            "defaults_temperature": "temperature",
            "defaults_max_tokens": "max_tokens",
            "defaults_timeout": "timeout",
        }
        for settings_key, config_key in mapping.items():
            value = getattr(settings, settings_key, None)
            if value is not None:
                defaults[config_key] = value
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
            resolved = resolved.rstrip("/")
            # OpenAI-compatible endpoints use the /v1 API prefix. Native
            # Ollama and Anthropic endpoints do not, so preserve their URL.
            if self.provider in ("openai", "local") and not resolved.endswith("/v1"):
                resolved = resolved.rstrip("/") + "/v1"
            self.base_url = resolved
        self.url = None  # clear alias after normalization
        return self


class AgentConfig(BaseModel):
    """Complete validated configuration for a single agent.

    ``id`` is the canonical identity (filename stem). ``name`` is an optional
    display label that defaults to ``id`` when omitted.
    """

    id: str = ""
    name: str = ""  # display name; defaults to id when omitted
    description: str = ""
    icon: str | None = None  # optional emoji/icon for UIs (e.g. Obsidian plugin)
    model: ModelConfig | None = None
    trigger: TriggerConfig = TriggerConfig()
    custom_tools: list[str] = []
    mcp: list[str] = []
    skills: list[str] = []
    agents: list[str] = []  # allowlist of peer agent ids (filename stems)
    settings: SettingsConfig = SettingsConfig()
    enabled: bool = True
    history: str = "low"  # 'low', 'medium', 'high', 'off'
    paths: dict[str, PathEntry] = {}
    confirm: list[str] = []
    auto_approve: list[str] | Literal["*", "all"] = []
    on_pending: str = "skip"
    confirm_timeout: str | None = None

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
    unknown_keys: list[str] = []  # frontmatter keys the parser ignored (typos)

    @model_validator(mode="before")
    @classmethod
    def accept_tools_alias(cls, data):
        """Accept 'tools' in YAML frontmatter as alias for 'custom_tools'."""
        if isinstance(data, dict) and "tools" in data and "custom_tools" not in data:
            data["custom_tools"] = data.pop("tools")
        return data

    @model_validator(mode="before")
    @classmethod
    def normalize_identity(cls, data):
        """Derive id/name so programmatic construction and parse stay consistent.

        - Parser always supplies ``id`` (stem); ``name`` may be absent → display = id.
        - Tests/helpers that only pass ``name`` get ``id = name`` (legacy convenience).
        """
        if not isinstance(data, dict):
            return data
        if "id" in data and data["id"] == "":
            raise ValueError("Agent id must be non-empty and have no leading/trailing spaces.")
        if "name" in data and data["name"] == "":
            raise ValueError("Agent name must be non-empty and have no leading/trailing spaces.")
        agent_id = data.get("id", None)
        name = data.get("name", None)
        if agent_id is None and name is not None:
            data["id"] = name
            agent_id = name
        if name is None and agent_id is not None:
            data["name"] = agent_id
        if data.get("id") in (None, "") and data.get("name") in (None, ""):
            raise ValueError("Agent id is required (filename stem), or provide name for programmatic use.")
        return data

    @model_validator(mode="before")
    @classmethod
    def apply_global_agent_defaults(cls, data):
        """Apply config.yaml agent defaults (frontmatter overrides)."""
        if not isinstance(data, dict):
            data = {}
        try:
            from agent_md.config.settings import settings

            if "history" not in data and settings.defaults_history:
                data["history"] = settings.defaults_history
            if "on_pending" not in data and settings.defaults_on_pending:
                data["on_pending"] = settings.defaults_on_pending
            if "confirm_timeout" not in data and settings.defaults_confirm_timeout:
                data["confirm_timeout"] = settings.defaults_confirm_timeout
        except Exception:
            pass
        return data

    @field_validator("skills", mode="before")
    @classmethod
    def normalize_skills(cls, v):
        """Accept a single string or a list of strings."""
        if isinstance(v, str):
            return [v]
        return v

    @field_validator("agents", mode="before")
    @classmethod
    def normalize_agents(cls, v):
        """Accept a single string or a list of strings."""
        if isinstance(v, str):
            return [v]
        return v if v else []

    @field_validator("paths", mode="before")
    @classmethod
    def validate_paths_format(cls, v):
        """Accept dict only — reject the legacy list format with a helpful error."""
        if v is None:
            return {}
        if isinstance(v, list):
            raise ValueError("paths must be a dict of alias: path pairs, not a list")
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

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        return validate_agent_identity(v, field="id")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return validate_agent_identity(v, field="name")

    @field_validator("confirm", mode="before")
    @classmethod
    def normalize_confirm(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v

    @field_validator("auto_approve", mode="before")
    @classmethod
    def normalize_auto_approve(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            if v in ("*", "all"):
                return v
            return [v]
        return v

    @field_validator("on_pending")
    @classmethod
    def validate_on_pending(cls, v):
        allowed = ("skip", "parallel")
        if v not in allowed:
            raise ValueError(f"on_pending must be one of {allowed}, got '{v}'")
        return v

    @field_validator("confirm_timeout")
    @classmethod
    def validate_confirm_timeout(cls, v):
        if v is None or v == "none":
            return v
        if not re.match(r"^\d+[smhd]$", v):
            raise ValueError(f"Invalid confirm_timeout: '{v}'. Use e.g. '30s', '5m', '2h', '1d', or 'none'.")
        return v


# --- Unknown frontmatter keys -------------------------------------------------
#
# Pydantic ignores extra keys, so a typo like `triger:` used to vanish without a
# trace and the agent silently ran as `manual`. These helpers make the ignored
# keys visible — as a warning, never an error: frontmatter written for a newer
# agentmd must keep loading on an older one.

# Aliases the validators above accept but that are not fields themselves.
_FRONTMATTER_ALIASES = {"tools"}

# Values the parser computes; never valid frontmatter keys.
COMPUTED_FIELDS = {"id", "system_prompt", "file_path", "config_hash", "unknown_keys"}


def _nested_model(annotation) -> type[BaseModel] | None:
    """Return the nested model behind ``X`` or ``X | None`` — never behind a container."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    if get_origin(annotation) in (Union, UnionType):
        for arg in get_args(annotation):
            if isinstance(arg, type) and issubclass(arg, BaseModel):
                return arg
    return None


def collect_unknown_keys(data, model: type[BaseModel] = None, prefix: str = "") -> list[str]:
    """Return the keys in *data* that *model* does not define, dotted for nested maps."""
    model = model or AgentConfig
    unknown: list[str] = []
    if not isinstance(data, dict):
        return unknown

    fields = model.model_fields
    for key, value in data.items():
        name = f"{prefix}{key}"
        if not isinstance(key, str):
            unknown.append(name)
            continue
        if key in _FRONTMATTER_ALIASES:
            continue
        if key not in fields or key in COMPUTED_FIELDS:
            unknown.append(name)
            continue
        nested = _nested_model(fields[key].annotation)
        if nested is not None:
            unknown.extend(collect_unknown_keys(value, nested, prefix=f"{name}."))
    return unknown


def format_unknown_key_warning(key: str) -> str:
    """Describe an unknown frontmatter *key*, suggesting the field it resembles."""
    parts = key.split(".")
    model: type[BaseModel] | None = AgentConfig
    for part in parts[:-1]:
        field = model.model_fields.get(part) if model else None
        model = _nested_model(field.annotation) if field else None

    candidates = sorted(set(model.model_fields) - COMPUTED_FIELDS) if model else []
    match = difflib.get_close_matches(parts[-1], candidates, n=1, cutoff=0.7)
    hint = f" — did you mean '{'.'.join(parts[:-1] + [match[0]])}'?" if match else ""
    return f"unknown frontmatter key '{key}' (ignored){hint}"
