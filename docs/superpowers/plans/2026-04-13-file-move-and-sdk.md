# file_move Tool + Custom Tool SDK — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `file_move` built-in tool and create `agent_md.sdk` module with utility functions for custom tool authors.

**Architecture:** `file_move` follows the existing factory pattern in `agent_md/tools/files/`. The SDK uses a `contextvars.ContextVar` set by the runner before graph execution to expose agent context via simple importable functions.

**Tech Stack:** Python 3.13+, LangChain tools, contextvars, shutil

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `agent_md/tools/files/move.py` | `file_move` tool factory |
| Create | `agent_md/sdk.py` | Public SDK: `resolve_path`, `workspace_root`, `agent_name`, `agent_paths` |
| Create | `tests/test_file_move.py` | Tests for file_move tool |
| Create | `tests/test_sdk.py` | Tests for SDK module |
| Modify | `agent_md/tools/files/__init__.py` | Export `create_file_move_tool` |
| Modify | `agent_md/tools/registry.py` | Register file_move in `resolve_builtin_tools` and `list_builtin_tools` |
| Modify | `agent_md/execution/runner.py` | Set/reset SDK contextvar around graph execution |
| Delete | `agent_md/sandbox.py` | Replaced by `agent_md/sdk` |
| Modify | `docs/tools/built-in-tools.md` | Add file_move documentation |
| Modify | `docs/tools/custom-tools.md` | Add SDK section with examples |
| Modify | `docs/tools/index.md` | Add file_move to tools list |
| Modify | `README.md` | Mention file_move and SDK |

---

### Task 1: file_move tool

**Files:**
- Create: `agent_md/tools/files/move.py`
- Modify: `agent_md/tools/files/__init__.py`
- Modify: `agent_md/tools/registry.py`
- Test: `tests/test_file_move.py`

- [ ] **Step 1: Write tests for file_move**

Create `tests/test_file_move.py`:

