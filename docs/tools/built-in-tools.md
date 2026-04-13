# Built-in Tools

Agent.md provides built-in tools for file I/O, HTTP, long-term memory, and skills — all with built-in security controls.

## file_read

Read files from the local filesystem with path security restrictions.

### Signature

```python
def file_read(path: str, offset: int | None = None, limit: int | None = None, with_line_numbers: bool = True) -> str
```

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `path` | `str` | Yes | - | Absolute or relative path to file |
| `offset` | `int` | No | `None` | 1-based line number to start reading from |
| `limit` | `int` | No | `None` | Number of lines to read |
| `with_line_numbers` | `bool` | No | `True` | Prefix each line with `N | ` |

### Behavior

- **Relative paths** resolve from workspace root
- **Absolute paths** checked against security restrictions
- Full reads are capped at 500 lines — use `offset` and `limit` for larger files
- Binary files are rejected (files containing null bytes)
- Returns file contents as UTF-8 string; lines prefixed as `N | ` when `with_line_numbers=True`
- Returns error message if access denied or file not found

### Security Rules

1. **Allowed paths**: Only paths in agent's `paths` config (defaults to workspace root)
2. **Blocked paths**: Cannot read `agents/`, `.env`, or `.env.*` files
3. **Watch paths**: Automatically added to allowed paths if agent uses `watch` trigger

### Configuration

```yaml
---
name: data-processor
paths:
  - data/           # Allow directory
  - config.json     # Allow specific file
---
```

### Examples

**Read configuration file:**
```yaml
---
name: config-reader
paths: config/
---

Read `config/app.json` and summarize the settings.
```

**Read a large file in chunks:**
```yaml
---
name: log-reader
paths: logs/
---

Read lines 1-500 of `logs/app.log`, then lines 501-1000 if needed.
```
Use `file_read("logs/app.log", offset=1, limit=500)` then `file_read("logs/app.log", offset=501, limit=500)`.

**Read from watched paths:**
```yaml
---
name: file-monitor
trigger:
  type: watch
  paths: /var/log/app.log
---

When the log file changes, summarize the last 100 lines.
```
Watch paths are automatically added to allowed read paths.

**Handle missing files gracefully:**
Agents should expect error messages like `ERROR: File not found: data/optional.txt` and continue execution with defaults.

---

## file_write

Write content to files with path security restrictions. Creates parent directories automatically.

### Signature

```python
def file_write(path: str, content: str) -> str
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `path` | `str` | Yes | Absolute or relative path |
| `content` | `str` | Yes | Text content (UTF-8) |

### Behavior

- **Relative paths** resolve from workspace root
- **Absolute paths** checked against security restrictions
- Binary content is rejected (content containing null bytes)
- Creates parent directories automatically
- Overwrites existing files without warning
- Returns confirmation: `Created path (N chars, M lines)` or `Updated path (N chars, M lines)`

### Security Rules

1. **Allowed paths**: Only paths in agent's `paths` config (defaults to workspace root)
2. **Blocked paths**: Cannot write to `agents/`, `.db`, `.env`, or `.env.*` files

### Configuration

```yaml
---
name: report-generator
paths:
  - reports/
  - archive/
---
```

### Examples

**Write simple output file:**
```yaml
---
name: hello-world
---

Write a greeting to `greeting.txt`.
```
The agent will call `file_write("greeting.txt", "Hello from Agent.md!")` → `workspace/greeting.txt`

**Generate timestamped reports:**
```yaml
---
name: daily-report
paths: reports/
---

Generate a daily summary and save to `reports/YYYY-MM-DD.md`.
```
The agent will call `file_write("reports/2026-03-11.md", "# Daily Report\n\n...")` → creates subdirectories automatically.

**Create multi-file outputs:**
```yaml
---
name: project-generator
paths: projects/my-app/
---

