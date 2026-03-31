"""Tool: file_list — List directory contents with path security."""

from __future__ import annotations

from langchain_core.tools import tool


def create_file_list_tool(agent_config, path_context):
    """Create a file_list tool bound to an agent's path context.

    Relative paths are resolved from the workspace root.
    Access is restricted to the agent's configured paths.
    """

    @tool
    def file_list(path: str) -> str:
        """List files and directories at the given path.

        Args:
            path: Absolute path to the directory (preferred), or a relative path
                  which resolves from the workspace root.

        Returns:
            A formatted listing of directory contents, or an error message.
        """
        resolved, error = path_context.validate_path(path, agent_config)
        if error:
            return f"ERROR: {error}"

        if not resolved.exists():
            return f"ERROR: Directory not found: {path}"
        if not resolved.is_dir():
            return f"ERROR: Path is not a directory: {path}"

        try:
            entries = sorted(resolved.iterdir(), key=lambda e: (not e.is_dir(), e.name))
            if not entries:
                return f"Directory is empty: {path}"

            lines = []
            for entry in entries:
                if entry.is_dir():
                    lines.append(f"[DIR]  {entry.name}/")
                else:
                    size = entry.stat().st_size
                    if size < 1024:
                        size_str = f"{size} B"
                    elif size < 1024 * 1024:
                        size_str = f"{size / 1024:.1f} KB"
                    else:
                        size_str = f"{size / (1024 * 1024):.1f} MB"
                    lines.append(f"[FILE] {entry.name} ({size_str})")

            return "\n".join(lines)
        except Exception as e:
            return f"ERROR listing directory: {e}"

    return file_list
