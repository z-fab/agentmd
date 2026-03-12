# CLI Reference

Complete reference for all Agent.md CLI commands, options, and examples.

## Command Overview

| Command | Description | Use Case |
|---------|-------------|----------|
| `agentmd start` | Start runtime with scheduler + watcher | Long-running daemon for scheduled agents |
| `agentmd run <agent>` | Execute single agent (one-shot) | Manual execution, testing, debugging |
| `agentmd list` | List all agents in workspace | Discover agents, check configuration |
| `agentmd logs <agent>` | View execution history | Debug failures, review outputs |
| `agentmd validate <file>` | Validate agent file syntax | Pre-deployment checks, CI/CD |
| `agentmd config` | Show effective configuration | Verify paths, API keys, defaults |
| `agentmd setup` | Interactive setup wizard | First-time setup or reconfiguration |
| `agentmd update` | Update to latest version | Self-update via uv or pip |

---

## agentmd start

Start the Agent.md runtime with scheduler and file watcher.

### Purpose

Launches a long-running daemon that:
1. Loads all agents from the workspace
2. Starts the scheduler for agents with `schedule` triggers (cron, interval)
3. Starts the file watcher for agents with `watch` triggers
4. Displays a summary table of all loaded agents
5. Runs until interrupted (Ctrl+C)

### Usage

```bash
agentmd start [OPTIONS]
```

### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--workspace PATH` | `-w` | Path | from config.yaml | Root workspace directory |
| `--agents-dir PATH` | — | Path | `{workspace}/agents` | Directory containing .md agent files |
| `--output-dir PATH` | — | Path | `{workspace}/output` | Default output directory for agent files |
| `--db-path PATH` | — | Path | `{workspace}/data/agentmd.db` | SQLite database for execution history |
| `--mcp-config PATH` | — | Path | `{agents}/mcp-servers.json` | MCP servers JSON configuration |
| `--tui` | — | Flag | false | Launch Terminal UI (feature in development) |
| `--quiet` | `-q` | Flag | false | Suppress all output except errors |
| `--verbose` | `-v` | Count | 0 | Increase verbosity (-v, -vv, -vvv) |

### Verbosity Levels

| Flag | Level | Output |
|------|-------|--------|
| `--quiet` / `-q` | 0 | Suppress all output except errors |
| (default) | 0 | Minimal output (summary and completion) |
| `-v` | 1 | Event stream (AI, tool calls, responses) |
| `-vv` | 2 | Event stream + INFO logs |
| `-vvv` | 3 | Event stream + INFO + DEBUG logs |

### Examples

```bash
# Start with default workspace (from config.yaml)
agentmd start

# Start with custom workspace
agentmd start --workspace /data/agents

# Start with verbose output (show event stream)
agentmd start -v
```

---

## agentmd run <agent>

Execute a single agent manually (one-shot execution).

### Usage

```bash
agentmd run <AGENT> [OPTIONS]
```

### Arguments

| Argument | Type | Description |
|----------|------|-------------|
| `<AGENT>` | String | Agent name or filename (with or without `.md` extension) |

### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--workspace PATH` | `-w` | Path | from config.yaml | Root workspace directory |
| `--agents-dir PATH` | — | Path | `{workspace}/agents` | Directory containing .md agent files |
| `--output-dir PATH` | — | Path | `{workspace}/output` | Default output directory for agent files |
| `--db-path PATH` | — | Path | `{workspace}/data/agentmd.db` | SQLite database for execution history |
| `--mcp-config PATH` | — | Path | — | MCP servers JSON configuration |
| `--quiet` | `-q` | Flag | false | Suppress event output (errors only) |
| `--verbose` | `-v` | Count | 1 | Increase verbosity (-v, -vv, -vvv) |

### Examples

```bash
# Run agent (finds my-agent.md in workspace/agents/)
agentmd run my-agent

# Run with custom workspace
agentmd run my-agent --workspace /data/agents

# Quiet mode (header + footer only)
agentmd run my-agent --quiet
```

### Event Icons

| Icon | Type | Description |
|------|------|-------------|
| 🤖 | AI message | LLM reasoning or response |
| 🔧 | Tool call | Tool invocation with arguments |
| 📎 | Tool response | Tool execution result |
| ✅ | Final answer | Agent's final output |

---

## agentmd list

List all agents in the workspace.

### Usage

```bash
agentmd list [OPTIONS]
```

### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--workspace PATH` | `-w` | Path | from config.yaml | Root workspace directory |
| `--agents-dir PATH` | — | Path | `{workspace}/agents` | Directory containing .md agent files |
| `--output-dir PATH` | — | Path | `{workspace}/output` | Default output directory |
| `--db-path PATH` | — | Path | `{workspace}/data/agentmd.db` | SQLite database path |
| `--mcp-config PATH` | — | Path | — | MCP servers JSON configuration |

### Table Columns

| Column | Example |
|--------|---------|
| **Name** | `daily-report` |
| **Description** | `Generate daily summary` |
| **Provider** | `openai`, `google`, `anthropic` |
| **Model** | `gpt-4o`, `gemini-2.5-flash` |
| **Trigger** | `schedule (cron: 0 9 * * *)` or `manual` |
| **Custom Tools** | `file_analyzer, report_gen` |
| **MCP** | `filesystem, database` |
| **Status** | `●` (enabled) / `○` (disabled) |

