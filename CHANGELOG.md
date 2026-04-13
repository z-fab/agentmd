# Changelog

All notable changes to Agent.md are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [0.9.1] — 2026-04-12

### Fixed
- **Cancellation of scheduled/watched executions** — scheduled and file-watch triggered executions now register cancel events, making `DELETE /executions/{id}` work for all execution types
- **Cancel endpoint tolerant** — `DELETE /executions/{id}` returns 200 for already-finished executions instead of 409
- **Watcher decoupled from scheduler** — `_AgentWatchHandler` receives an execute function instead of a scheduler reference, removing unnecessary coupling
- **`pricing.yaml` missing from package** — added to `setuptools.package-data` so it's included in pip/uv installations

## [0.9.0] — 2026-04-11

### Breaking Changes
- **Workspace restructured** — tools, skills, MCP config, and .env moved to `agents/_config/`
- **Database moved** to `~/.local/state/agentmd/` (out of workspace)
- **`agent_md.core` removed** — split into `agent_md.config`, `agent_md.execution`, `agent_md.workspace`
- **Migration code removed** — users recreate workspace via `agentmd setup`
- **`agentmd config` renamed to `agentmd info`**
- **`--reconfigure` flag removed** from setup (auto-detects existing config)

### Added
- All agent defaults configurable via `config.yaml` (temperature, max_tokens, timeout, history, loop_detection, max_execution_tokens)
- `.env` precedence: workspace (`agents/_config/.env`) overrides global (`~/.config/agentmd/.env`)
- Setup wizard asks all configurable defaults: LLM settings (temperature, max_tokens), execution limits (timeout, max_tool_calls, max_execution_tokens, max_cost_usd, loop_detection), and agent defaults (history)

### Changed
- `agentmd config` → `agentmd info`
- Setup wizard suggests `agentmd new` as next step instead of `agentmd start`
- `agentmd new` AI prompt uses capability descriptions instead of tool signatures
- `agentmd new --template` simplified to 3 questions (description, trigger, paths)
- Sandbox blocks `agents/_config/` instead of entire `agents/` directory
- Auto-start on login removed from setup wizard

### Removed
- `agent_md/core/` package (split into 3 subpackages)
- `workspace/` directory from git repository
- DB migration code (ALTER TABLE statements)
- Backward-compatibility shims in skills loader and CLI

## [0.8.0] — 2026-04-11

### Breaking Changes
- **Backend replaces daemon** — `agentmd start` now runs a FastAPI HTTP backend over Unix socket
- Old daemon (`daemon.py`) removed entirely
- `agentmd start` default is now foreground (use `-d`/`--daemon` for background)

### Added
- HTTP API with 15 endpoints for agents, executions, scheduler, and health
- SSE streaming for real-time execution events (`GET /executions/{id}/stream`) with DB catchup + live dedup
- Execution cancellation via `DELETE /executions/{id}` and Ctrl+C in CLI
- EventBus — in-memory pub/sub for execution events between runner and SSE clients
- CLI auto-spawn — `agentmd run` and `agentmd chat` start the backend automatically if not running
- Lifecycle manager with idle timeout (5min default, `--keep-alive` to disable)
- API key authentication for TCP transport (`--port` + `--api-key`)
- DB WAL mode for concurrent reader/writer access
- `POST /agents/reload` — re-parse agent files from disk without restart
- Scheduler pause/resume via `POST /scheduler/pause` and `/resume`
- `GET /agents/{name}` includes `next_run` for scheduled agents
- `POST /agents/{name}/run` accepts optional `message` field — chat is just repeated runs with user messages
- Chat mode in CLI — discrete display with accumulated session stats (turns, time, tokens, cost)
- "No final response" indicator when agent completes without a text response
- OpenAPI docs available at `/docs` (Swagger) and `/redoc` while backend is running

### Changed
- CLI `run` streams events via SSE with structured output (tool calls with `>>`, results with `<<`, final answer with `✅`)
- CLI `chat` shows only the response text, with tools and thinking in dim gray
- CLI `start`/`stop`/`status` are now thin HTTP clients
- `list`, `logs`, `validate` remain static (read-only DB, no backend needed)
- DB opened in read-only mode for static CLI commands
- Backend is the sole DB writer (eliminates SQLite lock contention)

### Fixed
- Ghost processes no longer possible (backend owns all executions)
- Cold start eliminated for subsequent runs (backend keeps state warm)

## [0.7.1] — 2026-04-10

### Added

- **Execution limits** — configurable hard limits to prevent runaway agents:
  - `max_tool_calls` (default: 50) — abort after N tool invocations
  - `max_execution_tokens` (default: 500,000) — abort when cumulative input+output tokens exceed limit
  - `max_cost_usd` (default: none) — abort when estimated cost exceeds cap
  - `loop_detection` (default: true) — abort when the same tool error repeats 3 consecutive times