```python
"""Tests for file_move tool."""

from pathlib import Path

import pytest

from agent_md.tools.files.move import create_file_move_tool
from agent_md.workspace.path_context import PathContext
from agent_md.config.models import PathEntry


class FakeConfig:
    def __init__(self, name="test-agent", paths=None):
        self.name = name
        self.paths = paths or {}

        class FakeTrigger:
            type = "manual"
            paths = []

        self.trigger = FakeTrigger()


@pytest.fixture
def workspace(tmp_path):
    return tmp_path / "workspace"


@pytest.fixture
def path_context(workspace):
    workspace.mkdir()
    agents_dir = workspace / "agents"
    agents_dir.mkdir()
    return PathContext(
        workspace_root=workspace,
        agents_dir=agents_dir,
        db_path=workspace / "data" / "agentmd.db",
        mcp_config=agents_dir / "_config" / "mcp-servers.json",
        tools_dir=agents_dir / "_config" / "tools",
        skills_dir=agents_dir / "_config" / "skills",
    )


class TestFileMoveSuccess:
    def test_move_file(self, workspace, path_context):
        """Move a file from one location to another."""
        config = FakeConfig()
        tool = create_file_move_tool(config, path_context)

        src = workspace / "hello.txt"
        src.write_text("hello")
        dest = workspace / "moved.txt"

        result = tool.invoke({"source": str(src), "destination": str(dest)})
        assert "Moved" in result
        assert not src.exists()
        assert dest.read_text() == "hello"

    def test_move_creates_parent_dirs(self, workspace, path_context):
        """Move creates destination parent directories if needed."""
        config = FakeConfig()
        tool = create_file_move_tool(config, path_context)

        src = workspace / "file.txt"
        src.write_text("data")
        dest = workspace / "sub" / "deep" / "file.txt"

        result = tool.invoke({"source": str(src), "destination": str(dest)})
        assert "Moved" in result
        assert dest.read_text() == "data"
        assert not src.exists()

    def test_move_with_relative_paths(self, workspace, path_context):
        """Move works with relative paths resolved from workspace root."""
        config = FakeConfig()
        tool = create_file_move_tool(config, path_context)

        src = workspace / "a.txt"
        src.write_text("content")

        result = tool.invoke({"source": "a.txt", "destination": "b.txt"})
        assert "Moved" in result
        assert not src.exists()
        assert (workspace / "b.txt").read_text() == "content"


class TestFileMoveErrors:
    def test_source_not_found(self, workspace, path_context):
        """Error when source file does not exist."""
        config = FakeConfig()
        tool = create_file_move_tool(config, path_context)

        result = tool.invoke({"source": str(workspace / "nope.txt"), "destination": str(workspace / "dest.txt")})
        assert "ERROR" in result
        assert "not found" in result.lower() or "does not exist" in result.lower()

    def test_source_is_directory(self, workspace, path_context):
        """Error when source is a directory."""
        config = FakeConfig()
        tool = create_file_move_tool(config, path_context)

        d = workspace / "mydir"
        d.mkdir()

        result = tool.invoke({"source": str(d), "destination": str(workspace / "dest")})
        assert "ERROR" in result

    def test_source_blocked_by_sandbox(self, workspace, path_context):
        """Error when source is outside allowed paths."""
        config = FakeConfig(paths={"output": PathEntry(path=str(workspace / "output"))})
        tool = create_file_move_tool(config, path_context)

        src = workspace / "secret.txt"
        src.write_text("secret")

        result = tool.invoke({"source": str(src), "destination": str(workspace / "output" / "moved.txt")})
        assert "ERROR" in result
        assert "denied" in result.lower() or "outside" in result.lower()

    def test_destination_blocked_by_sandbox(self, workspace, path_context):
        """Error when destination is outside allowed paths."""
        config = FakeConfig(paths={"data": PathEntry(path=str(workspace / "data"))})
        tool = create_file_move_tool(config, path_context)

        data_dir = workspace / "data"
        data_dir.mkdir()
        src = data_dir / "file.txt"
        src.write_text("data")

        result = tool.invoke({"source": str(src), "destination": "/tmp/evil.txt"})
        assert "ERROR" in result

    def test_move_env_file_blocked(self, workspace, path_context):
        """Cannot move .env files."""
        config = FakeConfig()
        tool = create_file_move_tool(config, path_context)

        env_file = workspace / ".env"
        env_file.write_text("SECRET=123")

        result = tool.invoke({"source": str(env_file), "destination": str(workspace / "env_backup")})
        assert "ERROR" in result

    def test_move_db_file_blocked(self, workspace, path_context):
        """Cannot move .db files."""
        config = FakeConfig()
        tool = create_file_move_tool(config, path_context)

        db_file = workspace / "data.db"
        db_file.write_text("fake db")

        result = tool.invoke({"source": str(db_file), "destination": str(workspace / "backup.db")})
        assert "ERROR" in result

    def test_move_into_config_blocked(self, workspace, path_context):
        """Cannot move files into _config/ directory."""
        config = FakeConfig()
        tool = create_file_move_tool(config, path_context)

        src = workspace / "file.txt"
        src.write_text("data")
        dest = workspace / "agents" / "_config" / "file.txt"

        result = tool.invoke({"source": str(src), "destination": str(dest)})
        assert "ERROR" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/zfab/repos/agentmd && python -m pytest tests/test_file_move.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent_md.tools.files.move'`

- [ ] **Step 3: Implement file_move tool**

Create `agent_md/tools/files/move.py`:

```python
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
```

- [ ] **Step 4: Export from `__init__.py`**

Edit `agent_md/tools/files/__init__.py` — add the import and export:

```python
"""File tools — read, write, edit, glob, move."""

from agent_md.tools.files.edit import create_file_edit_tool
from agent_md.tools.files.glob import create_file_glob_tool
from agent_md.tools.files.move import create_file_move_tool
from agent_md.tools.files.read import create_file_read_tool
from agent_md.tools.files.write import create_file_write_tool

__all__ = [
    "create_file_read_tool",
    "create_file_write_tool",
    "create_file_edit_tool",
    "create_file_glob_tool",
    "create_file_move_tool",
]
```

- [ ] **Step 5: Register in registry**

Edit `agent_md/tools/registry.py`:

1. Add import in `resolve_builtin_tools`:
```python
from agent_md.tools.files import (
    create_file_edit_tool,
    create_file_glob_tool,
    create_file_move_tool,
    create_file_read_tool,
    create_file_write_tool,
)
```

2. Add tool creation after `create_file_glob_tool`:
```python
tools.append(create_file_move_tool(agent_config, path_context))
```

