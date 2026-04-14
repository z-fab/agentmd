# Agent Configuration Reference

Complete reference for configuring agents via YAML frontmatter. This guide covers all configuration options for `.md` agent files.

## Overview

Every agent is defined in a `.md` file with YAML frontmatter and a Markdown body:

```yaml
---
name: my-agent
description: What this agent does
settings:
  temperature: 0.7
  max_tokens: 4096
  timeout: 300
trigger:
  type: manual
---

Your system prompt goes here...
```

> **Note:** The `model` field is optional. When omitted, Agent.md uses the default provider and model from your `config.yaml`.

## Required Fields

### `name`

| Property | Value |
|----------|-------|
| **Type** | string |
| **Required** | Yes |
| **Pattern** | `^[a-zA-Z0-9_-]+$` |
| **Default** | None |

Unique identifier for the agent. This is the canonical name used everywhere: CLI commands, API, logs, SSE events, and the `agents` allowlist for delegation.

- Must contain only alphanumeric characters, hyphens, and underscores
- Used with `agentmd run <name>`, `agentmd logs <name>`, API endpoints, and agent-to-agent calls

```yaml
name: file-summarizer
name: daily-report-generator
name: api_poller
```

## Optional Fields

### `model`

| Property | Value |
|----------|-------|
| **Type** | object |
| **Required** | No |
| **Default** | From `config.yaml` defaults |

LLM configuration object with provider, model name, and optional API endpoint.

When omitted, the agent uses the default provider and model defined in `config.yaml`:

```yaml
# config.yaml
defaults:
  provider: google
  model: gemini-2.5-flash
```

To override the default for a specific agent:

#### `model.provider`

| Property | Value |
|----------|-------|
| **Type** | string |
| **Required** | Yes (when `model` is specified) |
| **Allowed values** | `google`, `openai`, `anthropic`, `ollama`, `local` |

LLM provider to use. Each provider requires its API key in environment variables:
- `google` → `GOOGLE_API_KEY`
- `openai` → `OPENAI_API_KEY`
- `anthropic` → `ANTHROPIC_API_KEY`
- `ollama` → (local, no key needed)
- `local` → (custom OpenAI-compatible endpoint)

```yaml
model:
  provider: google
```

#### `model.name`

| Property | Value |
|----------|-------|
| **Type** | string |
| **Required** | Yes (when `model` is specified) |
| **Default** | From `config.yaml` defaults |

Model identifier (provider-specific):

- **Google:** `gemini-2.5-flash`, `gemini-1.5-pro`, `gemini-1.5-flash`
- **OpenAI:** `gpt-4`, `gpt-4-turbo`, `gpt-3.5-turbo`
- **Anthropic:** `claude-opus-4-6`, `claude-sonnet-4-5`, `claude-3-haiku`
- **Ollama:** `llama2`, `mistral`, `neural-chat`, etc.
- **Local:** Any OpenAI-compatible model name

```yaml
model:
  provider: openai
  name: gpt-4
```

#### `model.base_url` / `model.url`

| Property | Value |
|----------|-------|
| **Type** | string |
| **Required** | Conditional (required for `local` provider) |
| **Aliases** | `base_url`, `url` |
| **Default** | Provider default |

Base URL for API endpoint. Only needed for custom or local LLM endpoints.

- For `local` provider: Required
- For others: Optional (uses provider default)
- System auto-appends `/v1` if missing

```yaml
model:
  provider: local
  name: llama-3.1-8b
  base_url: http://localhost:8000

model:
  provider: local
  name: mistral-7b
  url: http://vllm:5000  # Alias: url instead of base_url
```

### `description`

| Property | Value |
|----------|-------|
| **Type** | string |
| **Required** | No |
| **Default** | `""` |

Human-readable description of what the agent does. Displayed in `agentmd list` output.

```yaml
description: Analyzes CSV files and generates statistical reports
```

### `trigger`

| Property | Value |
|----------|-------|
| **Type** | object |
| **Required** | No |
| **Default** | `{ type: manual }` |

Determines when the agent executes. See [Triggers](triggers.md) for detailed options.

**Three trigger types:**

1. **`manual`** - Run via CLI only (default)
2. **`schedule`** - Run automatically on interval or cron schedule
3. **`watch`** - Run when files change

```yaml
# Manual (default)
trigger:
  type: manual

# Every 5 minutes
trigger:
  type: schedule
  every: 5m

# Daily at 9 AM
trigger:
  type: schedule
  cron: "0 9 * * *"

# When files change
trigger:
  type: watch
  paths:
    - ./data
```

