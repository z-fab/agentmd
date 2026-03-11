"""Tool: file_write — Write content to files with path security."""

from __future__ import annotations

from langchain_core.tools import tool


def create_file_write_tool(agent_config, path_context):
    """Create a file_write tool bound to an agent's path context.

    Relative paths are resolved from the agent's default write directory.
    Access is restricted to the agent's configured write paths.
    """

    @tool
    def file_write(path: str, content: str) -> str:
        """Write content to a file. Creates parent directories if needed.

        Args:
            path: Path where the file will be written.
                  Relative paths resolve from the default output directory.
            content: Text content to write.

        Returns:
            Confirmation message or error.
        """
        resolved, error = path_context.validate_write(path, agent_config)
        if error:
            return f"ERROR: {error}"

        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
            return f"File written successfully: {resolved} ({len(content)} chars)"
        except Exception as e:
            return f"ERROR writing file: {e}"

    return file_write
