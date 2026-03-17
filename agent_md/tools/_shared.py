"""Shared utilities for file tools."""

from pathlib import Path


def validate_and_handle_errors(
    path: str,
    agent_config,
    path_context,
    resolve_from: str = "workspace",
) -> tuple[Path | None, str | None]:
    """Common validation logic for all file tools.

    Args:
        path: Path string to validate
        agent_config: Agent configuration
        path_context: Path context for validation
        resolve_from: Resolution strategy ("workspace" or "write")

    Returns:
        (resolved_path, None) on success or (None, error_message) on failure
    """
    resolved, error = path_context.validate_path(path, agent_config, resolve_from=resolve_from)
    if error:
        return None, f"ERROR: {error}"
    return resolved, None
