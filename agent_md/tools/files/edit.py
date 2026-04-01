"""Tool: file_edit — Targeted in-place text replacement."""

from __future__ import annotations

from langchain_core.tools import tool


def create_file_edit_tool(agent_config, path_context):
    """Create a file_edit tool bound to an agent's path context."""

    @tool
    def file_edit(
        path: str,
        old_text: str,
        new_text: str,
        replace_all: bool = False,
    ) -> str:
        """Edit a file by replacing text. Always read the file first with file_read before editing.

        Args:
            path: Absolute path to the file (preferred), or a relative path
                  which resolves from the workspace root.
            old_text: The exact text to find and replace. Use empty string to create a new file.
            new_text: The replacement text.
            replace_all: If True, replace all occurrences. If False (default), fail on multiple matches.

        Returns:
            A summary of changes, or an error message.
        """
        resolved, error = path_context.validate_path(path, agent_config)
        if error:
            return f"ERROR: {error}"

        # Create new file mode
        if old_text == "":
            if resolved.exists():
                return f"ERROR: File already exists: {path}. Use old_text to specify text to replace."

            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(new_text, encoding="utf-8")
            line_count = new_text.count("\n") + (1 if new_text and not new_text.endswith("\n") else 0)
            return f"Created {resolved} ({line_count} lines)"

        # Edit existing file mode
        if not resolved.exists():
            return f"ERROR: File not found: {path}"
        if not resolved.is_file():
            return f"ERROR: Path is not a file: {path}"

        try:
            content = resolved.read_text(encoding="utf-8")
        except Exception as e:
            return f"ERROR reading file: {e}"

        count = content.count(old_text)

        if count == 0:
            return f"ERROR: Text not found in {path}. Make sure old_text matches exactly (including whitespace and indentation)."

        if count > 1 and not replace_all:
            return (
                f"ERROR: Found {count} matches in {path}. "
                f"Provide more context in old_text to make it unique, or set replace_all=True."
            )

        new_content = content.replace(old_text, new_text) if replace_all else content.replace(old_text, new_text, 1)

        resolved.write_text(new_content, encoding="utf-8")

        old_lines = old_text.count("\n")
        new_lines = new_text.count("\n")
        lines_changed = abs(new_lines - old_lines) + 1
        replaced = count if replace_all else 1

        return (
            f"Updated {resolved} ({replaced} replacement{'s' if replaced > 1 else ''}, ~{lines_changed} lines changed)"
        )

    return file_edit
