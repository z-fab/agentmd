# Changelog

All notable changes to Agentmd are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Security

- **`--port` no longer binds an unauthenticated TCP listener** — the API key middleware was installed only when `--port` *and* `--api-key` were both given, while the TCP server came up either way. `agentmd start --port 8000` therefore exposed every endpoint with no authentication, including `POST /agents/{id}/run`, which executes an arbitrary agent; `--host` defaults to `127.0.0.1` but is freely overridable to `0.0.0.0`. `--port` now requires `--api-key` and refuses to start without it. Authentication is applied per transport: the TCP entrypoint is wrapped, the Unix socket (already `chmod 600`) is not — so the local CLI, which sends no key, keeps working while the port is guarded. Keys are compared in constant time.

### Added

- **Enriched scalar `trigger:`** — optional `input` (user-turn template with `{context}` / `{event}` / `{path}` placeholders), `filters.include` / `filters.exclude` globs for watch, and `debounce` (default still 0.5s). Agents that omit the fields behave as before. Watch filters run in the filesystem handler, not the admission gate. A declared `input` replaces the hardcoded prompt; for `manual` / `chat` / `agent`, a run `context` still appends as ` ({context})` unless the template already uses `{context}`.
- **Unknown frontmatter keys are reported** — a typo like `triger:` was ignored in silence and the agent ran as `manual` with no indication anything was wrong. Unknown keys are now logged when the file is parsed and listed by `agentmd validate`, with a did-you-mean for the field they resemble; nested keys are reported by path (`trigger.typ`). Still a warning, never an error, so a file written for a newer agentmd keeps loading on an older one.
- **Conversations have an id** — `POST /agents/{id}/run` accepts `session_id`, persisted in the new `executions.session_id` column and exposed on execution responses. A run carrying one is recorded with `trigger: "chat"` instead of `"manual"`. Existing databases gain the column on open; nothing else changes for clients that do not send it.
- **`context` in the run body is no longer discarded** — it was accepted and dropped; it now reaches the runner as `trigger_context` and is appended to the user turn of manual and chat runs.
- **SSE `meta` execution_info** ([#3](https://github.com/z-fab/agentmd/issues/3)) — every run opens its stream with a persisted `meta` frame whose payload `event_type` is `execution_info`, carrying `agent_id`, `display_name`, `model`, `trigger`, `args`, and `session_id`. Reconnect/replay reproduces it.
- **SSE `meta` stats** ([#1](https://github.com/z-fab/agentmd/issues/1)) — after each AI message the stream emits a persisted `meta` frame with `event_type: "stats"` and accumulated `input_tokens` / `output_tokens` / `total_tokens` / `cost_usd`, so a streaming UI can show cost growing without waiting for `complete`.

### Fixed

- **`pause` actually pauses watchers** — `POST /scheduler/pause` stopped APScheduler and set a flag that only the status endpoints read, so an agent with `trigger: watch` kept running on every file event while `GET /scheduler` reported `paused`. Pause now covers both trigger types, and `resume` restores both. Manual runs are deliberately unaffected: pausing the scheduler does not disable the run button.
- **A watch-only workspace no longer dies of idleness** — the idle-shutdown counted APScheduler jobs only. Watch agents have no job, so a workspace whose agents all use `trigger: watch` looked idle and the backend shut down after five minutes, taking the watchers with it in silence. Liveness now counts every active trigger source.
- **One concurrency rule instead of two copies** — `on_pending: skip` was implemented twice, in the scheduler and in the run endpoint, free to drift apart. Both now consume the same decision. The responses still differ by design — a dropped trigger is logged, a refused `POST /agents/{id}/run` answers 409 — but the 409 detail is now the reason the gate gave.
- **History seeding is scoped to a conversation** — a new run seeded from "the last finished execution of this agent", whatever its origin. An agent with `trigger: schedule` and an open chat mixed the two: the scheduled run inherited the chat's context and the next chat turn inherited the scheduled run's. Two simultaneous chats on one agent shared the same line. Seeding now follows `session_id` — same session for chat turns, sessionless executions otherwise — and `schedule`/`watch` runs never join a chat session. Checkpoint retention keeps the newest execution per *session* (not just per agent), so an active conversation cannot lose its memory to the 30-day sweep.
- **`final_answer` is no longer truncated** ([#2](https://github.com/z-fab/agentmd/issues/2)) — the log row kept only the first 500 characters while the live SSE event carried the whole answer, and `output_data` was cut at 10,000. Because the stream deduplicates catchup against live by event id, whichever version reached the client first won: replaying the short row made the complete live frame get dropped under the same id, so `run --detach` + `logs`, any stream reconnect, and every HILT cycle (the CLI reopens the stream after answering) could show a permanently clipped answer. The answer is now stored whole and the replayed frame carries it under `content`, the same key and the same bytes as the live one. An upper bound of 1,000,000 characters remains as a backstop, well above any model's output limit.
- **A waiting execution keeps a server backend alive** — an execution parked in `waiting` (human-in-the-loop) has no live task, so the idle timeout ignored it and the backend could shut down under a remote caller that had no way to restart it. In service mode (`--port` or `--keep-alive`) a waiting execution now holds the backend open. On the plain local socket it deliberately does not: `agentmd respond` rebuilds and resumes from the checkpoint on demand, and a forgotten HILT must not turn the backend immortal.
- **`start -d` no longer drops its server flags** — `agentmd start -d --keep-alive --port 4100 --api-key K` reported "Backend started" and then spawned a socket-only backend, because the daemon path passed only `--workspace` to the detached child. The flags are now carried through, and the daemon prints the address it is listening on. Autospawn is unchanged — it still asks for the socket alone.

### Documentation

- **Server mode is documented** — `--keep-alive`, `--port`, `--host` and `--api-key` were absent from the CLI reference. It now has a Server Mode section (when to keep the backend alive, why `--port` requires `--api-key`, what `--host 0.0.0.0` costs, how `waiting` behaves per mode), the API reference has an Authentication section, and the daemon log/PID paths were corrected to the XDG state directory the code actually uses.

## [0.16.0] — 2026-08-08

### Changed

- **Breaking — filename stem is the canonical agent id** — identity comes from `agents/<id>.md` (e.g. `pesquisador.md` → id `pesquisador`), not from frontmatter `name:`. `name:` is an optional display label (defaults to the id). Declaring `id:` in frontmatter is rejected. Memory files are `{id}.memory.md`. API routes, CLI commands, scheduler jobs, `executions.agent_id`, allowlists `agents:`, and `run_agent` all resolve by id. Public API exposes `id` + `display_name`. In SSE events, `agent_name` now mirrors the **id** (breaking for clients that treated it as a label); use `display_name` for the human title. Renaming the file changes identity; a later `mv` does **not** carry execution history or memory automatically. See [Migration v0.16](docs/migration-0.16.md).
- **No automatic migration** — 0.16 does not rewrite existing data. History and memory keyed by an old display name stay where they are and are simply not found under the new id. [Migration v0.16](docs/migration-0.16.md) documents the manual procedure: stop the backend, then either delete the database or re-key it by hand, and rename `{display}.memory.md` → `{id}.memory.md`. Workspaces where `name:` already matches the filename need no action.

### Fixed

- **Generated preamble no longer outranks the agent's own prompt** — the system prompt now opens with an `# Environment` block framed as reference material ("listing a tool is not a request to use it") and closes with the agent's prompt under `# Your task`. Previously an agent whose entire prompt was `Responda: ok.` received ~1150 characters of imperative tool documentation ahead of it and answered by demonstrating `file_write`, `file_read`, `file_edit`, `file_move` and `file_delete`. Tool sections are now descriptive rather than imperative, and the file-tool list matches what is actually attached — it advertised "four file tools" while six were available, leaving `file_move` and `file_delete` undocumented but usable.
- **Hot reload survives atomic saves** — editors and tools that save by writing a temp file and renaming it over the original (`perl -i`, `sed -i`, vim, most editors) emit a delete event for a path that still exists. The watcher trusted it and unregistered the agent, so the backend returned 404 for an agent still listed by `agentmd list`, which reads the workspace directly. Deletion is now ignored when the file is still on disk.
- **`get_next_run()` never returned a next run** — it looked the job up by bare name while jobs are registered as `agent_{id}`, so `GET /agents/{id}` always reported `next_run: null`. `get_jobs()` also leaked the `agent_` prefix as the agent name.

### Upgrading

`name:` is no longer the agent's identity, so an agent whose `name:` differed from its filename loses track of its history and memory. **Stop the backend before upgrading** — one started on 0.15.x keeps the old registry in memory and 404s on every `agentmd run <id>`. Full procedure in [Migration v0.16](docs/migration-0.16.md); workspaces where `name:` already matches the filename need no action.

## [0.15.3] — 2026-08-07

### Fixed
- **HILT pause no longer wipes execution metrics** — `update_execution` only writes fields that were passed, and sets `finished_at` only for terminal statuses. Resume reloads prior tokens/cost/tool-call counts so limits cannot be bypassed by pause/resume.
- **Fresh-install readonly DB** — `agentmd list` / `logs` no longer crash when the SQLite file does not exist yet; schema is created on first readonly open.
- **Schema migration for `pid` / `cost_usd`** — older databases gain missing columns via a generalized column migration loop.
- **Checkpoint DB path** — derived with `Path.stem + "_checkpoints.db"` so non-`.db` paths never collide with the main database.
- **Execution log ordering** — logs are ordered by insertion `id` (not 1s-resolution timestamps); default fetch limit raised for `logs -e`.
- **Command injection via memory/skills in the system prompt** — `!`cmd`` substitutions apply only to the agent file's system prompt, never to generated memory headers or skill descriptions.
- **`!`cmd`` no longer blocks the event loop** — shell substitutions run via `asyncio.to_thread`.
- **`agentmd start` refuses to steal a live socket** — health-checks before unlinking; aborts if a backend is already running.
- **Sub-agent cancel + limits** — `run_agent` propagates `cancel_event` and folds child tokens/cost into the parent's accumulators.
- **CLI exit codes** — `agentmd validate` exits 1 on errors; `agentmd run` exits 1 on failed terminal status.
- **Invalid `mcp-servers.json` no longer prevents startup** — logged and treated as empty.
- **`agentmd validate` resolves tools/MCP under `agents/_config/`** (same as bootstrap).
- **`POST /agents/reload`** — skips memory files, reschedules, removes deleted agents, reports errors. Agents whose `.md` fails to parse are also removed from the registry until a later successful reload (mid-edit saves can temporarily disappear).
- **Custom provider `base_url` honored** for OpenAI, Ollama, Anthropic, and Local. Native Ollama and Anthropic endpoints retain their URL rather than receiving an OpenAI `/v1` suffix.
- **MCP connect race** — per-server lock; stdio logger level always restored.
- **Duplicate agent `name:`** — warning on load/register (filename-as-id lands in 0.16).
- **Removed dead `chat_session()`** (always marked success on exception).
- **`agentmd checkpoint` uses config `db_path`** (no phantom state-dir DB).
- **Background `create_task` refs retained** so tasks are not GC'd mid-flight.
- **`skill_run_script` uses `sys.executable`**; bootstrap creates `tools_dir` + mcp config parent; `logs --follow` respects agent filter + utf-8; `agentmd new` validates AI output before write; unknown `config.yaml` keys warn; SQLite `synchronous=NORMAL`; custom tools cached by `(path, mtime)`; shutdown uses `get_running_loop()`; backend log fd closed in parent + size-based rotation.

## [0.15.2] — 2026-06-05

### Fixed
- **Transient transport drops no longer kill a run** — model calls now retry on transport-level errors (e.g. `RemoteProtocolError: Server disconnected without sending a response`, a flaky preview endpoint dropping the connection) up to 3 times with exponential backoff, instead of failing the whole execution. This was most visible during HILT: a dropped connection on resume would error the execution and the conversation only "continued" via history-seeding on a manual re-run. Genuine API errors (bad request, auth) are not retried. Applies to both `run` and `resume`.
- **Resume errors now log a traceback** — `AgentRunner.resume()` logs the full exception (parity with `run()`), making backend-side failures diagnosable in `backend.log`.

## [0.15.1] — 2026-06-05

### Added
- **`agentmd run --detach` / `-d`** — fire-and-forget background runs. The CLI dispatches the execution, prints its id, and returns immediately. If the agent needs input (HILT), it enters `waiting` instead of prompting inline and appears in `agentmd pending` (consistent with `agentmd start -d`).

### Changed
- **`agentmd run --quiet` / `-q` now prints only the final answer** — intermediate steps, the "execution started" line, and the summary line are suppressed, and the answer is printed undecorated (pipe-friendly). Previously `-q` suppressed the final answer too.

### Fixed
- **Standardized CLI tables** — `agentmd pending` now uses the same table style as `agentmd list`/`agentmd logs` and shows the agent icon next to its name.
- **Agent icon alignment** — single-codepoint symbol emoji (e.g. `☀`, `⚙`) are normalized to their emoji presentation (`U+FE0F` appended) so they render two cells wide and table columns no longer drift out of alignment in `list`, `pending`, and `logs`.

## [0.15.0] — 2026-06-05

### Added
- **Human-in-the-loop (HILT):** agents can pause to ask the user for confirmation, free-text input, or a choice, then resume.
  - Built-in tools `file_delete` and `file_write` ask for confirmation by default (configurable via `defaults.confirm_tools`).
  - New agent config: `confirm` (guard extra tools), `auto_approve` (skip confirmation; `"*"` disables all), `on_pending` (`skip`/`parallel`), `confirm_timeout` (auto-deny after a delay; default none).
  - New built-in tool `ask_user` and SDK primitives `request_confirmation` / `request_input` / `request_choice` for custom tools.
  - Survives backend restart: paused executions resume when answered.
  - API: `interrupt` SSE event, `POST /executions/{id}/respond`, `GET /executions/{id}/pending`.
  - CLI: inline prompt during both `agentmd run` and `agentmd chat`, plus `agentmd pending` and `agentmd respond` (`--yes/--no/--reason/--text/--choice`).
- **Checkpoint cleanup** (issue #12): startup retention sweep (`defaults.checkpoint_retention_days`, default 30) and `agentmd checkpoint --stats/--purge/--agent/--force`.
- `agentmd new`'s AI generation prompt now teaches the model about icons, skills, MCP, custom tools, and HILT, so generated agents can use the current feature set.

### Changed
- The LangGraph checkpointer is now always on (durability substrate for HILT). `history` only controls how much prior context is seeded into a new run; each execution uses its own checkpoint thread.
- Standardized the project name to **Agentmd** across the documentation, site, and API title (the CLI/package `agentmd` and module `agent_md` are unchanged).

## [0.14.0] — 2026-06-03

### Added
- **Agent `icon` field** — agents may declare an optional `icon:` (emoji/short string) in frontmatter, shown in the Obsidian plugin and the CLI.
- **Automatic icon resolution** — when an agent has no explicit `icon`, agentmd derives a stable emoji from its name (same name → same emoji). The resolved icon is returned by `GET /agents` and `GET /agents/{name}`, and is shown consistently in both the CLI (`agentmd list`, `agentmd logs`) and the Obsidian plugin.

### Changed
- **Agent names may contain spaces and accented characters** — the `name` field now allows letters (including accents), digits, spaces, hyphens, and underscores (no leading/trailing spaces, no slashes). The agent is identified by its `name` (not its filename); quote names with spaces when running, e.g. `agentmd run "Daily Processor"`.

## [0.13.1] — 2026-06-03

### Added
- **`agentmd info` shows database paths** — the configuration panel now displays the resolved execution DB (`Database`) and checkpoints DB (`Checkpoints DB`) paths, alongside the existing config/env/workspace entries. The DB location can be customized via `db_path` in `config.yaml` (absolute, or relative to the workspace); the checkpoints DB always sits beside it.

### Fixed
- **`_config` directory now follows `agents_dir`** — `tools_dir`, `skills_dir`, and `mcp_config` are now derived from the configured `agents_dir` (`{agents_dir}/_config/...`) by default, instead of a hardcoded `agents/_config/...`. With a custom `agents_dir` (e.g. `99. Agents`), agentmd no longer spawns a stray top-level `agents/` folder in the workspace; skills/tools/MCP config live inside the agents directory. Each path can still be overridden explicitly in `config.yaml`. The workspace `.env` lookup follows `agents_dir` too.

## [0.13.0] — 2026-06-03

### Fixed
- **Path sandbox rejected dotted directory names** — agents could not write into declared `paths` whose folder name contained a dot (e.g. Obsidian vaults like `90. Arquivos`); the sandbox misclassified the directory as a file. Writes into such directories now work.

### Added
- **`file_delete` tool** — new built-in tool to delete a single file within the agent's allowed paths. Files only (no directories), graceful "not found" for missing files. Enabled by default. (#7)
- **Full agent config in `GET /agents/{name}`** — the detail endpoint now exposes `paths`, `custom_tools`, `mcp`, `skills`, `trigger_every`, `trigger_cron`, `trigger_paths`, and `source_path`. (#4)

### Changed
- **Standardized tool-result event name** — the runtime now emits and persists `tool_result` consistently (previously `tool_response` in the DB/logger), matching the SSE stream. Delete the execution DB to drop stale `tool_response` rows. (#14)

## [0.12.3] — 2026-04-23

### Fixed
- **Graph recursion limit** — LangGraph's default `recursion_limit` of 25 was too low for agents with `max_tool_calls=50`, causing `GraphRecursionError` on complex executions. Now derived automatically from `max_tool_calls` setting.

## [0.12.2] — 2026-04-14

### Fixed
- **Full system prompt in execution logs** — system and human messages are no longer truncated to 500 chars in the database, storing the complete constructed prompt for debugging
- **`logs -e -v` shows system prompt** — new `--verbose` / `-v` flag on `agentmd logs` expands the full system prompt in execution detail view instead of showing only the char count

## [0.12.1] — 2026-04-14

### Fixed
- **System prompt now logged** — the fully constructed system prompt (with all substitutions, paths, agents) and user input are persisted to the execution log before streaming
- **Arguments passed as list** — API and CLI now pass arguments as `list[str]` through the entire execution chain instead of joining into a string at the boundary. `$ARGUMENTS` joins with newline, `$ARGUMENTS[N]` and `$0..$9` access by index — preserving spaces within each argument value

## [0.12.0] — 2026-04-14

### Added
- **`run_agent` built-in tool** — agents can now call other agents via a declared `agents` allowlist in frontmatter, enabling orchestration and ad-hoc delegation patterns
  - Called agent runs as an independent execution with its own sandbox, limits, and token tracking
  - Executions linked via `parent_execution_id` for traceability, trigger type `agent`
  - Depth control prevents runaway chains (default: 3, configurable via `defaults.max_agent_depth` in config.yaml)
  - Available agents and descriptions injected into system prompt automatically
  - Arguments forwarded to child agent via `$ARGUMENTS` substitution
- **`agents` frontmatter field** — allowlist of agent names this agent can call
- **`parent_execution_id`** — new field in execution records linking child to parent execution

### Fixed
- **Agent deletion by filename** — file watcher now uses a path-to-name registry mapping instead of `Path.stem`, fixing deletion when agent `name` differs from filename

## [0.11.0] — 2026-04-13

### Added
- **Global SSE event stream** — single persistent `GET /events/stream` endpoint that broadcasts all backend state changes as Server-Sent Events, replacing polling-based sync for clients (#5)
  - `heartbeat` — sent every 10s of inactivity, doubles as health signal
  - `execution_started` / `execution_completed` — real-time execution lifecycle events
  - `agents_changed` — agent file loaded, updated, or removed by file watcher
  - `scheduler_changed` — scheduler paused or resumed
  - No replay on reconnect — clients use existing REST endpoints to sync state
  - SSE connection keeps backend alive (counts as active stream for idle timeout)
- **`GlobalEventBus`** — lightweight in-memory pub/sub for system-wide events, separate from the per-execution `EventBus`

### Fixed
- **Double bootstrap on `--port`** — when running with `--port` (socket + TCP), the lifespan was triggered twice causing a watchdog `RuntimeError: Cannot add watch`. Now guarded to bootstrap only once.

## [0.10.0] — 2026-04-13

### Added
- **`file_move` built-in tool** — move/rename files with full sandbox validation on both source and destination paths (#6)
- **`agent_md.sdk` module** — public SDK for custom tool authors with `resolve_path()`, `workspace_root()`, `agent_name()`, and `agent_paths()` functions, powered by `contextvars` for async-safe per-execution context

### Removed
- **`agent_md.sandbox`** — replaced by `agent_md.sdk` with a simpler API (no factory injection required)

## [0.9.1] — 2026-04-12

### Fixed
- **Cancellation of scheduled/watched executions** — scheduled and file-watch triggered executions now register cancel events, making `DELETE /executions/{id}` work for all execution types
- **Cancel endpoint tolerant** — `DELETE /executions/{id}` returns 200 for already-finished executions instead of 409
- **Watcher decoupled from scheduler** — `_AgentWatchHandler` receives an execute function instead of a scheduler reference, removing unnecessary coupling
- **`pricing.yaml` missing from package** — added to `setuptools.package-data` so it's included in pip/uv installations

### Changed
- **Pricing registry updated** — added Google Gemini 3 family (pro, flash, flash-preview), OpenAI GPT-5 family (5.4, 5.2, 5.1, 5, mini, nano) and o1, Anthropic Claude Opus 4/4.1/4.5, Sonnet 4/4.5, Haiku 3.5

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
