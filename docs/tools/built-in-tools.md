# Built-in Tools

Agent.md provides three always-available tools for file I/O and HTTP operations with built-in security controls.

## file_read

Read files from the local filesystem with path security restrictions.

### Signature

```python
def file_read(path: str) -> str
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `path` | `str` | Yes | Absolute or relative path to file |

### Behavior

- **Relative paths** resolve from workspace root
- **Absolute paths** checked against security restrictions
- Returns file contents as UTF-8 string
- Returns error message if access denied or file not found

### Security Rules

1. **Allowed read paths**: Only paths in agent's `read` config (defaults to workspace root)
2. **Blocked paths**: Cannot read `agents/`, `.env`, or `.env.*` files
3. **Watch paths**: Automatically added to allowed paths if agent uses `watch` trigger

### Configuration

```yaml
---
name: data-processor
read:
  - data/           # Allow directory
  - config.json     # Allow specific file
---
```

### Examples

**Read configuration file:**
```yaml
---
name: config-reader
read: config/
---

Read `config/app.json` and summarize the settings.
```

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

- **Relative paths** resolve from first directory in `write` config, or `output/` if not specified
- **Absolute paths** checked against security restrictions
- Creates parent directories automatically
- Overwrites existing files without warning
- Returns confirmation with file path and character count

### Security Rules

1. **Allowed write paths**: Only paths in agent's `write` config (defaults to `output/`)
2. **Blocked paths**: Cannot write to `agents/`, `.db`, `.env`, or `.env.*` files

### Configuration

```yaml
---
name: report-generator
write:
  - reports/          # Default write directory
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
The agent will call `file_write("greeting.txt", "Hello from Agent.md!")` → `{output_dir}/greeting.txt`

**Generate timestamped reports:**
```yaml
---
name: daily-report
write: reports/
---

Generate a daily summary and save to `reports/YYYY-MM-DD.md`.
```
The agent will call `file_write("2026-03-11.md", "# Daily Report\n\n...")` → creates subdirectories automatically.

**Create multi-file outputs:**
```yaml
---
name: project-generator
write: projects/my-app/
---

Create project structure:
- `src/main.py`
- `src/utils.py`
- `README.md`
```
The agent calls `file_write` multiple times; parent directories are created automatically.

**Append pattern:**
`file_write` always overwrites. To append, read → modify → write back:
```yaml
read: logs/
write: logs/
```
Read `logs/events.log`, append new entry, write back.

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
| `Access denied: 'data/file.txt' is outside allowed read paths` | Add path to `read` config: `read: [data/]` |
| `File not found: output/data.txt` | Verify file exists, check spelling (case-sensitive), verify path resolution |
| `Request timed out after 30s` | Use faster APIs or split large requests into smaller chunks |
| File created but empty | Verify `content` parameter isn't empty and agent generated content successfully |

---

## Next Steps

- [Create custom tools →](custom-tools.md)
- [MCP integration →](mcp-integration.md)
- [Path configuration →](../paths-and-security.md)
