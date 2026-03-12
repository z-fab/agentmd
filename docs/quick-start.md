# Quick Start Guide

Get Agent.md running in 10 minutes—from installation to your first working agent.

## 1. Installation

### Prerequisites
- **Python 3.13+** ([download](https://www.python.org/downloads/))
- **git** ([download](https://git-scm.com/downloads))
- **API key** for one LLM provider (or skip with Ollama)

### Clone & Install
```bash
git clone https://github.com/z-fab/agentmd.git
cd agentmd

# Install with uv (recommended)
uv sync

# Install provider dependencies
uv pip install -e ".[all]"        # All providers
# OR choose one:
# uv pip install -e ".[openai]"     # OpenAI
# uv pip install -e ".[anthropic]"  # Anthropic
# uv pip install -e ".[ollama]"     # Ollama
```

### Verify Installation
```bash
agentmd --version
```

## 2. Set Up API Keys

Create `.env` file in project root:
```bash
cp .env.example .env
```

Edit `.env` and add your API key:
```bash
# .env
GOOGLE_API_KEY=your-key-here
# OR
OPENAI_API_KEY=your-key-here
# OR
ANTHROPIC_API_KEY=your-key-here
```

**Get a free API key:**
- [Google Gemini](https://makersuite.google.com/app/apikey) (free tier available)
- [OpenAI](https://platform.openai.com/api-keys) (requires credit card)
- [Anthropic](https://console.anthropic.com/) (requires credit card)
- [Ollama](https://ollama.com) (fully local, no key needed)

!!! warning "Security"
    Never commit `.env` to git. It's in `.gitignore` by default.

!!! tip "Using secrets in prompts"
    Use `${VAR_NAME}` in your agent's prompt body to inject `.env` values at runtime — no need to hardcode secrets. See [Environment Variable Substitution](agent-configuration.md#environment-variable-substitution).

## 3. Create Your First Agent

Create `workspace/agents/hello.md`:

```markdown
---
name: hello
description: First agent
model:
  provider: google
  name: gemini-2.5-flash
trigger:
  type: manual
settings:
  temperature: 0.7
  timeout: 30
enabled: true
---

You are a friendly assistant. Create a warm greeting message
and save it to a file called 'hello-output.txt'. Keep it
under 3 sentences and mention the date if possible.
```

**What this means:**
- **YAML frontmatter** (between `---`) = agent configuration
- **Markdown body** = system prompt (what the agent does)
- **provider/name** = which LLM to use
- **trigger: manual** = runs only when you execute it

## 4. Run Your Agent

```bash
agentmd run hello
```

You'll see live output:
```
▶ Running hello  google/gemini-2.5-flash

11:32:04 hello 🤖 I'll create a warm greeting for you...
11:32:05 hello 🔧 file_write → {'file_path': 'hello-output.txt', ...}
11:32:05 hello 📎 file_write ← File written successfully

11:32:05 hello ✅ Final answer:
  I've created a warm greeting and saved it to hello-output.txt!

✓ hello done in 523ms  tokens: 28 in / 87 out / 115 total  execution #1
```

## 5. Check the Output

```bash
cat workspace/output/hello-output.txt
```

Example:
```
Greetings! Today is March 11, 2026, and I'm delighted to connect with you.
May your day be filled with curiosity and purpose!
```

## 6. View Execution History

```bash
agentmd logs hello
```

Shows table with execution ID, status, duration, tokens used, etc.

## Next Steps

### Try Different Providers
```yaml
# Use Claude
model:
  provider: anthropic
  name: claude-sonnet-4-5-20250929

# Use GPT-4
model:
  provider: openai
  name: gpt-4o-mini

# Use local Ollama
model:
  provider: ollama
  name: llama3
```

→ [Full provider guide](providers.md)

### Add Scheduling
Make agent run automatically:
```yaml
trigger:
  type: schedule
  every: 1h    # Run hourly
```

Then start the runtime:
```bash
agentmd start
```

→ [Trigger configuration](triggers.md)

### Use HTTP Requests
Fetch data from APIs:
```markdown
---
name: quote-fetcher
model:
  provider: google
  name: gemini-2.5-flash
trigger:
  type: manual
---

Fetch a random quote from https://zenquotes.io/api/random
Parse the JSON and save the best quote to 'daily-quote.txt'.
```

→ [HTTP examples](examples.md)

### Explore Ready-Made Agents
Copy and customize from our library:
- [Code examples](examples.md)

### Learn Core Concepts
- [Agent configuration](agent-configuration.md)
- [Paths & Security](paths-and-security.md)
- [Tools reference](tools/built-in-tools.md)

### CLI Commands Reference
- `agentmd run <agent>` — Execute single agent
- `agentmd start` — Start runtime with scheduler
- `agentmd list` — List all agents
- `agentmd logs <agent>` — View execution history
- `agentmd validate <file>` — Check agent syntax

→ [Full CLI reference](cli-reference.md)

## Troubleshooting

**"API key not found"**
- Check `.env` exists in project root
- Verify key name matches provider (e.g., `GOOGLE_API_KEY`)
- No spaces around `=` in `.env`

**"No such file or directory"**
- Run `agentmd` from project root
- Verify workspace/agents/ directory exists

**"Provider requires langchain-..."**
- Install the provider: `uv pip install -e ".[openai]"`

→ [View troubleshooting above](#troubleshooting)

---

**You've got this!** You now understand:
- How to install Agent.md
- How to configure API keys
- How to create an agent file
- How to execute agents and view results

Start building! 🚀