3. Add `"file_move"` to the list in `list_builtin_tools()`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/zfab/repos/agentmd && python -m pytest tests/test_file_move.py -v`
Expected: All 10 tests PASS

- [ ] **Step 7: Run full test suite**

Run: `cd /Users/zfab/repos/agentmd && python -m pytest -x -q`
Expected: All existing tests still pass

- [ ] **Step 8: Commit**

```bash
git add agent_md/tools/files/move.py agent_md/tools/files/__init__.py agent_md/tools/registry.py tests/test_file_move.py
git commit -m "feat: add file_move built-in tool (#6)"
```

---

### Task 2: agent_md.sdk module

**Files:**
- Create: `agent_md/sdk.py`
- Delete: `agent_md/sandbox.py`
- Modify: `agent_md/execution/runner.py`
- Test: `tests/test_sdk.py`

- [ ] **Step 1: Write tests for SDK**

Create `tests/test_sdk.py`:

```python
"""Tests for agent_md.sdk — public utilities for custom tool authors."""

import asyncio
from pathlib import Path

import pytest

from agent_md.config.models import PathEntry
from agent_md.workspace.path_context import PathContext


class FakeConfig:
    def __init__(self, name="test-agent", paths=None):
        self.name = name
        self.paths = paths or {}

        class FakeTrigger:
            type = "manual"
            paths = []

        self.trigger = FakeTrigger()


@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


@pytest.fixture
def path_context(workspace):
    agents_dir = workspace / "agents"
    agents_dir.mkdir()
    return PathContext(
        workspace_root=workspace,
        agents_dir=agents_dir,
        db_path=workspace / "data" / "agentmd.db",
        mcp_config=agents_dir / "_config" / "mcp-servers.json",
        tools_dir=agents_dir / "_config" / "tools",
        skills_dir=agents_dir / "_config" / "skills",
    )


class TestSDKOutsideExecution:
    def test_resolve_path_raises_outside_execution(self):
        from agent_md.sdk import resolve_path

        with pytest.raises(RuntimeError, match="agent execution"):
            resolve_path("some/path")

    def test_workspace_root_raises_outside_execution(self):
        from agent_md.sdk import workspace_root

        with pytest.raises(RuntimeError, match="agent execution"):
            workspace_root()

    def test_agent_name_raises_outside_execution(self):
        from agent_md.sdk import agent_name

        with pytest.raises(RuntimeError, match="agent execution"):
            agent_name()

    def test_agent_paths_raises_outside_execution(self):
        from agent_md.sdk import agent_paths

        with pytest.raises(RuntimeError, match="agent execution"):
            agent_paths()


class TestSDKWithinExecution:
    def test_resolve_path_success(self, workspace, path_context):
        from agent_md.sdk import _set_context, _reset_context, resolve_path

        config = FakeConfig()
        token = _set_context(config, path_context)
        try:
            target = workspace / "file.txt"
            target.write_text("hello")
            resolved, error = resolve_path(str(target))
            assert error is None
            assert resolved == target
        finally:
            _reset_context(token)

    def test_resolve_path_with_alias(self, workspace, path_context):
        from agent_md.sdk import _set_context, _reset_context, resolve_path

        output_dir = workspace / "output"
        output_dir.mkdir()
        config = FakeConfig(paths={"output": PathEntry(path=str(output_dir))})
        token = _set_context(config, path_context)
        try:
            resolved, error = resolve_path("{output}/report.txt")
            assert error is None
            assert resolved == output_dir / "report.txt"
        finally:
            _reset_context(token)

    def test_resolve_path_sandbox_violation(self, workspace, path_context):
        from agent_md.sdk import _set_context, _reset_context, resolve_path

        config = FakeConfig(paths={"data": PathEntry(path=str(workspace / "data"))})
        token = _set_context(config, path_context)
        try:
            resolved, error = resolve_path("/etc/passwd")
            assert resolved is None
            assert error is not None
        finally:
            _reset_context(token)

    def test_workspace_root(self, workspace, path_context):
        from agent_md.sdk import _set_context, _reset_context, workspace_root

        config = FakeConfig()
        token = _set_context(config, path_context)
        try:
            assert workspace_root() == workspace
        finally:
            _reset_context(token)

    def test_agent_name(self, workspace, path_context):
        from agent_md.sdk import _set_context, _reset_context, agent_name

        config = FakeConfig(name="my-agent")
        token = _set_context(config, path_context)
        try:
            assert agent_name() == "my-agent"
        finally:
            _reset_context(token)

    def test_agent_paths_empty(self, workspace, path_context):
        from agent_md.sdk import _set_context, _reset_context, agent_paths

        config = FakeConfig()
        token = _set_context(config, path_context)
        try:
            assert agent_paths() == {}
        finally:
            _reset_context(token)

    def test_agent_paths_with_aliases(self, workspace, path_context):
        from agent_md.sdk import _set_context, _reset_context, agent_paths

        output_dir = workspace / "output"
        data_dir = workspace / "data"
        config = FakeConfig(
            paths={
                "output": PathEntry(path=str(output_dir)),
                "data": PathEntry(path=str(data_dir)),
            }
        )
        token = _set_context(config, path_context)
        try:
            paths = agent_paths()
            assert paths["output"] == output_dir
            assert paths["data"] == data_dir
        finally:
            _reset_context(token)


