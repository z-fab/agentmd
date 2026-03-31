"""Tool: file_write — Write content to files with path security."""

from __future__ import annotations

from langchain_core.tools import tool


def create_file_write_tool(agent_config, path_context):
    """Create a file_write tool bound to an agent's path context.

    Relative paths are resolved from the workspace root.
    Access is restricted to the agent's configured paths.
    """

    @tool
    def file_write(path: str, content: str) -> str:
        """Write content to a file. Creates parent directories if needed.

        Args:
            path: Absolute path or relative path. Absolute paths are used as-is.
                  Relative paths resolve from the workspace root.
            content: Text content to write.

        Returns:
            Confirmation message or error.
        """
        resolved, error = path_context.validate_path(path, agent_config)
        if error:
            return f"ERROR: {error}"

        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
            return f"File written successfully: {resolved} ({len(content)} chars)"
        except Exception as e:
            return f"ERROR writing file: {e}"

    return file_write
