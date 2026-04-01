# Debugging

Troubleshooting guide for common Agent.md errors and issues.

## Common Errors

### 1. Validation Errors

**Error:**
```
ValidationError: 1 validation error for AgentConfig
model.provider
  Input should be 'google', 'openai', 'anthropic', 'ollama', or 'local'
```

**Cause:** Invalid provider name in frontmatter.

**Fix:**
```yaml
# Wrong
model:
  provider: gpt4  # ❌

# Correct
model:
  provider: openai  # ✓
  name: gpt-4
```

---

**Error:**
```
ValidationError: 1 validation error for AgentConfig
triggers.0.cron
  Invalid cron expression: '* * * *'
```

**Cause:** Malformed cron expression (missing field).

**Fix:**
```yaml
# Wrong - only 4 fields
triggers:
  - type: schedule
    cron: "* * * *"  # ❌

# Correct - 5 fields (minute hour day month weekday)
triggers:
  - type: schedule
    cron: "0 9 * * *"  # ✓ Every day at 9 AM
```

**Cron format reminder:**
```
┌───────────── minute (0 - 59)
│ ┌───────────── hour (0 - 23)
│ │ ┌───────────── day of month (1 - 31)
│ │ │ ┌───────────── month (1 - 12)
│ │ │ │ ┌───────────── day of week (0 - 6, Sunday = 0)
│ │ │ │ │
* * * * *
```

---

**Error:**
```
ValidationError: 1 validation error for AgentConfig
paths
  Path '/workspace/../etc/passwd' is outside allowed workspace
```

**Cause:** Path traversal attempt or absolute path outside workspace.

**Fix:**
```yaml
# Wrong
paths:
  - /etc/passwd  # ❌ Outside workspace

# Correct
paths:
  - /workspace/data/  # ✓ Inside workspace
```

### 2. Provider Not Installed

**Error:**
```
ImportError: Provider 'openai' requires langchain-openai package.
Install with: pip install langchain-openai
```

**Cause:** Provider package not installed.

**Fix:**
```bash
# Install specific provider
pip install langchain-openai

# Or install with extras
uv pip install -e ".[openai]"

# Install all providers
uv pip install -e ".[all]"
```

**Check installed providers:**
```bash
# List installed packages
pip list | grep langchain

# Should see:
# langchain-openai       0.x.x
# langchain-anthropic    0.x.x
# langchain-google-genai 0.x.x
```

---

**Error:**
```
AuthenticationError: Invalid API key for provider 'openai'
```

**Cause:** Missing or invalid API key in environment.

**Fix:**
```bash
# Check if API key is set
echo $OPENAI_API_KEY

# If empty, add to .env
echo "OPENAI_API_KEY=sk-proj-your-key-here" >> .env

# Reload environment
source .env  # bash
# or
set -a; source .env; set +a  # More reliable
```

**Verify API key format:**
- OpenAI: `sk-proj-...` (newer) or `sk-...` (legacy)
- Anthropic: `sk-ant-...`
- Google: `AI...` (39 characters)

### 3. Tool Not Found

**Error:**
```
ToolNotFoundError: Tool 'file_read' not found in registry
```

**Cause:** Built-in tool name typo or custom tool not loaded.

**Fix:**
```yaml
# Wrong
tools:
  - name: read_file  # ❌ Wrong name

# Correct (built-in tools)
tools:
  - name: file_read   # ✓
  - name: file_write  # ✓
  - name: http_request  # ✓
```

**Available built-in tools:**
- `file_read` - Read files from allowed paths
- `file_write` - Write files to allowed paths
- `file_edit` - Edit files with targeted text replacement
- `file_glob` - Find files matching a glob pattern
- `http_request` - Make HTTP requests

---

**Error:**
```
ToolNotFoundError: Custom tool 'my_custom_tool' not found
```

**Cause:** Custom tool file not in `tools/` directory or not registered.

**Fix:**
```bash
# Check tools directory
ls -la /Users/zfab/repos/agentmd/tools/

# Custom tool must be:
# 1. In tools/ directory
# 2. Named <tool_name>.py
# 3. Define a function decorated with @tool
```

**Example custom tool (`tools/my_custom_tool.py`):**
```python
from langchain_core.tools import tool

@tool
def my_custom_tool(input: str) -> str:
    """Description of what the tool does."""
    return f"Processed: {input}"
```

### 4. MCP Connection Failed

**Error:**
```
MCPConnectionError: Failed to start MCP server 'filesystem'
Command: npx -y @modelcontextprotocol/server-filesystem
Error: ENOENT: no such file or directory
```

