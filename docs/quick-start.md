# Quick Start Guide

Get Agent.md running in 5 minutes—from installation to your first working agent.

## 1. Installation

### Prerequisites
- **Python 3.13+** ([download](https://www.python.org/downloads/))
- **API key** for one LLM provider (or skip with Ollama)

### Option A: One-line install (recommended)

**Linux/macOS:**
```bash
curl -fsSL https://raw.githubusercontent.com/z-fab/agentmd/master/install.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/z-fab/agentmd/master/install.ps1 | iex
```

This installs `uv` (if needed), `agentmd`, and runs the interactive setup wizard that configures your workspace, provider, and API key.

### Option B: Developer setup

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

Then run the setup wizard:
```bash
agentmd setup
```

### Verify Installation
```bash
agentmd --help
agentmd config    # Show current configuration
```

## 2. Configuration

The setup wizard creates two files in your workspace:

### `config.yaml` — Application settings

```yaml
workspace: ~/agentmd
agents_dir: agents
output_dir: output

defaults:
  provider: google
  model: gemini-2.5-flash
```

### `.env` — API keys (secrets only)

```bash
GOOGLE_API_KEY=your-key-here
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

The fastest way is with `agentmd new`:

```bash
agentmd new hello
```

If you have a provider configured, it will ask what the agent should do and generate the file using AI. Otherwise (or with `--template`), it walks you through an interactive questionnaire:

```bash
agentmd new hello --template
```

You can also create agents manually — just add an `.md` file to `agents/`:

```markdown
---
name: hello
description: First agent
---

You are a friendly assistant. Create a warm greeting message
and save it to a file called 'hello-output.txt'. Keep it
under 3 sentences and mention the date if possible.
```

**What this means:**
- **YAML frontmatter** (between `---`) = agent configuration
- **Markdown body** = system prompt (what the agent does)
- **No `model` needed** — uses the default from `config.yaml`

!!! tip "Override the default model"
    To use a specific model for an agent, add a `model` section:
    ```yaml
    model:
      provider: openai
      name: gpt-4o
    ```

## 4. Run Your Agent

```bash
agentmd run hello
```

You'll see live output:
```
  ▶ Running hello
    google / gemini-2.5-flash

  11:32:04  🤖 I'll create a warm greeting for you...
  11:32:05  🔧 file_write → {'file_path': 'hello-output.txt', ...}
  11:32:05  📎 file_write ← File written successfully

  11:32:05  ✅ I've created a warm greeting and saved it to hello-output.txt!

  ✓ hello completed in 523ms
    Tokens: 28 in / 87 out / 115 total
    Execution #1
```

## 5. Check the Output

```bash
cat ~/agentmd/output/hello-output.txt
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

Override the default model per agent:

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
- `agentmd new <name>` — Scaffold a new agent (AI-assisted or interactive)
- `agentmd run [agent]` — Execute single agent (interactive picker if omitted)
- `agentmd start` — Start runtime with scheduler (`-d` for daemon mode)
- `agentmd list` — List all agents
- `agentmd logs <agent>` — View execution history (`-f` to follow)
- `agentmd validate [agent]` — Validate agent configuration
- `agentmd status` — Check if runtime is running
- `agentmd stop` — Stop background runtime
- `agentmd config` — Show current configuration
- `agentmd setup` — Interactive setup wizard
- `agentmd update` — Update to latest version

→ [Full CLI reference](cli-reference.md)

## Troubleshooting

**"API key not found"**
- Check `.env` exists in your workspace
- Verify key name matches provider (e.g., `GOOGLE_API_KEY`)
- Run `agentmd config` to see which files are being loaded

**"No agents found in workspace"**
- Run `agentmd config` to check your workspace path
- Verify the `agents/` directory exists and contains `.md` files

**"Provider requires langchain-..."**
- Install the provider: `pip install agentmd[openai]`

---

**You've got this!** You now understand:
- How to install Agent.md
- How to configure with `config.yaml` and `.env`
- How to create an agent file (with optional model override)
- How to execute agents and view results

Start building! 🚀
