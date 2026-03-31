# File Tools Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize `agent_md/tools/` into domain-based subpackages, improve file_read with range reads, add file_edit and file_glob, simplify path resolution, and update docs.

**Architecture:** Each tool domain (files, memory, skills, http) becomes a subpackage with one module per tool and an `__init__.py` exporting factories. PathContext is simplified to always resolve from workspace root. The registry imports only from subpackage `__init__` files.

**Tech Stack:** Python 3.13+, LangChain tools (`@tool` decorator), Pydantic, pathlib

---

### Task 1: Simplify PathContext — remove output_dir resolution

Remove the `resolve_from` parameter and output-specific logic from `PathContext`. All paths resolve from workspace root.

**Files:**
- Modify: `agent_md/core/path_context.py`
- Modify: `agent_md/tools/file_write.py` (update `resolve_from="output"` call)
- Modify: `agent_md/core/bootstrap.py` (check if `output_dir` is passed to PathContext)
- Modify: `agent_md/graph/builder.py` (remove `get_default_output_dir` call in prompt)

- [ ] **Step 1: Read bootstrap.py to understand PathContext construction**

Run: `cat agent_md/core/bootstrap.py`

Check how `output_dir` is passed to `PathContext` — we need to know what to remove.

- [ ] **Step 2: Simplify PathContext**

Edit `agent_md/core/path_context.py`:

```python
"""Centralizes path resolution and security validation for agent file access."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class PathContext:
    """Centralizes path resolution and security validation for agent file access."""

    workspace_root: Path
    agents_dir: Path
    db_path: Path
    mcp_config: Path
    tools_dir: Path
    skills_dir: Path

    def get_allowed_paths(self, config) -> list[Path]:
        """Return resolved paths the agent can read from and write to.

        Defaults to [workspace_root] if the agent has no 'paths' config.
        Watch paths are automatically included so agents can access watched files.
        """
        paths = [self._resolve_relative(p) for p in config.paths] if config.paths else [self.workspace_root]

        # Include watch paths so agents can access files they're watching
        if config.trigger.type == "watch" and config.trigger.paths:
            watch_paths = [self._resolve_relative(p) for p in config.trigger.paths]
            paths.extend(watch_paths)

        return list(dict.fromkeys(paths))

    def get_memory_file_path(self, config) -> Path:
        """Return the path to the agent's .memory.md file."""
        return self.agents_dir / f"{config.name}.memory.md"

    def validate_path(self, path: str, config) -> tuple[Path | None, str | None]:
        """Resolve and validate a path for access.

        Relative paths resolve from workspace_root. Absolute paths are used as-is.

        Args:
            path: The path to validate (absolute or relative).
            config: AgentConfig with paths and trigger info.

        Returns:
            (resolved_path, None) on success or (None, error_message) on failure.
        """
        resolved = self._resolve_relative(path)

        # Security checks
        error = self._check_security(resolved)
        if error:
            return None, error

        # Check against allowed paths
        allowed = self.get_allowed_paths(config)
        if not self._is_within_any(resolved, allowed):
            return None, f"Access denied: '{path}' is outside allowed paths"

        return resolved, None

    # --- Private helpers ---

    def _resolve_relative(self, path: str) -> Path:
        """Resolve a path relative to workspace_root."""
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = self.workspace_root / p
        return p.resolve()

    def _check_security(self, resolved: Path) -> str | None:
        """Check security restrictions. Returns error message or None."""
        # Cannot access the agents directory
        if self._is_within(resolved, self.agents_dir):
            return "Access denied: cannot access agents directory"

        # Cannot access .env files
        if resolved.name.startswith(".env"):
            return "Access denied: cannot access .env files"

        # Cannot write .db files
        if resolved.suffix == ".db":
            return "Access denied: cannot access .db files"

        return None

    def _is_within(self, path: Path, directory: Path) -> bool:
        """Check if path is within a directory (follows symlinks)."""
        try:
            path.relative_to(directory.resolve())
            return True
        except ValueError:
            return False

    def _is_within_any(self, path: Path, directories: list[Path]) -> bool:
        """Check if path is within any of the given directories/files."""
        for d in directories:
            d_resolved = d.resolve()
            if d_resolved.is_file() or d_resolved.suffix:
                # It's a file path — exact match only
                if path == d_resolved:
                    return True
            else:
                # It's a directory — check containment
                if self._is_within(path, d_resolved):
                    return True
        return False
```

Key changes:
- Remove `output_dir` field
- Remove `get_default_output_dir` method
- Remove `_resolve_for_output` method
- Remove `resolve_from` parameter from `validate_path` — always resolves from workspace root

- [ ] **Step 3: Update bootstrap.py**

Remove `output_dir` from the `PathContext` constructor call. Find the line that passes `output_dir=...` and remove it. If `output_dir` is created as a directory elsewhere in bootstrap, that can stay or be removed depending on whether other code references it.

- [ ] **Step 4: Update file_write.py to use simplified validate_path**

