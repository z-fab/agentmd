"""Parse SKILL.md files into SkillConfig (tier 1) and SkillDefinition (tier 2)."""

from pathlib import Path

import yaml

from agent_md.skills.models import SkillConfig, SkillDefinition


def _extract_frontmatter(path: Path) -> tuple[dict, str]:
    """Extract YAML frontmatter and markdown body from a SKILL.md file.

    Returns:
        Tuple of (frontmatter_dict, body_str).

    Raises:
        ValueError: If the file format is invalid.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ValueError(f"Cannot read {path.name}: {e}") from e

    if not content.startswith("---"):
        raise ValueError(f"File {path.name} does not start with YAML frontmatter (---)")

    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"Malformed frontmatter in {path.name}: missing closing '---'")

    frontmatter_raw = parts[1].strip()
    body = parts[2].strip()

    try:
        frontmatter = yaml.safe_load(frontmatter_raw)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in {path.name}: {e}") from e

    if not isinstance(frontmatter, dict):
        raise ValueError(f"Frontmatter in {path.name} must be a YAML mapping, got {type(frontmatter).__name__}")

    # Normalize Claude Code hyphenated keys to underscored Python fields
    key_map = {
        "argument-hint": "argument_hint",
        "user-invocable": "user_invocable",
    }
    for yaml_key, python_key in key_map.items():
        if yaml_key in frontmatter:
            frontmatter[python_key] = frontmatter.pop(yaml_key)

    # Use directory name as fallback for name
    if "name" not in frontmatter:
        frontmatter["name"] = path.parent.name

    return frontmatter, body


def parse_skill_metadata(path: Path) -> SkillConfig:
    """Parse SKILL.md frontmatter only (tier 1 — fast discovery).

    Args:
        path: Path to the SKILL.md file.

    Returns:
        SkillConfig with metadata fields only.
    """
    frontmatter, _ = _extract_frontmatter(path)
    return SkillConfig(**frontmatter, skill_dir=str(path.parent.resolve()))


def parse_skill_full(path: Path) -> SkillDefinition:
    """Parse complete SKILL.md with instructions (tier 2 — on-demand).

    Args:
        path: Path to the SKILL.md file.

    Returns:
        SkillDefinition with full content and supporting file detection.
    """
    frontmatter, body = _extract_frontmatter(path)
    skill_dir = path.parent.resolve()

    return SkillDefinition(
        **frontmatter,
        instructions=body,
        skill_dir=str(skill_dir),
        has_scripts=(skill_dir / "scripts").is_dir(),
        has_references=(skill_dir / "references").is_dir(),
    )
