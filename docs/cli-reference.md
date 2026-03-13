# CLI Reference

Complete reference for all Agent.md CLI commands, options, and examples.

## Command Overview

| Command | Description | Use Case |
|---------|-------------|----------|
| `agentmd start` | Start runtime with scheduler + watcher | Long-running process for scheduled agents |
| `agentmd run [agent]` | Execute single agent (one-shot) | Manual execution, testing, debugging |
| `agentmd list` | List all agents in workspace | Discover agents, check status |
| `agentmd logs <agent>` | View execution history | Debug failures, review outputs |
| `agentmd validate [agent]` | Validate agent configuration | Pre-deployment checks, CI/CD |
| `agentmd status` | Check if runtime is running | Monitor daemon state |
| `agentmd stop` | Stop background runtime | Gracefully stop daemon |
| `agentmd config` | Show effective configuration | Verify paths, API keys, defaults |
| `agentmd setup` | Interactive setup wizard | First-time setup or reconfiguration |
| `agentmd update` | Update to latest version | Self-update via uv or pip |

## Global Options

These options are available for **all commands** via the app callback:

| Option | Short | Description |
|--------|-------|-------------|
| `--quiet` | `-q` | Suppress output except errors |
| `--verbose` | `-v` | Show debug output |

```bash
# Any command can use global options
agentmd -v list
agentmd -q run hello-world
```

---

## agentmd start

Start the Agent.md runtime with scheduler and file watcher.

### Purpose

Launches a process that:
1. Loads all agents from the workspace
2. Starts the scheduler for agents with `schedule` triggers (cron, interval)
3. Starts the file watcher for agents with `watch` triggers
4. Displays a summary of all loaded agents
5. Runs until interrupted (Ctrl+C) or stopped via `agentmd stop`

### Usage

```bash
agentmd start [OPTIONS]
```

### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--workspace PATH` | `-w` | Path | from config.yaml | Override workspace directory |
| `--daemon` | `-d` | Flag | false | Run in background |
| `--quiet` | `-q` | Flag | false | Suppress output except errors |

### Examples

```bash
# Start in foreground (default)
agentmd start

# Start as background daemon
agentmd start -d

# Start with custom workspace
agentmd start --workspace /data/agents

# Start daemon with custom workspace
agentmd start -d -w /data/agents
```

### Daemon Mode

When started with `--daemon` / `-d`:
- Runs as a detached background process
- Logs output to `{workspace}/data/agentmd.log`
- PID stored in `{workspace}/data/agentmd.pid`
- Use `agentmd status` to check and `agentmd stop` to stop

---

## agentmd run [agent]

Execute a single agent manually (one-shot execution).

### Usage

```bash
agentmd run [AGENT] [OPTIONS]
```

### Arguments

| Argument | Type | Description |
|----------|------|-------------|
| `[AGENT]` | String (optional) | Agent name. If omitted, shows an interactive picker |

### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--workspace PATH` | `-w` | Path | from config.yaml | Override workspace directory |
| `--quiet` | `-q` | Flag | false | Suppress output except result |

### Examples

```bash
# Run agent by name
agentmd run my-agent

# Interactive picker (when no name given)
agentmd run

# Quiet mode (result only)
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

List all agents in the workspace with their trigger, last run, and status.

### Usage

```bash
agentmd list [OPTIONS]
```

### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--workspace PATH` | `-w` | Path | from config.yaml | Override workspace directory |

### Table Columns

| Column | Example |
|--------|---------|
| **Name** | `daily-report` |
| **Trigger** | `cron (0 9 * * *)`, `every 1h`, `manual` |
| **Last Run** | `2h ago`, `never` |
| **Status** | `●` (enabled) / `○` (disabled) |

---

## agentmd logs

View execution history and detailed messages for an agent.

### Usage

```bash
agentmd logs <AGENT> [OPTIONS]
agentmd logs -e <ID> [OPTIONS]
agentmd logs -f [OPTIONS]
```

### Arguments & Options

| Item | Type | Default | Description |
|------|------|---------|-------------|
| `<AGENT>` | String | — | Agent name (required for execution list) |
| `-n` / `--last NUM` | Integer | 10 | Number of recent executions |
| `-e` / `--execution ID` | Integer | — | Show messages for specific execution ID |
| `-f` / `--follow` | Flag | false | Follow daemon log output in real-time |
| `--workspace PATH` | Path | from config.yaml | Override workspace directory |

### Examples

```bash
# Show last 10 executions
agentmd logs my-agent

# Show last 5 executions
agentmd logs my-agent -n 5

# View detailed messages for execution #42
agentmd logs -e 42

# Follow daemon logs (like tail -f)
agentmd logs -f
```

---

## agentmd validate [agent]

Validate an agent configuration without executing it.

### Usage

```bash
agentmd validate [AGENT] [OPTIONS]
```

### Arguments & Options

| Item | Type | Description |
|------|------|-------------|
| `[AGENT]` | String (optional) | Agent name or path. Interactive picker if omitted |
| `--workspace PATH` | Path | Override workspace directory |

### What it checks

- Model provider and API key availability
- Trigger configuration (cron syntax, watch paths)
- System prompt presence
- Built-in and custom tool availability (including loadability)
- MCP server configuration
- Read/write path existence

### Examples

```bash
# Validate by name
agentmd validate my-agent

# Interactive picker
agentmd validate

# Validate all agents
for agent in $(agentmd list --quiet 2>/dev/null); do
  agentmd validate "$agent"
done
```

---

## agentmd status

Check if the background runtime is running.

### Usage

```bash
agentmd status [OPTIONS]
```

### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--workspace PATH` | `-w` | Path | from config.yaml | Override workspace directory |

### Example output

```
  agentmd is running (pid 12345)

  Uptime         2h 30m
  Workspace      /home/user/agentmd
  Log file       /home/user/agentmd/data/agentmd.log
  Started        2026-03-13 09:00:00
```

---

## agentmd stop

Stop the background runtime.

### Usage

```bash
agentmd stop [OPTIONS]
```

### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--workspace PATH` | `-w` | Path | from config.yaml | Override workspace directory |

Sends SIGTERM for graceful shutdown. Falls back to SIGKILL after 5 seconds if needed.

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
- **Default model** — provider and model used when agents omit `model:`
- **API keys** — which providers have keys configured

### Example output

```
  agentmd v0.2.3

╭─────────────── Agent.md Configuration ───────────────╮
│   Config file      /home/user/agentmd/config.yaml    │
│   Env file         /home/user/agentmd/.env           │
│   Workspace        /home/user/agentmd               │
│   Default model    google / gemini-2.5-flash         │
│   API keys         google                            │
╰──────────────────────────────────────────────────────╯
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

Located in your workspace directory. Controls paths and default model.

```yaml
workspace: ~/agentmd
agents_dir: agents          # relative to workspace
output_dir: output          # relative to workspace
db_path: data/agentmd.db   # relative to workspace
mcp_config: agents/mcp-servers.json

defaults:
  provider: google
  model: gemini-2.5-flash
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

1. CLI flags (`--workspace`)
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
    ├── agentmd.db          # Execution history (auto-created)
    ├── agentmd.pid         # Daemon PID file (when running as daemon)
    └── agentmd.log         # Daemon log file (when running as daemon)
```
