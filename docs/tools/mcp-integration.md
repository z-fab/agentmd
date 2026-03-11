# MCP Integration

Agent.md integrates with the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) to provide access to external tool servers. Use pre-built MCP servers (fetch, GitHub, Slack, filesystem, etc.) without writing custom Python code.

## Overview

MCP allows you to:

- Use pre-built tool servers (fetch, filesystem, GitHub, Slack, etc.)
- Connect to remote APIs through standardized interfaces
- Share tools across multiple agents
- Keep agent logic separate from tool implementation

Agent.md supports both **stdio** (local processes) and **HTTP** (remote servers) transports.

---

## Quick Start

### 1. Create MCP Configuration File

Create `mcp-servers.json` in your agents directory:

```json
{
  "fetch": {
    "command": "uvx",
    "args": ["mcp-server-fetch"]
  }
}
```

Default location: `workspace/agents/mcp-servers.json`

### 2. Declare MCP Server in Agent

Reference the server name in the `mcp` field:

```yaml
---
name: web-researcher
mcp:
  - fetch
---

Use the `fetch` tool to retrieve content from https://news.ycombinator.com
and summarize the top 5 stories.
```

### 3. Run the Agent

```bash
agentmd run web-researcher
```

Agent.md will:
1. Load the MCP config from `mcp-servers.json`
2. Connect to the `fetch` server (launches `uvx mcp-server-fetch`)
3. Discover available tools (e.g., `fetch`)
4. Make them available to the agent

---

## MCP Configuration File

The configuration file is a JSON object where each key is a server name and the value defines how to connect.

### File Location

By default, Agent.md looks for:

```
workspace/agents/mcp-servers.json
```

Override with environment variable or CLI flag:

```bash
export AGENTMD_MCP_CONFIG=/path/to/mcp-servers.json
agentmd run agent --mcp-config /path/to/mcp-servers.json
```

### Configuration Schema

Each server config must specify either `command` (stdio) or `url` (HTTP):

```json
{
  "server-name": {
    "command": "executable",
    "args": ["arg1", "arg2"],
    "env": {
      "VAR": "value"
    }
  }
}
```

---

## Stdio Transport

Run MCP servers as local processes. Most common for tools like `npx` or `uvx`.

### Basic Configuration

```json
{
  "fetch": {
    "command": "uvx",
    "args": ["mcp-server-fetch"]
  }
}
```

### With Environment Variables

```json
{
  "github": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-github"],
    "env": {
      "GITHUB_TOKEN": "${GITHUB_TOKEN}"
    }
  }
}
```

Use `${VAR_NAME}` syntax to reference environment variables. They are resolved at runtime from `.env` or shell:

- Variables read from your `.env` file or shell environment
- Undefined variables remain as `${VAR_NAME}` (no substitution)
- **Never commit secrets to `mcp-servers.json`** — always use `${VAR}` references

### Fields

| Field | Required | Type | Description |
|---|---|---|---|
| `command` | Yes | `string` | Executable to run (`"uvx"`, `"npx"`, `"python"`) |
| `args` | No | `array` | Arguments passed to the command |
| `env` | No | `object` | Environment variables for the process |

---

## HTTP Transport

Connect to remote MCP servers running over HTTP.

### Basic Configuration

```json
{
  "remote-tools": {
    "url": "https://mcp.example.com/tools"
  }
}
```

### With Authentication

```json
{
  "authenticated-server": {
    "url": "https://api.example.com/mcp",
    "headers": {
      "Authorization": "Bearer ${API_TOKEN}",
      "X-Custom-Header": "value"
    }
  }
}
```

### Fields

| Field | Required | Type | Description |
|---|---|---|---|
| `url` | Yes | `string` | HTTP endpoint for the MCP server |
| `headers` | No | `object` | HTTP headers sent with requests |

---

## Examples

### Example 1: Web Fetching

Fetch web content and summarize.

**mcp-servers.json:**
```json
{
  "fetch": {
    "command": "uvx",
    "args": ["mcp-server-fetch"]
  }
}
```