### `settings`

| Property | Value |
|----------|-------|
| **Type** | object |
| **Required** | No |
| **Default** | `{ temperature: 0.7, max_tokens: 4096, timeout: 300 }` |

LLM runtime behavior settings. Customize LLM behavior with temperature, max_tokens, and timeout.

#### `settings.temperature`

| Property | Value |
|----------|-------|
| **Type** | float |
| **Range** | `0.0` - `1.0` |
| **Default** | `0.7` |

Controls randomness in model responses:

- **0.0-0.3:** Deterministic, focused (code generation, analysis)
- **0.4-0.7:** Balanced (general-purpose, default)
- **0.8-1.0:** Creative, varied (brainstorming, writing)

```yaml
settings:
  temperature: 0.2  # Precise code generation
```

#### `settings.max_tokens`

| Property | Value |
|----------|-------|
| **Type** | integer |
| **Range** | Provider-dependent (1-128000) |
| **Default** | `4096` |

Maximum tokens in model response (input tokens not included).

- **1024-2048:** Short responses (summaries)
- **4096:** Default (most tasks)
- **8192+:** Longer outputs (reports, documents)

```yaml
settings:
  max_tokens: 8192  # Comprehensive reports
```

#### `settings.timeout`

| Property | Value |
|----------|-------|
| **Type** | integer |
| **Unit** | seconds |
| **Default** | `300` (5 minutes) |

Maximum time waiting for LLM response before aborting.

- **30:** Quick tasks
- **60:** Standard operations
- **300:** Complex tasks (default)
- **600+:** Long-running operations

```yaml
settings:
  timeout: 120  # Allow 2 minutes
```

### Execution Limits

Control resource usage per execution:

```yaml
settings:
  max_tool_calls: 50          # default: 50
  max_execution_tokens: 500000 # default: 500,000
  max_cost_usd: 0.50          # default: none
  loop_detection: true         # default: true
```

See [Execution Limits](limits.md) for details on how limits work,
global defaults, and pricing configuration.

**Example configurations:**

```yaml
# Data Analysis
settings:
  temperature: 0.5
  max_tokens: 8192
  timeout: 180

# Code Generation
settings:
  temperature: 0.2
  max_tokens: 8192
  timeout: 120

# Quick Summaries
settings:
  temperature: 0.3
  max_tokens: 2048
  timeout: 60
```

### `custom_tools` / `tools`

| Property | Value |
|----------|-------|
| **Type** | string[] |
| **Required** | No |
| **Alias** | `custom_tools`, `tools` |
| **Default** | `[]` |

Custom tool modules to load from `workspace/tools/`. Built-in tools (`file_read`, `file_write`, `file_edit`, `file_glob`, `http_request`) are always available.

```yaml
custom_tools:
  - my_custom_tool
  - another_tool

# Or alias:
tools:
  - email_sender
  - database_client
```

### `mcp`

| Property | Value |
|----------|-------|
| **Type** | string[] |
| **Required** | No |
| **Default** | `[]` |

MCP (Model Context Protocol) servers to load tools from. Server definitions come from `mcp-servers.json`. See [MCP Integration](tools/mcp-integration.md).

```yaml
mcp:
  - fetch
  - filesystem
  - web-search
```

### `skills`

| Property | Value |
|----------|-------|
| **Type** | string \| string[] |
| **Required** | No |
| **Default** | `[]` |

List of skill names to enable for this agent. Skills are loaded from `workspace/agents/skills/<name>/SKILL.md`. See [Skills](skills.md) for full documentation.

```yaml
skills:
  - analyze-pr
  - generate-report

# Or single skill:
skills: review-code
```

When skills are enabled, three tools are added: `skill_use`, `skill_read_file`, and `skill_run_script`.

### `agents`

| Property | Value |
|----------|-------|
| **Type** | string \| string[] |
| **Required** | No |
| **Default** | `[]` |

List of agent names this agent is allowed to call via the `run_agent` tool. Agents are referenced by their frontmatter `name`. See [Agent Delegation](tools/run-agent.md) for full documentation.

```yaml
agents:
  - web-researcher
  - summarizer

# Or single agent:
agents: summarizer
```

When agents are configured, the `run_agent` tool is added automatically.

### `paths`

| Property | Value |
|----------|-------|
| **Type** | dict[string, string] |
| **Required** | No |
| **Default** | `[workspace_root]` |