class TestSDKConcurrentIsolation:
    async def test_concurrent_runs_isolated(self, workspace, path_context):
        """Two concurrent tasks see their own agent context."""
        from agent_md.sdk import _set_context, _reset_context, agent_name

        results = {}

        async def run_agent(name):
            config = FakeConfig(name=name)
            token = _set_context(config, path_context)
            try:
                await asyncio.sleep(0.01)  # yield to other task
                results[name] = agent_name()
            finally:
                _reset_context(token)

        await asyncio.gather(run_agent("agent-a"), run_agent("agent-b"))

        assert results["agent-a"] == "agent-a"
        assert results["agent-b"] == "agent-b"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/zfab/repos/agentmd && python -m pytest tests/test_sdk.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent_md.sdk'`

- [ ] **Step 3: Implement agent_md/sdk.py**

Create `agent_md/sdk.py`:

```python
"""Public SDK for custom tool authors.

Provides utility functions to access agent context (paths, workspace, identity)
from within custom tools without requiring factories or dependency injection.

Usage in custom tools::

    from agent_md.sdk import resolve_path, workspace_root, agent_name

    @tool
    def my_tool(path: str) -> str:
        resolved, error = resolve_path(path)
        if error:
            return f"ERROR: {error}"
        return resolved.read_text()
"""

from __future__ import annotations

import contextvars
from pathlib import Path

_current_context: contextvars.ContextVar[tuple | None] = contextvars.ContextVar(
    "agentmd_context", default=None
)


def _set_context(agent_config, path_context) -> contextvars.Token:
    """Set the agent context for the current async task. Returns a reset token."""
    return _current_context.set((agent_config, path_context))


def _reset_context(token: contextvars.Token) -> None:
    """Reset the agent context using the token from _set_context."""
    _current_context.reset(token)


def _get_context() -> tuple:
    """Return (agent_config, path_context) or raise if not in an execution."""
    ctx = _current_context.get()
    if ctx is None:
        raise RuntimeError("Must be called within an agent execution")
    return ctx


def resolve_path(path: str) -> tuple[Path | None, str | None]:
    """Resolve a path string and validate it against sandbox rules.

    Handles alias expansion (``{output}/file.txt``), relative paths
    (resolved from workspace root), and absolute paths.

    Returns:
        ``(resolved_path, None)`` on success, ``(None, error_message)`` on failure.
    """
    config, path_context = _get_context()
    return path_context.validate_path(path, config)


def workspace_root() -> Path:
    """Return the absolute path to the workspace root directory."""
    _, path_context = _get_context()
    return path_context.workspace_root


def agent_name() -> str:
    """Return the name of the currently executing agent."""
    config, _ = _get_context()
    return config.name


def agent_paths() -> dict[str, Path]:
    """Return the agent's declared path aliases, resolved to absolute paths.

    Returns an empty dict if the agent declares no paths.

    Example::

        {"output": Path("/abs/path/to/output"), "data": Path("/abs/path/to/data")}
    """
    config, path_context = _get_context()
    result = {}
    for alias, entry in config.paths.items():
        result[alias] = path_context._resolve_relative(entry.path)
    return result


__all__ = ["resolve_path", "workspace_root", "agent_name", "agent_paths"]
```

- [ ] **Step 4: Run SDK tests**

Run: `cd /Users/zfab/repos/agentmd && python -m pytest tests/test_sdk.py -v`
Expected: All 12 tests PASS

- [ ] **Step 5: Delete sandbox.py**

```bash
rm agent_md/sandbox.py
```

- [ ] **Step 6: Check for sandbox imports and remove them**

Run: `cd /Users/zfab/repos/agentmd && grep -r "agent_md.sandbox" --include="*.py" -l`

Remove any imports found. If none, continue.

- [ ] **Step 7: Commit**

```bash
git add agent_md/sdk.py tests/test_sdk.py
git rm agent_md/sandbox.py
git commit -m "feat: add agent_md.sdk module for custom tool authors (#13)"
```

---

### Task 3: Integrate SDK contextvar in runner

