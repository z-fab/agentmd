"""Environment variable resolution for templates."""

import os
import re
from typing import Any

_ENV_VAR_RE = re.compile(r"\$\{([^}]+)\}")


def resolve_env_vars(value: Any) -> Any:
    """Recursively resolve ${VAR_NAME} patterns in strings, lists, and dicts."""
    if isinstance(value, str):
        return _ENV_VAR_RE.sub(lambda m: os.environ.get(m.group(1), m.group(0)), value)
    if isinstance(value, list):
        return [resolve_env_vars(item) for item in value]
    if isinstance(value, dict):
        return {k: resolve_env_vars(v) for k, v in value.items()}
    return value