Allowed paths for file operations (reading, writing, editing, and discovering files). Each key is a named alias, each value is the path. Use `{alias}` syntax in prompts and file tools. See [Security & Paths](paths-and-security.md) for detailed options.

- Keys are alias names, values are paths
- Relative paths resolve from workspace root
- Absolute paths used as-is
- Supports home directory expansion (`~`)
- All file tools accept `{alias}` syntax: `file_read("{data}/input.csv")`

```yaml
# Single directory
paths:
  data: ./data

# Multiple paths
paths:
  data: ./data
  logs: ./logs
  app_logs: /var/log/app

# Specific files
paths:
  settings: ./config/settings.json
  input: ./data/input.csv
```

**Security restrictions:**
- Cannot access `workspace/agents` directory
- Cannot access `.env*` files (credentials)
- Cannot write to `.db` files (databases)

### `history`

| Property | Value |
|----------|-------|
| **Type** | string |
| **Required** | No |
| **Allowed values** | `low`, `medium`, `high`, `off` |
| **Default** | `low` |

Controls session history persistence via LangGraph checkpointing. Determines how many past messages are sent to the LLM on each execution.

- `low` (default): Last 10 messages — lightweight context
- `medium`: Last 50 messages — good for chat and multi-session workflows
- `high`: Last 200 messages — deep context for research and long projects
- `off`: Stateless — no history between runs

All messages are always saved to the checkpoint database; this setting only controls how many are sent to the LLM.

**Trimming behavior:** At the start of each run, the runtime applies smart compaction before count-based trimming:

1. Only the latest `SystemMessage` is kept (stale prompts from previous runs are discarded)
2. Skill instructions (`<skill-context>`) from previous runs are compacted to lightweight breadcrumbs
3. Large tool results (>500 chars) are truncated
4. Count-based limit is applied (10/50/200 messages)

Trimming runs **only at the start of each run** — during execution, the full conversation is available to the LLM. See [Memory](memory.md) for details.

```yaml
# Chat agent with extended history
history: medium

# Stateless one-shot agent
history: off
```

### `enabled`

| Property | Value |
|----------|-------|
| **Type** | boolean |
| **Required** | No |
| **Default** | `true` |

Whether agent is loaded by the runtime scheduler. Disabled agents skip scheduler but can still run manually.

- `true` (default): Agent is loaded and scheduled
- `false`: Agent is skipped (use `agentmd run` to override)

```yaml
enabled: false  # Won't run on schedule, but can run manually
```

## Field Aliases

Some fields accept aliases:

| Canonical | Alias |
|-----------|-------|
| `custom_tools` | `tools` |
| `base_url` | `url` |

```yaml
# Both are equivalent:
custom_tools: [tool1, tool2]
tools: [tool1, tool2]

model:
  base_url: http://localhost:8000
model:
  url: http://localhost:8000
```

## Environment Variable Substitution

Use `${VAR_NAME}` syntax in the prompt body (Markdown section) to inject values from `.env` or shell environment at runtime. This keeps secrets out of agent files.

```markdown
---
name: api-caller
model:
  provider: google
  name: gemini-2.5-flash
---

Fetch data from ${API_ENDPOINT} using header "Authorization: Bearer ${API_TOKEN}".
Summarize the response and save to `output/result.txt`.
```

With `.env`:
```bash
API_ENDPOINT=https://api.example.com/data
API_TOKEN=sk-my-secret-token
```

At runtime, the prompt becomes:
```
Fetch data from https://api.example.com/data using header "Authorization: Bearer sk-my-secret-token".
```

### Rules

- **Syntax:** `${VAR_NAME}` — the `$` prefix is required
- **Undefined variables** remain as literal `${VAR_NAME}` (no error)
- **`{var}` without `$`** is **not** substituted — use this for placeholders the LLM should fill in (e.g., `{date}`, `{filename}`)
- Substitution applies to the **Markdown body only**, not YAML frontmatter
- Same syntax used in [MCP configuration](tools/mcp-integration.md)

### Example: Mixing env vars and LLM placeholders

```markdown
---
name: gmail-digest
model:
  provider: google
  name: gemini-2.5-flash
---

1. Fetch emails from ${GMAIL_SCRIPT_URL}?token=${GMAIL_SECRET}
2. Analyze and classify each email
3. Save result to output/digest-{date}.md
```

Here `${GMAIL_SCRIPT_URL}` and `${GMAIL_SECRET}` are replaced with `.env` values, while `{date}` is left for the LLM to fill with the current date.

## Complete Examples

