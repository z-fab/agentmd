# Agent.md

<div align="center" markdown>

<img src="assets/agentmd_banner.png" alt="Agent.md" width="400">

**Markdown-first runtime for AI agents**

Write a `.md` file, describe what your agent should do, and let it run.
No boilerplate. No frameworks to learn. Just Markdown.

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-3776AB?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/zfab/agentmd/blob/master/LICENSE)
[![Built with LangGraph](https://img.shields.io/badge/built%20with-LangGraph-FF6F00)](https://github.com/langchain-ai/langgraph)

[Get Started](quick-start.md){ .md-button .md-button--primary }
[Browse Examples](examples.md){ .md-button }
[API Docs](https://github.com/zfab/agentmd){ .md-button }

</div>

---

## :sparkles: Why Agent.md?

Most agent frameworks require dozens of files, complex configurations, and deep knowledge of LLM internals. **Agent.md takes a different approach:**

<div class="grid cards" markdown>

-   :fontawesome-solid-file-lines:{ .lg .middle } **One file = One agent**

    ---

    Each `.md` file is a complete agent definition — YAML frontmatter for config, Markdown body for the system prompt.

-   :zap:{ .lg .middle } **Zero boilerplate**

    ---

    No classes, no decorators, no framework lock-in. Just write what your agent should do in plain English.

-   :fontawesome-solid-clock:{ .lg .middle } **Flexible triggers**

    ---

    Run manually, on schedules (cron/intervals), or automatically when files change.

-   :fontawesome-solid-wrench:{ .lg .middle } **Built-in tools**

    ---

    File I/O and HTTP requests work out of the box. Add custom tools or MCP servers when you need more.

-   :fontawesome-solid-chart-line:{ .lg .middle } **Execution tracking**

    ---

    Every run is logged with status, duration, token usage, and full message history — queryable via SQL.

-   :fontawesome-brands-git-alt:{ .lg .middle } **Git-friendly**

    ---

    Version control your prompts. See exactly how agents evolved. Roll back with confidence.

</div>

---

## :rocket: Quick Example

Create `workspace/agents/hello-world.md`:

```markdown
---
name: hello-world
model:
  provider: google
  name: gemini-2.5-flash
---

You are a friendly assistant. When asked to execute your task,
write a creative greeting and save it to 'greeting.txt'.
```

Run it:

```bash
agentmd run hello-world
```

Output:

```
▶ Running hello-world  google/gemini-2.5-flash  custom_tools: none

17:29:32 hello-world 🤖 Greetings, esteemed user!

May your day be filled with as much wonder and intrigue as a hidden scroll in an ancient library, and may your tasks unfold with the grace and preci…
17:29:32 hello-world 🔧 file_write → {'content': "Greetings, esteemed user!\n\nMay your day be filled with as much wo
17:29:32 hello-world 📎 file_write ← File written successfully: /Users/.../workspace/output/greeting.txt (235 chars)
17:29:35 hello-world 🤖 Greetings, esteemed user!

I've successfully written a creative greeting to 'greeting.txt'. You can find it at `/Users/.../workspace/output/greeting.txt`.

May your day be filled with a

17:29:35 hello-world ✅ Final answer:
  Greetings, esteemed user!

I've successfully written a creative greeting to 'greeting.txt'. You can find it at `/Users/zfab/repos/agentmd/workspace/output/greeting.txt`.

May your day be filled with as much wonder and intrigue as a hidden scroll in an ancient library, and may your tasks unfold with the grace and 
precision of a master artisan. I'm delighted to assist you today!

✓ hello-world done in 5121ms  tokens: 1130 in / 243 out / 1373 total  execution #51

```

That's it. Your agent ran, used tools, and logged everything. :tada:

---

## :gear: Key Features

### Multi-Provider Support

Use any LLM provider — switch with a simple config change:

=== "Google Gemini"

    ```yaml
    model:
      provider: google
      name: gemini-2.5-flash
    ```

=== "OpenAI GPT"

    ```yaml
    model:
      provider: openai
      name: gpt-4o
    ```

=== "Anthropic Claude"

    ```yaml
    model:
      provider: anthropic
      name: claude-sonnet-4-5-20250929
    ```

=== "Ollama (Local)"

    ```yaml
    model:
      provider: ollama
      name: llama3
    ```

=== "Custom Endpoint"

    ```yaml
    model:
      provider: local
      name: mistral-7b
      base_url: "http://localhost:8000"
    ```

[See all providers →](providers.md)

### Trigger System

Agents can run in three ways:

| Trigger Type | Description | Example |
|---|---|---|
| **Manual** | Run on-demand via CLI | `agentmd run my-agent` |
| **Schedule** | Run on cron or intervals | Every 5 minutes, daily at 9am, weekdays only |
| **Watch** | Run when files change | Monitor logs, process uploads automatically |

[Learn about triggers →](triggers.md)

### Built-in Tools

Every agent automatically gets:

- **`file_read`** — Read files from workspace
- **`file_write`** — Create and write files (with security restrictions)
- **`http_request`** — Make HTTP calls (GET, POST, etc.)

[Explore tools →](tools/built-in-tools.md)

### MCP Integration

Connect to any [Model Context Protocol](https://modelcontextprotocol.io/) server:

```yaml
mcp:
  - fetch      # Web fetching
  - github     # GitHub API
  - puppeteer  # Browser automation
```

[MCP integration guide →](tools/mcp-integration.md)

### Custom Tools

Extend agents with Python:

```python
# workspace/agents/tools/sentiment.py
from langchain_core.tools import tool

@tool
def analyze_sentiment(text: str) -> str:
    """Analyzes sentiment of the given text."""
    # Your implementation
    return "positive"
```

```yaml
custom_tools:
  - sentiment
```

[Create custom tools →](tools/custom-tools.md)

---

## :books: What's Next?

<div class="grid cards" markdown>

-   :fontawesome-solid-rocket:{ .lg .middle } **[Quick Start](quick-start.md)**

    ---

    Install Agent.md and run your first agent in 5 minutes.

-   :fontawesome-solid-book:{ .lg .middle } **[Agent Configuration](agent-configuration.md)**

    ---

    Learn about agent files, triggers, providers, and execution flow.

-   :fontawesome-solid-code:{ .lg .middle } **[Examples](examples.md)**

    ---

    See real-world examples for every use case and feature.

-   :fontawesome-solid-download:{ .lg .middle } **[Documentation](https://github.com/zfab/agentmd)**

    ---

    Copy-paste ready agents for common tasks — just add your API keys.

</div>

---

## :tada: Features at a Glance

- [x] **Multi-provider support** — Google, OpenAI, Anthropic, Ollama, custom endpoints
- [x] **Flexible triggers** — Manual, schedule (cron/interval), file watching
- [x] **Built-in tools** — File I/O, HTTP requests
- [x] **Custom tools** — Extend with Python
- [x] **MCP integration** — Connect to external tool servers
- [x] **File access security** — Read/write path restrictions
- [x] **Execution tracking** — Full history with token usage
- [x] **Git-friendly** — Version control your prompts
- [ ] **Memory & context persistence** — Coming soon
- [ ] **Skills support** — Coming soon
- [ ] **Agent pipelines** — Chain agents together
- [ ] **Terminal UI (TUI)** — Real-time monitoring

[View full roadmap →](roadmap.md)

---

## :busts_in_silhouette: Community & Support

- **Documentation**: You're reading it!
- **GitHub**: [github.com/zfab/agentmd](https://github.com/zfab/agentmd)
- **Issues**: [Report bugs or request features](https://github.com/zfab/agentmd/issues)
- **Discussions**: [Share your agents and ideas](https://github.com/zfab/agentmd/discussions)

---

<div align="center" markdown>

**Built with :heart: and Markdown**

*If agents could write themselves, they'd choose Markdown too.*

[Get Started →](quick-start.md){ .md-button .md-button--primary }

</div>
