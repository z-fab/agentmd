"""Tool: file_write — Write content to files."""

from pathlib import Path

from langchain_core.tools import tool


@tool
def file_write(path: str, content: str) -> str:
    """Write content to a file. Creates parent directories if needed.

    Args:
        path: Path where the file will be written.
        content: Text content to write.

    Returns:
        Confirmation message or error.
    """
    try:
        file_path = Path(path).expanduser()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return f"File written successfully: {path} ({len(content)} chars)"
    except Exception as e:
        return f"ERROR writing file: {e}"