Edit `agent_md/tools/file_write.py:27` — change:
```python
resolved, error = path_context.validate_path(path, agent_config, resolve_from="output")
```
to:
```python
resolved, error = path_context.validate_path(path, agent_config)
```

- [ ] **Step 5: Update file_read.py to use simplified validate_path**

Edit `agent_md/tools/file_read.py:26` — change:
```python
resolved, error = path_context.validate_path(path, agent_config, resolve_from="workspace")
```
to:
```python
resolved, error = path_context.validate_path(path, agent_config)
```

- [ ] **Step 6: Update file_list.py to use simplified validate_path**

Edit `agent_md/tools/file_list.py:26` — change:
```python
resolved, error = path_context.validate_path(path, agent_config, resolve_from="workspace")
```
to:
```python
resolved, error = path_context.validate_path(path, agent_config)
```

- [ ] **Step 7: Update builder.py — remove output_dir from file access prompt**

Edit `agent_md/graph/builder.py` function `_build_file_access_prompt`:

```python
def _build_file_access_prompt(agent_config, path_context) -> str:
    """Build the file access section of the system prompt."""
    allowed_paths = path_context.get_allowed_paths(agent_config)

    path_list = "\n".join(f"- `{p}`" for p in allowed_paths)

    sections = [
        "## File Access\n",
        "You have three file tools: `file_read`, `file_write`, and `file_list`.\n",
        "### Allowed paths\n",
        "You can ONLY access files within these paths:\n",
        f"{path_list}\n",
        "Any path outside these boundaries will be denied.\n",
        "### Path rules\n",
        "- **Always prefer absolute paths.** When you know the full path to a file, use it as-is.\n"
        "- Relative paths resolve from the workspace root.\n"
        "- Use `file_list` to discover files before reading. Never guess filenames.",
    ]

    if agent_config.trigger.type == "watch":
        sections.append(
            "\n### Watch trigger\n"
            "This agent is activated by file changes. The user message contains the event type "
            "and the **absolute path** of the changed file.\n"
            "**You MUST use that exact absolute path** with `file_read` to read the file. "
            "Do not extract just the filename — always use the full path provided."
        )

    return "\n".join(sections)
```

Remove `default_output = path_context.get_default_output_dir(agent_config)` and all references to output directory in the prompt.

- [ ] **Step 8: Search for any remaining references to output_dir or resolve_from**

Run: `rg "output_dir|resolve_from|get_default_output_dir|_resolve_for_output" agent_md/`

Fix any remaining references. The `output_dir` in settings/CLI args can remain for backwards compatibility of the CLI flag but should not flow into PathContext.

- [ ] **Step 9: Verify the project runs**

Run: `cd /Users/zfab/repos/agentmd && uv run agentmd list`

Expected: agent list displays without errors.

- [ ] **Step 10: Commit**

```bash
git add agent_md/core/path_context.py agent_md/tools/file_write.py agent_md/tools/file_read.py agent_md/tools/file_list.py agent_md/graph/builder.py agent_md/core/bootstrap.py
git commit -m "simplify path resolution: remove output_dir, always resolve from workspace root"
```

---

### Task 2: Reorganize tools into domain subpackages

Move existing tools from flat files into domain-based subpackages. No logic changes — pure restructuring.

**Files:**
- Create: `agent_md/tools/files/__init__.py`
- Create: `agent_md/tools/files/read.py` (moved from `agent_md/tools/file_read.py`)
- Create: `agent_md/tools/files/write.py` (moved from `agent_md/tools/file_write.py`)
- Create: `agent_md/tools/files/list.py` (moved from `agent_md/tools/file_list.py`)
- Create: `agent_md/tools/memory/__init__.py`
- Create: `agent_md/tools/memory/save.py`
- Create: `agent_md/tools/memory/append.py`
- Create: `agent_md/tools/memory/retrieve.py`
- Create: `agent_md/tools/skills/__init__.py`
- Create: `agent_md/tools/skills/use.py`
- Create: `agent_md/tools/skills/read_file.py`
- Create: `agent_md/tools/skills/run_script.py`
- Create: `agent_md/tools/http/__init__.py`
- Create: `agent_md/tools/http/request.py` (moved from `agent_md/tools/http_request.py`)
- Modify: `agent_md/tools/registry.py`
- Delete: `agent_md/tools/file_read.py`
- Delete: `agent_md/tools/file_write.py`
- Delete: `agent_md/tools/file_list.py`
- Delete: `agent_md/tools/memory.py`
- Delete: `agent_md/tools/http_request.py`
- Delete: `agent_md/skills/tools.py`

- [ ] **Step 1: Create files/ subpackage**

Create `agent_md/tools/files/read.py` — copy exact content from `agent_md/tools/file_read.py` (no changes).

Create `agent_md/tools/files/write.py` — copy exact content from `agent_md/tools/file_write.py` (no changes).

Create `agent_md/tools/files/list.py` — copy exact content from `agent_md/tools/file_list.py` (no changes).

