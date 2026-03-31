# File Tools Redesign

## Goal

Improve file manipulation tools and reorganize `agent_md/tools/` into domain-based subpackages to support the growing number of built-in tools.

## Decisions

- No file state tracker — no prior-read enforcement, no mtime checks
- Binary detection via null byte check (first 8KB), no extension blocklist
- Full-file read cap at 500 lines
- Glob results capped at 100
- Factory pattern preserved (`create_*_tool` with closure)
- `file_list` removed — replaced by `file_glob`
- System prompt instructs the LLM to read files before editing/overwriting
- Unified path resolution — all tools resolve relative paths from workspace root, no separate output dir logic

---

## 1. Tools directory reorganization

Current flat structure under `agent_md/tools/` becomes domain-based subpackages:

```
agent_md/tools/
├── files/
│   ├── __init__.py          # exports create_file_read_tool, create_file_write_tool,
│   │                        #   create_file_edit_tool, create_file_glob_tool
│   ├── read.py
│   ├── write.py
│   ├── edit.py              # new
│   └── glob.py              # new
├── memory/
│   ├── __init__.py          # exports create_memory_save_tool, create_memory_append_tool,
│   │                        #   create_memory_retrieve_tool
│   ├── save.py
│   ├── append.py
│   └── retrieve.py
├── skills/
│   ├── __init__.py          # exports create_skill_use_tool, create_skill_read_file_tool,
│   │                        #   create_skill_run_script_tool
│   ├── use.py
│   ├── read_file.py
│   └── run_script.py
├── http/
│   ├── __init__.py          # exports create_http_request_tool
│   └── request.py
├── registry.py              # imports from subpackage __init__.py only
└── custom_loader.py         # unchanged
```

Rules:

- Each subpackage `__init__.py` exports only the factory functions.
- `registry.py` imports from subpackage `__init__` — no deep imports.
- `agent_md/skills/tools.py` (current location of skill tools) moves to `agent_md/tools/skills/`.
- `file_list.py` is deleted — `file_glob` replaces it.
- `memory.py` (single file) splits into 3 modules, one per tool.

## 2. file_read improvements

**Signature:** `file_read(path, offset=None, limit=None, with_line_numbers=True)`

Parameters:

- `path` (str) — absolute or relative path (resolved from workspace root)
- `offset` (int, optional) — 1-based start line
- `limit` (int, optional) — number of lines to return
- `with_line_numbers` (bool, default True) — prefix each line with `N | `

Behavior:

- Without offset/limit: reads entire file. If file exceeds 500 lines, returns an error asking the model to retry with offset/limit.
- With offset/limit: reads lazily line by line — does not load the entire file into memory.
- Output starts with a header: path, line range, and total line count.
- Binary detection: reads first 8KB, rejects if null bytes found (clear error message).
- Normalizes line endings to `\n`.
- Path validation unchanged.

## 3. file_edit (new)

**Signature:** `file_edit(path, old_text, new_text, replace_all=False)`

Parameters:

- `path` (str) — absolute or relative path (resolved from output dir)
- `old_text` (str) — text to find and replace
- `new_text` (str) — replacement text
- `replace_all` (bool, default False) — replace all occurrences

Behavior:

- Replaces `old_text` with `new_text` in the file.
- `old_text` not found → error.
- Multiple matches with `replace_all=False` → error stating how many matches were found.
- `replace_all=True` → replaces all occurrences.
- `old_text=""` and file does not exist → creates the file with `new_text` as content.
- `old_text=""` and file exists → error.
- Returns summary: `updated path (N replacements, ~M lines changed)` or `created path (N lines)`.

## 4. file_write hardening

**Signature:** `file_write(path, content)` — unchanged.

Changes:

- Return message now includes: `created/updated path (N chars, M lines)`.
- Binary check on `content` before writing (null byte detection) — rejects with error.
- Preserves automatic parent directory creation.
- Path validation unchanged.

## 5. file_glob (new, replaces file_list)

**Signature:** `file_glob(pattern)`

Parameters:

- `pattern` (str) — glob pattern (e.g. `**/*.py`, `src/**/*.md`)

Behavior:

- Globs from workspace root.
- Results filtered by the agent's allowed paths.
- Maximum 100 results, sorted alphabetically.
- If more than 100 matches: returns first 100 + message `(showing 100 of N results, refine your pattern)`.
- Returns absolute paths, one per line.
- Read-only, no side effects.

## 6. Path resolution simplification

Remove `resolve_from` parameter from `validate_path`. All tools resolve relative paths the same way: relative to workspace root. Absolute paths are used as-is.

Changes to `PathContext`:

- Remove `resolve_from` parameter from `validate_path` — always resolves from workspace root.
- Remove `get_default_output_dir` method.
- Remove `_resolve_for_output` method.
- Remove `output_dir` field (no longer used).
- Permission check remains: resolved path must be within one of the agent's allowed paths.

## 7. System prompt update

The `## File Access` block injected by `builder.py` (`_build_file_access_prompt`) is updated to:

- List the 4 file tools: `file_read`, `file_write`, `file_edit`, `file_glob`.
- Remove all references to `file_list`.
- Document new `file_read` parameters (offset, limit, with_line_numbers).
- Explain when to use `file_edit` vs `file_write`: edit for surgical changes, write for create/full overwrite.
- Explain `file_glob` for file discovery.
- Remove separate output directory references — all paths resolve from workspace root.
- Add rule: **always read a file with `file_read` before modifying it with `file_edit` or overwriting it with `file_write`**.

## 8. Documentation update

Update user-facing documentation to reflect the new file tools:

- Update tool reference docs with new signatures, parameters, and behavior for all 4 file tools.
- Document the unified path resolution: all relative paths resolve from workspace root.
- Document the removal of `file_list` and its replacement by `file_glob`.
- Document the `file_edit` tool and when to use it vs `file_write`.
- Document the 500-line cap on `file_read` and how to use offset/limit for large files.
