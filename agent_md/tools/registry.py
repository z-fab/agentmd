"""Tool registry — central catalog of all available tools."""

from agent_md.tools.file_read import file_read
from agent_md.tools.file_write import file_write
from agent_md.tools.http_request import http_request

# Auto-built registry from imported tools.
# To add a new tool: import it above and add to the list below.
_ALL_TOOLS = [file_read, file_write, http_request]

TOOL_REGISTRY: dict[str, object] = {t.name: t for t in _ALL_TOOLS}


def resolve_tools(tool_names: list[str]) -> list:
    """Resolve tool names to their actual LangChain tool objects.

    Args:
        tool_names: List of tool name strings from the agent frontmatter.

    Returns:
        List of LangChain tool objects.

    Raises:
        ValueError: If a tool name is not found in the registry.
    """
    tools = []
    for name in tool_names:
        if name not in TOOL_REGISTRY:
            available = ", ".join(sorted(TOOL_REGISTRY.keys()))
            raise ValueError(f"Unknown tool: '{name}'. Available tools: {available}")
        tools.append(TOOL_REGISTRY[name])
    return tools


def list_tools() -> list[str]:
    """Return names of all available built-in tools."""
    return sorted(TOOL_REGISTRY.keys())