- **Pricing registry** — built-in cost-per-token table for Google, OpenAI, and Anthropic models. Override or add models via `~/.config/agentmd/pricing.yaml`.
- **Cost tracking** — estimated cost persisted in the database and shown in `agentmd logs` when available
- **Ghost cleanup** — PID tracked per execution; orphaned executions (dead process) automatically marked `orphaned` on startup
- **Global limit defaults** — configure default limits for all agents in `~/.config/agentmd/config.yaml` under `defaults:`
- **Validate pricing warning** — `agentmd validate` warns when `max_cost_usd` is set but the model has no pricing data
- **New execution statuses** — `aborted` (limit hit), `orphaned` (process died) shown in `agentmd logs`
- **Execution limits documentation** — `docs/limits.md` with configuration, pricing overrides, and behavior reference

### Fixed

- **`file_glob` sandbox warnings** — glob results are now filtered silently instead of logging a warning per rejected file (reduces noise in terminal and LLM context)
- **`data/` directory blocked in sandbox** — agents can no longer access the database directory via file tools
- **Loop detection reset** — successful tool responses now reset the error tracker, so only truly consecutive identical errors trigger abort

### Changed

- **Pricing cache** — pricing data loaded once per process instead of re-parsing YAML on every cost estimation call

## [0.7.0] — 2026-04-08

### Breaking Changes

- **`paths` field is now a dict of named aliases** — the list format (`paths: [/a, /b]`) is no longer accepted. Migrate to named aliases:
  ```yaml
  paths:
    vault: /Users/x/vault
    inbox: /Users/x/inbox
  ```
  `agentmd validate` detects the old format and prints a migration hint. See [Path Model](docs/path-model.md).

### Added

- **Named path aliases** — declare `paths` as a dict with aliases like `vault`, `inbox`, `output`. Use `{alias}` syntax in prompts and file tools: `file_read("{vault}/daily/x.md")`.
- **`$ARGUMENTS` and `!`cmd`` in agent prompts** — pass arguments via `agentmd run my-agent -- arg1 arg2`, reference them as `$ARGUMENTS`, `$0`, `$1` in the system prompt. Shell commands via `` !`date +%Y-%m-%d` `` are also supported.
- **`file_glob` accepts absolute and alias patterns** — `file_glob("{vault}/**/*.md")` and `file_glob("/abs/path/*.md")` now work. Previously only relative patterns were accepted.
- **`file_read` truncation hint** — when a partial read is returned, the output now includes a NOTE with the exact `offset` and `limit` to continue reading.
- **`agent_md.sandbox.validate_path`** — public helper for custom tool authors to opt-in to the same path sandbox as built-in tools.

### Fixed

- **`history: off` YAML parsing** — YAML 1.1 parses `off` as `False`. The validator now accepts `False` and normalizes to `"off"`. `True` raises a helpful error explaining the YAML gotcha.
- **`file_glob` error messages** — now include the pattern that failed and list available aliases as hints.

### Changed

- **System prompt: "Available paths" block** — lists alias names (not absolute paths) so the LLM knows the `{alias}` syntax without leaking filesystem layout.
- **`apply_substitutions` extracted** to `agent_md.core.substitutions` — shared between skills and agent prompts. The skills loader is now a backward-compatible shim.

## [0.6.3] - 2026-04-01

### Added
- **Meta messages** — system-injected `HumanMessage`s with XML tags (`<skill-context>`, `<skill-breadcrumb>`) and `additional_kwargs` metadata for semantic message handling
- **`post_tool_processor` graph node** — sits between tools and agent nodes; detects `skill_use` activation and injects skill instructions as meta messages (`HumanMessage` directives) instead of `ToolMessage` data
- **Smart history compaction** — `_trim_messages` compacts `skill-context` to breadcrumb and truncates large tool results (>500 chars) before applying count-based trimming

### Changed
- **`skill_use` tool** — now returns a short activation confirmation; full skill content is injected by `post_tool_processor` as a meta message
- **System prompt** — new "Meta Messages" section teaches agents to interpret `<skill-context>` and `<skill-breadcrumb>` tags (only for skill-enabled agents)
- **ReAct graph** — expanded from 2 nodes (agent, tools) to 3 nodes (agent, tools, post_tool_processor) when skills are configured

### Fixed
- **Session history** — only the latest `SystemMessage` is sent to the LLM; stale system prompts from previous runs are discarded
- **Trimming timing** — history trimming and compaction now run only once at the start of each run, not on every LLM call within the same execution

