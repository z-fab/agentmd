<div align="center">

<img src="assets/agentmd_banner.png" alt="Agent.md" width="800" alt="Agent.md - Markdown In, Agents Out" description="Agent.md - Markdown In, Agents Out"/>
<br>
<br/>


[![Python 3.13+](https://img.shields.io/badge/python-3.13+-3776AB?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Built with LangGraph](https://img.shields.io/badge/built%20with-LangGraph-FF6F00)](https://github.com/langchain-ai/langgraph)

Agent.md is a **markdown-first runtime** for AI agents.
Write a `.md` file, describe what your agent should do, and let it run — manually, on a schedule, or when files change.

No boilerplate. No frameworks to learn. Just Markdown.

</div>

---

## ✨ Why Agent.md?

Most agent frameworks require dozens of files, complex configurations, and deep knowledge of LLM internals. **Agent.md takes a different approach:**

- 📄 **One file = One agent** — each `.md` file is a complete agent definition
- ⚡ **Zero boilerplate** — YAML frontmatter for config, Markdown body for the prompt
- 🕐 **Flexible triggers** — run manually, on schedules, or watch files for changes
- 🔧 **Built-in tools** — file I/O, HTTP requests available without configuration
- 📊 **Execution tracking** — every run is logged with status, duration, and token usage
- 🔌 **MCP support** — connect to any MCP server and use its tools in your agents
- 🖥️ **Beautiful CLI** — Rich-powered terminal output with tables, colors, and status indicators

---

## 🚀 Quick Start

### 1. Install

```bash
# Clone the repo
git clone https://github.com/your-username/agentmd.git
cd agentmd

# Install with uv (recommended)
uv sync

# Or with pip
pip install -e .
```

### 2. Configure

```bash
cp .env.example .env
# Add your API keys (only the providers you use)
echo "GOOGLE_API_KEY=your-key-here" >> .env
echo "OPENAI_API_KEY=your-key-here" >> .env
echo "ANTHROPIC_API_KEY=your-key-here" >> .env
```

**Install provider dependencies:**

```bash
# Install all providers
uv pip install -e ".[all]"

# Or install only what you need
uv pip install -e ".[openai]"
uv pip install -e ".[anthropic]"
uv pip install -e ".[ollama]"
```

**Optional: Configure workspace paths**

By default, Agent.md uses `./workspace` for agents and output. You can customize locations via environment variables:

```bash
# Optional: customize workspace paths in .env
echo "AGENTMD_WORKSPACE=/path/to/my/workspace" >> .env
echo "AGENTMD_AGENTS_DIR=/path/to/agents" >> .env
echo "AGENTMD_OUTPUT_DIR=/path/to/output" >> .env
echo "AGENTMD_DB_PATH=/path/to/agentmd.db" >> .env
echo "AGENTMD_MCP_CONFIG=/path/to/mcp-servers.json" >> .env
```

See **[Workspace & Paths](#-workspace--paths)** section for full details on path resolution.

### 3. Create your first agent

Create a file at `workspace/agents/hello-world.md`:

```markdown
---
name: hello-world
description: A simple test agent that greets the user
model:
  provider: google
  name: gemini-2.5-flash
settings:
  temperature: 0.7
  timeout: 30
enabled: true
---

You are a friendly assistant. When asked to execute your task,
respond with a short, creative greeting message. Include the
current date if you know it. Keep it under 3 sentences.

Save the output to a file called 'greeting.txt'.
```

### 4. Run it

```bash
agentmd run hello-world
```

```
▶ Running hello-world  google/gemini-2.5-flash

11:32:04 hello-world 🤖 I'll create a friendly greeting for you and save it...
11:32:05 hello-world 🔧 file_write → {'file_path': 'greeting.txt', 'content': '...'}
11:32:05 hello-world 📎 file_write ← File written successfully: greeting.txt

11:32:05 hello-world ✅ Final answer:
  I've written a creative greeting to greeting.txt!

✓ hello-world done in 1823ms  tokens: 42 in / 118 out / 160 total  execution #1
```

That's it. Your agent ran, wrote a file, and logged everything. 🎉

---

## 📄 Agent File Format

Every agent is a single `.md` file with two parts:

| Section | Purpose |
|---|---|
| **YAML Frontmatter** | Configuration (model, trigger, settings) |
| **Markdown Body** | System prompt — what the agent should do |

### Frontmatter Reference

```yaml
---
name: my-agent              # Unique identifier (alphanumeric, hyphens, underscores)
description: What it does    # Human-readable description (optional)
model:
  provider: google           # LLM provider (see table below)
  name: gemini-2.5-flash     # Model name
  # base_url: http://...     # For 'local' provider (or use 'url' as alias)
trigger:
  type: manual               # manual | schedule | watch (default: manual)
  # every: 30m               # For schedule: 30s, 5m, 2h, 1d
  # cron: "0 9 * * *"        # For schedule: standard cron expression
  # paths: output/           # For watch: file or directory to monitor
custom_tools:                # Custom tools from workspace/agents/tools/ (optional)
  - my_tool
mcp:                         # MCP servers to connect (optional)
  - fetch
read:                        # Files/dirs agent can read (optional, defaults to workspace root)
  - data/
  - config.json
write:                       # Files/dirs agent can write (optional, defaults to output/)
  - output/
  - reports/
settings:
  temperature: 0.7           # LLM temperature (0.0 - 1.0)
  max_tokens: 4096           # Max output tokens
  timeout: 300               # Execution timeout in seconds
enabled: true                # Enable/disable without deleting
---
```

### Trigger Types

| Type | Description | Configuration |
|---|---|---|
| `manual` | Run only when explicitly invoked via `agentmd run` | No additional config needed |
| `schedule` | Run on a time-based schedule | Requires `every: "5m"` **OR** `cron: "0 9 * * *"` |
| `watch` | Run when monitored files/directories change | Requires `paths: ["output/", "data.json"]` |

**Schedule examples:**
```yaml
# Run every 30 seconds
trigger:
  type: schedule
  every: 30s

# Run daily at 9 AM
trigger:
  type: schedule
  cron: "0 9 * * *"
```

**Watch examples:**
```yaml
# Watch a directory (recursive)
trigger:
  type: watch
  paths: output/

# Watch specific files
trigger:
  type: watch
  paths:
    - data/input.csv
    - config.json

# Watch multiple paths
trigger:
  type: watch
  paths:
    - logs/
    - reports/summary.txt
```

When a watch trigger fires, the agent receives context about what changed:
- `created: /path/to/new-file.txt`
- `modified: /path/to/existing-file.txt`
- `deleted: /path/to/removed-file.txt`
- `moved: /old/path.txt -> /new/path.txt`

### Supported Providers

| Provider | Install | Model examples | Notes |
|---|---|---|---|
| `google` | *(included by default)* | `gemini-2.5-flash`, `gemini-2.5-pro` | Uses `GOOGLE_API_KEY` |
| `openai` | `uv pip install -e ".[openai]"` | `gpt-4o`, `gpt-4o-mini` | Uses `OPENAI_API_KEY` |
| `anthropic` | `uv pip install -e ".[anthropic]"` | `claude-sonnet-4-5-20250929` | Uses `ANTHROPIC_API_KEY` |
| `ollama` | `uv pip install -e ".[ollama]"` | `llama3`, `mistral` | Local Ollama server |
| `local` | `uv pip install -e ".[openai]"` | Any model name | OpenAI-compatible endpoint (vLLM, LM Studio, etc.) |

The `local` provider uses any OpenAI-compatible API. Set `base_url` (or `url`) in the model config. The `/v1` path is appended automatically if missing. Defaults to `http://localhost:11434/v1` (Ollama).

```yaml
model:
  provider: local
  name: mistral-7b
  base_url: "http://localhost:8000"   # /v1 is appended automatically
  # url: "http://localhost:8000"      # 'url' also works
```

---

## 🖥️ CLI Commands

| Command | Description |
|---|---|
| `agentmd start` | Start the runtime with scheduler + file watcher |
| `agentmd run <agent>` | Execute a single agent (one-shot) |
| `agentmd list` | List all agents in the workspace |
| `agentmd logs <agent>` | Show execution history with token usage |
| `agentmd logs <agent> -e <id>` | Show detailed messages for a specific run |
| `agentmd validate <file>` | Validate an agent file without running it |

### Workspace Options

All commands support optional workspace path arguments that override environment variables:

| Flag | Description | Default |
|---|---|---|
| `--workspace PATH` | Root workspace directory | `./workspace` or `$AGENTMD_WORKSPACE` |
| `--agents-dir PATH` | Agents directory | `{workspace}/agents` or `$AGENTMD_AGENTS_DIR` |
| `--output-dir PATH` | Output directory | `{workspace}/output` or `$AGENTMD_OUTPUT_DIR` |
| `--db-path PATH` | Database file path | `./data/agentmd.db` or `$AGENTMD_DB_PATH` |
| `--mcp-config PATH` | MCP config file | `{agents_dir}/mcp-servers.json` or `$AGENTMD_MCP_CONFIG` |

**Example:**
```bash
# Run with custom workspace
agentmd start --workspace /opt/production/agents

# Use production agents but development database
agentmd run my-agent \
  --workspace /opt/production/agents \
  --db-path /tmp/dev-test.db
```

See **[Workspace & Paths](#-workspace--paths)** for full details on path resolution.

### Verbosity

Both `run` and `start` support verbosity flags to control how much output is shown:

| Flag | Level | Behavior |
|---|---|---|
| `-q` / `--quiet` | 0 | Header + footer only (no event stream) |
| `-v` | 1 | Rich event stream (tool calls, AI reasoning, final answer) |
| `-vv` | 2 | Event stream + INFO logs (database, registry, HTTP requests) |
| `-vvv` | 3 | Event stream + DEBUG logs (everything) |

**Defaults:** `run` defaults to level 1 (events visible), `start` defaults to level 0 (quiet, one-line summary per run). Other commands (`list`, `logs`, `validate`) are always quiet.

### Examples

```bash
# Start the runtime — scheduled agents run automatically
agentmd start

# Start with real-time event stream for scheduled runs
agentmd start -v

# Run a specific agent (shows events by default)
agentmd run daily-quote

# Run without event output (quiet)
agentmd run daily-quote -q

# Run with full INFO logs
agentmd run daily-quote -vv

# List all agents with status
agentmd list

# Check the last 5 executions
agentmd logs daily-quote -n 5

# Validate before deploying
agentmd validate workspace/agents/my-agent.md
```

---

## 🔧 Built-in Tools

All agents have automatic access to these tools without any configuration:

| Tool | Description |
|---|---|
| `file_read` | Read contents from a file |
| `file_write` | Write or create files |
| `http_request` | Make HTTP requests (GET, POST, etc.) |

**No need to declare them** — they're always available. The agent chooses when to use them based on the task.

### File Access Security

By default:
- Agents can **read** from anywhere in the workspace
- Agents can **write** only to the `output/` directory

You can customize this with `read` and `write` fields:

```yaml
---
name: data-processor
model:
  provider: google
  name: gemini-2.5-flash
read:
  - data/          # Allow reading from data/ directory
  - config.json    # Allow reading specific file
write:
  - output/
  - reports/       # Allow writing to additional directory
---
```

**Watch triggers automatically grant read access** to monitored paths, so agents can read files they're watching.

### Custom Tools

Create custom tools by adding Python files to `workspace/agents/tools/`:

```python
# workspace/agents/tools/my_tool.py
from langchain_core.tools import tool

@tool
def my_tool(input: str) -> str:
    """Description of what my tool does."""
    return f"Processed: {input}"
```

Then reference them in the agent frontmatter:

```yaml
custom_tools:
  - my_tool
```

---

## 🔌 MCP Servers

Agents can use tools from external [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) servers. This lets you extend your agents with any MCP-compatible tool — web fetching, database access, code execution, and more.

### 1. Configure servers

Create `workspace/agents/mcp-servers.json`:

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

Each server entry supports:
- **stdio transport** — `command` + `args` (+ optional `env`)
- **HTTP transport** — `url` (+ optional `headers`)

Environment variables can be referenced with `${VAR_NAME}` syntax and are resolved at runtime.

### 2. Use MCP tools in an agent

Add an `mcp` field to the frontmatter listing the servers your agent needs:

```markdown
---
name: web-researcher
description: Fetches a URL and summarizes the content
model:
  provider: google
  name: gemini-2.5-flash
trigger:
  type: manual
mcp:
  - fetch
settings:
  temperature: 0.3
  timeout: 60
enabled: true
---

You are a web research assistant. Use the `fetch` tool to retrieve
the content of a URL and write a structured summary to a file.
```

MCP servers are connected lazily — only when an agent that references them is executed. Discovered tools are cached for the lifetime of the runtime.

> You can also set the `AGENTMD_MCP_CONFIG` environment variable to point to a custom config file location.

---

## 🗂️ Workspace & Paths

Agent.md uses a flexible workspace structure that can be customized via CLI arguments, environment variables, or defaults.

### Path Resolution Hierarchy

Paths are resolved in this order (highest priority first):

1. **CLI arguments** — `agentmd start --workspace /custom/path`
2. **Environment variables** — `AGENTMD_WORKSPACE=/custom/path`
3. **Defaults** — convention-based defaults

### Configuration Options

| Path | CLI Argument | Environment Variable | Default |
|---|---|---|---|
| Workspace root | `--workspace` | `AGENTMD_WORKSPACE` | `./workspace` |
| Agents directory | `--agents-dir` | `AGENTMD_AGENTS_DIR` | `{workspace}/agents` |
| Output directory | `--output-dir` | `AGENTMD_OUTPUT_DIR` | `{workspace}/output` |
| Database file | `--db-path` | `AGENTMD_DB_PATH` | `./data/agentmd.db` |
| MCP config | `--mcp-config` | `AGENTMD_MCP_CONFIG` | `{agents_dir}/mcp-servers.json` |

**Note:** `tools_dir` is always `{agents_dir}/tools` and cannot be customized.

### Relative vs Absolute Paths

Path resolution depends on **where** the path is specified:

| Location | Relative paths resolved from | Example |
|---|---|---|
| **CLI args / ENV vars** | Current working directory (CWD) | `--workspace ./my-agents` |
| **Frontmatter** (`read`, `write`, `trigger.paths`) | Workspace root | `read: ["data/"]` → `{workspace}/data/` |
| **Tool calls** (`file_read`) | Workspace root | `file_read("data/file.txt")` → `{workspace}/data/file.txt` |
| **Tool calls** (`file_write`) | Agent's default write directory | `file_write("report.txt")` → `{output_dir}/report.txt` |

All paths are automatically converted to absolute paths internally via `.resolve()`.

**Examples:**

```bash
# CLI/ENV: Relative to current directory
cd /home/user/myproject
agentmd start --workspace ./workspace  # → /home/user/myproject/workspace

# CLI/ENV: Absolute path (used as-is)
agentmd start --workspace /opt/agents  # → /opt/agents

# Environment variable with relative path (resolved from CWD)
export AGENTMD_WORKSPACE=./my-agents
cd /home/user
agentmd start  # workspace = /home/user/my-agents
```

**Frontmatter paths:**
```yaml
# workspace = /home/user/agents
read:
  - data/           # → /home/user/agents/data/
  - /tmp/external   # → /tmp/external (absolute, used as-is)
trigger:
  type: watch
  paths: output/    # → /home/user/agents/output/
```

**Tool calls:**
```python
# Inside agent with workspace = /opt/production
file_read("data/input.csv")     # → /opt/production/data/input.csv
file_write("report.txt")        # → /opt/production/output/report.txt (default write dir)
file_write("/tmp/debug.log")    # → /tmp/debug.log (absolute)
```

### Using .env File

The recommended approach for persistent configuration is using a `.env` file:

```bash
# .env
AGENTMD_WORKSPACE=/home/user/production/agents
AGENTMD_DB_PATH=/var/lib/agentmd/production.db
AGENTMD_OUTPUT_DIR=/mnt/storage/agent-outputs
```

Then simply run:
```bash
agentmd start
```

### Multi-Environment Setup

You can maintain different environments by using different `.env` files:

```bash
# Development
cp .env.example .env.dev
# Edit .env.dev with dev paths

# Production
cp .env.example .env.prod
# Edit .env.prod with production paths

# Run with specific env
cp .env.dev .env && agentmd start
cp .env.prod .env && agentmd start
```

Or use CLI args for one-off overrides:

```bash
# Use production workspace, but development database
agentmd start \
  --workspace /opt/production/agents \
  --db-path /tmp/dev-test.db
```

---

## 📂 Project Structure

```
agentmd/
├── workspace/              # Your workspace
│   ├── agents/             # Agent .md files
│   │   ├── hello-world.md
│   │   ├── daily-quote.md
│   │   ├── tools/          # Custom tools (optional)
│   │   │   └── my_tool.py
│   │   └── mcp-servers.json  # MCP config (optional)
│   └── output/             # Default output directory for agents
├── data/                   # SQLite database (auto-created)
├── agent_md/
│   ├── cli/                # Typer CLI commands
│   ├── core/               # Parser, runner, scheduler, registry
│   ├── db/                 # Async SQLite layer
│   ├── graph/              # LangGraph ReAct agent
│   ├── mcp/               # MCP server integration
│   ├── providers/          # LLM provider factory
│   └── tools/              # Built-in tool implementations
└── pyproject.toml
```

---

## 🧪 Example Agents

### 📰 Daily Quote Fetcher

Fetches a random quote from an API every 2 minutes and saves it to a file:

```markdown
---
name: daily-quote
description: Fetches an inspirational quote from the web and saves it to a file
model:
  provider: google
  name: gemini-2.5-flash
trigger:
  type: schedule
  every: 120s
settings:
  temperature: 0.9
  timeout: 30
enabled: false  # Disabled by default to avoid costs
---

You are a daily inspiration curator. Your task:

1. Use the `http_request` tool to fetch a random quote from `https://zenquotes.io/api/random`
2. Parse the JSON response and extract the quote text and author
3. Format the quote beautifully with the author name and today's date
4. Save the result to a file called 'quote-{DDMMYY}.txt'

Keep the formatting clean and elegant. Add a short motivational comment
of your own (1 sentence max) after the quote.
```

### 📋 File Summarizer

Reads a file and generates a structured summary:

```markdown
---
name: file-summarizer
description: Reads a text file and generates a concise summary
model:
  provider: google
  name: gemini-2.5-flash
trigger:
  type: manual
settings:
  temperature: 0.3
  timeout: 60
enabled: true
---

You are a precise text summarizer. Your task:

1. Read the file at `input.txt` in the default output directory
2. Analyze the content carefully
3. Write a summary containing:
   - A one-line TL;DR
   - 3-5 bullet points with the key ideas
   - Word count of the original text
4. Save the summary to `summary.txt`

Be concise but don't miss important details. Use clear, direct language.
```

### 👁️ File Watcher

Monitors a directory and processes new files automatically:

```markdown
---
name: new-file-processor
description: Processes files as soon as they appear in the watched directory
model:
  provider: google
  name: gemini-2.5-flash
trigger:
  type: watch
  paths: data/incoming/
settings:
  temperature: 0.5
  timeout: 120
enabled: true
---

You are a file processor that monitors incoming files.

When a new file is created in the watched directory:
1. Use `file_read` to read the file content
2. Process or analyze the content based on the file type
3. Write a processing report to `output/processed-{filename}.txt`
4. Include: timestamp, file size, summary of contents

Be thorough but concise in your analysis.
```

---

## 📑 Versioning & GitOps

Since every agent is a plain Markdown file, you get **developer superpowers for free**:

| Practice | How it works with Agent.md |
|---|---|
| **Prompt versioning** | `git diff` shows exactly how a system prompt changed and when |
| **Instant rollback** | Agent hallucinating? `git checkout` the previous `.md` version |
| **Prompt code review** | Use Pull Requests to review agent logic before it hits production |
| **Config as code** | Switched from `gemini-2.5-flash` to `gemini-2.5-pro`? It's in your commit history |

> Think of it as **Infrastructure as Documentation** — your agents are version-controlled, diffable, and reviewable just like any other code.

---

## 🛡️ Security & Best Practices

When you give tools to an agent, you're giving it the ability to interact with your system. Follow these guidelines for safe execution:

### 1. Least Privilege

- **File scope** — Agent.md writes to the `output/` directory by default. Avoid granting write access to system or config directories.
- **Read/write paths** — Use `read` and `write` fields to restrict file access to only what's needed.

### 2. Secret Management

- **Never** put API keys in the Markdown body or YAML frontmatter.
- Use the `.env` file to load environment variables. The Agent.md runtime injects them automatically into model and tool calls.

### 3. Infinite Loops & Costs

- **Timeouts** — Always set a `timeout` in the frontmatter to prevent runaway executions.
- **Token tracking** — Monitor usage via `agentmd logs`. Agents on `schedule` triggers can generate unexpected costs if prompts are too long or intervals too frequent.
- **Watch debouncing** — File watch triggers automatically debounce rapid changes (500ms), preventing duplicate executions.

### 4. Pre-validation

Before scheduling an agent, always validate it:

```bash
agentmd validate workspace/agents/my-agent.md
```

---

## 🗺️ Roadmap

- [x] 🔌 MCP support
- [x] 🤖 Multi-provider support (OpenAI, Anthropic, Ollama, Local)
- [x] 📂 File access security (read/write paths)
- [x] 👁️ File watching triggers
- [x] 🧰 Custom tools support
- [ ] 🧠 Memory & context persistence
- [ ] ⚡ Skills support
- [ ] 🔗 Pipelines — chain agents together
- [ ] 🪄 Agent generator command
- [ ] 🖥️ Terminal UI (TUI) with live monitoring
- [ ] 🏪 Agent Marketplace

---

## 🛠️ Tech Stack

| Component | Technology |
|---|---|
| Runtime | Python 3.13+ |
| Agent Framework | [LangGraph](https://github.com/langchain-ai/langgraph) |
| LLM Providers | Google Gemini, OpenAI, Anthropic, Ollama, Local (via LangChain) |
| CLI | [Typer](https://typer.tiangolo.com/) + [Rich](https://rich.readthedocs.io/) |
| Database | SQLite (async via [aiosqlite](https://github.com/omnilib/aiosqlite)) |
| Scheduling | [APScheduler](https://apscheduler.readthedocs.io/) |
| Config Validation | [Pydantic](https://docs.pydantic.dev/) |
| File Watching | [Watchdog](https://github.com/gorakhargosh/watchdog) |

---

## 📜 License

MIT — use it, fork it, build on it. Contributions are welcome!

---

<div align="center">

**Built with ❤️ and Markdown**

*If agents could write their own definition files, they'd choose Markdown too.*

</div>
