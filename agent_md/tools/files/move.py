"""Tool: file_move — Move/rename files with path security."""

from __future__ import annotations

import shutil

from langchain_core.tools import tool


def create_file_move_tool(agent_config, path_context):
    """Create a file_move tool bound to an agent's path context."""

    @tool
    def file_move(source: str, destination: str) -> str:
        """Move or rename a file. Both source and destination must be within allowed paths.

        Args:
            source: Path to the file to move.
            destination: Path to move the file to.

        Returns:
            Confirmation message or error.
        """
        resolved_src, error = path_context.validate_path(source, agent_config)
        if error:
            return f"ERROR: source — {error}"

        resolved_dst, error = path_context.validate_path(destination, agent_config)
        if error:
            return f"ERROR: destination — {error}"

        if not resolved_src.exists():
            return f"ERROR: Source does not exist: {resolved_src}"

        if not resolved_src.is_file():
            return f"ERROR: Source is not a file: {resolved_src}"

        try:
            resolved_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(resolved_src), str(resolved_dst))
            return f"Moved: {resolved_src} -> {resolved_dst}"
        except Exception as e:
            return f"ERROR moving file: {e}"

    return file_move