### Internal
- **`resolve_skill_content()`** — extracted from `skill_use` into `agent_md/tools/skills/_resolver.py` as an internal function (not a tool)

## [0.6.2] - 2026-03-31

### Added
- **`file_edit` tool** — targeted in-place text replacement with `old_text`/`new_text`, single or bulk replace, and new file creation mode
- **`file_glob` tool** — find files by glob pattern from workspace root, filtered by allowed paths, capped at 100 results

### Improved
- **`file_read`** — optional range reads with `offset`/`limit` parameters, line number prefixes, binary file detection (null byte check), and 500-line cap for full reads
- **`file_write`** — binary content detection, richer return messages with `Created/Updated` status, char and line counts
- **System prompt** — documents all four file tools with usage guidance, instructs agents to read before editing/overwriting

### Changed
- **Tools reorganization** — flat `agent_md/tools/` restructured into domain subpackages (`files/`, `memory/`, `skills/`, `http/`) for maintainability
- **Unified path resolution** — removed `output_dir` concept; all file tools resolve relative paths from workspace root
- **`file_list` removed** — replaced by `file_glob` which supports recursive patterns and is more useful for file discovery
- **Config location** — moved to `~/.config/agentmd/config.yaml` (XDG standard); auto-creates with defaults on first run
- **Simplified autostart** — systemd/launchd services no longer require workspace path or environment variables

### Removed
- **`output_dir`** — removed from settings, CLI setup, bootstrap, and documentation; agents write to workspace root or configured `paths`
- **`AGENTMD_WORKSPACE`** — environment variable removed; config is always at `~/.config/agentmd/config.yaml`

## [0.6.1] - 2026-03-16

### Fixed
- **Installer** — fix stdin redirect and update command for git-based installs
- **Agent generation (`agentmd new`)** — handle LLM providers (e.g. Gemini) that return `content` as a list of blocks instead of a plain string, which caused `'list' object has no attribute 'strip'`
- **File watcher** — `.memory.md` files were being treated as agent definitions during hot-reload, causing parse errors; centralized `is_agent_file()` helper now filters non-agent `.md` files consistently across bootstrap, watcher, and deletion handlers

### Improved
- **Agent generation prompt (`agentmd new`)** — richer prompt now documents all built-in tools (including memory and skills), the `history` field, trigger types with examples, and explicit guidance to prefer memory tools over file_write for persistent state
- **System prompt for agents** — clearer file access instructions with explicit path rules (prefer absolute paths), structured watch trigger context with exact `file_read` call, and `file_list` guidance; renamed internal `write_dir` nomenclature to `output` for consistency with unified `paths` field

## [0.6.0] - 2026-03-16

