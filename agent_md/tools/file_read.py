"""Tool: file_read — Read files from the local filesystem."""

from pathlib import Path

from langchain_core.tools import tool


@tool
def file_read(path: str) -> str:
    """Read the contents of a file from the local filesystem.

    Args:
        path: Absolute or relative path to the file.

    Returns:
        The file contents as a string, or an error message.
    """
    file_path = Path(path).expanduser()
    if not file_path.exists():
        return f"ERROR: File not found: {path}"
    if not file_path.is_file():
        return f"ERROR: Path is not a file: {path}"
    try:
        return file_path.read_text(encoding="utf-8")
    except Exception as e:
        return f"ERROR reading file: {e}"
