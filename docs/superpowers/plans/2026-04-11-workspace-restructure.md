# Workspace Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize workspace structure (`_config/` for infra, DB to state dir), split `core/` into `config/`, `execution/`, `workspace/` subpackages, repaginate setup wizard, and remove legacy code.

**Architecture:** File moves first (mechanical), then behavioral changes (settings, sandbox, setup). All imports updated via systematic grep-and-replace. Tests run before and after each task to catch breakage immediately.

**Tech Stack:** Same stack, no new dependencies. Breaking change — v0.9.0.

**Spec:** `docs/superpowers/specs/2026-04-11-workspace-restructure-design.md`

---

## File Structure

### New packages (created from `agent_md/core/`)

| New package | Files (moved from core/) |
|---|---|
| `agent_md/config/` | `settings.py`, `models.py`, `pricing.py`, `env.py`, `substitutions.py`, `pricing.yaml` |
| `agent_md/execution/` | `runner.py`, `execution_logger.py` → `logger.py`, `event_bus.py`, `lifecycle.py` |
| `agent_md/workspace/` | `bootstrap.py`, `registry.py`, `parser.py`, `path_context.py`, `scheduler.py`, `services.py` |

### Import mapping (98 import lines)

| Old import | New import |
|---|---|
| `agent_md.core.settings` | `agent_md.config.settings` |
| `agent_md.core.models` | `agent_md.config.models` |
| `agent_md.core.pricing` | `agent_md.config.pricing` |
| `agent_md.core.env` | `agent_md.config.env` |
| `agent_md.core.substitutions` | `agent_md.config.substitutions` |
| `agent_md.core.runner` | `agent_md.execution.runner` |
| `agent_md.core.execution_logger` | `agent_md.execution.logger` |
| `agent_md.core.event_bus` | `agent_md.execution.event_bus` |
| `agent_md.core.lifecycle` | `agent_md.execution.lifecycle` |
| `agent_md.core.bootstrap` | `agent_md.workspace.bootstrap` |
| `agent_md.core.registry` | `agent_md.workspace.registry` |
| `agent_md.core.parser` | `agent_md.workspace.parser` |
| `agent_md.core.path_context` | `agent_md.workspace.path_context` |
| `agent_md.core.scheduler` | `agent_md.workspace.scheduler` |
| `agent_md.core.services` | `agent_md.workspace.services` |

---

## Task 1: Create new packages and move files

**Files:**
- Create: `agent_md/config/__init__.py`, `agent_md/execution/__init__.py`, `agent_md/workspace/__init__.py`
- Move: all 15 files from `agent_md/core/` to new packages
- Delete: `agent_md/core/`

This is a pure mechanical move. No code changes, only file relocation. The `execution_logger.py` is renamed to `logger.py` during the move.

- [ ] **Step 1: Create new package directories**

```bash
mkdir -p agent_md/config agent_md/execution agent_md/workspace
touch agent_md/config/__init__.py agent_md/execution/__init__.py agent_md/workspace/__init__.py
```

- [ ] **Step 2: Move config files**

```bash
git mv agent_md/core/settings.py agent_md/config/settings.py
git mv agent_md/core/models.py agent_md/config/models.py
git mv agent_md/core/pricing.py agent_md/config/pricing.py
git mv agent_md/core/pricing.yaml agent_md/config/pricing.yaml
git mv agent_md/core/env.py agent_md/config/env.py
git mv agent_md/core/substitutions.py agent_md/config/substitutions.py
```

- [ ] **Step 3: Move execution files**

```bash
git mv agent_md/core/runner.py agent_md/execution/runner.py
git mv agent_md/core/execution_logger.py agent_md/execution/logger.py
git mv agent_md/core/event_bus.py agent_md/execution/event_bus.py
git mv agent_md/core/lifecycle.py agent_md/execution/lifecycle.py
```

- [ ] **Step 4: Move workspace files**

```bash
git mv agent_md/core/bootstrap.py agent_md/workspace/bootstrap.py
git mv agent_md/core/registry.py agent_md/workspace/registry.py
git mv agent_md/core/parser.py agent_md/workspace/parser.py
git mv agent_md/core/path_context.py agent_md/workspace/path_context.py
git mv agent_md/core/scheduler.py agent_md/workspace/scheduler.py
git mv agent_md/core/services.py agent_md/workspace/services.py
```

