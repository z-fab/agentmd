"""Tool registry — built-in tools that are always available to every agent."""

from __future__ import annotations

from agent_md.tools.http import http_request

# Static tools (no agent context needed)
_STATIC_TOOLS = [http_request]


def resolve_builtin_tools(agent_config=None, path_context=None) -> list:
    """Return all built-in tools, ready to use.

    Context-aware tools (file_read, file_write, file_glob, memory_*, skill_*)
    are created dynamically with the agent's path context. Static tools are included as-is.

    Args:
        agent_config: AgentConfig for context-aware tools.
        path_context: PathContext for context-aware tools.

    Returns:
        List of all built-in LangChain tool objects.
    """
    from agent_md.tools.files import (
        create_file_edit_tool,
        create_file_glob_tool,
        create_file_move_tool,
        create_file_read_tool,
        create_file_write_tool,
    )
    from agent_md.tools.memory import (
        create_memory_append_tool,
        create_memory_retrieve_tool,
        create_memory_save_tool,
    )

    tools = list(_STATIC_TOOLS)

    if agent_config is not None and path_context is not None:
        tools.append(create_file_read_tool(agent_config, path_context))
        tools.append(create_file_write_tool(agent_config, path_context))
        tools.append(create_file_edit_tool(agent_config, path_context))
        tools.append(create_file_glob_tool(agent_config, path_context))
        tools.append(create_file_move_tool(agent_config, path_context))
        tools.append(create_memory_save_tool(agent_config, path_context))
        tools.append(create_memory_append_tool(agent_config, path_context))
        tools.append(create_memory_retrieve_tool(agent_config, path_context))

        # Skill tools — only when the agent has skills configured
        if agent_config.skills and path_context.skills_dir.exists():
            from agent_md.tools.skills import (
                create_skill_read_file_tool,
                create_skill_run_script_tool,
                create_skill_use_tool,
            )

            tools.append(create_skill_use_tool(agent_config, path_context.skills_dir))
            tools.append(create_skill_read_file_tool(agent_config, path_context.skills_dir))
            tools.append(create_skill_run_script_tool(agent_config, path_context.skills_dir))

    return tools


def list_builtin_tools() -> list[str]:
    """Return names of all built-in tools."""
    return sorted(
        [t.name for t in _STATIC_TOOLS]
        + [
            "file_read",
            "file_write",
            "file_edit",
            "file_glob",
            "file_move",
            "memory_save",
            "memory_append",
            "memory_retrieve",
            "skill_use",
            "skill_read_file",
            "skill_run_script",
        ]
    )
