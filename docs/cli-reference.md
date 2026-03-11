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
| `--workspace PATH` | `-w` | Path | `./workspace` | Root workspace directory |
| `--agents-dir PATH` | — | Path | `{workspace}/agents` | Directory containing .md agent files |
| `--output-dir PATH` | — | Path | `{workspace}/output` | Default output directory for agent files |
| `--db-path PATH` | — | Path | `{workspace}/agentmd.db` | SQLite database for execution history |
| `--mcp-config PATH` | — | Path | `{workspace}/mcp.json` | MCP servers JSON configuration |
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

**Basic usage:**
```bash
# Start with default workspace (./workspace)
agentmd start

# Start with custom workspace
agentmd start --workspace /data/agents

# Start with verbose output (show event stream)
agentmd start -v
```

**Custom paths:**
```bash
# Override all paths
agentmd start \
  --workspace /data/agents \
  --agents-dir /data/agents/md \
  --output-dir /data/output \
  --db-path /var/lib/agentmd/history.db \
  --mcp-config /etc/agentmd/mcp.json

# Use environment variables instead
export AGENTMD_WORKSPACE=/data/agents
export AGENTMD_OUTPUT_DIR=/data/output
agentmd start
```

**Verbosity:**
```bash
# Quiet mode (errors only)
agentmd start --quiet

# Show event stream for each agent execution
agentmd start -v

# Show event stream + INFO logs
agentmd start -vv

# Show event stream + INFO + DEBUG logs
agentmd start -vvv
```

---

## agentmd run <agent>

Execute a single agent manually (one-shot execution).

### Purpose

Runs a specific agent immediately and exits when complete. Use for:
- Manual execution of one-off tasks
- Testing new agents during development
- Debugging agent behavior with verbose output
- CI/CD pipelines with single-execution semantics

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
| `--workspace PATH` | `-w` | Path | `./workspace` | Root workspace directory |
| `--agents-dir PATH` | — | Path | `{workspace}/agents` | Directory containing .md agent files |
| `--output-dir PATH` | — | Path | `{workspace}/output` | Default output directory for agent files |
| `--db-path PATH` | — | Path | `{workspace}/agentmd.db` | SQLite database for execution history |
| `--mcp-config PATH` | — | Path | — | MCP servers JSON configuration |
| `--quiet` | `-q` | Flag | false | Suppress event output (errors only) |
| `--verbose` | `-v` | Count | 1 | Increase verbosity (-v, -vv, -vvv) |

### Verbosity Levels

| Flag | Level | Output |
|------|-------|--------|
| `--quiet` / `-q` | 0 | Header + footer only, no event stream |
| (default) | 1 | Event stream (AI, tool calls, responses) |
| `-v` | 1 | Same as default |
| `-vv` | 2 | Event stream + INFO logs |
| `-vvv` | 3 | Event stream + INFO + DEBUG logs |

### Examples

**Basic usage:**
```bash
# Run agent (finds my-agent.md in workspace/agents/)
agentmd run my-agent

# Run with .md extension (same result)
agentmd run my-agent.md

# Run with custom workspace
agentmd run my-agent --workspace /data/agents
```

**Verbosity:**
```bash
# Quiet mode (header + footer only, no event stream)
agentmd run my-agent --quiet

# Default (event stream)
agentmd run my-agent

# Event stream + INFO logs
agentmd run my-agent -vv

# Event stream + INFO + DEBUG logs
agentmd run my-agent -vvv
```

**Custom paths:**
```bash
# Override specific paths
agentmd run my-agent \
  --agents-dir /data/agents/md \
  --output-dir /tmp/output

# Use environment variables
export AGENTMD_AGENTS_DIR=/data/agents/md
export AGENTMD_OUTPUT_DIR=/tmp/output
agentmd run my-agent
```

### Output Format

**Header:**
```
▶ Running my-agent  openai/gpt-4o  custom_tools: file_analyzer  mcp: filesystem
```

**Event stream (default verbosity):**
```
14:32:15 my-agent 🤖 I'll analyze the log file and create a summary report
14:32:16 my-agent 🔧 file_read → {"path": "logs/app.log"}
14:32:16 my-agent 📎 file_read ← Read 2048 bytes
14:32:18 my-agent 🔧 file_write → {"path": "output/summary.md", "content": "# Log Summary..."}
14:32:18 my-agent 📎 file_write ← Wrote 512 bytes
14:32:19 my-agent 🤖 Summary report has been created at output/summary.md

14:32:20 my-agent ✅ Final answer:
  I've analyzed the log file and created a summary report at output/summary.md.
  The file contains 15 errors and 42 warnings from the past 24 hours.
```

**Footer (summary):**
```
✓ my-agent done in 4820ms  tokens: 850 in / 320 out / 1170 total  execution #42
```

### Event Icons

| Icon | Type | Description |
|------|------|-------------|
| 🤖 | AI message | LLM reasoning or response |
| 🔧 | Tool call | Tool invocation with arguments |
| 📎 | Tool response | Tool execution result |
| ✅ | Final answer | Agent's final output |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Agent not found, validation error, or runtime error |

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
| `--workspace PATH` | `-w` | Path | `./workspace` | Root workspace directory |
| `--agents-dir PATH` | — | Path | `{workspace}/agents` | Directory containing .md agent files |
| `--output-dir PATH` | — | Path | `{workspace}/output` | Default output directory |
| `--db-path PATH` | — | Path | `{workspace}/agentmd.db` | SQLite database path |
| `--mcp-config PATH` | — | Path | — | MCP servers JSON configuration |

