# Custom Tools

Custom tools live in `<workspace>/agents/tools/` and are declared per agent
via the `custom_tools` (or `tools`) frontmatter field.

## Adding external dependencies

If your custom tool needs a Python package that isn't already in the
AgentMD core install, reinstall the CLI with the `--with` flag:

    uv tool install agentmd --with python-frontmatter --force

The `--force` flag is required to replace the existing install. Pass
`--with` multiple times to add several packages:

    uv tool install agentmd --with python-frontmatter --with httpx --force

## Sandbox and custom tools

Custom tools run with full process permissions. AgentMD does **not**
enforce the agent's `paths` whitelist on them — they are your code and
your responsibility.

If you want to opt in to the same path validation that built-in tools
use, import from `agent_md.sdk`:

```python
from langchain_core.tools import tool
from agent_md.sdk import resolve_path

@tool
def my_custom_tool(file: str) -> str:
    """Read a file with sandbox validation."""
    resolved, error = resolve_path(file)
    if error:
        return error
    return resolved.read_text()
```

See [Custom Tools — SDK](tools/custom-tools.md#sdk-path-resolution-for-custom-tools) for full documentation.