Create project structure:
- `projects/my-app/src/main.py`
- `projects/my-app/src/utils.py`
- `projects/my-app/README.md`
```
The agent calls `file_write` multiple times; parent directories are created automatically.

**Append pattern:**
`file_write` always overwrites. To append, read → modify → write back:
```yaml
paths: logs/
```
Read `logs/events.log`, append new entry, write back.

---

## file_edit

Edit files with targeted text replacement. Always read the file first with `file_read`.

### Signature

```python
def file_edit(path: str, old_text: str, new_text: str, replace_all: bool = False) -> str
```

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
- Empty `old_text` creates a new file (fails if file already exists)
- Returns summary with replacement count and lines changed

### When to use

- **`file_edit`**: surgical changes — fix a line, rename a variable, update a config value
- **`file_write`**: create new files or full rewrites

---

## file_glob

Find files matching a glob pattern. Use this to discover files before reading.

### Signature

```python
def file_glob(pattern: str) -> str
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `pattern` | `str` | Yes | Glob pattern (e.g. `**/*.py`, `src/**/*.md`) |

### Behavior

- Globs from workspace root
- Filtered by agent's allowed paths
- Returns up to 100 absolute paths, sorted alphabetically
- If more than 100 matches, shows first 100 with a count of omitted results
- Read-only, no side effects

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

---

## http_request

Make HTTP requests to external APIs and services.

### Signature

```python
def http_request(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    body: str | None = None,
) -> str
```

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `url` | `str` | Yes | - | Full URL (must include scheme) |
| `method` | `str` | No | `GET` | HTTP method: GET, POST, PUT, DELETE, PATCH |
| `headers` | `dict` | No | `None` | Request headers dictionary |
| `body` | `str` | No | `None` | Request body (for POST/PUT/PATCH) |

### Behavior

- **Timeout**: 30 seconds per request
- **Redirects**: Followed automatically
- **Response**: Body truncated to 5000 characters
- **Output**: Status code + response body

### Examples

**Simple GET request:**
```yaml
---
name: api-fetcher
---

Fetch data from https://api.github.com/repos/python/cpython and summarize it.
```
Agent calls: `http_request("https://api.github.com/repos/python/cpython")`

**Authenticated API call:**
```yaml
---
name: authenticated-api
---

Call https://api.example.com/user with Authorization header "Bearer abc123".
```
Agent calls:
```python
http_request(
    "https://api.example.com/user",
    headers={"Authorization": "Bearer abc123"}
)
```

**POST with JSON body:**
```yaml
---
name: webhook-sender
---

Send POST to https://hooks.example.com/notify with JSON: {"event": "test", "message": "Hello"}
```
Agent calls:
```python
http_request(
    "https://hooks.example.com/notify",
    method="POST",
    headers={"Content-Type": "application/json"},
    body='{"event": "test", "message": "Hello"}'
)
```

---

## memory_save

Save or replace a named section in the agent's long-term memory file.

### Signature

```python
def memory_save(section: str, content: str) -> str
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `section` | `str` | Yes | Section name (e.g., `"user_preferences"`) |
| `content` | `str` | Yes | Content to store (replaces existing) |

### Behavior

- Creates the `.memory.md` file if it doesn't exist
- If the section exists, **replaces** its content entirely
- If the section doesn't exist, creates it
- Ideal for rewriting or summarizing a section

### Example

```yaml
---
name: assistant
---

When the user shares preferences, save them to the "preferences" memory section.
```

---

## memory_append

Append content to a named section in the agent's long-term memory file.

### Signature

```python
def memory_append(section: str, content: str) -> str
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `section` | `str` | Yes | Section name |
| `content` | `str` | Yes | Content to append |

### Behavior

- Creates the section if it doesn't exist
- Appends content to the end of the section
- **Digest hint**: When a section exceeds 50 lines, the response suggests summarizing with `memory_save`

### Example

```yaml
---
name: logger
trigger:
  type: schedule
  every: 1h
---

Check system status and append a timestamped entry to the "status_log" memory section.
```

---

## memory_retrieve

Read the content of a named section from the agent's long-term memory file.

### Signature

```python
def memory_retrieve(section: str) -> str
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `section` | `str` | Yes | Section name to retrieve |

### Behavior

- Returns the section content as a string
- If the section doesn't exist, returns available section names
- If no memory file exists, returns a helpful message

### Example

```yaml
---
name: researcher
---