**Agent:**
```yaml
---
name: web-summarizer
mcp:
  - fetch
write: summaries/
---

Use the `fetch` tool to retrieve https://example.com/blog/post-1.
Summarize the content in 3-5 bullet points.
Write the summary to `summaries/example-summary.txt`.
```

**Available tools:** `fetch(url: str)` — Fetch URL and return markdown

---

### Example 2: GitHub Integration

Interact with GitHub repositories.

**mcp-servers.json:**
```json
{
  "github": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-github"],
    "env": {
      "GITHUB_TOKEN": "${GITHUB_TOKEN}"
    }
  }
}
```

**Agent:**
```yaml
---
name: github-reporter
mcp:
  - github
write: reports/
---

Use GitHub tools to:
1. List open issues in the repository "owner/repo"
2. Get details of the top 3 issues by comments
3. Write a summary report to `reports/github-issues.md`
```

**Available tools:** `create_or_update_file`, `push_files`, `create_issue`, `create_pull_request` — See [MCP GitHub server docs](https://github.com/modelcontextprotocol/servers/tree/main/src/github) for more

---

### Example 3: Slack Integration

Send messages to Slack channels.

**mcp-servers.json:**
```json
{
  "slack": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-slack"],
    "env": {
      "SLACK_BOT_TOKEN": "${SLACK_BOT_TOKEN}",
      "SLACK_TEAM_ID": "${SLACK_TEAM_ID}"
    }
  }
}
```

**Agent:**
```yaml
---
name: slack-notifier
trigger:
  type: schedule
  every: 1d
mcp:
  - slack
---

Send a daily summary message to the #general Slack channel with:
- Current date
- A motivational quote
- Reminder to review pending tasks

Use the `post_message` tool from the Slack server.
```

---

### Example 4: Multiple MCP Servers

Use multiple servers in one agent.

**mcp-servers.json:**
```json
{
  "fetch": {
    "command": "uvx",
    "args": ["mcp-server-fetch"]
  },
  "github": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-github"],
    "env": {
      "GITHUB_TOKEN": "${GITHUB_TOKEN}"
    }
  }
}
```

**Agent:**
```yaml
---
name: release-notes-generator
mcp:
  - fetch
  - github
write: releases/
---

1. Use the `fetch` tool to get the latest release notes from https://example.com/changelog
2. Use GitHub tools to create a new issue in "owner/repo" with the release notes
3. Write a summary to `releases/summary.txt`
```

---

## Available MCP Servers

Popular MCP servers you can use:

| Server | Package | Description |
|---|---|---|
| **fetch** | `mcp-server-fetch` | Fetch web content as markdown |
| **filesystem** | `@modelcontextprotocol/server-filesystem` | Read/write files outside workspace |
| **github** | `@modelcontextprotocol/server-github` | GitHub API integration |
| **slack** | `@modelcontextprotocol/server-slack` | Slack messaging |
| **google-maps** | `@modelcontextprotocol/server-google-maps` | Google Maps API |
| **postgres** | `@modelcontextprotocol/server-postgres` | PostgreSQL queries |

See the full list: [MCP Servers Repository](https://github.com/modelcontextprotocol/servers)

### Installing MCP Servers

**Python-based servers (uvx):**
```bash
# No installation needed — uvx downloads on first run
uvx mcp-server-fetch
```

**Node-based servers (npx):**
```bash
# No installation needed — npx downloads on first run
npx -y @modelcontextprotocol/server-github
```

---

## Troubleshooting

### "Unknown MCP server" error

**Error:**
```
ValueError: Unknown MCP server(s): my-server. Available: fetch, github
```

**Solution:**
1. Check that `my-server` is defined in `mcp-servers.json`
2. Verify the server name matches exactly (case-sensitive)
3. Ensure `mcp-servers.json` is in the correct location

### MCP server fails to start

**Problem:** Agent fails with "Error connecting to MCP server"

**Solution:**
1. Test the command manually:
   ```bash
   uvx mcp-server-fetch
   npx -y @modelcontextprotocol/server-github
   ```
2. Check for missing dependencies (Node.js for `npx`, Python for `uvx`)
3. Verify environment variables are set:
   ```bash
   echo $GITHUB_TOKEN
   ```
4. Check logs: `agentmd run agent -vvv` (debug mode)

### Environment variables not expanded

**Problem:** `${GITHUB_TOKEN}` appears literally in errors

**Solution:**
1. Make sure the variable is set in `.env`:
   ```bash
   GITHUB_TOKEN=ghp_your_token_here
   ```
2. Restart the agent to reload environment
3. Verify variable is loaded:
   ```bash
   agentmd run agent -vv  # Check startup logs
   ```

### MCP tools not appearing

**Problem:** Agent says "I don't have access to the `fetch` tool"

**Solution:**
1. Check that the MCP server is declared in agent frontmatter:
   ```yaml
   mcp:
     - fetch
   ```
2. Verify MCP server started successfully (check logs with `-vv`)
3. Test connection manually:
   ```bash
   agentmd run agent -vvv  # Debug logs show tool discovery
   ```

### Invalid JSON in mcp-servers.json

**Error:**
```
ValueError: Invalid JSON in mcp-servers.json: Expecting property name...
```

**Solution:**
1. Validate JSON syntax: https://jsonlint.com/
2. Common issues:
   - Missing commas between entries
   - Trailing commas (not allowed in JSON)
   - Unquoted keys or values
   - Comments (not allowed in JSON)

**Invalid:**
```json
{
  "fetch": {
    "command": "uvx",
    "args": ["mcp-server-fetch"],  // Wrong: trailing comma
  }
}
```

**Valid:**
```json
{
  "fetch": {
    "command": "uvx",
    "args": ["mcp-server-fetch"]
  }
}
```

---

## Best Practices

### 1. Use Environment Variables for Secrets

Never hardcode tokens or API keys:

**Bad:**
```json
{
  "github": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-github"],
    "env": {
      "GITHUB_TOKEN": "ghp_hardcoded_token_here"
    }
  }
}
```

**Good:**
```json
{
  "github": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-github"],
    "env": {
      "GITHUB_TOKEN": "${GITHUB_TOKEN}"
    }
  }
}
```

### 2. Test MCP Servers Independently

Test servers before using them in agents:

```bash
# Test fetch server
uvx mcp-server-fetch

# Test GitHub server with token
GITHUB_TOKEN=your_token npx -y @modelcontextprotocol/server-github
```

### 3. Limit Server Access per Agent

Only give agents access to the MCP servers they need:

**Bad:**
```yaml
mcp:
  - fetch
  - github
  - slack
  - filesystem  # Unnecessary access
```

**Good:**
```yaml
mcp:
  - fetch  # Only needs web fetching
```

### 4. Document Required Environment Variables

Add comments to your `.env.example` file:

```bash
# GitHub MCP server (required for github-reporter agent)
GITHUB_TOKEN=ghp_your_token_here

# Slack MCP server (required for slack-notifier agent)
SLACK_BOT_TOKEN=xoxb-your-token
SLACK_TEAM_ID=T1234567
```

### 5. Use Stdio for Local Tools

Prefer stdio transport over HTTP for local MCP servers:

- Faster (no network overhead)
- More secure (no exposed ports)
- Easier to debug

### 6. Version Pin MCP Servers (Production)

For production agents, pin MCP server versions:

```json
{
  "fetch": {
    "command": "uvx",
    "args": ["mcp-server-fetch==0.1.0"]
  }
}
```

This prevents breaking changes from affecting your agents.

---

## Next Steps

- [Built-in tools reference →](built-in-tools.md)
- [Custom tools guide →](custom-tools.md)
- [MCP official documentation →](https://modelcontextprotocol.io/)
- [MCP servers repository →](https://github.com/modelcontextprotocol/servers)
