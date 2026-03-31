"""Shared parse/serialize helpers for .memory.md files."""

from __future__ import annotations


def parse_memory_file(content: str) -> dict[str, str]:
    """Parse a .memory.md file into sections keyed by header name.

    Each section starts with '# SECTION_NAME' and includes all content
    until the next section header or end of file.
    """
    sections: dict[str, str] = {}
    current_section = None
    current_lines: list[str] = []

    for line in content.split("\n"):
        if line.startswith("# "):
            # Save previous section
            if current_section is not None:
                sections[current_section] = "\n".join(current_lines).strip()
            current_section = line[2:].strip()
            current_lines = []
        else:
            current_lines.append(line)

    # Save last section
    if current_section is not None:
        sections[current_section] = "\n".join(current_lines).strip()

    return sections


def serialize_memory_file(sections: dict[str, str]) -> str:
    """Serialize sections dict back to .memory.md format."""
    parts = []
    for name, content in sections.items():
        parts.append(f"# {name}\n\n{content}")
    return "\n\n".join(parts) + "\n" if parts else ""
