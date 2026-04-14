<div align="center">

<img src="assets/agentmd_banner.png" alt="Agent.md" width="800"/>

<br>
<br>

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-3776AB?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Built with LangGraph](https://img.shields.io/badge/built%20with-LangGraph-FF6F00)](https://github.com/langchain-ai/langgraph)

**Markdown-first runtime for AI agents**

Write a `.md` file, describe what your agent should do, and let it run.
No boilerplate. No frameworks to learn. Just Markdown.

[📖 Documentation](https://z-fab.github.io/agentmd) • [🚀 Quick Start](#quick-start) • [📦 Examples](#examples) • [🤝 Contributing](#contributing)

</div>

---

## ✨ Why Agent.md?

- **📄 One file = One agent** — YAML frontmatter for config, Markdown body for the prompt
- **⚡ Zero boilerplate** — No classes, decorators, or complex frameworks
- **🕐 Flexible triggers** — Run manually, on schedules (cron/intervals), or when files change
- **🔧 Built-in tools** — File I/O (read, write, edit, move, glob) and HTTP requests work out of the box
- **🔌 MCP support** — Connect to any Model Context Protocol server
- **📊 Execution tracking** — Every run logged with status, duration, token usage, and estimated cost
- **🤖 Agent-to-agent delegation** — Agents can call other agents with allowlist control and depth limits
- **🛡️ Execution limits** — Hard caps on tool calls, tokens, and cost to prevent runaway agents
- **🌐 Real-time SSE event stream** — Subscribe to live execution and system events via `/events/stream`
- **🎯 Git-friendly** — Version control your prompts. See exactly how they evolved.

---

## 🚀 Quick Start

### Option A: One-line install (Linux/macOS)

```bash
curl -fsSL https://raw.githubusercontent.com/z-fab/agentmd/master/install.sh | bash
```

This installs `uv`, `agentmd`, and runs the interactive setup wizard.

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/z-fab/agentmd/master/install.ps1 | iex
```

### Option B: Developer setup

```bash
git clone https://github.com/z-fab/agentmd.git
cd agentmd
uv sync
uv pip install -e ".[all]"
agentmd setup
```

### Create Your First Agent

```bash
agentmd new hello-world
```

This uses AI to generate the agent from a description you provide. Or use `--template` for an interactive questionnaire:

```bash
agentmd new hello-world --template
```

You can also create agents manually — just add an `.md` file to `agents/`:

```markdown
---
name: hello-world
---

You are a friendly assistant. When asked to execute your task,
write a creative greeting and save it to 'greeting.txt'.
```

> **Note:** No `model` needed — Agent.md uses the default provider/model you configured during setup.

### Run It

```bash
agentmd run hello-world
```

**Output:**

```
Execution 1 started
  🔧 >> file_write ({'path': 'greeting.txt', 'content': 'Hello! ...'})
  📎 << file_write → Created greeting.txt (42 chars, 1 lines)
  🤖 I created a friendly greeting for you!

✅ I created a friendly greeting and saved it to greeting.txt.

success  |  1.8s  |  160 tokens  |  $0.0001
```

### Or Chat with It

Start a multi-turn conversation instead of a one-shot run:

```bash
agentmd chat hello-world
```

```
Chat with hello-world (google/gemini-2.5-flash)
Type /exit to end the session

> Write me a greeting in Portuguese
  file_write...
Olá! Que seu dia seja cheio de alegria e boas surpresas!

> Now save it to greeting-pt.txt
  file_write...
Done! Saved to greeting-pt.txt.

> /exit

3 turns  |  12.3s  |  580 tokens  |  $0.0002
```

That's it! 🎉

---

## ⚙️ Configuration

Agent.md uses two configuration files:

| File | Purpose |
|------|---------|
| `~/.config/agentmd/config.yaml` | Application settings (paths, default model) — auto-created on first run |
| `~/agentmd/agents/_config/.env` | Secrets only (API keys) — workspace-level, overrides global `.env` |

```yaml
# ~/.config/agentmd/config.yaml
workspace: ~/agentmd
agents_dir: agents

defaults:
  provider: google
  model: gemini-2.5-flash
  max_tool_calls: 50        # optional: limit tool invocations per run
  max_cost_usd: 1.00        # optional: cost cap per run (USD)
```

```bash
# ~/agentmd/agents/_config/.env
GOOGLE_API_KEY=your-key-here
```

Run `agentmd info` to see the current effective configuration.

---

## 📚 Examples

### Scheduled Tasks

Run agents on intervals or cron schedules:

```yaml
trigger:
  type: schedule
  every: 1h          # or use cron: "0 9 * * *"
```

### File Watching

Process files automatically as they appear:

```yaml
trigger:
  type: watch
  paths: data/uploads/
```

### Multi-Provider Support

Switch LLM providers with a config change:

```yaml
model:
  provider: openai       # google, anthropic, ollama, local
  name: gpt-4o
```

### MCP Integration

Use external tools via Model Context Protocol:

```yaml
mcp:
  - fetch      # Web fetching
  - github     # GitHub API
```

**[→ See all examples in documentation](https://z-fab.github.io/agentmd/examples)**

---

## 📖 Documentation

Comprehensive documentation is available at **[z-fab.github.io/agentmd](https://z-fab.github.io/agentmd)**

**Quick Links:**

- [Quick Start](https://z-fab.github.io/agentmd/quick-start)
- [Agent Configuration](https://z-fab.github.io/agentmd/agent-configuration)
- [CLI Reference](https://z-fab.github.io/agentmd/cli-reference)
- [Execution Limits](https://z-fab.github.io/agentmd/limits)
- [Providers](https://z-fab.github.io/agentmd/providers)
- [Triggers](https://z-fab.github.io/agentmd/triggers)
- [Tools Documentation](https://z-fab.github.io/agentmd/tools/)
- [REST API](https://z-fab.github.io/agentmd/api)
- [Examples](https://z-fab.github.io/agentmd/examples)
- [Security Best Practices](https://z-fab.github.io/agentmd/guides/security-best-practices)

---

## 🌐 HTTP Backend

As of v0.8.0, `agentmd start` runs a FastAPI HTTP backend over a Unix domain socket. The CLI communicates with it automatically — no manual API calls needed for normal use.

```bash
agentmd start          # foreground (Ctrl+C to stop)
agentmd start -d       # background daemon
agentmd status         # check backend status
agentmd stop           # graceful shutdown
```

The backend exposes a full REST API for integrations. When `--port` and `--api-key` are provided, it also binds to TCP:

```bash
agentmd start --port 4100 --api-key YOUR_KEY
curl -H "X-API-Key: YOUR_KEY" http://127.0.0.1:4100/health
```

Interactive API docs are available at `/docs` (Swagger) and `/redoc` while the backend is running.

**[→ REST API Reference](https://z-fab.github.io/agentmd/api)**

---

## 🛠️ Tech Stack

| Component | Technology |
|---|---|
| Runtime | Python 3.13+ |
| Agent Framework | [LangGraph](https://github.com/langchain-ai/langgraph) |
| LLM Providers | Google, OpenAI, Anthropic, Ollama, Local |
| HTTP Backend | [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) |
| HTTP Client | [HTTPX](https://www.python-httpx.org/) |
| CLI | [Typer](https://typer.tiangolo.com/) + [Rich](https://rich.readthedocs.io/) |
| Database | SQLite (async via [aiosqlite](https://github.com/omnilib/aiosqlite)) |
| Scheduling | [APScheduler](https://apscheduler.readthedocs.io/) |

---

## 🤝 Contributing

Contributions are welcome! Please open an issue or pull request on [GitHub](https://github.com/z-fab/agentmd).

```bash
# Development setup
git clone https://github.com/z-fab/agentmd.git
cd agentmd
uv sync
uv pip install -e ".[all]"
agentmd setup              # Interactive setup wizard
ruff format .              # Format code
```

---

## 📜 License

MIT License — use it, fork it, build on it.

---

<div align="center">

**Built with ❤️ and Markdown**

*If agents could write themselves, they'd choose Markdown too.*

[⭐ Star on GitHub](https://github.com/z-fab/agentmd) • [📖 Read the Docs](https://z-fab.github.io/agentmd)

</div>