### Added
- **Skills system** — reusable instruction packages for agents, compatible with the [Agent Skills](https://agentskills.io) standard
  - Skills are directories with a `SKILL.md` file (YAML frontmatter + markdown instructions)
  - Two-tier loading: descriptions in system prompt, full content loaded on-demand via tools
  - Three new built-in tools: `skill_use`, `skill_read_file`, `skill_run_script`
  - Variable substitution: `$ARGUMENTS`, `${SKILL_DIR}`, `!`command`` (dynamic context injection)
  - Compatible with Claude Code skill format — copy a skill from `.claude/skills/` and use it directly
  - Path traversal protection on file reads and script execution
  - `skills` frontmatter field on agents: list of skill names to enable
  - Skills directory: `workspace/agents/skills/<name>/SKILL.md`

### Fixed
- **Chat history trimming** — `_trim_messages` could leave an AIMessage (with tool_calls) as the first non-system message after trimming, causing Gemini to reject with INVALID_ARGUMENT; now walks backward to always start on a HumanMessage boundary

### Changed
- **CLI refactor** — consolidated presentation logic into `theme.py`, extracted lifecycle hooks (`on_start`/`on_complete`) from runner into CLI layer, simplified `commands.py`

## [0.5.1] - 2026-03-16

### Improved
- **CLI output layout** — sanitize event content (no broken line wraps), hierarchical indentation for events, compact run header/footer
- **Chat responses** — render agent responses as formatted Markdown (bold, lists, code blocks)
- **Chat callback** — separate callback that shows intermediate steps but renders final answer via Markdown

### Fixed
- **Chat history trimming** — memory_limit could cut in the middle of a tool-call sequence, leaving orphaned ToolMessages that broke Gemini's strict message ordering

## [0.5.0] - 2026-03-13

### Added
- **Session history** — LangGraph checkpointing with SQLite persists conversation history between runs
  - `history` frontmatter field: `low` (default, 10 msgs), `medium` (50), `high` (200), `off` (stateless)
  - Works for both `agentmd run` and `agentmd chat` — agents accumulate context over time
  - Thread ID = agent name — all executions of the same agent share the same conversation thread
- **Long-term memory tools** — three new built-in tools for persistent, structured knowledge
  - `memory_save(section, content)` — store/replace a named section
  - `memory_append(section, content)` — append to a section (with digest hint at 50+ lines)
  - `memory_retrieve(section)` — read a section
  - Memory stored in `agents/{name}.memory.md` files
  - Available sections listed in system prompt automatically
- **`agentmd validate`** — now shows history level in output

## [0.4.0] - 2026-03-13

### Added
- **`agentmd chat [agent]`** — interactive multi-turn chat sessions with agents, supporting streaming output, tool use, and conversation memory within a session
  - One execution record per session (trigger type `"chat"`)
  - Token usage accumulated across all turns
  - Graceful exit via `/exit`, Ctrl+C, or Ctrl+D with session summary

## [0.3.0] - 2026-03-13

### Added
- **`agentmd new <name>`** — scaffold new agents via AI generation or interactive questionnaire (`--template`)
- **Daemon mode** — `agentmd start -d` runs the runtime as a background process
- **New commands** — `agentmd status` and `agentmd stop` for daemon management
- **Follow logs** — `agentmd logs -f` tails the daemon log in real-time
- **Interactive agent picker** — `agentmd run` and `agentmd validate` without arguments open an interactive selector (via `questionary`)
- **Centralized theme** — new `theme.py` with shared console, helpers, and event display mapping

### Changed
- **Global `--quiet`/`--verbose`** — logging options moved to app callback, available for all commands
- **Simplified CLI options** — removed per-command `--agents-dir`, `--output-dir`, `--db-path`, `--mcp-config` (resolved automatically from `config.yaml`)
- **`agentmd validate`** now accepts an agent name instead of a file path
- **`agentmd list`** shows compact table with trigger, last run time, and status dot
- **`agentmd config`** output streamlined (removed internal paths, log level)
- Extracted `_runtime()` async context manager in services.py (replaces manual bootstrap/aclose)
- Extracted `_finish_execution()` in runner.py (eliminates 3x duplicated result dict + db update)
- Removed duplicate methods in path_context.py (`_resolve_for_read`, `_is_write_allowed`)
- Extracted `_resolve_relative()` helper in services.py for path resolution
- Declarative defaults flatten in settings.py

### Fixed
- Leaked file handle in daemon.py `start_daemon`

## [0.2.3] - 2026-03-12

### Added
- Separate `config.yaml` from `.env` — application settings vs secrets
- Default model support in `config.yaml` (`defaults.provider`, `defaults.model`)
- One-line installers for Linux/macOS (bash) and Windows (PowerShell)
- `agentmd setup` interactive wizard
- `agentmd update` self-update command
- `agentmd config` to display effective configuration

### Fixed
- PATH refresh after `uv tool install` in PowerShell installer
- Duplicated directory prefix in write path resolution (e.g., `output/output/`)

## [0.2.2] - 2026-03-12

### Added
- `${VAR}` environment variable substitution in agent prompts
- Agents can reference `.env` values directly in their system prompt

### Fixed
- Correct GitHub URLs from `zfab` to `z-fab`

## [0.2.0] - 2026-03-11

### Added
- **Workspace structure** — `agents/`, `output/`, `data/` directories with `PathContext` for security
- **Multi-provider support** — OpenAI, Anthropic, Ollama, and local providers alongside Google
- **MCP integration** — connect agents to Model Context Protocol servers
- **Custom tools** — load Python tools from `agents/tools/`
- **Trigger system** — `schedule` (cron/interval), `watch` (file changes), and `manual` triggers
- **Built-in tools always available** — `file_read`, `file_write`, `http_request`
- **Rich CLI output** — verbosity levels, colored event stream
- **Execution tracking** — SQLite database with per-execution logs and token usage

### Fixed
- Accept `url` alias and auto-append `/v1` for local provider base URLs

## [0.1.0] - 2026-03-10

### Added
- Initial release
- Markdown-first agent definition (YAML frontmatter + prompt body)
- Google Gemini provider support
- LangGraph-based ReAct agent execution
- Basic CLI with `agentmd start`, `agentmd run`, `agentmd list`
- SQLite execution history

[0.5.0]: https://github.com/z-fab/agentmd/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/z-fab/agentmd/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/z-fab/agentmd/compare/v0.2.3...v0.3.0
[0.2.3]: https://github.com/z-fab/agentmd/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/z-fab/agentmd/compare/v0.2.0...v0.2.2
[0.2.0]: https://github.com/z-fab/agentmd/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/z-fab/agentmd/releases/tag/v0.1.0