### Example 1: Basic File Processor

```yaml
---
name: csv-analyzer
description: Analyzes CSV files and generates insights
model:
  provider: google
  name: gemini-2.5-flash
settings:
  temperature: 0.5
  max_tokens: 4096
  timeout: 60
paths:
  - ./data
  - ./output
---

Analyze the provided CSV file and generate a summary report including:
1. Data statistics and distributions
2. Missing values and anomalies
3. Key insights and patterns
4. Recommendations for further analysis
```

### Example 2: Scheduled Daily Report

```yaml
---
name: daily-reporter
description: Generates daily summary reports from application logs
model:
  provider: anthropic
  name: claude-sonnet-4-5
trigger:
  type: schedule
  cron: "0 9 * * *"  # Every day at 9 AM
settings:
  temperature: 0.5
  max_tokens: 8192
  timeout: 180
custom_tools:
  - log_parser
paths:
  - /var/log/app
  - ./data/config.json
  - ./reports
  - ./archive
enabled: true
---

Analyze application logs from the past 24 hours and generate a comprehensive report with:
1. Error summary and severity breakdown
2. Performance metrics
3. Notable events and patterns
4. Recommendations and action items
Save to daily-report-{date}.md
```

### Example 3: File Watcher

```yaml
---
name: file-processor
description: Processes new data files as they arrive
model:
  provider: openai
  name: gpt-4
trigger:
  type: watch
  paths:
    - ./inbox
settings:
  temperature: 0.3
  max_tokens: 2048
  timeout: 90
tools:
  - file_validator
  - data_transformer
paths: ./processed
---

When files appear in the inbox:
1. Validate file format and content
2. Transform and normalize data
3. Generate processing report
4. Move to processed directory
```

### Example 4: Local Model with MCP

```yaml
---
name: research-assistant
description: Web research agent with local LLM
model:
  provider: local
  name: llama-3.1-8b
  base_url: http://localhost:8000
settings:
  temperature: 0.7
  max_tokens: 4096
  timeout: 300
trigger:
  type: manual
mcp:
  - fetch
  - web-search
paths:
  - ./research-queries
  - ./research-results
---

You are a research assistant. For each query:
1. Search the web using available tools
2. Read and summarize relevant sources
3. Compile findings into a comprehensive report
4. Cite all sources
```

## Validation Rules

The system validates agent configuration during startup and before execution:

### Agent Name
- Must match pattern: `^[a-zA-Z0-9_-]+$`
- Cannot be empty

### Model Configuration
- `model` is optional — when omitted, uses defaults from `config.yaml`
- When specified: `provider` must be one of: `google`, `openai`, `anthropic`, `ollama`, `local`
- When specified: `name` must not be empty
- `base_url` required for `local` provider

### Trigger Configuration
- `type` must be: `manual`, `schedule`, or `watch`
- **Schedule triggers:** Must have `every` OR `cron` (not both, not neither)
- **Watch triggers:** Must have `paths` with at least one entry

### Settings
- `temperature`: 0.0 - 1.0
- `max_tokens`: Positive integer
- `timeout`: Positive integer (seconds)

### Path Configuration
- `paths` can be string or string[]
- Cannot include forbidden directories (agents, .env files, .db files)
- Paths support relative (`./`), absolute (`/`), and home (`~`) expansion

### Custom Tools & MCP
- Must be non-empty arrays of strings
- Tool modules must be importable from `workspace/tools/`
- MCP servers must be defined in `mcp-servers.json`

## Configuration Inheritance & Defaults

When fields are omitted, defaults are applied:

```yaml
# Minimal valid agent — uses default model from config.yaml
---
name: minimal-agent
---
# Defaults:
# - model: from config.yaml defaults (e.g., google/gemini-2.5-flash)
# - trigger: { type: manual }
# - settings: { temperature: 0.7, max_tokens: 4096, timeout: 300 }
# - history: low (last 10 messages)
# - custom_tools: []
# - mcp: []
# - skills: []
# - paths: [workspace_root]
# - enabled: true
```

## Related Documentation

- [Skills](skills.md) - Reusable instruction packages
- [Memory](memory.md) - Session history and long-term memory
- [Triggers](triggers.md) - Detailed schedule and watch options
- [Paths & Security](paths-and-security.md) - File access permissions and global path configuration
- [Custom Tools](tools/custom-tools.md) - Building custom tools
- [MCP Integration](tools/mcp-integration.md) - Using MCP servers
- [Providers](providers.md) - Supported LLM providers
