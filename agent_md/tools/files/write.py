"""Tool: file_write — Write content to files with path security."""

from __future__ import annotations

from langchain_core.tools import tool


def create_file_write_tool(agent_config, path_context):
    """Create a file_write tool bound to an agent's path context."""

    @tool
    def file_write(path: str, content: str) -> str:
        """Write content to a file. Creates parent directories if needed.
        Always read the file first with file_read before overwriting an existing file.

        Args:
            path: Absolute path or relative path (resolves from workspace root).
            content: Text content to write.

        Returns:
            Confirmation message or error.
        """
        resolved, error = path_context.validate_path(path, agent_config)
        if error:
            return f"ERROR: {error}"

        if "\x00" in content:
            return "ERROR: Content contains null bytes. file_write only supports text content."

        existed = resolved.exists()

        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
            char_count = len(content)
            line_count = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
            action = "Updated" if existed else "Created"
            return f"{action} {resolved} ({char_count} chars, {line_count} lines)"
        except Exception as e:
            return f"ERROR writing file: {e}"

    return file_write
