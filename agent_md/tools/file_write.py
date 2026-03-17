"""Tool: file_write — Write content to files with path security."""

from __future__ import annotations

from langchain_core.tools import tool

from agent_md.tools._shared import validate_and_handle_errors


def create_file_write_tool(agent_config, path_context):
    """Create a file_write tool bound to an agent's path context.

    Relative paths resolve from the first directory in allowed paths.
    Access is restricted to the agent's configured paths.
    """

    @tool
    def file_write(path: str, content: str) -> str:
        """Write content to a file. Creates parent directories if needed.

        Args:
            path: Absolute path or relative path.
                  Absolute paths are used as-is (must be within allowed paths).
                  Relative paths resolve from the first directory in allowed paths (or workspace if no paths defined).
            content: Text content to write.

        Returns:
            Confirmation message or error.
        """
        resolved, error = validate_and_handle_errors(path, agent_config, path_context, resolve_from="write")
        if error:
            return error

        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
            return f"File written successfully: {resolved} ({len(content)} chars)"
        except Exception as e:
            return f"ERROR: {e}"

    return file_write

