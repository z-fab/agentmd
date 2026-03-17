"""Tool: file_read — Read files from the local filesystem with path security."""

from __future__ import annotations

from langchain_core.tools import tool

from agent_md.tools._shared import validate_and_handle_errors


def create_file_read_tool(agent_config, path_context):
    """Create a file_read tool bound to an agent's path context.

    Relative paths are resolved from the workspace root.
    Access is restricted to the agent's configured paths.
    """

    @tool
    def file_read(path: str) -> str:
        """Read the contents of a file.

        Args:
            path: Absolute path to the file (preferred), or a relative path
                  which resolves from the workspace root.

        Returns:
            The file contents as a string, or an error message.
        """
        resolved, error = validate_and_handle_errors(path, agent_config, path_context, resolve_from="workspace")
        if error:
            return error

        if not resolved.exists():
            return f"ERROR: File not found: {path}"
        if not resolved.is_file():
            return f"ERROR: Path is not a file: {path}"

        try:
            return resolved.read_text(encoding="utf-8")
        except Exception as e:
            return f"ERROR: {e}"

    return file_read
