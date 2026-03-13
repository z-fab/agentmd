# Architecture Overview

Agent.md is a markdown-first runtime for AI agents. Each agent is a single `.md` file with YAML frontmatter (config) and a Markdown body (system prompt). The runtime parses these files, builds a LangGraph ReAct agent, and executes it with tool support, scheduling, and execution tracking.

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Core Runtime** | Python 3.13+ | Agent execution engine |
| **Agent Logic** | LangGraph | ReAct pattern orchestration |
| **LLM Abstraction** | LangChain | Unified provider interface |
| **Config Validation** | Pydantic | Type-safe configuration parsing |
| **CLI Interface** | Typer + Rich | User-friendly command-line interface |
| **Persistence** | SQLite + aiosqlite | Async execution history storage |
| **Session Memory** | langgraph-checkpoint-sqlite | Conversation history across runs |
| **Scheduling** | APScheduler | Cron/interval-based triggers |
| **Async I/O** | AsyncIO | Non-blocking execution throughout |

## System Architecture

```
Agent .md file (YAML + Markdown)
    ↓
Parser → AgentConfig (Pydantic validated)
    ↓
LLM Factory (OpenAI, Anthropic, Google, Ollama, Local)
    ↓
Tool Resolver (Built-in + Custom + MCP)
    ↓
ReAct Graph (LangGraph)
    ├─ Call LLM (system prompt + user input)
    ├─ Execute tools if requested
    ├─ Loop until final answer
    └─ Stream all messages in real-time
    ↓
Execution Logger (SQLite + Console)
```

## Key Components

### 1. Parser (`agent_md/core/parser.py`)
Extracts YAML frontmatter (config) and Markdown body (system prompt) from `.md` files. Validates config against Pydantic models. Computes config hash for change detection (hot-reload).

### 2. AgentConfig (`agent_md/core/models.py`)
Pydantic models validating:
- **AgentConfig** — Top-level agent configuration
- **ModelConfig** — LLM provider settings (model name, API key, temperature, etc.)
- **SettingsConfig** — Runtime settings (output directory, timeout, max retries)
- **ToolsConfig** — Tool definitions and parameters

### 3. Provider Factory (`agent_md/providers/factory.py`)
Single entry point for creating LLM instances. Supports: `google`, `openai`, `anthropic`, `ollama`, `local`. Uses lazy imports to keep unused providers from loading. Reads API keys automatically from environment variables (LangChain built-in).

### 4. Tool System (`agent_md/tools/`)
Three types of tools available:

**Built-in Tools** (always available):
- `file_read` — Read files (with path validation)
- `file_write` — Write/create files (with path validation)
- `http_request` — Make HTTP GET/POST requests
- `memory_save` / `memory_append` / `memory_retrieve` — Long-term memory

**Custom Tools** — Loaded from `tools/` directory per agent
**MCP Tools** — Connected via Model Context Protocol servers

### 5. ReAct Agent (`agent_md/graph/`)
LangGraph-based agent implementing Reasoning + Acting pattern:
```
START
  ↓
[Call LLM] ← system prompt + conversation history
  ↓
Has tool calls? ─ No → END (final answer)
  ↓ Yes
[Execute Tools] (file I/O, HTTP, etc.)
  ↓
[Format results as messages]
  ↓
[Call LLM again] ← tool results
  ↓
(repeat...)
```

### 6. Scheduler (`agent_md/core/scheduler.py`)
APScheduler-based task scheduling:
- **Manual** — Triggered via CLI: `agentmd run <agent>`
- **Schedule** — Cron or interval-based: `every: 30m`, `cron: "0 9 * * *"`
- **Watch** — File system events: monitors paths and triggers on file changes

### 7. Execution Logger (`agent_md/core/logger.py`)
SQLite-backed persistence recording:
- Execution metadata (status, duration, timestamps)
- All messages (system, human, AI, tool calls, tool results)
- Token usage (input + output tokens accumulated across all AI calls)
- Errors and final answer

## Execution Flow (Simplified)

```
1. Load & Parse
   Agent .md file → YAML + Markdown → AgentConfig (validated)

2. Create Chat Model
   AgentConfig.model → Factory → LangChain BaseChatModel (LLM instance)

3. Resolve Tools
   Built-in tools + Custom tools + MCP tools → Tool list

4. Build ReAct Graph
   LLM + Tools → LangGraph StateGraph (the agent loop)

5. Build Messages
   System prompt (Markdown body) + User input → LangChain messages

6. Stream Execution
   Iterate: [Call LLM] → [Tool calls?] → [Execute tools] → [Next iteration]
   Stream each message in real-time, accumulate token usage

7. Log & Persist
   Save execution record to SQLite, emit console output via Rich
```

## Design Principles

1. **Markdown-First** — Agents are single `.md` files; config and prompt co-located
2. **Async Throughout** — All I/O is non-blocking via asyncio for scalability
3. **Streaming-First** — Responses stream in real-time; token usage accumulates continuously
4. **Factory Pattern** — Single entry point (`create_chat_model()`) for LLM creation
5. **Lazy Loading** — Provider packages are optional; only load what you use
6. **Type Safety** — Pydantic validates all configuration before runtime
7. **No Manual API Keys** — LangChain reads from env vars automatically
8. **Stateful When Needed** — Session history and long-term memory, with stateless as opt-out

## Directories

```
agent_md/
  core/       → Runner, parser, models, settings, scheduler
  providers/  → LLM provider factory
  graph/      → LangGraph ReAct agent
  tools/      → Built-in tools (file I/O, HTTP)
  mcp/        → MCP server integration
  cli/        → Typer CLI commands

workspace/   → User agent .md files
output/      → Default output directory for agent artifacts
```

## Typical Workflow

1. **Create** — Write a `.md` agent in `workspace/`
2. **Configure** — Add YAML frontmatter with model, tools, triggers
3. **Test** — Run `agentmd run <agent>` manually
4. **Schedule** — Use `agentmd start` for scheduled/watch-based execution
5. **Monitor** — View execution history with `agentmd logs <agent>`

## Key Files

| File | Purpose |
|------|---------|
| `agent_md/providers/factory.py` | LLM instance creation (factory pattern) |
| `agent_md/core/runner.py` | Execution orchestration (full lifecycle) |
| `agent_md/core/models.py` | Pydantic config models |
| `agent_md/core/parser.py` | Parse `.md` files (frontmatter + body) |
| `agent_md/core/settings.py` | Environment variable loading |
| `agent_md/graph/create_react_graph.py` | Build LangGraph ReAct agent |

## For Contributors

- **Adding a new provider?** → Extend `create_chat_model()` in `agent_md/providers/factory.py`
- **Adding a new built-in tool?** → Register in `agent_md/tools/registry.py`
- **Modifying config?** → Update Pydantic models in `agent_md/core/models.py`
- **Changing execution flow?** → Edit `agent_md/core/runner.py` or `agent_md/graph/`
- **Debugging?** → Enable debug logs and check `agentmd logs <agent>`