- [ ] **Step 5: Remove core/ directory**

```bash
rm -rf agent_md/core/
```

If `core/__init__.py` or `core/__pycache__` remain, remove them too.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: move core/ files to config/, execution/, workspace/ packages"
```

Note: Tests will FAIL after this step — imports are not yet updated. That's expected.

---

## Task 2: Update all imports in source code

**Files:** Every `.py` file under `agent_md/` that imports from `agent_md.core`

This is systematic find-and-replace across the codebase. Use the import mapping table above. The key rename is `execution_logger` → `logger` (module name changed).

- [ ] **Step 1: Replace all imports using sed**

Run these replacements across all Python files in `agent_md/`:

```bash
# config/ imports
find agent_md/ -name "*.py" -exec sed -i '' 's/agent_md\.core\.settings/agent_md.config.settings/g' {} +
find agent_md/ -name "*.py" -exec sed -i '' 's/agent_md\.core\.models/agent_md.config.models/g' {} +
find agent_md/ -name "*.py" -exec sed -i '' 's/agent_md\.core\.pricing/agent_md.config.pricing/g' {} +
find agent_md/ -name "*.py" -exec sed -i '' 's/agent_md\.core\.env/agent_md.config.env/g' {} +
find agent_md/ -name "*.py" -exec sed -i '' 's/agent_md\.core\.substitutions/agent_md.config.substitutions/g' {} +

# execution/ imports (note: execution_logger → execution.logger)
find agent_md/ -name "*.py" -exec sed -i '' 's/agent_md\.core\.execution_logger/agent_md.execution.logger/g' {} +
find agent_md/ -name "*.py" -exec sed -i '' 's/agent_md\.core\.runner/agent_md.execution.runner/g' {} +
find agent_md/ -name "*.py" -exec sed -i '' 's/agent_md\.core\.event_bus/agent_md.execution.event_bus/g' {} +
find agent_md/ -name "*.py" -exec sed -i '' 's/agent_md\.core\.lifecycle/agent_md.execution.lifecycle/g' {} +

# workspace/ imports
find agent_md/ -name "*.py" -exec sed -i '' 's/agent_md\.core\.bootstrap/agent_md.workspace.bootstrap/g' {} +
find agent_md/ -name "*.py" -exec sed -i '' 's/agent_md\.core\.registry/agent_md.workspace.registry/g' {} +
find agent_md/ -name "*.py" -exec sed -i '' 's/agent_md\.core\.parser/agent_md.workspace.parser/g' {} +
find agent_md/ -name "*.py" -exec sed -i '' 's/agent_md\.core\.path_context/agent_md.workspace.path_context/g' {} +
find agent_md/ -name "*.py" -exec sed -i '' 's/agent_md\.core\.scheduler/agent_md.workspace.scheduler/g' {} +
find agent_md/ -name "*.py" -exec sed -i '' 's/agent_md\.core\.services/agent_md.workspace.services/g' {} +
```

- [ ] **Step 2: Update imports in tests/**

```bash
find tests/ -name "*.py" -exec sed -i '' 's/agent_md\.core\.settings/agent_md.config.settings/g' {} +
find tests/ -name "*.py" -exec sed -i '' 's/agent_md\.core\.models/agent_md.config.models/g' {} +
find tests/ -name "*.py" -exec sed -i '' 's/agent_md\.core\.pricing/agent_md.config.pricing/g' {} +
find tests/ -name "*.py" -exec sed -i '' 's/agent_md\.core\.substitutions/agent_md.config.substitutions/g' {} +
find tests/ -name "*.py" -exec sed -i '' 's/agent_md\.core\.execution_logger/agent_md.execution.logger/g' {} +
find tests/ -name "*.py" -exec sed -i '' 's/agent_md\.core\.runner/agent_md.execution.runner/g' {} +
find tests/ -name "*.py" -exec sed -i '' 's/agent_md\.core\.event_bus/agent_md.execution.event_bus/g' {} +
find tests/ -name "*.py" -exec sed -i '' 's/agent_md\.core\.lifecycle/agent_md.execution.lifecycle/g' {} +
find tests/ -name "*.py" -exec sed -i '' 's/agent_md\.core\.bootstrap/agent_md.workspace.bootstrap/g' {} +
find tests/ -name "*.py" -exec sed -i '' 's/agent_md\.core\.path_context/agent_md.workspace.path_context/g' {} +
find tests/ -name "*.py" -exec sed -i '' 's/agent_md\.core\.services/agent_md.workspace.services/g' {} +
find tests/ -name "*.py" -exec sed -i '' 's/agent_md\.core\.registry/agent_md.workspace.registry/g' {} +
```

- [ ] **Step 3: Verify no remaining core imports**

```bash
grep -rn "agent_md\.core\." agent_md/ tests/ --include="*.py"
```

Expected: ZERO results. If any remain, fix them manually.

- [ ] **Step 4: Fix the pricing.yaml path in pricing.py**

The `pricing.py` loads `pricing.yaml` from `Path(__file__).parent / "pricing.yaml"`. Since the file moved to `agent_md/config/`, this still works — `pricing.yaml` is in the same directory. Verify:

```bash
ls agent_md/config/pricing.yaml
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/ -q --ignore=tests/test_runner_limits.py --ignore=tests/test_runner_timeout.py --ignore=tests/test_orphan_sweep.py --ignore=tests/test_loop_detection.py
```

Expected: All 148 tests PASS. If any fail, fix the remaining import issues.

- [ ] **Step 6: Run linter**

```bash
uv run ruff check .
```

Fix any issues (unused imports from the rename, etc).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: update all imports from agent_md.core to config/execution/workspace"
```