Create `agent_md/tools/files/__init__.py`:
```python
"""File tools — read, write, list."""

from agent_md.tools.files.list import create_file_list_tool
from agent_md.tools.files.read import create_file_read_tool
from agent_md.tools.files.write import create_file_write_tool

__all__ = [
    "create_file_read_tool",
    "create_file_write_tool",
    "create_file_list_tool",
]
```

- [ ] **Step 2: Create memory/ subpackage**

Split `agent_md/tools/memory.py` into three files.

Create `agent_md/tools/memory/save.py`:
```python
"""Tool: memory_save — Save/replace a section in agent memory."""

from __future__ import annotations

from langchain_core.tools import tool

from agent_md.tools.memory._parser import parse_memory_file, serialize_memory_file


def create_memory_save_tool(agent_config, path_context):
    """Create a memory_save tool that replaces a section in the agent's memory file."""

    @tool
    def memory_save(section: str, content: str) -> str:
        """Save content to a named section in long-term memory, replacing any existing content.

        Use this to store important information that should persist across sessions.
        Also use this to rewrite/summarize a section when it gets too long.

        Args:
            section: Name of the memory section (e.g., 'user_preferences', 'project_context').
            content: The content to save in this section.

        Returns:
            Confirmation message.
        """
        memory_path = path_context.get_memory_file_path(agent_config)

        sections = parse_memory_file(memory_path.read_text(encoding="utf-8")) if memory_path.exists() else {}

        sections[section] = content

        memory_path.write_text(serialize_memory_file(sections), encoding="utf-8")
        return f"Memory section '{section}' saved ({len(content)} chars)."

    return memory_save
```

Create `agent_md/tools/memory/append.py`:
```python
"""Tool: memory_append — Append to a section in agent memory."""

from __future__ import annotations

from langchain_core.tools import tool

from agent_md.tools.memory._parser import parse_memory_file, serialize_memory_file

MEMORY_SECTION_WARN_THRESHOLD = 50


def create_memory_append_tool(agent_config, path_context):
    """Create a memory_append tool that appends to a section in the agent's memory file."""

    @tool
    def memory_append(section: str, content: str) -> str:
        """Append content to a named section in long-term memory.

        Use this to incrementally add information to an existing section.

        Args:
            section: Name of the memory section.
            content: The content to append.

        Returns:
            Confirmation message, with a hint to summarize if the section is getting long.
        """
        memory_path = path_context.get_memory_file_path(agent_config)

        sections = parse_memory_file(memory_path.read_text(encoding="utf-8")) if memory_path.exists() else {}

        if section in sections:
            sections[section] = sections[section] + "\n" + content
        else:
            sections[section] = content

        memory_path.write_text(serialize_memory_file(sections), encoding="utf-8")

        line_count = len(sections[section].split("\n"))
        hint = ""
        if line_count > MEMORY_SECTION_WARN_THRESHOLD:
            hint = (
                f" Note: section '{section}' has {line_count} lines. "
                "Consider using memory_save to summarize and replace it."
            )

        return f"Appended to memory section '{section}' ({line_count} lines total).{hint}"

    return memory_append
```

Create `agent_md/tools/memory/retrieve.py`:
```python
"""Tool: memory_retrieve — Read a section from agent memory."""

from __future__ import annotations

from langchain_core.tools import tool

from agent_md.tools.memory._parser import parse_memory_file


def create_memory_retrieve_tool(agent_config, path_context):
    """Create a memory_retrieve tool that reads a section from the agent's memory file."""

    @tool
    def memory_retrieve(section: str) -> str:
        """Retrieve the content of a named section from long-term memory.

        Args:
            section: Name of the memory section to retrieve.

        Returns:
            The section content, or a message if not found.
        """
        memory_path = path_context.get_memory_file_path(agent_config)

        if not memory_path.exists():
            return "No memory file found. Use memory_save to create one."

        sections = parse_memory_file(memory_path.read_text(encoding="utf-8"))

        if section not in sections:
            available = list(sections.keys())
            if available:
                return f"Section '{section}' not found. Available sections: {', '.join(available)}"
            return f"Section '{section}' not found. Memory file is empty."

        return sections[section]

    return memory_retrieve
```

Create `agent_md/tools/memory/_parser.py` — extract the shared parsing logic:
```python
"""Memory file parser — shared by memory tools."""

from __future__ import annotations


def parse_memory_file(content: str) -> dict[str, str]:
    """Parse a .memory.md file into sections keyed by header name."""
    sections: dict[str, str] = {}
    current_section = None
    current_lines: list[str] = []

    for line in content.split("\n"):
        if line.startswith("# "):
            if current_section is not None:
                sections[current_section] = "\n".join(current_lines).strip()
            current_section = line[2:].strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_section is not None:
        sections[current_section] = "\n".join(current_lines).strip()

    return sections


def serialize_memory_file(sections: dict[str, str]) -> str:
    """Serialize sections dict back to .memory.md format."""
    parts = []
    for name, content in sections.items():
        parts.append(f"# {name}\n\n{content}")
    return "\n\n".join(parts) + "\n" if parts else ""
```

