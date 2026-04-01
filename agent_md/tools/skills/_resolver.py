"""Internal skill content resolver — loads and processes SKILL.md on demand.

This is NOT a tool. It is called by the post_tool_processor graph node
to build the content that gets injected as a meta message.
"""

from __future__ import annotations

from pathlib import Path

from agent_md.skills.loader import apply_substitutions
from agent_md.skills.parser import parse_skill_full
from agent_md.tools.skills._validation import validate_skill_access


def resolve_skill_content(
    skill_name: str,
    arguments: str,
    agent_config,
    skills_dir: Path,
) -> str | None:
    """Load a skill's SKILL.md, apply substitutions, and return formatted content.

    Args:
        skill_name: Name of the skill to resolve.
        arguments: User-provided arguments string (replaces $ARGUMENTS).
        agent_config: AgentConfig — used to validate skill access.
        skills_dir: Root skills directory (contains skill subdirectories).

    Returns:
        Formatted skill content string, or None if skill is invalid/missing.
    """
    skill_path, error = validate_skill_access(skill_name, agent_config, skills_dir)
    if error:
        return None

    try:
        definition = parse_skill_full(skill_path)
    except (OSError, ValueError):
        return None

    processed = apply_substitutions(
        definition.instructions,
        arguments=arguments,
        skill_dir=definition.skill_dir,
    )

    parts = [f"# Skill: {definition.name}"]
    if definition.description:
        parts.append(f"\n{definition.description}\n")
    parts.append(f"\n{processed}")

    if definition.has_scripts:
        scripts_path = Path(definition.skill_dir) / "scripts"
        scripts = [f.name for f in scripts_path.iterdir() if f.is_file()]
        if scripts:
            parts.append(f"\n\nAvailable scripts: {', '.join(scripts)}")
            parts.append("Use skill_run_script to execute them.")

    if definition.has_references:
        refs_path = Path(definition.skill_dir) / "references"
        refs = [f.name for f in refs_path.iterdir() if f.is_file()]
        if refs:
            parts.append(f"\n\nAvailable references: {', '.join(refs)}")
            parts.append("Use skill_read_file to read them.")

    return "\n".join(parts)