---

## Task 3: Remove legacy code

**Files:**
- Modify: `agent_md/db/database.py`
- Modify: `agent_md/skills/loader.py`
- Modify: `agent_md/cli/commands.py`
- Modify: `agent_md/config/models.py`

- [ ] **Step 1: Remove MIGRATIONS from database.py**

In `agent_md/db/database.py`, remove the `MIGRATIONS` list and the migration loop in `connect()`. The schema already has all columns (`cost_usd`, `pid`) in the CREATE TABLE. The ALTER TABLE migrations are only needed for upgrading old databases — users will recreate via `setup`.

Remove:
```python
MIGRATIONS = [
    "ALTER TABLE executions ADD COLUMN cost_usd REAL",
    "ALTER TABLE executions ADD COLUMN pid INTEGER",
]
```

And remove the migration loop in `connect()`:
```python
            for migration in MIGRATIONS:
                try:
                    await self._db.execute(migration)
                    await self._db.commit()
                except Exception:
                    pass
```

- [ ] **Step 2: Remove backward-compat shim from skills/loader.py**

In `agent_md/skills/loader.py`, remove the backward-compat comment and any shim logic for `skill_dir` → `cwd` mapping. Read the file first to understand what exactly to remove.

- [ ] **Step 3: Remove backward-compat from cli/commands.py**

In `agent_md/cli/commands.py`, find and remove the line around line 966:
```python
    # Backward compat: if arg contains / or ends in .md, treat as path
```
And the associated logic.

- [ ] **Step 4: Simplify paths validation in models.py**

In `agent_md/config/models.py`, in the `validate_paths_format` validator, remove the "Migrate from" instruction in the error message for legacy list format. Just reject with a clean error:

Change from:
```python
"Migrate from:\n  paths:\n    - /a\n    - /b\n"
```

To a simple error like:
```python
"paths must be a dict of alias: path pairs, not a list"
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/ -q --ignore=tests/test_runner_limits.py --ignore=tests/test_runner_timeout.py --ignore=tests/test_orphan_sweep.py --ignore=tests/test_loop_detection.py
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: remove migration code, backward-compat shims, legacy error messages"
```

---

## Task 4: Settings — DB path, .env loading, new defaults

**Files:**
- Modify: `agent_md/config/settings.py`
- Modify: `agent_md/config/models.py`
- Create: `tests/test_settings_env.py`

- [ ] **Step 1: Write tests for .env precedence**