**Files:**
- Modify: `agent_md/execution/runner.py`

- [ ] **Step 1: Add SDK context to the runner's `run()` method**

Edit `agent_md/execution/runner.py`:

1. Add import at the top:
```python
from agent_md.sdk import _set_context, _reset_context
```

2. In the `run()` method, wrap the graph execution with context set/reset. Find the line:
```python
graph = await self._build_graph(config)
```

Add **before** it:
```python
sdk_token = _set_context(config, self.path_context)
```

3. In the `try` block's `finally` (you need to add one), reset the context. The existing try/except structure at line ~300 starts with `try:` and has `except asyncio.TimeoutError`, `except LimitExceeded`, `except Exception`. Wrap the entire execution in an additional try/finally around the SDK token:

The structure should be:
```python
sdk_token = _set_context(config, self.path_context)
try:
    # ... existing try/except block with graph build, stream, etc. ...
finally:
    _reset_context(sdk_token)
```

Place the `sdk_token = _set_context(...)` right before the existing `try:` block (line 300), and add `finally: _reset_context(sdk_token)` after the last `except Exception` block (after line 544).

- [ ] **Step 2: Run full test suite**

Run: `cd /Users/zfab/repos/agentmd && python -m pytest -x -q`
Expected: All tests pass (existing + new)

- [ ] **Step 3: Commit**

```bash
git add agent_md/execution/runner.py
git commit -m "feat: set SDK context in runner for custom tool access"
```

---

### Task 4: Update documentation

**Files:**
- Modify: `docs/tools/built-in-tools.md`
- Modify: `docs/tools/custom-tools.md`
- Modify: `docs/tools/index.md`
- Modify: `README.md`

- [ ] **Step 1: Add file_move to built-in-tools.md**

Edit `docs/tools/built-in-tools.md` — add after the `file_glob` section (before `## http_request`):

```markdown
---

## file_move

Move or rename a file. Both source and destination must be within allowed paths.

### Signature

```python
def file_move(source: str, destination: str) -> str
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `source` | `str` | Yes | Path to the file to move |
| `destination` | `str` | Yes | Path to move the file to |

### Behavior

- Validates both source and destination against sandbox rules
- Source must exist and be a file (directories are not supported)
- Creates destination parent directories automatically
- Atomic on the same filesystem (uses `shutil.move`)
- Returns confirmation: `Moved: {source} -> {destination}`

### Security Rules

1. **Both paths** must be within the agent's declared `paths`
2. **Blocked**: Cannot move `.env`, `.db` files, or files into `_config/`
3. **Watch paths**: Automatically included as allowed paths

### Examples

**Rename a file:**
```yaml
---
name: file-organizer
paths:
  data: data/
---

Rename `data/raw.csv` to `data/processed.csv`.
```

**Move to subdirectory:**
```yaml
---
name: inbox-processor
paths:
  inbox: inbox/
  archive: archive/
---

Move files from `inbox/` to `archive/` after processing.
```
```

- [ ] **Step 2: Add SDK section to custom-tools.md**

Edit `docs/tools/custom-tools.md` — add a new section before `## Troubleshooting`:

```markdown
---

## SDK — Path Resolution for Custom Tools

Custom tools that need to read or write files should use `agent_md.sdk` for sandbox-safe path resolution. This gives your tool the same security guarantees as built-in tools.

### Available Functions

| Function | Returns | Description |
|---|---|---|
| `resolve_path(path)` | `(Path \| None, str \| None)` | Resolve aliases + validate sandbox |
| `workspace_root()` | `Path` | Absolute path to workspace root |
| `agent_name()` | `str` | Name of the executing agent |
| `agent_paths()` | `dict[str, Path]` | Agent's declared path aliases, resolved |

All functions are available during agent execution. Calling them outside of execution raises `RuntimeError`.

### Example: File Processing Tool

```python
# workspace/agents/_config/tools/word_count.py
from langchain_core.tools import tool
from agent_md.sdk import resolve_path

@tool
def word_count(path: str) -> str:
    """Count words in a file, with sandbox validation.

    Args:
        path: Path to the file (supports aliases like {data}/file.txt).

    Returns:
        Word count or error message.
    """
    resolved, error = resolve_path(path)
    if error:
        return f"ERROR: {error}"

    try:
        text = resolved.read_text()
        return f"{len(text.split())} words in {resolved.name}"
    except Exception as e:
        return f"ERROR: {e}"
