"""Public SDK for custom tool authors.

Provides utility functions to access agent context (paths, workspace, identity)
from within custom tools without requiring factories or dependency injection.

Usage in custom tools::

    from agent_md.sdk import resolve_path, workspace_root, agent_name, agent_id

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
from typing import NamedTuple


class _ExecutionContext(NamedTuple):
    """What the SDK knows about the execution running on the current task.

    A ``NamedTuple`` rather than a bare tuple so fields can be added without
    breaking readers: ``execution_id`` arrived this way. It defaults to ``None``
    because tools and tests may set a context outside a recorded execution.
    """

    agent_config: object
    path_context: object
    execution_id: int | None = None


_current_context: contextvars.ContextVar[_ExecutionContext | None] = contextvars.ContextVar(
    "agentmd_context", default=None
)


def _set_context(agent_config, path_context, execution_id: int | None = None) -> contextvars.Token:
    """Set the agent context for the current async task. Returns a reset token.

    Always pair with :func:`_reset_context` on the token in a ``finally``: the
    token is what keeps one execution's context from leaking into whatever runs
    next on the same task.
    """
    return _current_context.set(_ExecutionContext(agent_config, path_context, execution_id))


def _reset_context(token: contextvars.Token) -> None:
    """Reset the agent context using the token from _set_context."""
    _current_context.reset(token)


def _current_execution() -> _ExecutionContext | None:
    """Return the current context, or None outside an execution.

    The non-raising counterpart of :func:`_get_context`, for internal callers
    that must stay silent when no execution is on the task — the self-write
    ledger records nothing for a write that belongs to no agent.
    """
    return _current_context.get()


def _get_context() -> _ExecutionContext:
    """Return the current execution context or raise if not in an execution."""
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
    ctx = _get_context()
    return ctx.path_context.validate_path(path, ctx.agent_config)


def workspace_root() -> Path:
    """Return the absolute path to the workspace root directory."""
    return _get_context().path_context.workspace_root


def agent_id() -> str:
    """Return the canonical id (filename stem) of the currently executing agent."""
    return _get_context().agent_config.id


def agent_name() -> str:
    """Return the display name of the currently executing agent."""
    return _get_context().agent_config.name


def execution_id() -> int | None:
    """Return the id of the execution currently running on this task.

    ``None`` only when the context was set without one (custom tool tests, and
    code paths that build a context before an execution row exists).
    """
    return _get_context().execution_id


def agent_paths() -> dict[str, Path]:
    """Return the agent's declared path aliases, resolved to absolute paths.

    Returns an empty dict if the agent declares no paths.

    Example::

        {"output": Path("/abs/path/to/output"), "data": Path("/abs/path/to/data")}
    """
    ctx = _get_context()
    result = {}
    for alias, entry in ctx.agent_config.paths.items():
        result[alias] = ctx.path_context._resolve_relative(entry.path)
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
    "agent_id",
    "agent_name",
    "agent_paths",
    "execution_id",
    "request_confirmation",
    "request_input",
    "request_choice",
]