```python
# tests/test_settings_env.py
"""Tests for .env loading precedence and new default paths."""

import os
from pathlib import Path
from unittest.mock import patch

from agent_md.config.settings import _find_env_files, get_state_dir


def test_state_dir_default():
    path = get_state_dir()
    assert path.name == "agentmd"
    assert ".local/state" in str(path) or "XDG_STATE_HOME" in os.environ


def test_state_dir_xdg_override():
    with patch.dict(os.environ, {"XDG_STATE_HOME": "/tmp/xdg-state"}):
        path = get_state_dir()
        assert str(path) == "/tmp/xdg-state/agentmd"


def test_find_env_files_workspace_over_global(tmp_path):
    # Create both .env files
    global_env = tmp_path / "global" / ".env"
    global_env.parent.mkdir()
    global_env.write_text("GOOGLE_API_KEY=global-key\n")

    ws_env = tmp_path / "ws" / "agents" / "_config" / ".env"
    ws_env.parent.mkdir(parents=True)
    ws_env.write_text("GOOGLE_API_KEY=workspace-key\n")

    files = _find_env_files(
        config_dir=tmp_path / "global",
        workspace=tmp_path / "ws",
    )
    # Workspace should be LAST (loaded last = wins)
    assert len(files) == 2
    assert files[0] == str(global_env)
    assert files[1] == str(ws_env)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_settings_env.py -v
```

Expected: FAIL — `_find_env_files` and `get_state_dir` don't exist yet.

- [ ] **Step 3: Update settings.py**

Rewrite `agent_md/config/settings.py` with:

1. New `get_state_dir()` function (same as in `cli/client.py` — DRY by importing from there, or duplicate the 3-line function)
2. New `_find_env_files(config_dir, workspace)` that returns list of .env paths to load (global first, workspace second — workspace wins)
3. Default `db_path` changed from `"data/agentmd.db"` to state dir path
4. New default paths: `mcp_config: "agents/_config/mcp-servers.json"`, `tools_dir: "agents/_config/tools"`, `skills_dir: "agents/_config/skills"`
5. New flattened defaults: `defaults_temperature`, `defaults_max_tokens`, `defaults_history`
6. `.env` loading uses both global and workspace files

Key changes in Settings class:
```python
class Settings(BaseSettings):
    # --- App config ---
    workspace: str = ""
    agents_dir: str = "agents"
    db_path: str = ""  # empty = use state dir default
    mcp_config: str = "agents/_config/mcp-servers.json"
    tools_dir: str = "agents/_config/tools"
    skills_dir: str = "agents/_config/skills"
    
    # --- Defaults (all configurable via config.yaml) ---
    defaults_provider: str = "google"
    defaults_model: str = "gemini-2.5-flash"
    defaults_temperature: float | None = None
    defaults_max_tokens: int | None = None
    defaults_timeout: int | None = None
    defaults_max_tool_calls: int | None = None
    defaults_max_execution_tokens: int | None = None
    defaults_max_cost_usd: float | None = None
    defaults_loop_detection: bool | None = None
    defaults_history: str | None = None
```

And update `_get_global_limit_defaults()` in `models.py` to also read `temperature`, `max_tokens`, `timeout`, `history`.

- [ ] **Step 4: Update bootstrap.py for new default paths**

