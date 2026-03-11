# Agent Configuration Reference

Complete reference for configuring agents via YAML frontmatter. This guide covers all configuration options for `.md` agent files.

## Overview

Every agent is defined in a `.md` file with YAML frontmatter and a Markdown body:

```yaml
---
name: my-agent
description: What this agent does
model:
  provider: google
  name: gemini-2.5-flash
settings:
  temperature: 0.7
  max_tokens: 4096
  timeout: 300
trigger:
  type: manual
---

Your system prompt goes here...
```

## Required Fields

### `name`

| Property | Value |
|----------|-------|
| **Type** | string |
| **Required** | Yes |
| **Pattern** | `^[a-zA-Z0-9_-]+$` |
| **Default** | None |

Unique identifier for the agent. Used in CLI commands, logs, and execution history.

- Must contain only alphanumeric characters, hyphens, and underscores
- Used with `agentmd run <name>` and `agentmd logs <name>`

```yaml
name: file-summarizer
name: daily-report-generator
name: api_poller
```

### `model`

| Property | Value |
|----------|-------|
| **Type** | object |
| **Required** | Yes |
| **Default** | None |

LLM configuration object with provider, model name, and optional API endpoint.

#### `model.provider`

| Property | Value |
|----------|-------|
| **Type** | string |
| **Required** | Yes |
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
| **Required** | Yes |
| **Default** | None |

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

## Optional Fields

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

Custom tool modules to load from `workspace/tools/`. Built-in tools (`file_read`, `file_write`, `http_request`) are always available.

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

### `read`

| Property | Value |
|----------|-------|
| **Type** | string \| string[] |
| **Required** | No |
| **Default** | `[workspace_root]` |

Allowed paths for reading files. See [Security & Paths](paths-and-security.md) for detailed options.

- Can be single path (string) or multiple paths (array)
- Relative paths resolve from workspace root
- Absolute paths used as-is
- Supports home directory expansion (`~`)

```yaml
# Single directory
read: ./data

# Multiple paths
read:
  - ./data
  - ./logs
  - /var/log/app

# Specific files
read:
  - ./config/settings.json
  - ./data/input.csv
```

**Security restrictions:**
- Cannot read `workspace/agents` directory
- Cannot read `.env*` files (credentials)

### `write`

| Property | Value |
|----------|-------|
| **Type** | string \| string[] |
| **Required** | No |
| **Default** | `[output_dir]` (workspace/output) |

Allowed paths for writing files. See [Security & Paths](paths-and-security.md) for detailed options.

- Can be single path (string) or multiple paths (array)
- First directory in array is default write location
- Relative paths resolve from default write directory
- Absolute paths used as-is

```yaml
# Single directory (default)
write: ./output

# Multiple directories
write:
  - ./reports
  - ./archive
  - /tmp/cache

# Specific files
write:
  - ./output/result.txt
```

**Security restrictions:**
- Cannot write to `workspace/agents` directory
- Cannot write to `.db` files (databases)
- Cannot write `.env*` files (credentials)

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
read: ./data
write: ./output
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
read:
  - /var/log/app
  - ./data/config.json
write:
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
write: ./processed
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
read:
  - ./research-queries
write:
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
- `provider` must be one of: `google`, `openai`, `anthropic`, `ollama`, `local`
- `name` must not be empty
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
- `read`/`write` can be string or string[]
- Cannot include forbidden directories (agents, .env files, .db files)
- Paths support relative (`./`), absolute (`/`), and home (`~`) expansion

### Custom Tools & MCP
- Must be non-empty arrays of strings
- Tool modules must be importable from `workspace/tools/`
- MCP servers must be defined in `mcp-servers.json`

## Configuration Inheritance & Defaults

When fields are omitted, defaults are applied:

```yaml
# Minimal valid agent
---
name: minimal-agent
model:
  provider: google
  name: gemini-2.5-flash
---
# Defaults:
# - trigger: { type: manual }
# - settings: { temperature: 0.7, max_tokens: 4096, timeout: 300 }
# - custom_tools: []
# - mcp: []
# - read: [workspace_root]
# - write: [output_dir]
# - enabled: true
```

## Related Documentation

- [Triggers](triggers.md) - Detailed schedule and watch options
- [Paths & Security](paths-and-security.md) - File access permissions and global path configuration
- [Custom Tools](tools/custom-tools.md) - Building custom tools
- [MCP Integration](tools/mcp-integration.md) - Using MCP servers
- [Providers](providers.md) - Supported LLM providers
