"""Tool registry — built-in tools that are always available to every agent."""

from __future__ import annotations

from agent_md.tools.http_request import http_request

# Static tools (no agent context needed)
_STATIC_TOOLS = [http_request]


def resolve_builtin_tools(agent_config=None, path_context=None) -> list:
    """Return all built-in tools, ready to use.

    Context-aware tools (file_read, file_write) are created dynamically
    with the agent's path context. Static tools are included as-is.

    Args:
        agent_config: AgentConfig for context-aware tools.
        path_context: PathContext for context-aware tools.

    Returns:
        List of all built-in LangChain tool objects.
    """
    from agent_md.tools.file_read import create_file_read_tool
    from agent_md.tools.file_write import create_file_write_tool

    tools = list(_STATIC_TOOLS)

    if agent_config is not None and path_context is not None:
        tools.append(create_file_read_tool(agent_config, path_context))
        tools.append(create_file_write_tool(agent_config, path_context))

    return tools


def list_builtin_tools() -> list[str]:
    """Return names of all built-in tools."""
    return sorted([t.name for t in _STATIC_TOOLS] + ["file_read", "file_write"])