**Cause:** `npx` not installed or MCP server package not found.

**Fix:**
```bash
# Check if npx is installed
which npx

# If not found, install Node.js
brew install node  # macOS
# or
apt install nodejs npm  # Linux

# Verify
npx --version
```

**Test MCP server manually:**
```bash
# Try running MCP server directly
npx -y @modelcontextprotocol/server-filesystem /workspace

# Should output JSON on stdout
# Press Ctrl+C to stop
```

---

**Error:**
```
MCPConnectionError: Server 'filesystem' closed unexpectedly
```

**Cause:** MCP server crashed or invalid arguments.

**Fix:**
```yaml
# Check server arguments
mcp:
  servers:
    filesystem:
      command: "npx"
      args:
        - "-y"
        - "@modelcontextprotocol/server-filesystem"
        - "/workspace/data"  # Must be valid directory
```

**Debug MCP server:**
```bash
# Run server manually with verbose output
MCP_DEBUG=1 npx -y @modelcontextprotocol/server-filesystem /workspace/data
```

### 5. Path Permissions

**Error:**
```
PermissionError: Access denied to path '/workspace/data/secrets.txt'
```

**Cause:** File not in allowed `paths`.

**Fix:**
```yaml
# Add path to allowed list
paths:
  - /workspace/data/secrets.txt
```

**Or check file actually exists:**
```bash
ls -la /workspace/data/secrets.txt

# If permission denied:
chmod 644 /workspace/data/secrets.txt
```

---

**Error:**
```
PathSecurityError: Write path '/workspace/input.json' not allowed
```

**Cause:** Agent trying to write to directory not in `paths`.

**Fix:**
```yaml
# Wrong
paths:
  - /output/  # Can only access /output/

# Agent tries to write to /workspace/ → Error

# Correct
paths:
  - /output/
  - /workspace/results/  # Add if needed
```

**Best practice:** Only include the paths the agent actually needs.
```yaml
paths:
  - /workspace/data/  # Source data
  - /output/          # Generated files
```

### 6. Timeouts

**Error:**
```
TimeoutError: Agent execution exceeded 120 seconds
```

**Cause:** Agent taking too long, default timeout reached.

**Fix:**
```yaml
# Increase timeout
settings:
  timeout: 300  # 5 minutes
```

**Or investigate why agent is slow:**
```bash
# Check logs for what it was doing
agentmd logs my-agent --verbose

# Look for:
# - Infinite loops (max_iterations reached)
# - Slow tool calls (http_request to slow API)
# - Large file operations
```

---

**Error:**
```
HTTPTimeoutError: Request to https://api.example.com timed out after 30s
```

**Cause:** HTTP request tool timeout.

**Fix:**
```yaml
# Increase HTTP timeout
tools:
  - name: http_request
    config:
      timeout: 60  # Increase from default 30s
```

### 7. Model Errors

**Error:**
```
InvalidRequestError: maximum context length is 4096 tokens, requested 8192
```

**Cause:** Prompt too long for model's context window.

**Fix:**
```yaml
# Use model with larger context
model:
  provider: openai
  name: gpt-4-turbo  # 128K context vs gpt-3.5-turbo 4K
```

**Or reduce prompt length:**
- Shorten system prompt
- Reduce conversation history
- Use smaller tool descriptions

---

**Error:**
```
RateLimitError: Rate limit exceeded for gpt-4
```

**Cause:** Too many requests to LLM provider.

**Fix:**
```bash
# Check schedule frequency
# If cron: "* * * * *" (every minute) → reduce

# Or add delay between runs
```

```yaml
# Reduce frequency
triggers:
  - type: schedule
    cron: "*/5 * * * *"  # Every 5 minutes instead of 1
```

## How to Read Logs

### Basic Logs

```bash
# List all executions for an agent
agentmd logs my-agent

# Output:
# Execution ID: abc123 | Started: 2026-03-11 09:00:00 | Status: success
# Execution ID: def456 | Started: 2026-03-11 09:15:00 | Status: failed
```

### Verbose Logs

```bash
# Show full details
agentmd logs my-agent --verbose

# Output:
# Execution: abc123
# Agent: my-agent
# Started: 2026-03-11 09:00:00
# Completed: 2026-03-11 09:01:23
# Status: success
# Input tokens: 1,234
# Output tokens: 567
# Total tokens: 1,801
#
# Messages:
# [AI] Analyzing input file...
# [TOOL] file_read: /workspace/data/input.txt
# [AI] Processing complete. Writing output...
# [TOOL] file_write: /output/result.txt
# [AI] Task completed successfully.
```

