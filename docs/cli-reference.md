# CLI Reference

Complete reference for all Agent.md CLI commands, options, and examples.

## Command Overview

| Command | Description | Use Case |
|---------|-------------|----------|
| `agentmd new <name>` | Scaffold a new agent | Create agents via AI or interactive questionnaire |
| `agentmd start` | Start runtime with scheduler + watcher | Long-running process for scheduled agents |
| `agentmd run [agent]` | Execute single agent (one-shot) | Manual execution, testing, debugging |
| `agentmd chat [agent]` | Interactive chat session | Multi-turn conversation with an agent |
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

## agentmd new

Scaffold a new agent definition file.

### Purpose

Creates a new agent `.md` file in the workspace. Two modes:

1. **AI-assisted** (default, when a provider + API key are configured): asks what the agent should do, then uses the configured LLM to generate the complete agent file (frontmatter + system prompt)
2. **Interactive questionnaire** (no provider configured, or `--template` flag): walks you through each field — description, provider, model, trigger, paths, and system prompt

If AI generation fails, it automatically falls back to the interactive questionnaire.

### Usage

```bash
agentmd new <AGENT_NAME> [OPTIONS]
```

### Arguments

| Argument | Type | Description |
|----------|------|-------------|
| `AGENT_NAME` | String (required) | Name for the agent (alphanumeric, hyphens, underscores) |

### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--workspace PATH` | `-w` | Path | from config.yaml | Override workspace directory |
| `--template` | `-t` | Flag | false | Skip AI, use interactive questionnaire |

### Examples

```bash
# AI-assisted (prompts for description, generates via LLM)
agentmd new daily-report

# Interactive questionnaire (no AI)
agentmd new daily-report --template

# Custom workspace
agentmd new my-agent -w /data/agents
```

### Interactive Questionnaire Fields

When using `--template` or without an AI provider configured, the command asks:

| Field | Example | Required |
|-------|---------|----------|
| Description | "Summarizes daily logs" | No |
| Provider | google, openai, anthropic, ollama, local | No (uses default) |
| Model name | gemini-2.5-flash, gpt-4o | No (uses default) |
| Trigger | manual, schedule, watch | No (defaults to manual) |
| Schedule/paths | 30m, `0 9 * * *`, data/uploads/ | Only for schedule/watch |
| Read paths | logs/, data/input.csv | No |
| Write paths | output/, reports/ | No |
| System prompt | "Read all logs and summarize..." | Yes |

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

## agentmd chat [agent]

Start an interactive multi-turn chat session with an agent.

### Purpose

Unlike `agentmd run` (one-shot), `agentmd chat` opens a REPL where you type messages and the agent responds in real-time. The agent retains full conversation context across turns — it remembers everything you've said during the session.

One execution record is created for the entire chat session (trigger type `"chat"`), with token usage accumulated across all turns.

### Usage

```bash
agentmd chat [AGENT] [OPTIONS]
```

### Arguments

| Argument | Type | Description |
|----------|------|-------------|
| `[AGENT]` | String (optional) | Agent name. If omitted, shows an interactive picker |

### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--workspace PATH` | `-w` | Path | from config.yaml | Override workspace directory |

### Examples

```bash
# Chat with an agent by name
agentmd chat my-agent

# Interactive picker (when no name given)
agentmd chat

# Custom workspace
agentmd chat my-agent -w /data/agents
```

### Session Controls

| Input | Action |
|-------|--------|
| `/exit` or `/quit` | End session gracefully |
| `Ctrl+C` | End session gracefully |
| `Ctrl+D` (EOF) | End session gracefully |
| Empty input | Ignored (re-prompts) |

### Example Session

```
  Chat with hello-world
    google / gemini-2.5-flash
    Type /exit or Ctrl+C to end session

  > What files are in the output directory?
  11:33:01  🔧 file_read → {'path': '.'}
  11:33:01  📎 file_read ← greeting.txt, report.txt
  11:33:02  ✅ The output directory contains: greeting.txt and report.txt

  > Read greeting.txt and translate it to Spanish
  11:33:10  🔧 file_read → {'path': 'greeting.txt'}
  11:33:11  🤖 Here's the translation...
  11:33:11  ✅ ¡Hola! Que tu día esté lleno de alegría...

  > /exit

  Session ended: 2 turns, 450 tokens (120 in / 330 out), 15.2s
  Execution #42
```

### Viewing Chat History

Chat sessions appear in `agentmd logs` like any other execution:

```bash
agentmd logs my-agent       # Shows chat sessions with trigger "chat"
agentmd logs -e 42          # View full message history of a chat session
```

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
- History level (session memory configuration)
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

## agentmd info

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
│   Config file      ~/.config/agentmd/config.yaml     │
│   Env file         /home/user/agentmd/.env           │
│   Workspace        /home/user/agentmd                │
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
6. Creates workspace structure (`agents/`, `agents/tools/`)
7. Writes `~/.config/agentmd/config.yaml` (paths and defaults)
8. Writes `.env` in workspace (API key only)
9. Creates sample `hello-world` agent

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

Located at `~/.config/agentmd/config.yaml` (XDG standard). Auto-created with defaults on first run.

```yaml
workspace: ~/agentmd
agents_dir: agents          # relative to workspace

defaults:
  provider: google
  model: gemini-2.5-flash
```

### `.env` — API keys

Located in your workspace directory (`~/agentmd/.env`). Contains **only** API keys (secrets).

```bash
GOOGLE_API_KEY=AIza...
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
```

### How config is found

**config.yaml:** `~/.config/agentmd/config.yaml` (auto-created if missing)

**.env:** workspace `.env` (`~/agentmd/.env`)

### Precedence (highest to lowest)

1. CLI flags (`--workspace`)
2. `config.yaml` values
3. Built-in defaults

---

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `GOOGLE_API_KEY` | Google AI (Gemini) API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `ANTHROPIC_API_KEY` | Anthropic (Claude) API key |

---

## Workspace Structure

```
~/.config/agentmd/
└── config.yaml             # Application settings (auto-created)

~/agentmd/
├── .env                    # API keys (secrets)
├── agents/                 # Agent .md files
│   ├── hello-world.md
│   ├── hello-world.memory.md  # Long-term memory (auto-created)
│   ├── mcp-servers.json    # MCP servers config (optional)
│   └── tools/              # Custom tools (Python modules)
└── data/
    ├── agentmd.db          # Execution history (auto-created)
    ├── agentmd_checkpoints.db  # Session history checkpoints (auto-created)
    ├── agentmd.pid         # Daemon PID file (when running as daemon)
    └── agentmd.log         # Daemon log file (when running as daemon)
```
