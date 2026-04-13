"""Public SDK for custom tool authors.

Provides utility functions to access agent context (paths, workspace, identity)
from within custom tools without requiring factories or dependency injection.

Usage in custom tools::

    from agent_md.sdk import resolve_path, workspace_root, agent_name

    @tool
    def my_tool(path: str) -> str:
        resolved, error = resolve_path(path)
        if error:
            return f"ERROR: {error}"
        return resolved.read_text()
"""

from __future__ import annotations

import contextvars
from pathlib import Path

_current_context: contextvars.ContextVar[tuple | None] = contextvars.ContextVar("agentmd_context", default=None)


def _set_context(agent_config, path_context) -> contextvars.Token:
    """Set the agent context for the current async task. Returns a reset token."""
    return _current_context.set((agent_config, path_context))


def _reset_context(token: contextvars.Token) -> None:
    """Reset the agent context using the token from _set_context."""
    _current_context.reset(token)


def _get_context() -> tuple:
    """Return (agent_config, path_context) or raise if not in an execution."""
    ctx = _current_context.get()
    if ctx is None:
        raise RuntimeError("Must be called within an agent execution")
    return ctx


def resolve_path(path: str) -> tuple[Path | None, str | None]:
    """Resolve a path string and validate it against sandbox rules.

    Handles alias expansion (``{output}/file.txt``), relative paths
    (resolved from workspace root), and absolute paths.

    Returns:
        ``(resolved_path, None)`` on success, ``(None, error_message)`` on failure.
    """
    config, path_context = _get_context()
    return path_context.validate_path(path, config)


def workspace_root() -> Path:
    """Return the absolute path to the workspace root directory."""
    _, path_context = _get_context()
    return path_context.workspace_root


def agent_name() -> str:
    """Return the name of the currently executing agent."""
    config, _ = _get_context()
    return config.name


def agent_paths() -> dict[str, Path]:
    """Return the agent's declared path aliases, resolved to absolute paths.

    Returns an empty dict if the agent declares no paths.

    Example::

        {"output": Path("/abs/path/to/output"), "data": Path("/abs/path/to/data")}
    """
    config, path_context = _get_context()
    result = {}
    for alias, entry in config.paths.items():
        result[alias] = path_context._resolve_relative(entry.path)
    return result


__all__ = ["resolve_path", "workspace_root", "agent_name", "agent_paths"]
