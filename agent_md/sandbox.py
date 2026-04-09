"""Public sandbox helper for custom tool authors.

Custom tools run with full process permissions — AgentMD does not enforce
the agent's `paths` whitelist on them. Use this helper to opt-in to
the same path validation that built-in tools use.

Example::

    from agent_md.sandbox import validate_path

    def create_my_tool(agent_config, path_context):
        @tool
        def my_custom_tool(file: str) -> str:
            resolved, error = validate_path(file, agent_config, path_context)
            if error:
                return error
            return resolved.read_text()
        return my_custom_tool
"""

from __future__ import annotations

from pathlib import Path

from agent_md.core.path_context import PathContext


def validate_path(
    path: str,
    agent_config,
    path_context: PathContext,
) -> tuple[Path | None, str | None]:
    """Resolve and sandbox-check a path against the agent's `paths`.

    Same semantics as the built-in file tools: alias expansion, absolute
    and relative path support, sandbox enforcement.

    Returns:
        (resolved_path, None) on success, (None, error_message) on failure.
    """
    return path_context.validate_path(path, agent_config)


__all__ = ["validate_path"]
