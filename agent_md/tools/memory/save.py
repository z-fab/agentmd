"""Tool: memory_save — Replace a section in the agent's memory file."""

from __future__ import annotations

from langchain_core.tools import tool

from agent_md.tools.memory._parser import parse_memory_file, serialize_memory_file


def create_memory_save_tool(agent_config, path_context):
    """Create a memory_save tool that replaces a section in the agent's memory file."""

    @tool
    def memory_save(section: str, content: str) -> str:
        """Save content to a named section in long-term memory, replacing any existing content.

        Use this to store important information that should persist across sessions.
        Also use this to rewrite/summarize a section when it gets too long.

        Args:
            section: Name of the memory section (e.g., 'user_preferences', 'project_context').
            content: The content to save in this section.

        Returns:
            Confirmation message.
        """
        memory_path = path_context.get_memory_file_path(agent_config)

        sections = parse_memory_file(memory_path.read_text(encoding="utf-8")) if memory_path.exists() else {}

        sections[section] = content

        memory_path.write_text(serialize_memory_file(sections), encoding="utf-8")
        return f"Memory section '{section}' saved ({len(content)} chars)."

    return memory_save
