"""Tool: file_delete — Delete a single file with path security."""

from __future__ import annotations

from langchain_core.tools import tool


def create_file_delete_tool(agent_config, path_context):
    """Create a file_delete tool bound to an agent's path context."""

    @tool
    def file_delete(path: str) -> str:
        """Delete a single file. The path must be within the agent's allowed paths.

        Only deletes files, never directories. Returns a "not found" message
        (not an error) if the file does not exist.

        Args:
            path: Path to the file to delete.

        Returns:
            Confirmation message or error.
        """
        resolved, error = path_context.validate_path(path, agent_config)
        if error:
            return f"ERROR: {error}"

        if not resolved.exists():
            return f"File not found: {resolved}"

        if not resolved.is_file():
            return f"ERROR: Not a file (refusing to delete directory): {resolved}"

        try:
            resolved.unlink()
            return f"Deleted: {resolved}"
        except Exception as e:
            return f"ERROR deleting file: {e}"

    return file_delete
