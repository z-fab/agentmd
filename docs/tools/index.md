# Tools

Agent.md provides three types of tools for your agents.

## Built-in Tools

Always available, no configuration needed:

- **[file_read](built-in-tools.md#file_read)** — Read files from workspace
- **[file_write](built-in-tools.md#file_write)** — Write files to allowed paths
- **[http_request](built-in-tools.md#http_request)** — Make HTTP calls (GET, POST, etc.)

[Learn more →](built-in-tools.md)

## Custom Tools

Extend with Python:

```python
# workspace/agents/tools/my_tool.py
from langchain_core.tools import tool

@tool
def my_tool(input: str) -> str:
    """What the tool does."""
    return f"Result: {input}"
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
