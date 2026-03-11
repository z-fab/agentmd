<div align="center">

<img src="assets/agentmd_banner.png" alt="Agent.md" width="800" alt="Agent.md - Markdown In, Agents Out" description="Agent.md - Markdown In, Agents Out"/>
<br>
<br/>


[![Python 3.13+](https://img.shields.io/badge/python-3.13+-3776AB?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Built with LangGraph](https://img.shields.io/badge/built%20with-LangGraph-FF6F00)](https://github.com/langchain-ai/langgraph)

Agent.md is a **markdown-first runtime** for AI agents.  
Write a `.md` file, describe what your agent should do, and let it run — manually, on a schedule, or on a loop.

No boilerplate. No frameworks to learn. Just Markdown.

</div>

---

## ✨ Why Agent.md?

Most agent frameworks require dozens of files, complex configurations, and deep knowledge of LLM internals. **Agent.md takes a different approach:**

- 📄 **One file = One agent** — each `.md` file is a complete agent definition
- ⚡ **Zero boilerplate** — YAML frontmatter for config, Markdown body for the prompt
- 🕐 **Built-in scheduling** — cron expressions, intervals, or manual triggers
- 🔧 **Pluggable tools** — file I/O, HTTP requests, and more out of the box
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

### 3. Create your first agent

Create a file at `workspace/hello-world.md`:

```markdown
---
name: hello-world
description: A simple test agent that greets the user
model:
  provider: google
  name: gemini-2.5-flash
trigger:
  type: manual
tools:
  - file_write
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
▶ hello-world  google/gemini-2.5-flash  tools: file_write

✓ Done in 1823ms  tokens: 42 in / 118 out / 160 total  execution #1
```

That's it. Your agent ran, wrote a file, and logged everything. 🎉

---

## 📄 Agent File Format

Every agent is a single `.md` file with two parts:

| Section | Purpose |
|---|---|
| **YAML Frontmatter** | Configuration (model, trigger, tools, settings) |
| **Markdown Body** | System prompt — what the agent should do |

### Frontmatter Reference

```yaml
---
name: my-agent              # Unique identifier (alphanumeric, hyphens, underscores)
description: What it does    # Human-readable description
model:
  provider: google           # LLM provider (see table below)
  name: gemini-2.5-flash     # Model name
  # base_url: http://...     # Only for 'local' provider
trigger:
  type: interval             # manual | interval | cron
  interval: 30m              # For interval: 30s, 5m, 2h, 1d
  # schedule: "0 9 * * *"    # For cron: standard cron expression
tools:                       # Built-in tools to enable
  - file_read
  - file_write
  - http_request
mcp:                         # MCP servers to connect (optional)
  - fetch
settings:
  temperature: 0.7           # LLM temperature (0.0 - 1.0)
  max_tokens: 4096           # Max output tokens
  timeout: 300               # Execution timeout in seconds
enabled: true                # Enable/disable without deleting
---
```

### Supported Providers

| Provider | Install | Model examples | Notes |
|---|---|---|---|
| `google` | *(included by default)* | `gemini-2.5-flash`, `gemini-2.5-pro` | Uses `GOOGLE_API_KEY` |
| `openai` | `uv pip install -e ".[openai]"` | `gpt-4o`, `gpt-4o-mini` | Uses `OPENAI_API_KEY` |
| `anthropic` | `uv pip install -e ".[anthropic]"` | `claude-sonnet-4-5-20250929` | Uses `ANTHROPIC_API_KEY` |
| `ollama` | `uv pip install -e ".[ollama]"` | `llama3`, `mistral` | Local Ollama server |
| `local` | `uv pip install -e ".[openai]"` | Any model name | OpenAI-compatible endpoint (vLLM, LM Studio, etc.) |

The `local` provider uses any OpenAI-compatible API. Set `base_url` in the model config (defaults to `http://localhost:11434/v1`):

```yaml
model:
  provider: local
  name: mistral-7b
  base_url: "http://localhost:8000/v1"
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

### Examples

```bash
# Start the runtime — scheduled agents run automatically
agentmd start

# Run a specific agent
agentmd run daily-quote

# List all agents with status
agentmd list

# Check the last 5 executions
agentmd logs daily-quote -n 5

# Validate before deploying
agentmd validate workspace/my-agent.md
```

---

## 🔧 Built-in Tools

Agents can use tools by listing them in the `tools` frontmatter field:

| Tool | Description |
|---|---|
| `file_read` | Read contents from a file |
| `file_write` | Write or create files |
| `http_request` | Make HTTP requests (GET, POST, etc.) |

More tools coming soon — and the registry is designed to be easily extensible.

---

## 🔌 MCP Servers

Agents can use tools from external [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) servers. This lets you extend your agents with any MCP-compatible tool — web fetching, database access, code execution, and more.

### 1. Configure servers

Create a `mcp-servers.json` file in your workspace directory:

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
tools:
  - file_write
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

> You can also set the `MCP_CONFIG_PATH` environment variable to point to a custom config file location.

---

## 📂 Project Structure

```
agentmd/
├── workspace/              # Your agent .md files go here
│   ├── hello-world.md
│   ├── daily-quote.md
│   └── file-summarizer.md
├── output/                 # Default output directory for agents
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
  type: interval
  interval: 120s
tools:
  - http_request
  - file_write
settings:
  temperature: 0.9
  timeout: 30
enabled: true
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
tools:
  - file_read
  - file_write
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
- **Critical tools** — Only enable `http_request` if the agent actually needs external data.

### 2. Secret Management

- **Never** put API keys in the Markdown body or YAML frontmatter.
- Use the `.env` file to load environment variables. The Agent.md runtime injects them automatically into model and tool calls.

### 3. Infinite Loops & Costs

- **Timeouts** — Always set a `timeout` in the frontmatter to prevent runaway executions.
- **Token tracking** — Monitor usage via `agentmd logs`. Agents on `interval` or `cron` triggers can generate unexpected costs if prompts are too long or intervals too frequent.

### 4. Pre-validation

Before scheduling an agent, always validate it:

```bash
agentmd validate workspace/my-agent.md
```

---

## 🗺️ Roadmap

- [x] 🔌 MCP support
- [x] 🤖 Multi-provider support (OpenAI, Anthropic, Ollama, Local)
- [ ] 🧠 Memory & context persistence
- [ ] 🧰 More built-in tools
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
