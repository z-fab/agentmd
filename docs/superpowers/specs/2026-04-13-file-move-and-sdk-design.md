# file_move Tool + Custom Tool SDK

**Goal:** Add a `file_move` built-in tool and create `agent_md.sdk` — a public module with utility functions for custom tool authors.

**Architecture:** `file_move` follows the existing built-in tool factory pattern. The SDK uses a `contextvars.ContextVar` set by the runner to give custom tools access to agent context without factories or injection.

**Scope:** Issues #6 and #13.

---

## 1. file_move Tool (#6)

### Location

`agent_md/tools/files/move.py`

### Behavior

- Factory: `create_file_move_tool(agent_config, path_context)` — same pattern as file_read, file_write, etc.
- Signature exposed to LLM: `file_move(source: str, destination: str) -> str`
- Validates **both** source and destination via `path_context.validate_path()`
- Source must exist and be a file (not a directory)
- Creates destination parent directories if needed (`mkdir(parents=True, exist_ok=True)`)
- Moves via `shutil.move()` (atomic on same filesystem)
- Returns `"Moved: {source} -> {destination}"` on success
- Returns `"ERROR: ..."` on failure (same pattern as other tools)

### Sandbox Rules

- Source must be within agent's declared paths
- Destination must be within agent's declared paths
- Cannot move into `_config/`, agents dir, or other blocked paths
- Cannot move `.env` or `.db` files

### Registration

Add to `agent_md/tools/registry.py` alongside other file tools in `resolve_builtin_tools()`.

---

## 2. agent_md.sdk (#13)

### Location

`agent_md/sdk.py` — replaces `agent_md/sandbox.py`.

### Context Mechanism

A `contextvars.ContextVar` stores `(agent_config, path_context)` for the current execution. The runner sets it before executing the graph and resets it after. Since `contextvars` is per-asyncio-task, concurrent agent runs are isolated.

### Public API

```python
def resolve_path(path: str) -> tuple[Path | None, str | None]
```
Resolve aliases (`{output}/file.txt`) and validate sandbox rules. Returns `(resolved_absolute_path, None)` on success or `(None, error_message)` on failure.

```python
def workspace_root() -> Path
```
Absolute path to the workspace root directory.

```python
def agent_name() -> str
```
Name of the currently executing agent.

```python
def agent_paths() -> dict[str, Path]
```
Agent's declared path aliases, resolved to absolute paths. Example: `{"output": Path("/abs/path/to/output"), "data": Path("/abs/path/to/data")}`.

### Error Handling

All functions raise `RuntimeError("Must be called within an agent execution")` if called outside of an agent run (contextvar not set).

### Runner Integration

In `agent_md/execution/runner.py`, before `stream_agent_graph()`:

```python
from agent_md.sdk import _set_context, _reset_context

token = _set_context(config, self.path_context)
try:
    # ... stream_agent_graph() ...
finally:
    _reset_context(token)
```

`_set_context` and `_reset_context` are private helpers in `sdk.py` — not part of the public API.

---

## 3. Cleanup

- Delete `agent_md/sandbox.py` (replaced by `agent_md/sdk`)
- Remove any imports of `agent_md.sandbox` (search codebase)

---

## 4. Documentation

- Update `README.md` — mention `file_move` in tools list, mention SDK for custom tools
- Update `docs/tools.md` — add `file_move` documentation
- Update or create `docs/custom-tools.md` — document SDK usage with examples
- Update `docs/migration-0.9.md` if needed — note `sandbox.py` removal

---

## 5. Tests

### file_move

- Move file successfully (source removed, destination exists)
- Source does not exist → error
- Source is a directory → error
- Destination blocked by sandbox → error
- Source blocked by sandbox → error
- Move to subdirectory that doesn't exist yet (parent creation)
- Move `.env` file → blocked
- Move `.db` file → blocked

### SDK

- `resolve_path` works correctly within agent execution
- `resolve_path` with alias resolution
- `resolve_path` with sandbox violation → returns error
- All functions raise `RuntimeError` outside execution context
- `workspace_root()` returns correct path
- `agent_name()` returns correct name
- `agent_paths()` returns resolved dict
- Concurrent runs have isolated contexts