### Examples

```bash
# List agents in default workspace
agentmd list

# List agents in custom workspace
agentmd list --workspace /data/agents

# Use custom agents directory
agentmd list --agents-dir /data/agents/production
```

### Table Columns

| Column | Example |
|--------|---------|
| **Name** | `daily-report` |
| **Description** | `Generate daily summary` |
| **Provider** | `openai`, `google`, `anthropic` |
| **Model** | `gpt-4o`, `gemini-2.0-flash` |
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
| `--workspace PATH` | Path | `./workspace` | Root workspace directory |
| `--agents-dir PATH` | Path | `{workspace}/agents` | Directory with .md agent files |
| `--output-dir PATH` | Path | `{workspace}/output` | Default output directory |
| `--db-path PATH` | Path | `{workspace}/agentmd.db` | SQLite database path |

### Examples

```bash
# Show last 10 executions
agentmd logs my-agent

# Show last 5 executions
agentmd logs my-agent -n 5

# View detailed messages for execution #42
agentmd logs my-agent -e 42

# Custom database
agentmd logs my-agent --db-path /data/history.db
```

### Output Columns

| Column | Example |
|--------|---------|
| **#** | `45` |
| **Status** | `success`, `error`, `timeout` |
| **Trigger** | `manual`, `schedule`, `watch` |
| **Duration** | `3250ms` |
| **Input / Output / Total Tokens** | `1200 / 450 / 1650` |
| **Started at** | `2026-03-11 14:35:22` |
| **Output / Error** | Preview (80 chars) |

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
# Validate agent in workspace
agentmd validate workspace/agents/my-agent.md

# Validate with custom agents directory
agentmd validate /data/agents/my-agent.md --agents-dir /data/agents

# Validate before running
agentmd validate workspace/agents/my-agent.md && agentmd run my-agent

# Validate all agents
for agent in workspace/agents/*.md; do
  agentmd validate "$agent" || echo "Invalid: $agent"
done
```

### Output Examples

**Success:**
```
✓ Valid agent: daily-report
  Provider:     openai
  Model:        gpt-4o
  Trigger:      schedule (cron: 0 9 * * *)
  Built-in:     file_read, file_write, http_request
  Custom tools: csv_parser
  MCP Servers:  postgres
  Enabled:      True
```

**Error:**
```
✗ Validation failed: YAML parsing error: expected <block end>
  in "workspace/agents/broken.md", line 5, column 1
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Valid (may have warnings) |
| 1 | Invalid YAML, validation error, or file not found |

---

## Global Options

### Workspace Path Configuration

**Precedence** (highest to lowest):
1. CLI flags (`--workspace`, `--agents-dir`, etc.)
2. Environment variables (`AGENTMD_WORKSPACE`, `AGENTMD_AGENTS_DIR`, etc.)
3. Default values (`./workspace`, `./workspace/agents`, etc.)

### Common Flags

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--workspace` | `-w` | Path | `./workspace` | Root workspace directory |
| `--agents-dir` | — | Path | `{workspace}/agents` | Directory containing .md agent files |
| `--output-dir` | — | Path | `{workspace}/output` | Default output directory for agent files |
| `--db-path` | — | Path | `{workspace}/agentmd.db` | SQLite database for execution history |
| `--mcp-config` | — | Path | `{workspace}/mcp.json` | MCP servers JSON configuration |

### Verbosity Options

| Flag | Description |
|------|-------------|
| `--quiet` / `-q` | Suppress all output except errors |
| `-v` | Show event stream and basic logs |
| `-vv` | Show event stream + INFO logs |
| `-vvv` | Show event stream + INFO + DEBUG logs |

---

## Environment Variables

Agent.md respects the following environment variables:

### Provider API Keys

```bash
GOOGLE_API_KEY          # Google AI (Gemini)
OPENAI_API_KEY          # OpenAI (GPT-4, etc.)
ANTHROPIC_API_KEY       # Anthropic (Claude)
OLLAMA_API_BASE         # Ollama API endpoint
```

### Workspace Paths

```bash
AGENTMD_WORKSPACE       # Root workspace directory
AGENTMD_AGENTS_DIR      # Agent .md files location
AGENTMD_OUTPUT_DIR      # Default output directory
AGENTMD_DB_PATH         # SQLite database path
AGENTMD_MCP_CONFIG      # MCP servers config path
```

### Example `.env` file

```bash
# Provider keys
OPENAI_API_KEY=sk-proj-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...

# Workspace paths
AGENTMD_WORKSPACE=/data/agents
AGENTMD_OUTPUT_DIR=/data/output
AGENTMD_DB_PATH=/data/history.db
```

---

## Workspace Structure

**Default layout:**
```
./workspace/
├── agents/                 # Agent .md files
│   ├── my-agent.md
│   ├── tools/             # Custom tools (Python modules)
│   │   ├── csv_parser.py
│   │   └── data_validator.py
│   └── mcp.json           # MCP servers config (optional)
├── output/                # Default output directory
│   └── agent-outputs/
├── agentmd.db            # Execution history (auto-created)
└── .env                  # Environment variables (optional)
```

**Custom layout example:**
```bash
# Use environment variables
export AGENTMD_WORKSPACE=/data/agents
export AGENTMD_AGENTS_DIR=/data/agents/production
export AGENTMD_OUTPUT_DIR=/data/output
export AGENTMD_DB_PATH=/var/lib/agentmd/history.db
agentmd start
```