### Filter by Status

```bash
# Only show failed executions
agentmd logs my-agent --status failed

# Only show successful executions
agentmd logs my-agent --status success
```

### Filter by Date

```bash
# Show logs from last 24 hours
agentmd logs my-agent --since "24 hours ago"

# Show logs from specific date
agentmd logs my-agent --since "2026-03-10"
```

### Export Logs

```bash
# Export to JSON
agentmd logs my-agent --format json > logs.json

# Export to CSV
agentmd logs my-agent --format csv > logs.csv
```

## Verbosity Levels

### Level 0: Silent

```bash
# No output except errors
agentmd run my-agent --quiet
```

Use for: Cron jobs, background tasks

### Level 1: Normal (Default)

```bash
# Show agent messages only
agentmd run my-agent
```

Output:
```
Starting agent: my-agent
[AI] Analyzing data...
[AI] Writing report...
Execution complete.
```

### Level 2: Verbose

```bash
# Show tool calls and details
agentmd run my-agent --verbose
```

Output:
```
Starting agent: my-agent
[AI] Analyzing data...
[TOOL CALL] file_read
  Path: /workspace/data/input.txt
  Result: 1,234 bytes read
[AI] Writing report...
[TOOL CALL] file_write
  Path: /output/report.txt
  Result: 567 bytes written
Execution complete.
Token usage: 1,801 tokens ($0.05)
```

### Level 3: Debug

```bash
# Show everything including internal state
agentmd run my-agent --debug
```

Output:
```
[DEBUG] Loading agent from: /workspace/my-agent.md
[DEBUG] Parsed config: AgentConfig(name='my-agent', ...)
[DEBUG] Creating chat model: provider=openai, name=gpt-4
[DEBUG] Building ReAct graph...
[DEBUG] Starting execution...
Starting agent: my-agent
[DEBUG] State: messages=[SystemMessage(...)]
[AI] Analyzing data...
[DEBUG] Tool call: file_read(path="/workspace/data/input.txt")
[TOOL CALL] file_read
  Path: /workspace/data/input.txt
  Result: 1,234 bytes read
[DEBUG] State: messages=[SystemMessage(...), HumanMessage(...), AIMessage(...)]
...
```

Use for: Debugging validation errors, provider issues, graph execution

## Debugging Workflow

1. **Validate syntax:**
   ```bash
   agentmd validate workspace/my-agent.md
   ```

2. **Check provider installed:**
   ```bash
   pip list | grep langchain-openai
   ```

3. **Test with dry run:**
   ```bash
   agentmd run my-agent --dry-run
   ```

4. **Run with verbose output:**
   ```bash
   agentmd run my-agent --verbose
   ```

5. **Check logs if failed:**
   ```bash
   agentmd logs my-agent --status failed --verbose
   ```

6. **Enable debug mode:**
   ```bash
   agentmd run my-agent --debug
   ```

## Common Issues & Quick Fixes

| Issue | Quick Fix |
|-------|-----------|
| Validation error | `agentmd validate <file>` |
| Provider not found | `pip install langchain-<provider>` |
| API key error | Check `.env` file, `echo $OPENAI_API_KEY` |
| Tool not found | Check tool name in `tools:` list |
| MCP error | Test server manually: `npx -y <mcp-package> <args>` |
| Path permission | Add path to `paths` |
| Timeout | Increase `settings.timeout` |
| Rate limit | Reduce schedule frequency |
| Context too long | Use model with larger context or shorten prompt |
| Import error | `uv sync` to reinstall dependencies |

## Getting Help

1. **Check documentation:**
   ```bash
   agentmd --help
   agentmd run --help
   ```

2. **Validate config:**
   ```bash
   agentmd validate workspace/my-agent.md
   ```

3. **Enable verbose logging:**
   ```bash
   agentmd run my-agent --verbose --debug
   ```

4. **Check database:**
   ```bash
   # SQLite database location
   ls -la /Users/zfab/repos/agentmd/data/executions.db

   # Query directly
   sqlite3 data/executions.db "SELECT * FROM executions ORDER BY started_at DESC LIMIT 5;"
   ```

5. **Test components individually:**
   ```bash
   # Test provider
   python -c "from langchain_openai import ChatOpenAI; print(ChatOpenAI())"

   # Test MCP server
   npx -y @modelcontextprotocol/server-filesystem /workspace

   # Test tool
   python -c "from agent_md.tools import file_read; print(file_read)"
   ```
