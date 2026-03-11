"""Tool registry — central catalog of all available tools."""

from __future__ import annotations

from agent_md.tools.http_request import http_request

# Static tools (no agent context needed)
_STATIC_TOOLS = [http_request]

TOOL_REGISTRY: dict[str, object] = {t.name: t for t in _STATIC_TOOLS}

# Tools that require agent context (created via factory)
_CONTEXT_TOOLS = {"file_read", "file_write"}


def resolve_tools(tool_names: list[str], agent_config=None, path_context=None) -> list:
    """Resolve tool names to their actual LangChain tool objects.

    Context-aware tools (file_read, file_write) are created dynamically
    with the agent's path context. Other tools come from the static registry.

    Args:
        tool_names: List of tool name strings from the agent frontmatter.
        agent_config: AgentConfig for context-aware tools.
        path_context: PathContext for context-aware tools.

    Returns:
        List of LangChain tool objects.

    Raises:
        ValueError: If a tool name is not found in the registry.
    """
    tools = []
    for name in tool_names:
        if name in _CONTEXT_TOOLS:
            if agent_config is None or path_context is None:
                raise ValueError(f"Tool '{name}' requires agent_config and path_context")
            if name == "file_read":
                from agent_md.tools.file_read import create_file_read_tool

                tools.append(create_file_read_tool(agent_config, path_context))
            elif name == "file_write":
                from agent_md.tools.file_write import create_file_write_tool

                tools.append(create_file_write_tool(agent_config, path_context))
        elif name in TOOL_REGISTRY:
            tools.append(TOOL_REGISTRY[name])
        else:
            all_tools = sorted(list(TOOL_REGISTRY.keys()) + list(_CONTEXT_TOOLS))
            raise ValueError(f"Unknown tool: '{name}'. Available tools: {', '.join(all_tools)}")
    return tools


def list_tools() -> list[str]:
    """Return names of all available built-in tools."""
    return sorted(list(TOOL_REGISTRY.keys()) + list(_CONTEXT_TOOLS))
