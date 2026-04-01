"""Tool: skill_use — Load skill instructions on-demand."""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

from agent_md.skills.loader import apply_substitutions
from agent_md.skills.parser import parse_skill_full
from agent_md.tools.skills._validation import validate_skill_access


def create_skill_use_tool(agent_config, skills_dir: Path):
    """Create skill_use tool for loading skill instructions on-demand."""

    @tool
    def skill_use(skill_name: str, arguments: str = "") -> str:
        """Load a skill's instructions with variable substitutions applied.

        Use this to activate a skill and receive its detailed instructions.
        The system prompt lists available skills — call this tool to load one.

        Args:
            skill_name: Name of the skill to use.
            arguments: Optional arguments to pass to the skill (replaces $ARGUMENTS).

        Returns:
            The skill's processed instructions ready to follow.
        """
        skill_path, error = validate_skill_access(skill_name, agent_config, skills_dir)
        if error:
            return error

        try:
            definition = parse_skill_full(skill_path)
        except (OSError, ValueError) as e:
            return f"Error loading skill '{skill_name}': {e}"

        # Apply substitutions
        processed = apply_substitutions(
            definition.instructions,
            arguments=arguments,
            skill_dir=definition.skill_dir,
        )

        # Build response with context
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

    return skill_use
