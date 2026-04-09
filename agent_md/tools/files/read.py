"""Tool: file_read — Read files with optional range reads and binary detection."""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

MAX_LINES = 500


def _is_binary(path: Path) -> bool:
    """Check if a file is binary by looking for null bytes in the first 8KB."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
        return b"\x00" in chunk
    except OSError:
        return False


def _count_lines(path: Path) -> int:
    """Count total lines in a file efficiently."""
    count = 0
    with open(path, "rb") as f:
        for _ in f:
            count += 1
    return count


def _read_line_range(path: Path, offset: int, limit: int) -> list[str]:
    """Read a range of lines lazily. offset is 1-based."""
    lines = []
    start = offset - 1  # convert to 0-based
    end = start + limit
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= end:
                break
            if i >= start:
                lines.append(line.rstrip("\r\n"))
    return lines


def create_file_read_tool(agent_config, path_context):
    """Create a file_read tool bound to an agent's path context."""

    @tool
    def file_read(
        path: str,
        offset: int | None = None,
        limit: int | None = None,
        with_line_numbers: bool = True,
    ) -> str:
        """Read the contents of a file, optionally a specific line range.

        Args:
            path: Absolute path to the file (preferred), or a relative path
                  which resolves from the workspace root.
            offset: Start line (1-based). If omitted, reads from the beginning.
            limit: Number of lines to return. If omitted, reads to the end.
            with_line_numbers: Prefix each line with its line number (default True).

        Returns:
            The file contents as a string, or an error message.
        """
        resolved, error = path_context.validate_path(path, agent_config)
        if error:
            return f"ERROR: {error}"

        if not resolved.exists():
            return f"ERROR: File not found: {path}"
        if not resolved.is_file():
            return f"ERROR: Path is not a file: {path}"

        if _is_binary(resolved):
            return f"ERROR: Cannot read binary file: {path}"

        try:
            total_lines = _count_lines(resolved)

            # Full-file read
            if offset is None and limit is None:
                if total_lines > MAX_LINES:
                    return (
                        f"ERROR: File has {total_lines} lines (max {MAX_LINES} for full read). "
                        f'Use offset and limit to read a specific range, e.g. file_read("{path}", offset=1, limit={MAX_LINES}).'
                    )
                lines = _read_line_range(resolved, 1, total_lines)
                start_line = 1
                end_line = total_lines
            else:
                start_line = offset if offset is not None else 1
                read_limit = limit if limit is not None else max(total_lines - start_line + 1, 0)

                if start_line < 1:
                    return "ERROR: offset must be >= 1"
                if read_limit < 0:
                    return "ERROR: limit must be >= 0"

                lines = _read_line_range(resolved, start_line, read_limit)
                end_line = start_line + len(lines) - 1 if lines else start_line

            # Format output
            header = f"{resolved} (lines {start_line}-{end_line} of {total_lines})"

            if with_line_numbers:
                numbered = [f"{start_line + i} | {line}" for i, line in enumerate(lines)]
                body = "\n".join(numbered)
            else:
                body = "\n".join(lines)

            tail = ""
            if end_line < total_lines:
                next_offset = end_line + 1
                remaining = total_lines - end_line
                tail = (
                    f"\n\nNOTE: file has {total_lines} lines, showed {start_line}-{end_line}. "
                    f"{remaining} more lines remain. "
                    f'Call file_read again with offset={next_offset}, limit={MAX_LINES} to continue.'
                )
            return f"{header}\n{body}{tail}"

        except Exception as e:
            return f"ERROR reading file: {e}"

    return file_read