Create `agent_md/tools/memory/__init__.py`:
```python
"""Memory tools — save, append, retrieve."""

from agent_md.tools.memory.append import create_memory_append_tool
from agent_md.tools.memory.retrieve import create_memory_retrieve_tool
from agent_md.tools.memory.save import create_memory_save_tool

__all__ = [
    "create_memory_save_tool",
    "create_memory_append_tool",
    "create_memory_retrieve_tool",
]
```

- [ ] **Step 3: Create skills/ subpackage**

Move `agent_md/skills/tools.py` content into `agent_md/tools/skills/`.

Create `agent_md/tools/skills/_validation.py` — extract the shared validation helpers:
```python
"""Shared validation for skill tools."""

from __future__ import annotations

from pathlib import Path


def validate_skill_access(skill_name: str, agent_config, skills_dir: Path) -> tuple[Path | None, str | None]:
    """Validate that the agent has access to a skill and it exists.

    Returns:
        (skill_path, None) on success, or (None, error_message) on failure.
    """
    if skill_name not in agent_config.skills:
        available = ", ".join(agent_config.skills) if agent_config.skills else "none"
        return None, f"Skill '{skill_name}' is not enabled for this agent. Available: {available}"

    skill_path = skills_dir / skill_name / "SKILL.md"
    if not skill_path.exists():
        return None, f"Skill '{skill_name}' not found at {skill_path}"

    return skill_path, None


def is_within(path: Path, directory: Path) -> bool:
    """Check if a resolved path is within a directory (safe against traversal)."""
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False
```

Create `agent_md/tools/skills/use.py`:
```python
"""Tool: skill_use — Load skill instructions on-demand."""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

from agent_md.skills.loader import apply_substitutions
from agent_md.skills.parser import parse_skill_full
from agent_md.tools.skills._validation import validate_skill_access


def create_skill_use_tool(agent_config, skills_dir: Path):
    """Create skill_use tool for loading skill instructions on-demand."""

    @tool
    def skill_use(skill_name: str, arguments: str = "") -> str:
        """Load a skill's instructions with variable substitutions applied.

        Use this to activate a skill and receive its detailed instructions.
        The system prompt lists available skills — call this tool to load one.

        Args:
            skill_name: Name of the skill to use.
            arguments: Optional arguments to pass to the skill (replaces $ARGUMENTS).

        Returns:
            The skill's processed instructions ready to follow.
        """
        skill_path, error = validate_skill_access(skill_name, agent_config, skills_dir)
        if error:
            return error

        try:
            definition = parse_skill_full(skill_path)
        except (OSError, ValueError) as e:
            return f"Error loading skill '{skill_name}': {e}"

        processed = apply_substitutions(
            definition.instructions,
            arguments=arguments,
            skill_dir=definition.skill_dir,
        )

        parts = [f"# Skill: {definition.name}"]
        if definition.description:
            parts.append(f"\n{definition.description}\n")
        parts.append(f"\n{processed}")

        if definition.has_scripts:
            scripts_path = Path(definition.skill_dir) / "scripts"
            scripts = [f.name for f in scripts_path.iterdir() if f.is_file()]
            if scripts:
                parts.append(f"\n\nAvailable scripts: {', '.join(scripts)}")
                parts.append("Use skill_run_script to execute them.")

        if definition.has_references:
            refs_path = Path(definition.skill_dir) / "references"
            refs = [f.name for f in refs_path.iterdir() if f.is_file()]
            if refs:
                parts.append(f"\n\nAvailable references: {', '.join(refs)}")
                parts.append("Use skill_read_file to read them.")

        return "\n".join(parts)

    return skill_use
```

Create `agent_md/tools/skills/read_file.py`:
```python
"""Tool: skill_read_file — Read supporting files from a skill."""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

from agent_md.tools.skills._validation import is_within, validate_skill_access


def create_skill_read_file_tool(agent_config, skills_dir: Path):
    """Create skill_read_file tool for reading supporting files from a skill."""

    @tool
    def skill_read_file(skill_name: str, file_path: str) -> str:
        """Read a file from a skill's directory (references, scripts, etc.).

        Args:
            skill_name: Name of the skill.
            file_path: Relative path within the skill directory (e.g., 'references/api-docs.md').

        Returns:
            File contents or error message.
        """
        _, error = validate_skill_access(skill_name, agent_config, skills_dir)
        if error:
            return error

        skill_dir = (skills_dir / skill_name).resolve()
        target = (skill_dir / file_path).resolve()

        if not is_within(target, skill_dir):
            return f"Access denied: '{file_path}' is outside skill directory"

        if not target.exists():
            return f"File not found: '{file_path}' in skill '{skill_name}'"

        if not target.is_file():
            return f"Not a file: '{file_path}'"

        try:
            return target.read_text(encoding="utf-8")
        except OSError as e:
            return f"Error reading file: {e}"

    return skill_read_file
```

