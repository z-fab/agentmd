# CLI Reference

Complete reference for all Agentmd CLI commands, options, and examples.

## Command Overview

| Command | Description | Use Case |
|---------|-------------|----------|
| `agentmd new <name>` | Scaffold a new agent | Create agents via AI or interactive questionnaire |
| `agentmd start` | Start runtime with scheduler + watcher | Long-running process for scheduled agents |
| `agentmd run [agent]` | Execute single agent (one-shot) | Manual execution, testing, debugging |
| `agentmd chat [agent]` | Interactive chat session | Multi-turn conversation with an agent |
| `agentmd list` | List all agents in workspace | Discover agents, check status |
| `agentmd logs <agent>` | View execution history | Debug failures, review outputs |
| `agentmd pending` | List executions awaiting a response | Find paused (HILT) executions |
| `agentmd respond <id>` | Answer a waiting execution | Approve/deny or provide input |
| `agentmd checkpoint` | Inspect / purge checkpoint storage | Manage `agentmd_checkpoints.db` |
| `agentmd validate [agent]` | Validate agent configuration | Pre-deployment checks, CI/CD |
| `agentmd status` | Check if runtime is running | Monitor daemon state |
| `agentmd stop` | Stop background runtime | Gracefully stop daemon |
| `agentmd info` | Show effective configuration | Verify paths, API keys, defaults |
| `agentmd setup` | Interactive setup wizard | First-time setup or reconfiguration |
| `agentmd update` | Update to latest version | Self-update via uv or pip |

## Global Options

These options are available for **all commands** via the app callback:

| Option | Short | Description |
|--------|-------|-------------|
| `--quiet` | `-q` | Print only the final answer (on `run`) |
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

Start the Agentmd runtime with scheduler and file watcher.

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
| `--quiet` | `-q` | Flag | false | Print only the final answer (no steps, no summary) |
| `--detach` | `-d` | Flag | false | Run in the background and return immediately |

### Examples

```bash
# Run agent by name
agentmd run my-agent

# Interactive picker (when no name given)
agentmd run

# Quiet mode (final answer only — pipe-friendly)
agentmd run my-agent --quiet

# Background mode (returns immediately; check progress with `agentmd logs`)
agentmd run my-agent --detach
```

### Event Icons

| Icon | Type | Description |
|------|------|-------------|
| 🤖 | AI message | LLM reasoning or response |
| 🔧 | Tool call | Tool invocation with arguments |
| 📎 | Tool response | Tool execution result |
| ✅ | Final answer | Agent's final output |

### Human-in-the-Loop prompts

If the agent calls a guarded tool (e.g. `file_delete`, `file_write`) or `ask_user`, `agentmd run` pauses and prompts you inline for a confirmation, free-text answer, or choice, then resumes. If you are not watching the terminal, the execution enters `waiting` state and can be answered later with [`agentmd respond`](#agentmd-respond-id). With `--detach`, the run never prompts inline — any request goes straight to `waiting` and shows up in [`agentmd pending`](#agentmd-pending). See [Human-in-the-Loop](human-in-the-loop.md).

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

Like `agentmd run`, a chat session also prompts inline for [Human-in-the-Loop](human-in-the-loop.md) requests: when a guarded tool or `ask_user` fires mid-turn, you answer in the terminal and the agent continues.

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

## agentmd pending

List executions that are paused, waiting for a Human-in-the-Loop response.

### Usage

```bash
agentmd pending [OPTIONS]
```

### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--workspace PATH` | `-w` | Path | from config.yaml | Override workspace directory |

### Example output

```
 #   Agent      Question
 ──────────────────────────────────────────────────────────────
 42  cleaner    Confirm file_delete {"path": "output/stale.log"}
 51  reporter   Enter the report title:
```

Use the execution `#` with `agentmd respond` to answer. See [Human-in-the-Loop](human-in-the-loop.md).

---

## agentmd respond <id>

Answer a waiting execution. Resumes the run automatically once answered.

### Usage

```bash
agentmd respond <EXECUTION_ID> [OPTIONS]
```

### Arguments

| Argument | Type | Description |
|----------|------|-------------|
| `EXECUTION_ID` | Integer (required) | The waiting execution's id (from `agentmd pending`) |

### Options

| Option | Type | Description |
|--------|------|-------------|
| `--yes` | Flag | Approve a `confirm` request |
| `--no` | Flag | Deny a `confirm` request |
| `--reason TEXT` | String | Optional reason to attach to `--yes`/`--no` |
| `--text TEXT` | String | Answer for an `input` request |
| `--choice VALUE` | String | Selected option for a `choice` request |
| `--workspace PATH` | Path | Override workspace directory |

With no response flags, the command prompts interactively based on the pending request kind.

### Examples

```bash
# Interactive (prompts for the response)
agentmd respond 42

# Approve / deny a confirmation
agentmd respond 42 --yes
agentmd respond 42 --no --reason "file is still needed"

# Provide text for an input request
agentmd respond 51 --text "Monthly Summary"

# Select a choice
agentmd respond 55 --choice staging
```

---

## agentmd checkpoint

Inspect or purge the LangGraph checkpoint database (`agentmd_checkpoints.db`). The checkpointer is always on (it is the durability substrate for Human-in-the-Loop and history seeding), so it grows one thread per execution. A retention sweep runs automatically on startup (`defaults.checkpoint_retention_days`, default 30); this command is for manual inspection and cleanup.

### Usage

```bash
agentmd checkpoint [OPTIONS]
```

### Options

| Option | Type | Description |
|--------|------|-------------|
| `--stats` | Flag | Show DB size and thread count, grouped per agent (default when no flag given) |
| `--purge` | Flag | Delete eligible checkpoint threads |
| `--agent NAME` | String | Limit `--purge` to a single agent |
| `--force` | Flag | Ignore the keep-set (also removes latest-per-agent and `waiting` threads) |

### Keep-set

`--purge` (without `--force`) always preserves:

- the **latest execution per agent** (needed to seed `history` on the next run), and
- any **`waiting` execution** (needed to resume a paused run).

`--force` is the explicit "wipe everything" escape hatch.

### Examples

```bash
# Size + thread count per agent
agentmd checkpoint --stats

# Delete eligible old threads (respects the keep-set)
agentmd checkpoint --purge

# Purge for one agent only
agentmd checkpoint --purge --agent cleaner

# Wipe everything, including latest/waiting threads
agentmd checkpoint --purge --force
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
agentmd info
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

╭─────────────── Agentmd Configuration ───────────────╮
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

### What it does

1. Detects existing config — asks if you want to reconfigure
2. Asks for workspace directory (default: `~/agentmd`)
3. Asks for LLM provider and model
4. Asks for API key (masked input; skipped for ollama)
5. Asks for execution defaults (temperature, max_tokens, timeout, limits, history)
6. Creates workspace structure (`agents/`, `agents/_config/tools/`, `agents/_config/skills/`)
7. Writes `~/.config/agentmd/config.yaml`
8. Writes `.env` to `agents/_config/.env` and `~/.config/agentmd/.env`
9. Creates sample `hello-world` agent

### Examples

```bash
agentmd setup
```

---

## agentmd update

Update Agentmd to the latest version.

### Usage

```bash
agentmd update
```

Tries `uv tool upgrade` first, falls back to `pip install --upgrade`. Shows current version before updating.

---

## Configuration Files

Agentmd uses two configuration files:

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
