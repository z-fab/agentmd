# Changelog

All notable changes to Agent.md are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

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
