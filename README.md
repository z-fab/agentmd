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

[📖 Documentation](https://zfab.github.io/agentmd) • [🚀 Quick Start](#quick-start) • [📦 Examples](#examples) • [🤝 Contributing](#contributing)

</div>

---

## ✨ Why Agent.md?

- **📄 One file = One agent** — YAML frontmatter for config, Markdown body for the prompt
- **⚡ Zero boilerplate** — No classes, decorators, or complex frameworks
- **🕐 Flexible triggers** — Run manually, on schedules (cron/intervals), or when files change
- **🔧 Built-in tools** — File I/O and HTTP requests work out of the box
- **🔌 MCP support** — Connect to any Model Context Protocol server
- **📊 Execution tracking** — Every run logged with status, duration, and token usage
- **🎯 Git-friendly** — Version control your prompts. See exactly how they evolved.

---

## 🚀 Quick Start

### 1. Install

```bash
git clone https://github.com/zfab/agentmd.git
cd agentmd
uv sync                     # Install dependencies
uv pip install -e ".[all]"  # Install all provider support
```

### 2. Configure

```bash
cp .env.example .env
echo "GOOGLE_API_KEY=your-key-here" >> .env
```

### 3. Create Your First Agent

Create `workspace/agents/hello-world.md`:

```markdown
---
name: hello-world
model:
  provider: google
  name: gemini-2.5-flash
trigger:
  type: manual
---

You are a friendly assistant. When asked to execute your task,
write a creative greeting and save it to 'greeting.txt'.
```

### 4. Run It

```bash
agentmd run hello-world
```

**Output:**

```
▶ Running hello-world  google/gemini-2.5-flash

11:32:04 hello-world 🤖 I'll create a friendly greeting...
11:32:05 hello-world 🔧 file_write → greeting.txt
11:32:05 hello-world ✅ Final answer: Done!

✓ hello-world done in 1823ms  tokens: 42 in / 118 out / 160 total
```

That's it! 🎉

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

**[→ See all examples in documentation](https://zfab.github.io/agentmd/examples)**

---

## 📖 Documentation

Comprehensive documentation is available at **[zfab.github.io/agentmd](https://zfab.github.io/agentmd)**

**Quick Links:**

- [Quick Start](https://zfab.github.io/agentmd/quick-start)
- [Agent Configuration](https://zfab.github.io/agentmd/agent-configuration)
- [CLI Reference](https://zfab.github.io/agentmd/cli-reference)
- [Providers](https://zfab.github.io/agentmd/providers)
- [Triggers](https://zfab.github.io/agentmd/triggers)
- [Tools Documentation](https://zfab.github.io/agentmd/tools/)
- [Examples](https://zfab.github.io/agentmd/examples)
- [Security Best Practices](https://zfab.github.io/agentmd/guides/security-best-practices)

---

## 🛠️ Tech Stack

| Component | Technology |
|---|---|
| Runtime | Python 3.13+ |
| Agent Framework | [LangGraph](https://github.com/langchain-ai/langgraph) |
| LLM Providers | Google, OpenAI, Anthropic, Ollama, Local |
| CLI | [Typer](https://typer.tiangolo.com/) + [Rich](https://rich.readthedocs.io/) |
| Database | SQLite (async via [aiosqlite](https://github.com/omnilib/aiosqlite)) |
| Scheduling | [APScheduler](https://apscheduler.readthedocs.io/) |

---

## 🤝 Contributing

Contributions are welcome! Please open an issue or pull request on [GitHub](https://github.com/zfab/agentmd).

```bash
# Development setup
uv sync
uv pip install -e ".[all]"
pytest              # Run tests
ruff format .       # Format code
```

---

## 📜 License

MIT License — use it, fork it, build on it.

---

<div align="center">

**Built with ❤️ and Markdown**

*If agents could write themselves, they'd choose Markdown too.*

[⭐ Star on GitHub](https://github.com/zfab/agentmd) • [📖 Read the Docs](https://zfab.github.io/agentmd)

</div>