Before starting research, retrieve the "known_topics" memory section
to avoid duplicating previous work.
```

For detailed usage, examples, and best practices, see [Memory](../memory.md).

---

## skill_use

Activate a skill. Only available when the agent has `skills` configured.

### Signature

```python
def skill_use(skill_name: str, arguments: str = "") -> str
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `skill_name` | `str` | Yes | Name of the skill to activate |
| `arguments` | `str` | No | Arguments for variable substitution (`$ARGUMENTS`) |

### Behavior

- Validates the skill is enabled for this agent
- Returns a short activation confirmation
- The `post_tool_processor` graph node then loads the full `SKILL.md`, applies substitutions (`$ARGUMENTS`, `${SKILL_DIR}`, `` !`command` ``), and injects the instructions as a meta message (`HumanMessage` with `<skill-context>` tags)

This design ensures skill instructions are treated as directives (user messages) rather than optional data (tool results), improving instruction-following by the LLM.

### Example

```yaml
---
name: assistant
skills:
  - review-code
---

Use skills to help with code tasks.
```

Agent calls: `skill_use("review-code", "main.py")` → returns `"Skill 'review-code' activated successfully."` → skill instructions are injected as a follow-up meta message.

---

## skill_read_file

Read a supporting file from a skill's directory. Only available when the agent has `skills` configured.

### Signature

```python
def skill_read_file(skill_name: str, file_path: str) -> str
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `skill_name` | `str` | Yes | Name of the skill |
| `file_path` | `str` | Yes | Relative path within skill directory |

### Behavior

- Validates skill access and path security (no directory traversal)
- Returns file contents as UTF-8 string
- Works with any file in the skill directory (`references/`, `scripts/`, etc.)

---

## skill_run_script

Execute a script from a skill's `scripts/` directory. Only available when the agent has `skills` configured.

### Signature

```python
def skill_run_script(skill_name: str, script_name: str, script_args: str = "") -> str
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `skill_name` | `str` | Yes | Name of the skill |
| `script_name` | `str` | Yes | Script filename in `scripts/` |
| `script_args` | `str` | No | Arguments passed to the script |

### Behavior

- Auto-detects interpreter: `.py` → Python, `.sh` → Bash, `.js` → Node
- Runs with 30-second timeout and skill directory as cwd
- Returns stdout + stderr

For full documentation, see [Skills](../skills.md).

---

## Security Best Practices

### File Access
1. **Least privilege**: Only grant minimum required paths
2. **Separate workspaces**: Use different roots for different trust levels
3. **Environment files**: Never make `.env` files readable

### HTTP Requests
1. **Use environment variables**: Never hardcode secrets in URLs or headers — use `${VAR}` syntax in the prompt body, which is resolved from `.env` at runtime
   ```yaml
   Call the API at ${API_ENDPOINT} with header "X-API-Key: ${API_KEY}"
   ```
   See [Environment Variable Substitution](../agent-configuration.md#environment-variable-substitution) for details.
2. **Validate responses**: Check HTTP status codes before processing
3. **Rate limiting**: Use scheduled triggers (`every: 1m`) to avoid overwhelming APIs
4. **Timeout awareness**: 30-second limit may be too short for slow APIs

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `Access denied: 'data/file.txt' is outside allowed paths` | Add path to `paths` config: `paths: [data/]` |
| `File not found: data/data.txt` | Verify file exists, check spelling (case-sensitive), verify path resolution |
| `Binary file detected` | `file_read` and `file_write` only work with text files |
| `old_text not found` | `file_edit` requires an exact match — read the file first with `file_read` |
| `Request timed out after 30s` | Use faster APIs or split large requests into smaller chunks |
| File created but empty | Verify `content` parameter isn't empty and agent generated content successfully |

---

## Next Steps

- [Memory system →](../memory.md)
- [Create custom tools →](custom-tools.md)
- [MCP integration →](mcp-integration.md)
- [Path configuration →](../paths-and-security.md)
