"""Parse agent .md files into validated AgentConfig objects."""

import hashlib
import logging
from pathlib import Path

import yaml

from agent_md.config.env import resolve_env_vars
from agent_md.config.models import (
    COMPUTED_FIELDS,
    AgentConfig,
    ModelConfig,
    collect_unknown_keys,
    format_unknown_key_warning,
    validate_agent_identity,
)
from agent_md.config.settings import settings

logger = logging.getLogger(__name__)


def is_agent_file(path: Path) -> bool:
    """Check if a path is an agent definition file (not memory, not directory)."""
    return path.suffix == ".md" and not path.name.endswith(".memory.md")


def parse_agent_file(path: Path) -> AgentConfig:
    """Parse a .md agent file and return a validated AgentConfig.

    The file must start with YAML frontmatter delimited by '---' lines,
    followed by the Markdown body which becomes the system prompt.

    Canonical identity is the filename stem (``path.stem``). Frontmatter
    must not declare ``id``; ``name`` is an optional display label.

    If the agent does not define a ``model`` section, the default provider
    and model from ``config.yaml`` are used.

    Raises:
        ValueError: If the file format, stem, or frontmatter is invalid.
        pydantic.ValidationError: If the frontmatter fields fail validation.
    """
    content = path.read_text(encoding="utf-8")

    # Extract frontmatter
    if not content.startswith("---"):
        raise ValueError(f"File {path.name} does not start with YAML frontmatter (---)")

    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"Malformed frontmatter in {path.name}: missing closing '---'")

    frontmatter_raw = parts[1].strip()
    body = resolve_env_vars(parts[2].strip())

    # Parse YAML
    try:
        frontmatter = yaml.safe_load(frontmatter_raw)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in {path.name}: {e}") from e

    if not isinstance(frontmatter, dict):
        raise ValueError(f"Frontmatter in {path.name} must be a YAML mapping, got {type(frontmatter).__name__}")

    # Identity is the filename stem — never accepted from frontmatter.
    if "id" in frontmatter:
        raise ValueError(
            f"Frontmatter in {path.name} must not declare 'id'; identity is the filename stem '{path.stem}'"
        )

    try:
        agent_id = validate_agent_identity(path.stem, field="id")
    except ValueError as e:
        raise ValueError(f"Invalid agent filename stem in {path.name}: {e}") from e

    # Compute config hash for change detection
    config_hash = hashlib.sha256(frontmatter_raw.encode()).hexdigest()[:16]

    # Unknown keys are ignored by Pydantic — warn instead of failing, so a typo
    # is visible without breaking files written for a newer agentmd.
    unknown_keys = collect_unknown_keys(frontmatter)
    for key in unknown_keys:
        logger.warning("%s: %s", path.name, format_unknown_key_warning(key))

    # Computed values are never taken from frontmatter — they are reported as
    # unknown above and dropped here so they cannot collide with the kwargs.
    fields = {k: v for k, v in frontmatter.items() if k not in COMPUTED_FIELDS}

    # Validate with Pydantic (name may be omitted → display defaults to id)
    config = AgentConfig(
        **fields,
        id=agent_id,
        system_prompt=body,
        config_hash=config_hash,
        file_path=str(path.resolve()),
        unknown_keys=unknown_keys,
    )

    # Apply default model from config.yaml if not specified in agent
    if config.model is None:
        config.model = ModelConfig(
            provider=settings.defaults_provider,
            name=settings.defaults_model,
        )

    return config