```

### Example: Context-Aware Tool

```python
# workspace/agents/_config/tools/file_info.py
from langchain_core.tools import tool
from agent_md.sdk import agent_name, workspace_root, agent_paths

@tool
def show_context() -> str:
    """Show the current agent's workspace context.

    Returns:
        Agent name, workspace root, and declared paths.
    """
    paths = agent_paths()
    path_list = "\n".join(f"  {alias}: {path}" for alias, path in paths.items())
    return (
        f"Agent: {agent_name()}\n"
        f"Workspace: {workspace_root()}\n"
        f"Paths:\n{path_list or '  (none)'}"
    )
```

### When to Use the SDK

- **Use `resolve_path`** when your tool reads or writes files — it validates sandbox rules and resolves aliases
- **Use `workspace_root`** when you need the base directory for relative operations
- **Use `agent_name`** for logging, naming output files, or conditional behavior per agent
- **Use `agent_paths`** to discover which directories the agent has access to

### When NOT to Use the SDK

If your tool doesn't touch the filesystem (API calls, text processing, calculations), you don't need the SDK. A plain `@tool` function works fine.
```

- [ ] **Step 3: Update tools index**

Edit `docs/tools/index.md` — add `file_move` and `file_edit` to the built-in tools list, and add SDK mention to custom tools:

Replace the built-in tools list with:
```markdown
- **[file_read](built-in-tools.md#file_read)** — Read files from workspace
- **[file_write](built-in-tools.md#file_write)** — Write files to allowed paths
- **[file_edit](built-in-tools.md#file_edit)** — Edit files with targeted text replacement
- **[file_move](built-in-tools.md#file_move)** — Move or rename files
- **[file_glob](built-in-tools.md#file_glob)** — Find files matching a pattern
- **[http_request](built-in-tools.md#http_request)** — Make HTTP calls (GET, POST, etc.)
- **[memory_save / memory_append / memory_retrieve](built-in-tools.md#memory_save)** — Long-term memory
- **[skill_use / skill_read_file / skill_run_script](built-in-tools.md#skill_use)** — [Skills](../skills.md) (when enabled)
```

Update the custom tools section to mention the SDK:
```markdown
## Custom Tools

Extend with Python. Use the SDK for sandbox-safe file access:

```python
# workspace/agents/_config/tools/my_tool.py
from langchain_core.tools import tool
from agent_md.sdk import resolve_path

@tool
def my_tool(path: str) -> str:
    """Read a file safely."""
    resolved, error = resolve_path(path)
    if error:
        return f"ERROR: {error}"
    return resolved.read_text()
```

[Create custom tools →](custom-tools.md)
```

- [ ] **Step 4: Update README.md**

Find the section that lists tools/features and add `file_move` to the tool list. Add a brief mention of the SDK for custom tools. The exact edit depends on the current README structure — look for where tools are mentioned and add `file_move` there. If there's a custom tools section, add a one-liner about the SDK.

- [ ] **Step 5: Run docs build (if applicable)**

Run: `cd /Users/zfab/repos/agentmd && python -m mkdocs build --strict 2>&1 | tail -5`
Expected: Build succeeds (or warnings only)

- [ ] **Step 6: Commit**

```bash
git add docs/tools/built-in-tools.md docs/tools/custom-tools.md docs/tools/index.md README.md
git commit -m "docs: add file_move and SDK documentation"
```

---

### Task 5: Final validation and cleanup

- [ ] **Step 1: Run full test suite**

Run: `cd /Users/zfab/repos/agentmd && python -m pytest -v`
Expected: All tests pass

- [ ] **Step 2: Run linter**

Run: `cd /Users/zfab/repos/agentmd && ruff check .`
Expected: No errors

- [ ] **Step 3: Run formatter**

Run: `cd /Users/zfab/repos/agentmd && ruff format --check .`
Expected: No formatting issues (or run `ruff format .` to fix)

- [ ] **Step 4: Verify sandbox.py is deleted**

Run: `cd /Users/zfab/repos/agentmd && test -f agent_md/sandbox.py && echo "STILL EXISTS" || echo "OK deleted"`
Expected: `OK deleted`

- [ ] **Step 5: Verify no broken imports**

Run: `cd /Users/zfab/repos/agentmd && python -c "from agent_md.sdk import resolve_path, workspace_root, agent_name, agent_paths; print('SDK OK')"`
Run: `cd /Users/zfab/repos/agentmd && python -c "from agent_md.tools.files import create_file_move_tool; print('file_move OK')"`
Expected: Both print OK