Create `agent_md/tools/skills/run_script.py`:
```python
"""Tool: skill_run_script — Execute scripts from a skill."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from langchain_core.tools import tool

from agent_md.tools.skills._validation import is_within, validate_skill_access


def create_skill_run_script_tool(agent_config, skills_dir: Path):
    """Create skill_run_script tool for executing scripts from a skill."""

    @tool
    def skill_run_script(skill_name: str, script_name: str, script_args: str = "") -> str:
        """Execute a script from a skill's scripts/ directory.

        Args:
            skill_name: Name of the skill.
            script_name: Script filename (must be in the skill's scripts/ directory).
            script_args: Optional arguments to pass to the script.

        Returns:
            Script output (stdout + stderr) or error message.
        """
        _, error = validate_skill_access(skill_name, agent_config, skills_dir)
        if error:
            return error

        skill_dir = (skills_dir / skill_name).resolve()
        scripts_dir = skill_dir / "scripts"

        if not scripts_dir.is_dir():
            return f"Skill '{skill_name}' has no scripts/ directory"

        script_path = (scripts_dir / script_name).resolve()

        if not is_within(script_path, scripts_dir):
            return f"Access denied: '{script_name}' is outside scripts/ directory"

        if not script_path.exists():
            available = [f.name for f in scripts_dir.iterdir() if f.is_file()]
            return f"Script not found: '{script_name}'. Available: {', '.join(available) or 'none'}"

        if not script_path.is_file():
            return f"Not a file: '{script_name}'"

        ext = script_path.suffix.lower()
        if ext == ".py":
            cmd = ["python", str(script_path)]
        elif ext in (".sh", ".bash"):
            cmd = ["bash", str(script_path)]
        elif ext == ".js":
            cmd = ["node", str(script_path)]
        else:
            cmd = [str(script_path)]

        if script_args:
            cmd.extend(shlex.split(script_args))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(skill_dir),
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"
            if result.returncode != 0:
                output += f"\n[exit code: {result.returncode}]"
            return output.strip() or "[no output]"
        except subprocess.TimeoutExpired:
            return f"Script timed out after 30s: {script_name}"
        except FileNotFoundError:
            return f"Cannot execute '{script_name}': interpreter not found or file not executable"
        except OSError as e:
            return f"Error running script: {e}"

    return skill_run_script
```

Create `agent_md/tools/skills/__init__.py`:
```python
"""Skill tools — use, read_file, run_script."""

from agent_md.tools.skills.read_file import create_skill_read_file_tool
from agent_md.tools.skills.run_script import create_skill_run_script_tool
from agent_md.tools.skills.use import create_skill_use_tool

__all__ = [
    "create_skill_use_tool",
    "create_skill_read_file_tool",
    "create_skill_run_script_tool",
]
```

- [ ] **Step 4: Create http/ subpackage**

Create `agent_md/tools/http/request.py` — copy exact content from `agent_md/tools/http_request.py`.

Create `agent_md/tools/http/__init__.py`:
```python
"""HTTP tools — request."""

from agent_md.tools.http.request import http_request

__all__ = ["http_request"]
```

- [ ] **Step 5: Update registry.py**

Replace `agent_md/tools/registry.py`:
```python
"""Tool registry — built-in tools that are always available to every agent."""

from __future__ import annotations

from agent_md.tools.http import http_request

# Static tools (no agent context needed)
_STATIC_TOOLS = [http_request]


def resolve_builtin_tools(agent_config=None, path_context=None) -> list:
    """Return all built-in tools, ready to use.

    Context-aware tools (file_*, memory_*, skill_*) are created dynamically
    with the agent's path context. Static tools are included as-is.

    Args:
        agent_config: AgentConfig for context-aware tools.
        path_context: PathContext for context-aware tools.

    Returns:
        List of all built-in LangChain tool objects.
    """
    from agent_md.tools.files import (
        create_file_list_tool,
        create_file_read_tool,
        create_file_write_tool,
    )
    from agent_md.tools.memory import (
        create_memory_append_tool,
        create_memory_retrieve_tool,
        create_memory_save_tool,
    )

    tools = list(_STATIC_TOOLS)

    if agent_config is not None and path_context is not None:
        tools.append(create_file_read_tool(agent_config, path_context))
        tools.append(create_file_write_tool(agent_config, path_context))
        tools.append(create_file_list_tool(agent_config, path_context))
        tools.append(create_memory_save_tool(agent_config, path_context))
        tools.append(create_memory_append_tool(agent_config, path_context))
        tools.append(create_memory_retrieve_tool(agent_config, path_context))

        # Skill tools — only when the agent has skills configured
        if agent_config.skills and path_context.skills_dir.exists():
            from agent_md.tools.skills import (
                create_skill_read_file_tool,
                create_skill_run_script_tool,
                create_skill_use_tool,
            )

            tools.append(create_skill_use_tool(agent_config, path_context.skills_dir))
            tools.append(create_skill_read_file_tool(agent_config, path_context.skills_dir))
            tools.append(create_skill_run_script_tool(agent_config, path_context.skills_dir))

    return tools


def list_builtin_tools() -> list[str]:
    """Return names of all built-in tools."""
    return sorted(
        [t.name for t in _STATIC_TOOLS]
        + [
            "file_read", "file_write", "file_list",
            "memory_save", "memory_append", "memory_retrieve",
            "skill_use", "skill_read_file", "skill_run_script",
        ]
    )
```