---

## agentmd logs <agent>

View execution history and detailed messages for an agent.

### Usage

```bash
agentmd logs <AGENT> [OPTIONS]
```

### Arguments & Options

| Item | Type | Default | Description |
|------|------|---------|-------------|
| `<AGENT>` | String | — | Agent name |
| `-n` / `--n NUM` | Integer | 10 | Number of recent executions |
| `-e` / `--execution ID` | Integer | — | Show messages for specific execution ID |
| `--workspace PATH` | Path | from config.yaml | Root workspace directory |
| `--db-path PATH` | Path | `{workspace}/data/agentmd.db` | SQLite database path |

### Examples

```bash
# Show last 10 executions
agentmd logs my-agent

# Show last 5 executions
agentmd logs my-agent -n 5

# View detailed messages for execution #42
agentmd logs my-agent -e 42
```

---

## agentmd validate <file>

Validate an agent file without executing it.

### Usage

```bash
agentmd validate <FILE> [OPTIONS]
```

### Arguments & Options

| Item | Type | Description |
|------|------|-------------|
| `<FILE>` | Path | Path to agent `.md` file (absolute or relative) |
| `--agents-dir PATH` | Path | Directory containing tools/ subdirectory |

### Examples

```bash
# Validate agent
agentmd validate agents/my-agent.md

# Validate all agents
for agent in agents/*.md; do
  agentmd validate "$agent" || echo "Invalid: $agent"
done
```

---

## agentmd config

Show the current effective configuration.

### Usage

```bash
agentmd config
```

Displays:
- **Config file** — path to `config.yaml` being used
- **Env file** — path to `.env` being used
- **Workspace** — resolved workspace path
- **Agents/Output/DB/MCP paths** — resolved from config.yaml
- **Default model** — provider and model used when agents omit `model:`
- **API keys** — which providers have keys configured
- **Log level** — current logging level

### Example output

```
Agent.md v0.2.2

⚙️  Agent.md Configuration
  Config file    /home/user/agentmd/config.yaml
  Env file       /home/user/agentmd/.env
  Workspace      /home/user/agentmd
  Agents dir     /home/user/agentmd/agents
  Output dir     /home/user/agentmd/output
  DB path        /home/user/agentmd/data/agentmd.db
  MCP config     /home/user/agentmd/agents/mcp-servers.json
  Default model  google / gemini-2.5-flash
  API keys       google
  Log level      INFO
```

---

## agentmd setup

Interactive setup wizard for first-time configuration or reconfiguration.

### Usage

```bash
agentmd setup [OPTIONS]
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--reconfigure` | `-r` | Force reconfiguration even if already set up |

### What it does

1. Asks for workspace directory (default: `~/agentmd`)
2. Asks for LLM provider (google, openai, anthropic, ollama)
3. Asks for default model name
4. Asks for API key (masked input; skipped for ollama)
5. Asks about auto-start on login
6. Creates workspace structure (`agents/`, `output/`, `agents/tools/`)
7. Writes `config.yaml` (paths and defaults)
8. Writes `.env` (API key only)
9. Creates sample `hello-world` agent
10. Exports `AGENTMD_WORKSPACE` to shell profile

### Examples

```bash
# First-time setup
agentmd setup

# Reconfigure existing installation
agentmd setup --reconfigure
```

---

## agentmd update

Update Agent.md to the latest version.

### Usage

```bash
agentmd update
```

Tries `uv tool upgrade` first, falls back to `pip install --upgrade`. Shows current version before updating.

---

## Configuration Files

Agent.md uses two configuration files:

### `config.yaml` — Application settings

Located in your workspace directory. Controls paths, default model, and log level.

```yaml
workspace: ~/agentmd
agents_dir: agents          # relative to workspace
output_dir: output          # relative to workspace
db_path: data/agentmd.db   # relative to workspace
mcp_config: agents/mcp-servers.json

defaults:
  provider: google
  model: gemini-2.5-flash

log_level: INFO
```

### `.env` — API keys

Located in your workspace directory. Contains **only** API keys (secrets).

```bash
GOOGLE_API_KEY=AIza...
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
```

### How config is found

**config.yaml:** `AGENTMD_WORKSPACE` env var → `~/agentmd/config.yaml` → CWD `config.yaml`

**.env:** CWD `.env` → workspace `.env` → `~/agentmd/.env`

### Precedence (highest to lowest)

1. CLI flags (`--workspace`, `--agents-dir`, etc.)
2. `config.yaml` values
3. Built-in defaults

---

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `AGENTMD_WORKSPACE` | Points to workspace directory (used to locate `config.yaml` and `.env`) |
| `GOOGLE_API_KEY` | Google AI (Gemini) API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `ANTHROPIC_API_KEY` | Anthropic (Claude) API key |

---

## Workspace Structure

```
~/agentmd/
├── config.yaml             # Application settings
├── .env                    # API keys (secrets)
├── agents/                 # Agent .md files
│   ├── hello-world.md
│   ├── mcp-servers.json    # MCP servers config (optional)
│   └── tools/              # Custom tools (Python modules)
├── output/                 # Default output directory
└── data/
    └── agentmd.db          # Execution history (auto-created)
```