In `agent_md/workspace/bootstrap.py`, when `db_path` is empty, resolve to `get_state_dir() / "agentmd.db"`. Update `tools_dir` and `skills_dir` resolution to use the new defaults.

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/ -q --ignore=tests/test_runner_limits.py --ignore=tests/test_runner_timeout.py --ignore=tests/test_orphan_sweep.py --ignore=tests/test_loop_detection.py
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: DB path to state dir, .env precedence, all defaults configurable"
```

---

## Task 5: Sandbox — block `_config/` directory

**Files:**
- Modify: `agent_md/workspace/path_context.py`
- Modify: `tests/test_file_tools_paths.py` or create new test

- [ ] **Step 1: Write test for _config blocking**

```python
# tests/test_sandbox_config.py
"""Tests for _config/ directory blocking in sandbox."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock
from agent_md.workspace.path_context import PathContext


@pytest.fixture
def path_ctx(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    config_dir = agents_dir / "_config"
    config_dir.mkdir()
    (config_dir / ".env").write_text("KEY=val")
    (config_dir / "tools").mkdir()

    return PathContext(
        workspace_root=tmp_path,
        agents_dir=agents_dir,
        db_path=tmp_path / "state" / "agentmd.db",
        mcp_config=config_dir / "mcp-servers.json",
        tools_dir=config_dir / "tools",
        skills_dir=config_dir / "skills",
    )


def test_config_dir_blocked(path_ctx):
    config = MagicMock()
    config.paths = {}
    _, error = path_ctx.validate_path(
        str(path_ctx.agents_dir / "_config" / "tools" / "hack.py"),
        config,
    )
    assert error is not None
    assert "_config" in error


def test_config_env_blocked(path_ctx):
    config = MagicMock()
    config.paths = {}
    _, error = path_ctx.validate_path(
        str(path_ctx.agents_dir / "_config" / ".env"),
        config,
    )
    assert error is not None


def test_env_anywhere_blocked(path_ctx):
    config = MagicMock()
    config.paths = {}
    _, error = path_ctx.validate_path(
        str(path_ctx.workspace_root / ".env"),
        config,
    )
    assert error is not None
    assert ".env" in error


def test_agent_files_still_blocked(path_ctx):
    config = MagicMock()
    config.paths = {}
    _, error = path_ctx.validate_path(
        str(path_ctx.agents_dir / "some-agent.md"),
        config,
    )
    assert error is not None
```

- [ ] **Step 2: Update path_context.py**

Replace `_check_security` to block `_config/` instead of `data/`:

```python
def _check_security(self, resolved: Path) -> str | None:
    """Check security constraints on a resolved path."""
    # Block _config directory (tools, skills, .env, mcp-servers.json)
    config_dir = self.agents_dir / "_config"
    if self._is_within(resolved, config_dir):
        return "Access denied: cannot access _config directory"
    # Block agent definition files
    if self._is_within(resolved, self.agents_dir) and resolved.suffix == ".md":
        return "Access denied: cannot access agent definition files"
    # Block .env files anywhere
    if resolved.name.startswith(".env"):
        return "Access denied: cannot access .env files"
    # Block .db files anywhere
    if resolved.suffix == ".db":
        return "Access denied: cannot access .db files"
    return None
```

Note: the old check `_is_within(resolved, self.agents_dir)` blocked the ENTIRE agents dir. The new check only blocks `.md` files in agents dir and the `_config/` subdirectory. This means agents CAN still have paths pointing to subdirectories within `agents/` (if not `_config/`), which is more flexible.

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/test_sandbox_config.py tests/test_file_tools_paths.py -v
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: sandbox blocks _config/ directory, allows non-config agent subdirs"
```

---

## Task 6: Setup wizard repaginated

**Files:**
- Modify: `agent_md/cli/setup.py`

- [ ] **Step 1: Read current setup.py**

Read the full `agent_md/cli/setup.py` to understand the current structure.

- [ ] **Step 2: Update `_create_workspace`**

Change directory creation:
```python
def _create_workspace(workspace: Path, provider: str, model: str):
    agents_dir = workspace / "agents"
    config_dir = agents_dir / "_config"
    tools_dir = config_dir / "tools"
    skills_dir = config_dir / "skills"

    for d in (agents_dir, config_dir, tools_dir, skills_dir):
        d.mkdir(parents=True, exist_ok=True)

    # hello-world agent
    hello = agents_dir / "hello-world.md"
    if not hello.exists():
        hello.write_text(HELLO_WORLD_AGENT)

    # Empty MCP config
    mcp = config_dir / "mcp-servers.json"
    if not mcp.exists():
        mcp.write_text("{}\n")
```

No more `data/` directory. No more `output/` directory.

- [ ] **Step 3: Update `_write_config_yaml`**

```python
def _write_config_yaml(workspace, provider, model, defaults=None):
    config = {
        "workspace": str(workspace),
        "agents_dir": "agents",
        "defaults": {
            "provider": provider,
            "model": model,
        },
        "log_level": "INFO",
    }
    if defaults:
        config["defaults"].update(defaults)
    # Write to ~/.config/agentmd/config.yaml
```

No more `db_path` or `mcp_config` in config (uses new defaults).

- [ ] **Step 4: Update `_write_env_file` path**

Change to write to `agents/_config/.env` AND `~/.config/agentmd/.env`:

```python
def _write_env_file(workspace, api_key, env_var):
    content = _build_env_content(api_key, env_var)

    # Workspace-specific
    ws_env = workspace / "agents" / "_config" / ".env"
    ws_env.parent.mkdir(parents=True, exist_ok=True)
    ws_env.write_text(content)

    # Global fallback
    global_env = _get_config_dir() / ".env"
    global_env.write_text(content)
```

- [ ] **Step 5: Repaginate setup flow**

Update the `setup()` command to add step 4 (defaults):

After the API key step, add:
```python
    # 4. Defaults (optional)
    console.print("\n  [bold]4/4 · Defaults[/bold] [dim](press Enter to keep defaults)[/dim]")

    max_tool_calls_input = Prompt.ask("  Max tool calls per run", default="50")
    max_cost_input = Prompt.ask("  Max cost per run (USD)", default="")
    timeout_input = Prompt.ask("  Timeout (seconds)", default="300")

    extra_defaults = {}
    if max_tool_calls_input:
        extra_defaults["max_tool_calls"] = int(max_tool_calls_input)
    if max_cost_input:
        extra_defaults["max_cost_usd"] = float(max_cost_input)
    if timeout_input:
        extra_defaults["timeout"] = int(timeout_input)
```

Remove the auto-start question.

Update the summary panel to suggest `agentmd new my-first-agent`.

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/ -q --ignore=tests/test_runner_limits.py --ignore=tests/test_runner_timeout.py --ignore=tests/test_orphan_sweep.py --ignore=tests/test_loop_detection.py
```

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: setup wizard repaginated with defaults step, new workspace structure"
```

---

## Task 7: Improve `new` command

**Files:**
- Modify: `agent_md/cli/commands.py`

- [ ] **Step 1: Update AI generation prompt**

Replace the detailed tool list in `_generate_agent_with_ai` with capability descriptions:

```python
GENERATE_PROMPT = """
Generate the content of a markdown agent file for an agent named "{agent_name}" based on this description:
{description}