- [ ] **Step 6: Delete old flat files**

```bash
rm agent_md/tools/file_read.py
rm agent_md/tools/file_write.py
rm agent_md/tools/file_list.py
rm agent_md/tools/memory.py
rm agent_md/tools/http_request.py
rm agent_md/skills/tools.py
```

- [ ] **Step 7: Check for any imports of the old paths**

Run: `rg "from agent_md\.tools\.(file_read|file_write|file_list|memory|http_request)" agent_md/`
Run: `rg "from agent_md\.skills\.tools" agent_md/`

Fix any remaining imports to point to the new locations.

- [ ] **Step 8: Verify the project runs**

Run: `cd /Users/zfab/repos/agentmd && uv run agentmd list`

Expected: agent list displays without errors.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "reorganize tools into domain-based subpackages

Move file, memory, skill, and http tools into subpackages under
agent_md/tools/. Each domain has its own __init__.py exporting
factory functions. Registry imports only from subpackage init files."
```

---

### Task 3: Improve file_read with range reads, binary detection, and line cap

Rewrite `agent_md/tools/files/read.py` with the new features.

**Files:**
- Modify: `agent_md/tools/files/read.py`

- [ ] **Step 1: Implement the improved file_read**

Replace `agent_md/tools/files/read.py`:

```python
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
                        f"Use offset and limit to read a specific range, e.g. file_read(\"{path}\", offset=1, limit={MAX_LINES})."
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

            return f"{header}\n{body}"

        except Exception as e:
            return f"ERROR reading file: {e}"

    return file_read
```

- [ ] **Step 2: Verify the project runs**

Run: `cd /Users/zfab/repos/agentmd && uv run agentmd list`

Expected: no import errors.

- [ ] **Step 3: Commit**

```bash
git add agent_md/tools/files/read.py
git commit -m "improve file_read: range reads, binary detection, 500-line cap"
```

---

### Task 4: Add file_edit tool

Create the new `file_edit` tool for targeted in-place replacements.

**Files:**
- Create: `agent_md/tools/files/edit.py`
- Modify: `agent_md/tools/files/__init__.py`
- Modify: `agent_md/tools/registry.py`

- [ ] **Step 1: Create file_edit tool**

Create `agent_md/tools/files/edit.py`:

```python
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

        return f"Updated {resolved} ({replaced} replacement{'s' if replaced > 1 else ''}, ~{lines_changed} lines changed)"

    return file_edit
```

- [ ] **Step 2: Update files/__init__.py**

Add `file_edit` to exports:

```python
"""File tools — read, write, edit, list."""

from agent_md.tools.files.edit import create_file_edit_tool
from agent_md.tools.files.list import create_file_list_tool
from agent_md.tools.files.read import create_file_read_tool
from agent_md.tools.files.write import create_file_write_tool

__all__ = [
    "create_file_read_tool",
    "create_file_write_tool",
    "create_file_edit_tool",
    "create_file_list_tool",
]
```

- [ ] **Step 3: Register file_edit in registry.py**

Add after the `create_file_write_tool` line in `resolve_builtin_tools`:

```python
from agent_md.tools.files import (
    create_file_edit_tool,
    create_file_list_tool,
    create_file_read_tool,
    create_file_write_tool,
)
```

And add to the tools list:
```python
tools.append(create_file_edit_tool(agent_config, path_context))
```

Add `"file_edit"` to `list_builtin_tools`.

- [ ] **Step 4: Verify the project runs**

Run: `cd /Users/zfab/repos/agentmd && uv run agentmd list`

- [ ] **Step 5: Commit**

```bash
git add agent_md/tools/files/edit.py agent_md/tools/files/__init__.py agent_md/tools/registry.py
git commit -m "add file_edit tool for targeted in-place text replacement"
```

---

### Task 5: Add file_glob tool and remove file_list

Create `file_glob` and remove `file_list` from the codebase.

**Files:**
- Create: `agent_md/tools/files/glob.py`
- Modify: `agent_md/tools/files/__init__.py`
- Modify: `agent_md/tools/registry.py`
- Delete: `agent_md/tools/files/list.py`

- [ ] **Step 1: Create file_glob tool**

Create `agent_md/tools/files/glob.py`:

```python
"""Tool: file_glob — Find files matching a glob pattern."""

from __future__ import annotations

from langchain_core.tools import tool

MAX_RESULTS = 100


