"""Shared validation helpers for skill tools."""

from __future__ import annotations

from pathlib import Path


def validate_skill_access(skill_name: str, agent_config, skills_dir: Path) -> tuple[Path | None, str | None]:
    """Validate that the agent has access to a skill and it exists.

    Returns:
        (skill_path, None) on success, or (None, error_message) on failure.
    """
    if skill_name not in agent_config.skills:
        available = ", ".join(agent_config.skills) if agent_config.skills else "none"
        return None, f"Skill '{skill_name}' is not enabled for this agent. Available: {available}"

    skill_path = skills_dir / skill_name / "SKILL.md"
    if not skill_path.exists():
        return None, f"Skill '{skill_name}' not found at {skill_path}"

    return skill_path, None


def is_within(path: Path, directory: Path) -> bool:
    """Check if a resolved path is within a directory (safe against traversal)."""
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False
