"""Parse agent .md files into validated AgentConfig objects."""

import hashlib
from pathlib import Path

import yaml

from agent_md.core.env import resolve_env_vars
from agent_md.core.models import AgentConfig, ModelConfig
from agent_md.core.settings import settings


def is_agent_file(path: Path) -> bool:
    """Check if a path is an agent definition file (not memory, not directory)."""
    return path.suffix == ".md" and not path.name.endswith(".memory.md")


def parse_agent_file(path: Path) -> AgentConfig:
    """Parse a .md agent file and return a validated AgentConfig.

    The file must start with YAML frontmatter delimited by '---' lines,
    followed by the Markdown body which becomes the system prompt.

    If the agent does not define a ``model`` section, the default provider
    and model from ``config.yaml`` are used.

    Raises:
        ValueError: If the file format or frontmatter is invalid.
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

    # Compute config hash for change detection
    config_hash = hashlib.sha256(frontmatter_raw.encode()).hexdigest()[:16]

    # Validate with Pydantic
    config = AgentConfig(
        **frontmatter,
        system_prompt=body,
        file_path=str(path.resolve()),
        config_hash=config_hash,
    )

    # Apply default model from config.yaml if not specified in agent
    if config.model is None:
        config.model = ModelConfig(
            provider=settings.defaults_provider,
            name=settings.defaults_model,
        )

    return config
