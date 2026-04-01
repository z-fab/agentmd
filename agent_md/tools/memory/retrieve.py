"""Tool: memory_retrieve — Read a section from the agent's memory file."""

from __future__ import annotations

from langchain_core.tools import tool

from agent_md.tools.memory._parser import parse_memory_file


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
            return "No memory file found. Use memory_save to create one."

        sections = parse_memory_file(memory_path.read_text(encoding="utf-8"))

        if section not in sections:
            available = list(sections.keys())
            if available:
                return f"Section '{section}' not found. Available sections: {', '.join(available)}"
            return f"Section '{section}' not found. Memory file is empty."

        return sections[section]

    return memory_retrieve
