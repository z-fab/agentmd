# Changelog

All notable changes to Agent.md are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

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

[0.3.0]: https://github.com/z-fab/agentmd/compare/v0.2.3...v0.3.0
[0.2.3]: https://github.com/z-fab/agentmd/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/z-fab/agentmd/compare/v0.2.0...v0.2.2
[0.2.0]: https://github.com/z-fab/agentmd/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/z-fab/agentmd/releases/tag/v0.1.0
