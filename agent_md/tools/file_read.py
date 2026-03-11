"""Tool: file_read — Read files from the local filesystem with path security."""

from __future__ import annotations

from langchain_core.tools import tool


def create_file_read_tool(agent_config, path_context):
    """Create a file_read tool bound to an agent's path context.

    Relative paths are resolved from the workspace root.
    Access is restricted to the agent's configured read paths.
    """

    @tool
    def file_read(path: str) -> str:
        """Read the contents of a file.

        Args:
            path: Path to the file. Relative paths resolve from the workspace root.

        Returns:
            The file contents as a string, or an error message.
        """
        resolved, error = path_context.validate_read(path, agent_config)
        if error:
            return f"ERROR: {error}"

        if not resolved.exists():
            return f"ERROR: File not found: {path}"
        if not resolved.is_file():
            return f"ERROR: Path is not a file: {path}"

        try:
            return resolved.read_text(encoding="utf-8")
        except Exception as e:
            return f"ERROR reading file: {e}"

    return file_read
