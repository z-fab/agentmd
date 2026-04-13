# Tools

Agent.md provides three types of tools for your agents.

## Built-in Tools

Always available, no configuration needed:

- **[file_read](built-in-tools.md#file_read)** — Read files from workspace
- **[file_write](built-in-tools.md#file_write)** — Write files to allowed paths
- **[file_edit](built-in-tools.md#file_edit)** — Edit files with targeted text replacement
- **[file_move](built-in-tools.md#file_move)** — Move or rename files
- **[file_glob](built-in-tools.md#file_glob)** — Find files matching a pattern
- **[http_request](built-in-tools.md#http_request)** — Make HTTP calls (GET, POST, etc.)
- **[memory_save / memory_append / memory_retrieve](built-in-tools.md#memory_save)** — Long-term memory
- **[skill_use / skill_read_file / skill_run_script](built-in-tools.md#skill_use)** — [Skills](../skills.md) (when enabled)

[Learn more →](built-in-tools.md)

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

## MCP Integration

Use external MCP servers:

```yaml
mcp:
  - fetch
  - github
```

[MCP integration →](mcp-integration.md)