def create_file_glob_tool(agent_config, path_context):
    """Create a file_glob tool bound to an agent's path context."""

    @tool
    def file_glob(pattern: str) -> str:
        """Find files matching a glob pattern from the workspace root.

        Args:
            pattern: Glob pattern (e.g., '**/*.py', 'src/**/*.md', '*.json').

        Returns:
            Matching file paths (one per line), or an error message.
        """
        workspace = path_context.workspace_root
        allowed = path_context.get_allowed_paths(agent_config)

        try:
            all_matches = sorted(workspace.glob(pattern))
        except Exception as e:
            return f"ERROR: Invalid glob pattern: {e}"

        # Filter to only files (not directories) within allowed paths
        matches = []
        for match in all_matches:
            if not match.is_file():
                continue
            resolved = match.resolve()
            if path_context._is_within_any(resolved, allowed):
                matches.append(resolved)

        if not matches:
            return f"No files found matching '{pattern}'"

        total = len(matches)
        capped = matches[:MAX_RESULTS]
        lines = [str(p) for p in capped]

        if total > MAX_RESULTS:
            lines.append(f"\n(showing {MAX_RESULTS} of {total} results, refine your pattern)")

        return "\n".join(lines)

    return file_glob
```

- [ ] **Step 2: Update files/__init__.py — replace file_list with file_glob**

```python
"""File tools — read, write, edit, glob."""

from agent_md.tools.files.edit import create_file_edit_tool
from agent_md.tools.files.glob import create_file_glob_tool
from agent_md.tools.files.read import create_file_read_tool
from agent_md.tools.files.write import create_file_write_tool

__all__ = [
    "create_file_read_tool",
    "create_file_write_tool",
    "create_file_edit_tool",
    "create_file_glob_tool",
]
```

- [ ] **Step 3: Update registry.py — replace file_list with file_glob**

Update imports:
```python
from agent_md.tools.files import (
    create_file_edit_tool,
    create_file_glob_tool,
    create_file_read_tool,
    create_file_write_tool,
)
```

Replace `create_file_list_tool(agent_config, path_context)` with `create_file_glob_tool(agent_config, path_context)`.

In `list_builtin_tools`, replace `"file_list"` with `"file_glob"`.

- [ ] **Step 4: Delete file_list**

```bash
rm agent_md/tools/files/list.py
```

- [ ] **Step 5: Search for remaining file_list references**

Run: `rg "file_list" agent_md/`

Fix any remaining references (should be none in code after registry update).

- [ ] **Step 6: Verify the project runs**

Run: `cd /Users/zfab/repos/agentmd && uv run agentmd list`

- [ ] **Step 7: Commit**

```bash
git add agent_md/tools/files/ agent_md/tools/registry.py
git commit -m "add file_glob tool, remove file_list"
```

---

### Task 6: Harden file_write

Add binary detection and improved return messages.

**Files:**
- Modify: `agent_md/tools/files/write.py`

- [ ] **Step 1: Update file_write**

Replace `agent_md/tools/files/write.py`:

```python
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
```

- [ ] **Step 2: Verify the project runs**

Run: `cd /Users/zfab/repos/agentmd && uv run agentmd list`

- [ ] **Step 3: Commit**

```bash
git add agent_md/tools/files/write.py
git commit -m "harden file_write: binary detection, improved return messages"
```

---

### Task 7: Update system prompt for new file tools

Update `_build_file_access_prompt` in `builder.py` to reflect the new tool set.

**Files:**
- Modify: `agent_md/graph/builder.py`

- [ ] **Step 1: Update the file access prompt**

Replace the `_build_file_access_prompt` function in `agent_md/graph/builder.py`:

```python
def _build_file_access_prompt(agent_config, path_context) -> str:
    """Build the file access section of the system prompt."""
    allowed_paths = path_context.get_allowed_paths(agent_config)

    path_list = "\n".join(f"- `{p}`" for p in allowed_paths)

    sections = [
        "## File Access\n",
        "You have four file tools: `file_read`, `file_write`, `file_edit`, and `file_glob`.\n",
        "### Allowed paths\n",
        "You can ONLY access files within these paths:\n",
        f"{path_list}\n",
        "Any path outside these boundaries will be denied.\n",
        "### Path rules\n",
        "- **Always prefer absolute paths.** When you know the full path to a file, use it as-is.\n"
        "- Relative paths resolve from the workspace root.\n"
        "- Use `file_glob` to discover files before reading. Never guess filenames.\n"
        "- **Always read a file with `file_read` before modifying it** with `file_edit` or overwriting with `file_write`.\n",
        "### Tool usage\n",
        "- `file_read(path)`: Read a file. Supports `offset` and `limit` for reading specific line ranges.\n"
        "- `file_edit(path, old_text, new_text)`: Make targeted replacements in a file. Use for surgical edits.\n"
        "- `file_write(path, content)`: Create a new file or fully overwrite an existing one.\n"
        "- `file_glob(pattern)`: Find files matching a glob pattern (e.g. `**/*.py`).",
    ]

    if agent_config.trigger.type == "watch":
        sections.append(
            "\n### Watch trigger\n"
            "This agent is activated by file changes. The user message contains the event type "
            "and the **absolute path** of the changed file.\n"
            "**You MUST use that exact absolute path** with `file_read` to read the file. "
            "Do not extract just the filename — always use the full path provided."
        )

    return "\n".join(sections)
