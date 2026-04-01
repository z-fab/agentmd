"""Tool: skill_use — Activate a skill (content injected by post_tool_processor)."""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

from agent_md.tools.skills._validation import validate_skill_access


def create_skill_use_tool(agent_config, skills_dir: Path):
    """Create skill_use tool that returns a short activation confirmation.

    The full skill content is NOT returned here — it is resolved and injected
    as a meta message by the post_tool_processor graph node.
    """

    @tool
    def skill_use(skill_name: str, arguments: str = "") -> str:
        """Activate a skill to receive its detailed instructions.

        Use this to activate a skill listed in the system prompt.
        After activation, the skill's full instructions will be provided
        as a follow-up message.

        Args:
            skill_name: Name of the skill to activate.
            arguments: Optional arguments to pass to the skill (replaces $ARGUMENTS).

        Returns:
            Short confirmation that the skill was activated.
        """
        skill_path, error = validate_skill_access(skill_name, agent_config, skills_dir)
        if error:
            return error

        return f"Skill '{skill_name}' activated successfully. Instructions will follow."

    return skill_use