## File format

YAML frontmatter (between --- delimiters) followed by the system prompt in Markdown.

## Frontmatter fields

Required:
- name: {agent_name}

Optional:
- description: one-line summary
- model: object with provider and name (omit to use default)
- trigger: execution trigger — manual (default), schedule (every/cron), watch (paths)
- settings: temperature, max_tokens, timeout
- history: "low" (default, 10 msgs), "medium" (50), "high" (200), "off"
- paths: dict of alias: path pairs for directories the agent can access

## Agent capabilities

Agents have built-in tools for:
- Reading, writing, and editing files within declared paths
- Searching for files using glob patterns
- Making HTTP requests
- Persistent memory across runs (save, append, retrieve by section)

Custom tools can be added in agents/_config/tools/.

## Rules

- Write ONLY the file content (starts with ---, ends after the prompt)
- System prompt must be clear, specific, and actionable
- Use paths aliases ({{alias}}) for file access, not hardcoded paths
- Only include frontmatter fields that differ from defaults
"""
```

- [ ] **Step 2: Simplify template mode**

Update `_ask_agent_details` to only ask 3 questions:

```python
def _ask_agent_details(agent_name: str) -> str:
    from rich.prompt import Prompt

    console.print()
    description = Prompt.ask("  [cyan]What should this agent do?[/cyan]")

    trigger_type = Prompt.ask(
        "  [cyan]Trigger[/cyan]",
        choices=["manual", "schedule", "watch"],
        default="manual",
    )
    trigger_extra = ""
    if trigger_type == "schedule":
        schedule_val = Prompt.ask("  [cyan]Schedule[/cyan] [dim](e.g. 30m, 2h, or cron expression)[/dim]")
        # ... build trigger_extra
    elif trigger_type == "watch":
        watch_paths = Prompt.ask("  [cyan]Paths to watch[/cyan] [dim](comma-separated)[/dim]")
        # ... build trigger_extra

    agent_paths = Prompt.ask(
        "  [cyan]Paths[/cyan] [dim](alias=path pairs, e.g. data=./data,output=./out)[/dim]",
        default="",
    )

    # Build frontmatter (no provider/model questions)
    lines = ["---", f"name: {agent_name}"]
    if description:
        lines.append(f"description: {description}")
    # ... trigger, paths
    lines.append("---")
    lines.append("")
    lines.append(description or "You are a helpful assistant.")
    lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/ -q --ignore=tests/test_runner_limits.py --ignore=tests/test_runner_timeout.py --ignore=tests/test_orphan_sweep.py --ignore=tests/test_loop_detection.py
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: improve new command — capability-based AI prompt, simplified template"
```

---

## Task 8: Git cleanup

**Files:**
- Delete: `workspace/` from git
- Modify: `.gitignore`

- [ ] **Step 1: Remove workspace/ from git**

```bash
git rm -r workspace/
```

- [ ] **Step 2: Clean up .gitignore**

Remove these lines from `.gitignore`:
```
workspace/output/
workspace/config.yaml
workspace/agents/*
!workspace/agents/hello-world.md
```

Keep `.env` and `*.env*` entries.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: remove legacy workspace/ from repo, clean .gitignore"
```

---

## Task 9: Documentation and release prep

**Files:**
- Create: `docs/migration-0.9.md`
- Modify: `CHANGELOG.md`
- Modify: `README.md`
- Modify: `pyproject.toml` (version bump)
- Modify: `mkdocs.yml`
- Modify: `docs/limits.md` (document max_tokens vs max_execution_tokens)
- Modify: `docs/agent-configuration.md` (update paths, defaults)

- [ ] **Step 1: Create migration guide**

```markdown
# Migration Guide: v0.8.x → v0.9.0

## Breaking Changes

### Workspace restructured

Tools, skills, MCP config, and .env are now inside `agents/_config/`:

```
agents/
├── my-agent.md
└── _config/
    ├── .env
    ├── mcp-servers.json
    ├── tools/
    └── skills/
```

### Database moved

The database is now stored in `~/.local/state/agentmd/` instead of
`workspace/data/`. Previous execution history is not migrated.

### How to upgrade

1. Back up your agents: `cp ~/agentmd/agents/*.md /tmp/backup/`
2. Run `agentmd setup --reconfigure`
3. Copy agents back: `cp /tmp/backup/*.md ~/agentmd/agents/`
4. Move custom tools: `cp -r /old/agents/tools/ ~/agentmd/agents/_config/tools/`
5. Move skills: `cp -r /old/agents/skills/ ~/agentmd/agents/_config/skills/`

### Import paths changed

All `agent_md.core.*` imports have been reorganized:

| Old | New |
|-----|-----|
| `agent_md.core.runner` | `agent_md.execution.runner` |
| `agent_md.core.models` | `agent_md.config.models` |
| `agent_md.core.settings` | `agent_md.config.settings` |
| `agent_md.core.bootstrap` | `agent_md.workspace.bootstrap` |
| `agent_md.core.services` | `agent_md.workspace.services` |

This only affects users who import AgentMD internals directly.
```

- [ ] **Step 2: Update CHANGELOG**

Add v0.9.0 entry following Keep a Changelog format.

- [ ] **Step 3: Update README**

Update workspace structure example in README to show `_config/`.

- [ ] **Step 4: Update docs/limits.md**

Add clear explanation of `max_tokens` (per-call, single response size) vs `max_execution_tokens` (cumulative across all LLM calls in a run).

- [ ] **Step 5: Bump version**

```toml
version = "0.9.0"
```

- [ ] **Step 6: Update mkdocs.yml**

Add migration-0.9.md to nav.

- [ ] **Step 7: Run full test suite and linter**

```bash
uv run pytest tests/ -q --ignore=tests/test_runner_limits.py --ignore=tests/test_runner_timeout.py --ignore=tests/test_orphan_sweep.py --ignore=tests/test_loop_detection.py
uv run ruff check .
uv run ruff format --check .
```

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "docs: migration guide, changelog, version bump for v0.9.0"
```

---

## Summary

| Task | Description | Key files |
|------|-------------|-----------|
| 1 | Move files from core/ to new packages | All 15 core/ files |
| 2 | Update all imports (98 lines) | ~40 files across agent_md/ and tests/ |
| 3 | Remove legacy code | database.py, loader.py, commands.py, models.py |
| 4 | Settings — DB path, .env, new defaults | settings.py, models.py, bootstrap.py |
| 5 | Sandbox — block _config/ | path_context.py |
| 6 | Setup wizard repaginated | setup.py |
| 7 | Improve `new` command | commands.py |
| 8 | Git cleanup | workspace/, .gitignore |
| 9 | Documentation + release | docs/, CHANGELOG, README, pyproject.toml |