```

- [ ] **Step 2: Verify the project runs**

Run: `cd /Users/zfab/repos/agentmd && uv run agentmd list`

- [ ] **Step 3: Commit**

```bash
git add agent_md/graph/builder.py
git commit -m "update system prompt for new file tools (edit, glob, read ranges)"
```

---

### Task 8: Update documentation

Update user-facing docs to reflect all changes.

**Files:**
- Modify: `docs/tools/built-in-tools.md`
- Modify: `docs/paths-and-security.md`

- [ ] **Step 1: Update built-in-tools.md**

Replace the `file_read`, `file_write`, and `file_list` sections in `docs/tools/built-in-tools.md`. Remove `file_list` entirely. Add `file_edit` and `file_glob` sections.

**file_read section** — update signature table to include `offset`, `limit`, `with_line_numbers`. Update behavior section to mention 500-line cap, binary detection, line numbers. Update examples.

**file_write section** — update behavior to mention binary detection and new return format (`Created/Updated path (N chars, M lines)`). Remove references to output directory resolution. State that relative paths resolve from workspace root.

**file_edit section** — new section after file_write:

```markdown
## file_edit

Edit files with targeted text replacement. Always read the file first with `file_read`.

### Signature

\```python
def file_edit(path: str, old_text: str, new_text: str, replace_all: bool = False) -> str
\```

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `path` | `str` | Yes | - | Absolute or relative path to file |
| `old_text` | `str` | Yes | - | Exact text to find and replace |
| `new_text` | `str` | Yes | - | Replacement text |
| `replace_all` | `bool` | No | `False` | Replace all occurrences |

### Behavior

- Replaces exact match of `old_text` with `new_text`
- Fails if `old_text` not found (ensures precision)
- Fails if multiple matches found and `replace_all=False`
- Empty `old_text` creates a new file (fails if file exists)
- Returns summary with replacement count and lines changed

### When to use

- **`file_edit`**: surgical changes — fix a line, rename a variable, update a config value
- **`file_write`**: create new files or full rewrites
```

**file_glob section** — new section replacing file_list:

```markdown
## file_glob

Find files matching a glob pattern. Replaces `file_list`.

### Signature

\```python
def file_glob(pattern: str) -> str
\```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `pattern` | `str` | Yes | Glob pattern (e.g. `**/*.py`) |

### Behavior

- Globs from workspace root
- Filtered by agent's allowed paths
- Returns up to 100 absolute paths, sorted alphabetically
- Read-only, no side effects
```

- [ ] **Step 2: Update paths-and-security.md**

Remove all references to output directory as default write location. Update the path resolution section to state all tools resolve from workspace root. Remove "First directory in array is the default write location" line. Update examples that mention output dir resolution.

- [ ] **Step 3: Search for remaining file_list references in docs**

Run: `rg "file_list" docs/`

Update any remaining references in `docs/examples.md`, `docs/guides/debugging.md`, `docs/agent-configuration.md`, `docs/tools/custom-tools.md` to use `file_glob` instead.

- [ ] **Step 4: Search for remaining output_dir references in docs**

Run: `rg "output.dir|default.output|default write location" docs/`

Update or remove references that describe the old output directory resolution behavior.

- [ ] **Step 5: Commit**

```bash
git add docs/
git commit -m "update documentation for file tools redesign"
```

---

### Task 9: Final cleanup and verification

Remove any remaining dead code and verify everything works end-to-end.

- [ ] **Step 1: Check for any remaining references to old module paths**

Run: `rg "from agent_md\.tools\.(file_read|file_write|file_list|memory|http_request)" .`
Run: `rg "from agent_md\.skills\.tools" .`
Run: `rg "resolve_from" agent_md/`
Run: `rg "_resolve_for_output|get_default_output_dir" agent_md/`

Fix any remaining references.

- [ ] **Step 2: Check agent_md/skills/tools.py is deleted**

Verify `agent_md/skills/tools.py` no longer exists. If `agent_md/skills/__init__.py` imported from it, update.

- [ ] **Step 3: Run linting**

Run: `cd /Users/zfab/repos/agentmd && uv run ruff check .`
Run: `cd /Users/zfab/repos/agentmd && uv run ruff format .`

Fix any issues.

- [ ] **Step 4: Verify the project runs end-to-end**

Run: `cd /Users/zfab/repos/agentmd && uv run agentmd list`
Run: `cd /Users/zfab/repos/agentmd && uv run agentmd validate workspace/agents/<any-agent>.md` (if an agent file exists)

Expected: both commands succeed without errors.

- [ ] **Step 5: Commit any cleanup**

```bash
git add -A
git commit -m "final cleanup: remove dead code and fix lint issues"
```
