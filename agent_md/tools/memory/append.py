"""Tool: memory_append — Append to a section in the agent's memory file."""

from __future__ import annotations

from langchain_core.tools import tool

from agent_md.tools.memory._parser import parse_memory_file, serialize_memory_file

MEMORY_SECTION_WARN_THRESHOLD = 50


def create_memory_append_tool(agent_config, path_context):
    """Create a memory_append tool that appends to a section in the agent's memory file."""

    @tool
    def memory_append(section: str, content: str) -> str:
        """Append content to a named section in long-term memory.

        Use this to incrementally add information to an existing section.

        Args:
            section: Name of the memory section.
            content: The content to append.

        Returns:
            Confirmation message, with a hint to summarize if the section is getting long.
        """
        memory_path = path_context.get_memory_file_path(agent_config)

        sections = parse_memory_file(memory_path.read_text(encoding="utf-8")) if memory_path.exists() else {}

        if section in sections:
            sections[section] = sections[section] + "\n" + content
        else:
            sections[section] = content

        memory_path.write_text(serialize_memory_file(sections), encoding="utf-8")

        line_count = len(sections[section].split("\n"))
        hint = ""
        if line_count > MEMORY_SECTION_WARN_THRESHOLD:
            hint = (
                f" Note: section '{section}' has {line_count} lines. "
                "Consider using memory_save to summarize and replace it."
            )

        return f"Appended to memory section '{section}' ({line_count} lines total).{hint}"

    return memory_append
