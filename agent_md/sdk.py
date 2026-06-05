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


def request_confirmation(message: str, *, tool_name: str | None = None, tool_args: dict | None = None) -> bool:
    """Pause and ask the user to approve an action. Returns True if approved.

    For use inside custom tools. Requires an active execution with a checkpointer.
    """
    from langgraph.types import interrupt
    from agent_md.tools.hilt import build_request

    answer = interrupt(build_request("confirm", message, tool_name=tool_name, tool_args=tool_args))
    return bool(answer.get("approved")) if isinstance(answer, dict) else bool(answer)


def request_input(message: str) -> str:
    """Pause and ask the user for free text. Returns the text (empty string if none)."""
    from langgraph.types import interrupt
    from agent_md.tools.hilt import build_request

    answer = interrupt(build_request("input", message))
    if isinstance(answer, dict):
        return str(answer.get("text", ""))
    return str(answer or "")


def request_choice(message: str, options: list[str], *, multi: bool = False) -> list[str] | str:
    """Pause and ask the user to choose from *options*. Returns selection(s)."""
    from langgraph.types import interrupt
    from agent_md.tools.hilt import build_request

    answer = interrupt(build_request("choice", message, options=options, multi=multi))
    selected = answer.get("selected", []) if isinstance(answer, dict) else (answer or [])
    if not multi:
        return selected[0] if selected else ""
    return list(selected)


__all__ = [
    "resolve_path",
    "workspace_root",
    "agent_name",
    "agent_paths",
    "request_confirmation",
    "request_input",
    "request_choice",
]
