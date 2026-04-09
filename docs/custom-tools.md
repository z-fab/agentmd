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
use, import the helper from `agent_md.sandbox`:

```python
from langchain_core.tools import tool
from agent_md.sandbox import validate_path

@tool
def my_custom_tool(file: str, agent_config, path_context) -> str:
    resolved, error = validate_path(file, agent_config, path_context)
    if error:
        return error
    return resolved.read_text()
```
