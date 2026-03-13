"""Tools: memory_save, memory_append, memory_retrieve — Long-term memory for agents."""

from __future__ import annotations

from langchain_core.tools import tool

MEMORY_SECTION_WARN_THRESHOLD = 50


def _parse_memory_file(content: str) -> dict[str, str]:
    """Parse a .memory.md file into sections keyed by header name.

    Each section starts with '# SECTION_NAME' and includes all content
    until the next section header or end of file.
    """
    sections: dict[str, str] = {}
    current_section = None
    current_lines: list[str] = []

    for line in content.split("\n"):
        if line.startswith("# "):
            # Save previous section
            if current_section is not None:
                sections[current_section] = "\n".join(current_lines).strip()
            current_section = line[2:].strip()
            current_lines = []
        else:
            current_lines.append(line)

    # Save last section
    if current_section is not None:
        sections[current_section] = "\n".join(current_lines).strip()

    return sections


def _serialize_memory_file(sections: dict[str, str]) -> str:
    """Serialize sections dict back to .memory.md format."""
    parts = []
    for name, content in sections.items():
        parts.append(f"# {name}\n\n{content}")
    return "\n\n".join(parts) + "\n" if parts else ""


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

        sections = _parse_memory_file(memory_path.read_text(encoding="utf-8")) if memory_path.exists() else {}

        sections[section] = content

        memory_path.write_text(_serialize_memory_file(sections), encoding="utf-8")
        return f"Memory section '{section}' saved ({len(content)} chars)."

    return memory_save


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

        sections = _parse_memory_file(memory_path.read_text(encoding="utf-8")) if memory_path.exists() else {}

        if section in sections:
            sections[section] = sections[section] + "\n" + content
        else:
            sections[section] = content

        memory_path.write_text(_serialize_memory_file(sections), encoding="utf-8")

        line_count = len(sections[section].split("\n"))
        hint = ""
        if line_count > MEMORY_SECTION_WARN_THRESHOLD:
            hint = (
                f" Note: section '{section}' has {line_count} lines. "
                "Consider using memory_save to summarize and replace it."
            )

        return f"Appended to memory section '{section}' ({line_count} lines total).{hint}"

    return memory_append


def create_memory_retrieve_tool(agent_config, path_context):
    """Create a memory_retrieve tool that reads a section from the agent's memory file."""

    @tool
    def memory_retrieve(section: str) -> str:
        """Retrieve the content of a named section from long-term memory.

        Args:
            section: Name of the memory section to retrieve.

        Returns:
            The section content, or a message if not found.
        """
        memory_path = path_context.get_memory_file_path(agent_config)

        if not memory_path.exists():
            return f"No memory file found. Use memory_save to create one."

        sections = _parse_memory_file(memory_path.read_text(encoding="utf-8"))

        if section not in sections:
            available = list(sections.keys())
            if available:
                return f"Section '{section}' not found. Available sections: {', '.join(available)}"
            return f"Section '{section}' not found. Memory file is empty."

        return sections[section]

    return memory_retrieve
