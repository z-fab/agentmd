"""Tool: skill_read_file — Read supporting files from a skill directory."""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

from agent_md.tools.skills._validation import is_within, validate_skill_access


def create_skill_read_file_tool(agent_config, skills_dir: Path):
    """Create skill_read_file tool for reading supporting files from a skill."""

    @tool
    def skill_read_file(skill_name: str, file_path: str) -> str:
        """Read a file from a skill's directory (references, scripts, etc.).

        Args:
            skill_name: Name of the skill.
            file_path: Relative path within the skill directory (e.g., 'references/api-docs.md').

        Returns:
            File contents or error message.
        """
        _, error = validate_skill_access(skill_name, agent_config, skills_dir)
        if error:
            return error

        skill_dir = (skills_dir / skill_name).resolve()
        target = (skill_dir / file_path).resolve()

        # Security: resolved path must be within skill directory
        if not is_within(target, skill_dir):
            return f"Access denied: '{file_path}' is outside skill directory"

        if not target.exists():
            return f"File not found: '{file_path}' in skill '{skill_name}'"

        if not target.is_file():
            return f"Not a file: '{file_path}'"

        try:
            return target.read_text(encoding="utf-8")
        except OSError as e:
            return f"Error reading file: {e}"

    return skill_read_file
