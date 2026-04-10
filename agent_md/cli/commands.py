"""CLI command definitions — presentation layer only."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from agent_md.cli import app
from agent_md.cli.theme import (
    EVENT_DISPLAY,
    agent_status_dot,
    console,
    format_duration,
    format_relative_time,
    format_tokens,
    format_trigger,
    make_panel,
    make_table,
    print_agent_complete,
    print_agent_event,
    print_agent_start,
    print_banner,
    print_chat_header,
    print_check,
    print_chat_summary,
    print_error,
    print_kv,
    print_markdown,
    print_success,
    print_warning,
    select_agent,
)
from agent_md.core.models import AgentConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_workspace(workspace: Path | None) -> Path:
    """Resolve workspace path from CLI arg or settings."""
    from agent_md.core.settings import settings

    if workspace:
        return workspace.resolve()
    ws = settings.workspace
    if ws:
        return Path(ws).expanduser().resolve()
    return Path("./workspace").resolve()


def _get_agents_for_picker(workspace: Path | None) -> list[AgentConfig]:
    """Bootstrap lightly to get agent list for interactive picker."""
    from agent_md.core.services import list_agents as svc_list

    return asyncio.run(svc_list(workspace))


def _pick_or_resolve_agent(agent: str | None, workspace: Path | None) -> str:
    """Resolve agent name: if None, use interactive picker."""
    if agent is not None:
        return agent

    agents = _get_agents_for_picker(workspace)
    if not agents:
        print_error("No agents found in workspace.", "Create an agent in agents/ directory.")
        raise typer.Exit(1)

    selected = select_agent(agents)
    if selected is None:
        print_error("No agent selected.")
        raise typer.Exit(1)
    return selected.name


# ---------------------------------------------------------------------------
# agentmd new
# ---------------------------------------------------------------------------


def _validate_agent_name(name: str) -> str | None:
    """Return error string if name is invalid, else None."""
    import re

    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        return "Agent name must contain only alphanumeric characters, hyphens, and underscores."
    return None


def _can_use_ai() -> tuple[bool, str, str]:
    """Check if AI generation is available. Returns (available, provider, model)."""
    import os

    from agent_md.core.services import _PROVIDER_ENV_VARS
    from agent_md.core.settings import settings

    provider = settings.defaults_provider
    model = settings.defaults_model

    if not provider:
        return False, "", ""

    if provider in ("ollama", "local"):
        return True, provider, model

    env_var = _PROVIDER_ENV_VARS.get(provider)
    if env_var and os.environ.get(env_var):
        return True, provider, model

    return False, provider, model


def _generate_agent_with_ai(agent_name: str, description: str, provider: str, model: str) -> str:
    """Use the configured LLM to generate the agent .md content."""
    from agent_md.providers.factory import create_chat_model

    llm = create_chat_model(provider, model, {"temperature": 0.7, "max_tokens": 4096})

    prompt = f"""You are an expert at creating AI agent definitions for the Agent.md framework.

Generate the content of a markdown agent file for an agent named "{agent_name}" based on this description:
{description}

## File format

YAML frontmatter (between --- delimiters) followed by the system prompt in Markdown.

## Frontmatter fields

Required:
- name: {agent_name}

Optional:
- description: one-line summary of what the agent does
- model: object with provider and name fields. Only include if the user specified a model.
- trigger: execution trigger (see Trigger types below)
- settings: object with temperature (float), max_tokens (int), timeout (int, seconds)
- history: conversation memory across runs — "low" (10 msgs), "medium" (50), "high" (200), "off" (default)
- paths: dict of named aliases for directories the agent can access. Each key is an alias name (lowercase, e.g. "vault", "output"), each value is a path string. Use `{{alias}}` syntax in prompts and tool calls.

### Trigger types
- manual (default): agent runs only when invoked via `agentmd run`
- schedule: runs on a schedule. Fields: `every` (e.g. "30m", "2h", "24h") or `cron` (e.g. "0 9 * * *")
- watch: runs when files change. Fields: `paths` (list of glob patterns to watch)

## Built-in tools

These tools are always available to the agent. Do NOT list them in frontmatter.
Choose the right tool for each use case — especially prefer memory tools over file_write for persistent knowledge.

### Filesystem
- file_read(path): Read a file. Only works within `paths`.
- file_write(path, content): Write/create a file. Only works within `paths`. Creates parent dirs automatically.
- file_glob(pattern): Find files matching a glob pattern (e.g. '**/*.py'). Only works within `paths`.

### HTTP
- http_request(url, method="GET", headers=None, body=None): Make HTTP requests. Returns status code and response body.

### Long-term memory (persistent across runs)
Use these when the agent needs to remember information between executions (e.g. tracking state, accumulating knowledge, storing preferences). Memory is stored in a dedicated `.memory.md` file per agent — do NOT use file_write for this purpose.
- memory_save(section, content): Save/replace a named section in memory.
- memory_append(section, content): Append to a named section (creates it if missing).
- memory_retrieve(section): Read a named section from memory.

## Rules

- Write ONLY the file content. No explanations, no code fences.
- Start with --- and end after the system prompt.
- The system prompt must be clear, specific, and actionable — tell the agent exactly what to do, step by step.
- If the agent needs to persist state or knowledge across runs, use memory tools (memory_save/memory_append/memory_retrieve), NOT file_write.
- If the agent needs to remember previous conversations, set the `history` field.
- Match the trigger type to the use case: use `watch` for file-change reactions, `schedule` for periodic tasks, `manual` for on-demand.
- Only include frontmatter fields that are relevant. Omit fields that use defaults.

## Example

---
name: daily-summary
description: Summarizes daily activity logs
trigger:
  type: schedule
  every: 24h
history: medium
paths:
  logs: logs/
  output: output/
---

You are a summarization agent. Every day:

1. Use `file_glob` to discover files in the logs directory (e.g. `file_glob('{{logs}}/**/*')`).
2. Read each file using `file_read` with the `{{logs}}` alias.
3. Generate a concise summary of the day's activity.
4. Write the summary to `{{output}}/daily-summary-YYYY-MM-DD.md` using `file_write`.
5. Use `memory_save` to store the latest summary date in the "last_run" section so you can avoid reprocessing.
"""

    response = llm.invoke(prompt)
    raw = response.content
    if isinstance(raw, list):
        raw = "".join(block if isinstance(block, str) else block.get("text", "") for block in raw)
    content = raw.strip()

    # Strip code fences if present
    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else content[3:]
    if content.endswith("```"):
        content = content[: content.rfind("```")]

    return content.strip()


def _ask_agent_details(agent_name: str) -> str:
    """Interactively ask the user for agent details and build the .md content."""
    from rich.prompt import Prompt

    console.print()

    description = Prompt.ask("  [cyan]Description[/cyan]", default="")

    # Provider / model
    provider = Prompt.ask(
        "  [cyan]Provider[/cyan] [dim](google, openai, anthropic, ollama, local, or empty for default)[/dim]",
        default="",
    )
    model_name = ""
    if provider:
        model_name = Prompt.ask("  [cyan]Model name[/cyan]", default="")

    # Trigger
    trigger_type = Prompt.ask(
        "  [cyan]Trigger[/cyan] [dim](manual, schedule, watch)[/dim]",
        default="manual",
    )
    trigger_extra = ""
    if trigger_type == "schedule":
        schedule_val = Prompt.ask("  [cyan]Schedule[/cyan] [dim](e.g. 30m, 2h, or cron: 0 9 * * *)[/dim]")
        if schedule_val.strip():
            if " " in schedule_val.strip():
                trigger_extra = f'  cron: "{schedule_val.strip()}"'
            else:
                trigger_extra = f"  every: {schedule_val.strip()}"
    elif trigger_type == "watch":
        watch_paths = Prompt.ask("  [cyan]Paths to watch[/cyan] [dim](comma-separated)[/dim]")
        if watch_paths.strip():
            paths = [p.strip() for p in watch_paths.split(",") if p.strip()]
            trigger_extra = "\n".join(f"  - {p}" for p in paths)
            trigger_extra = f"  paths:\n{trigger_extra}"

    # Paths (named aliases)
    agent_paths = Prompt.ask(
        "  [cyan]Paths[/cyan] [dim](alias=path pairs, comma-separated, e.g. vault=/data,output=./out)[/dim]", default=""
    )

    # System prompt
    console.print()
    system_prompt = Prompt.ask("  [cyan]System prompt[/cyan] [dim](what should this agent do?)[/dim]")

    # Build frontmatter
    lines = ["---", f"name: {agent_name}"]
    if description:
        lines.append(f"description: {description}")
    if provider and model_name:
        lines.append("model:")
        lines.append(f"  provider: {provider}")
        lines.append(f"  name: {model_name}")
    if trigger_type != "manual":
        lines.append("trigger:")
        lines.append(f"  type: {trigger_type}")
        if trigger_extra:
            lines.append(trigger_extra)
    if agent_paths.strip():
        lines.append("paths:")
        for pair in agent_paths.split(","):
            pair = pair.strip()
            if not pair:
                continue
            if "=" in pair:
                alias, path = pair.split("=", 1)
                lines.append(f"  {alias.strip()}: {path.strip()}")
            else:
                # No alias given — use basename as alias
                from pathlib import Path as _P

                alias = _P(pair).name or pair.replace("/", "_").strip("_") or "data"
                lines.append(f"  {alias}: {pair}")
    lines.append("---")
    lines.append("")
    lines.append(system_prompt or "You are a helpful assistant. Describe your agent's task here.")
    lines.append("")

    return "\n".join(lines)


@app.command()
def new(
    agent_name: str = typer.Argument(..., help="Name for the new agent"),
    workspace: Path = typer.Option(None, "--workspace", "-w", help="Override workspace directory"),
    template: bool = typer.Option(False, "--template", "-t", help="Skip AI, use interactive questionnaire"),
):
    """Scaffold a new agent definition file."""
    # 1. Validate name
    error = _validate_agent_name(agent_name)
    if error:
        print_error(error)
        raise typer.Exit(1)

    # 2. Resolve workspace and agents dir
    from agent_md.core.services import _resolve_ws_and_agents_dir

    ws, agents_dir = _resolve_ws_and_agents_dir(workspace)
    agent_file = agents_dir / f"{agent_name}.md"

    # 3. Check if file already exists
    if agent_file.exists():
        print_error(f"Agent '{agent_name}' already exists.", f"File: {agent_file}")
        raise typer.Exit(1)

    # 4. Ensure agents dir exists
    agents_dir.mkdir(parents=True, exist_ok=True)

    # 5. Decide mode: AI or interactive
    ai_available, provider, model = _can_use_ai()

    if ai_available and not template:
        from rich.prompt import Prompt

        console.print()
        description = Prompt.ask("  [cyan]What should this agent do?[/cyan]")
        if not description.strip():
            print_error("Description cannot be empty.")
            raise typer.Exit(1)

        try:
            with console.status("  Generating agent..."):
                content = _generate_agent_with_ai(agent_name, description, provider, model)
        except Exception as e:
            print_warning(f"AI generation failed: {e}")
            console.print("  [dim]Falling back to interactive mode...[/dim]")
            content = _ask_agent_details(agent_name)
    else:
        # Interactive questionnaire
        if not ai_available and not template:
            console.print()
            console.print("  [dim]No AI provider configured. Tip: run 'agentmd setup'[/dim]")
        content = _ask_agent_details(agent_name)

    agent_file.write_text(content + "\n", encoding="utf-8")
    console.print()
    print_success(f"Agent '{agent_name}' created.")

    console.print(f"  [dim]File: {agent_file}[/dim]")
    console.print(f"  [dim]Run: agentmd run {agent_name}[/dim]")
    console.print(f"  [dim]Validate: agentmd validate {agent_name}[/dim]")
    console.print()


# ---------------------------------------------------------------------------
# agentmd start
# ---------------------------------------------------------------------------


@app.command()
def start(
    workspace: Path = typer.Option(None, "--workspace", "-w", help="Override workspace directory"),
    daemon: bool = typer.Option(False, "--daemon", "-d", help="Run in background"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress output except errors"),
):
    """Start the Agent.md runtime (scheduler + watcher)."""
    ws = _resolve_workspace(workspace)

    if daemon:
        from agent_md.cli.daemon import is_running, start_daemon, get_log_file

        running, pid = is_running(ws)
        if running:
            print_error(f"agentmd is already running (pid {pid}).", "Use 'agentmd stop' first.")
            raise typer.Exit(1)

        pid = start_daemon(ws)
        console.print(f"  agentmd started (pid {pid})")
        console.print(f"  Log: {get_log_file(ws)}")
        console.print("  [dim]Use 'agentmd status' to check, 'agentmd stop' to stop.[/dim]")
        return

    # Foreground mode
    on_event = print_agent_event if not quiet else None
    asyncio.run(_start_foreground(ws, on_event=on_event, quiet=quiet))


async def _start_foreground(workspace: Path, on_event=None, quiet: bool = False) -> None:
    from agent_md import __version__
    from agent_md.core.bootstrap import bootstrap

    on_start = print_agent_start if on_event else None
    on_complete = print_agent_complete if on_event else None
    runtime = await bootstrap(
        workspace, start_scheduler=True, on_event=on_event, on_complete=on_complete, on_start=on_start
    )

    agents = runtime.registry.all()
    enabled = [a for a in agents if a.enabled]
    scheduled = [a for a in enabled if a.trigger.type != "manual"]

    if not quiet:
        console.print()
        print_banner(__version__)
        console.print()

        # Runtime info panel
        from rich.table import Table

        info = Table(show_header=False, box=None, padding=(0, 2))
        info.add_column("Key", style="bold")
        info.add_column("Value")
        info.add_row("Workspace", str(runtime.path_context.workspace_root))
        info.add_row("Agents", f"{len(agents)} loaded, {len(scheduled)} scheduled")
        console.print(make_panel(info, title="Runtime"))
        console.print()

        # Agent table with next-run
        if agents:
            table = make_table(
                ("Name", {"style": "cyan"}),
                ("Trigger", {}),
                ("Next Run", {"style": "dim"}),
            )
            for a in agents:
                next_run = "\u2014"
                if runtime.scheduler and a.trigger.type != "manual":
                    job = runtime.scheduler.scheduler.get_job(f"agent_{a.name}")
                    if job and job.next_run_time:
                        next_run = job.next_run_time.strftime("%H:%M:%S")
                table.add_row(a.name, format_trigger(a), next_run)
            console.print(table)
            console.print()

        console.print("  [dim]Listening... Press Ctrl+C to stop[/dim]")
        console.print()

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        console.print("\n  [yellow]Shutting down...[/yellow]")
        await runtime.aclose()
        print_success("agentmd stopped.")


# ---------------------------------------------------------------------------
# agentmd run
# ---------------------------------------------------------------------------


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def run(
    ctx: typer.Context,
    agent: str = typer.Argument(None, help="Agent name (interactive picker if omitted)"),
    workspace: Path = typer.Option(None, "--workspace", "-w", help="Override workspace directory"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress output except result"),
):
    """Execute a single agent manually (one-shot).

    Pass extra positional arguments to substitute $ARGUMENTS / $0..$9 in the prompt:
        agentmd run my-agent -- arg1 arg2
    """
    from agent_md.core.services import AgentNotFoundError, run_agent

    agent_name = _pick_or_resolve_agent(agent, workspace)
    arguments = " ".join(ctx.args) if ctx.args else ""

    on_event = print_agent_event if not quiet else None
    on_start = print_agent_start if not quiet else None
    on_complete = print_agent_complete if not quiet else None

    try:
        _, result = asyncio.run(
            run_agent(
                agent_name,
                workspace,
                on_event=on_event,
                on_start=on_start,
                on_complete=on_complete,
                arguments=arguments,
            )
        )
    except AgentNotFoundError:
        print_error(f"Agent '{agent_name}' not found in workspace.", "Run 'agentmd list' to see available agents.")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# agentmd chat
# ---------------------------------------------------------------------------


@app.command()
def chat(
    agent: str = typer.Argument(None, help="Agent name (interactive picker if omitted)"),
    workspace: Path = typer.Option(None, "--workspace", "-w", help="Override workspace directory"),
):
    """Start an interactive chat session with an agent."""
    agent_name = _pick_or_resolve_agent(agent, workspace)

    try:
        asyncio.run(_chat_loop(agent_name, workspace))
    except KeyboardInterrupt:
        pass


async def _chat_loop(agent_name: str, workspace: Path | None) -> None:
    import time

    from agent_md.core.services import AgentNotFoundError, chat_session

    from functools import partial

    on_event = partial(print_agent_event, include_final_answer=False)

    try:
        async with chat_session(agent_name, workspace, on_event=on_event) as session:
            config = session.config
            model_info = f"{config.model.provider} / {config.model.name}" if config.model else "default"
            print_chat_header(config.name, model_info)

            loop = asyncio.get_running_loop()
            start_time = time.monotonic()

            while True:
                try:
                    user_input = await loop.run_in_executor(None, lambda: input("  > "))
                except EOFError:
                    break
                except KeyboardInterrupt:
                    break

                stripped = user_input.strip()
                if not stripped:
                    continue
                if stripped.lower() in ("/exit", "/quit"):
                    break

                console.print()

                try:
                    response = await session.send(stripped)
                    if response:
                        print_markdown(response)
                except asyncio.TimeoutError:
                    print_error(f"Timeout after {config.settings.timeout}s")
                except Exception as e:
                    print_error(f"{type(e).__name__}: {e}")

            duration_ms = int((time.monotonic() - start_time) * 1000)
            print_chat_summary(
                session.turns,
                session.total_input_tokens,
                session.total_output_tokens,
                duration_ms,
                session.execution_id,
            )

    except AgentNotFoundError:
        print_error(f"Agent '{agent_name}' not found in workspace.", "Run 'agentmd list' to see available agents.")


# ---------------------------------------------------------------------------
# agentmd list
# ---------------------------------------------------------------------------


@app.command(name="list")
def list_agents(
    workspace: Path = typer.Option(None, "--workspace", "-w", help="Override workspace directory"),
):
    """List all agents in the workspace."""
    from agent_md.core.services import _runtime

    async def _list_with_last_runs():
        async with _runtime(workspace) as rt:
            agents = rt.registry.all()
            last_runs: dict[str, str] = {}
            for a in agents:
                ex = await rt.db.get_last_execution(a.name)
                if ex:
                    last_runs[a.name] = ex.started_at
            return agents, last_runs

    agents, last_runs = asyncio.run(_list_with_last_runs())

    if not agents:
        print_warning("No agents found in workspace.")
        console.print("  [dim]Create an agent .md file in agents/ directory.[/dim]")
        return

    console.print()

    table = make_table(
        ("Name", {"style": "cyan"}),
        ("Trigger", {}),
        ("Last Run", {"style": "dim"}),
        ("Status", {"justify": "center"}),
    )

    for config in agents:
        last_run = format_relative_time(last_runs.get(config.name))
        table.add_row(
            config.name,
            format_trigger(config),
            last_run,
            agent_status_dot(config.enabled),
        )

    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# agentmd logs
# ---------------------------------------------------------------------------


@app.command()
def logs(
    agent: str = typer.Argument(None, help="Agent name (all agents if omitted)"),
    last: int = typer.Option(10, "--last", "-n", help="Number of recent executions"),
    execution: int = typer.Option(None, "--execution", "-e", help="Show details for execution ID"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output in real-time"),
    workspace: Path = typer.Option(None, "--workspace", "-w", help="Override workspace directory"),
):
    """Show recent execution history for an agent."""

    # Follow mode
    if follow:
        _follow_logs(workspace)
        return

    # Execution detail mode
    if execution is not None:
        _show_execution_detail(execution, workspace)
        return

    # List executions
    if agent is None:
        print_error("Agent name required for execution list.", "Usage: agentmd logs <agent-name>")
        raise typer.Exit(1)

    from agent_md.core.services import get_agent_logs

    executions = asyncio.run(get_agent_logs(agent, last, workspace))

    if not executions:
        print_warning(f"No executions found for '{agent}'.")
        return

    console.print(f"\n  [bold]Recent executions \u2014 {agent}[/bold]\n")

    status_style = {
        "success": "green",
        "error": "red",
        "timeout": "yellow",
        "running": "cyan",
        "aborted": "yellow",
        "killed": "red",
        "orphaned": "dim red",
    }

    has_cost = any(getattr(ex, "cost_usd", None) is not None for ex in executions)

    columns = [
        ("#", {"style": "dim"}),
        ("Status", {"justify": "center"}),
        ("Trigger", {}),
        ("Duration", {"justify": "right"}),
        ("Tokens", {"justify": "right"}),
    ]
    if has_cost:
        columns.append(("Cost", {"justify": "right"}))
    columns.append(("Started", {"style": "dim"}))

    table = make_table(*columns)

    for ex in executions:
        style = status_style.get(ex.status, "white")
        started = ex.started_at
        if started and len(started) > 10:
            started = started.split("T")[-1].split(".")[0] if "T" in started else started

        row = [
            str(ex.id),
            f"[{style}]{ex.status}[/{style}]",
            ex.trigger or "\u2014",
            format_duration(ex.duration_ms),
            format_tokens(ex.total_tokens),
        ]
        if has_cost:
            cost = getattr(ex, "cost_usd", None)
            row.append(f"${cost:.4f}" if cost is not None else "\u2014")
        row.append(started or "\u2014")

        table.add_row(*row)

    console.print(table)
    console.print()


def _show_execution_detail(execution_id: int, workspace: Path | None) -> None:
    """Show detailed messages for a specific execution."""
    from agent_md.core.services import get_execution_messages

    messages = asyncio.run(get_execution_messages(execution_id, workspace))

    if not messages:
        print_warning(f"No messages found for execution #{execution_id}.")
        return

    # Try to get execution summary
    console.print(f"\n  [bold]Execution #{execution_id}[/bold]")

    console.print()
    for log in messages:
        emoji, style = EVENT_DISPLAY.get(log.event_type, ("\u2753", "white"))
        ts = (
            log.timestamp.split("T")[-1].split(".")[0]
            if log.timestamp and "T" in log.timestamp
            else (log.timestamp or "")
        )

        if log.event_type == "system":
            # Show system prompt as summary
            chars = len(log.message) if log.message else 0
            console.print(f"  [dim]{ts}  {emoji}  System prompt ({chars:,} chars)[/dim]")
        elif log.event_type == "human":
            console.print(f"  [dim]{ts}  {emoji}  {log.message}[/dim]")
        else:
            content = log.message or ""
            console.print(f"  [dim]{ts}[/dim]  [{style}]{emoji} {content}[/{style}]")

    console.print()


def _follow_logs(workspace: Path | None) -> None:
    """Tail the daemon log file in real-time."""
    from agent_md.cli.daemon import is_running, get_log_file

    ws = _resolve_workspace(workspace)
    running, _ = is_running(ws)
    if not running:
        print_warning("agentmd is not running.")
        console.print("  [dim]Start with: agentmd start -d[/dim]")
        return

    log_file = get_log_file(ws)
    if not log_file.exists():
        print_warning(f"Log file not found: {log_file}")
        return

    import time

    console.print(f"  [dim]Following {log_file} (Ctrl+C to stop)[/dim]\n")
    try:
        with open(log_file) as f:
            # Seek to end
            f.seek(0, 2)
            while True:
                line = f.readline()
                if line:
                    console.print(f"  {line.rstrip()}")
                else:
                    time.sleep(0.2)
    except KeyboardInterrupt:
        console.print("\n  [dim]Stopped following logs.[/dim]")


# ---------------------------------------------------------------------------
# agentmd validate
# ---------------------------------------------------------------------------


@app.command()
def validate(
    agent: str = typer.Argument(None, help="Agent name (interactive picker if omitted)"),
    workspace: Path = typer.Option(None, "--workspace", "-w", help="Override workspace directory"),
):
    """Validate an agent file without executing it."""
    from agent_md.core.services import validate_agent

    # Backward compat: if arg contains / or ends in .md, treat as path
    if agent and ("/" in agent or agent.endswith(".md")):
        agent_ref = agent
    else:
        agent_ref = _pick_or_resolve_agent(agent, workspace)

    try:
        result = validate_agent(agent_ref, workspace=workspace)
    except FileNotFoundError:
        print_error(f"Agent '{agent_ref}' not found.", "Run 'agentmd list' to see available agents.")
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Validation failed: {e}")
        raise typer.Exit(1)

    config = result.config
    errors = 0

    console.print()
    console.print(f"  [green]\u2713[/green] [bold]{config.name}[/bold]")
    console.print()

    # Model + API key
    model_str = f"{config.model.provider} / {config.model.name}" if config.model else "default"
    api_status = "[green]\u2713 API key set[/green]" if result.api_key_set else "[red]\u2717 API key missing[/red]"
    if not result.api_key_set and config.model and config.model.provider not in ("ollama", "local"):
        errors += 1
    print_kv("Model", f"{model_str}         {api_status}")

    # History (session memory)
    if result.history_level != "off":
        from agent_md.core.models import HISTORY_LIMITS

        limit = HISTORY_LIMITS[result.history_level]
        print_kv("History", f"{result.history_level} (last {limit} messages)")
    else:
        print_kv("History", "off [dim](stateless)[/dim]")

    # Trigger
    trigger_str = format_trigger(config)
    trigger_valid = "[green]\u2713 Valid[/green]"
    for w in result.warnings:
        if "cron" in w.lower() or "watch path" in w.lower():
            trigger_valid = f"[red]\u2717 {w}[/red]"
            errors += 1
            break
    print_kv("Trigger", f"{trigger_str:<28}{trigger_valid}")

    # Prompt
    print_kv("Prompt", f"{len(config.system_prompt):,} chars")

    # Tools
    if result.builtin_tools or config.custom_tools:
        console.print("\n  [bold]Tools[/bold]")
        for t in result.builtin_tools:
            print_check(t, detail="built-in")
        for t in result.custom_tools_found:
            if t in result.custom_tools_loadable:
                print_check(t, detail="custom")
            elif t in result.custom_tools_load_errors:
                print_check(t, "error", f"load error: {result.custom_tools_load_errors[t]}")
                errors += 1
            else:
                print_check(t, detail="custom")
        for t in result.custom_tools_missing:
            print_check(t, "error", "not found")
            errors += 1

    # MCP Servers
    if config.mcp:
        console.print("\n  [bold]MCP Servers[/bold]")
        for s in result.mcp_servers_configured:
            print_check(s)
        for s in result.mcp_servers_missing:
            print_check(s, "error", "not in mcp-servers.json")
            errors += 1

    # Paths
    if config.paths:
        console.print("\n  [bold]Paths[/bold]")
        for p in result.paths_valid:
            print_check(p, detail="exists")
        for p in result.paths_missing:
            print_check(p, "warn", "does not exist yet")

    # Other warnings (not already surfaced above)
    _surfaced = {"cron", "watch path", "path:"}
    other_warnings = [w for w in result.warnings if not any(k in w.lower() for k in _surfaced)]
    if other_warnings:
        console.print("\n  [bold]Warnings[/bold]")
        for w in other_warnings:
            console.print(f"  [yellow]⚠ {w}[/yellow]")

    # Summary
    warn_count = len(result.warnings)
    console.print()
    if errors == 0 and warn_count == 0:
        print_success("No issues found.")
    else:
        parts = []
        if errors:
            parts.append(f"{errors} error{'s' if errors != 1 else ''}")
        if warn_count:
            parts.append(f"{warn_count} warning{'s' if warn_count != 1 else ''}")
        console.print(f"  {', '.join(parts)}")
    console.print()


# ---------------------------------------------------------------------------
# agentmd status
# ---------------------------------------------------------------------------


@app.command()
def status(
    workspace: Path = typer.Option(None, "--workspace", "-w", help="Override workspace directory"),
):
    """Check if the agentmd runtime is running."""
    from agent_md.cli.daemon import is_running, get_daemon_uptime, get_daemon_start_time, get_log_file

    ws = _resolve_workspace(workspace)
    running, pid = is_running(ws)

    console.print()
    if running:
        uptime = get_daemon_uptime(ws) or "unknown"
        start_time = get_daemon_start_time(ws) or "unknown"
        if start_time != "unknown":
            from datetime import datetime

            try:
                dt = datetime.fromisoformat(start_time)
                start_time = dt.strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                pass

        console.print(f"  [green]agentmd is running[/green] (pid {pid})")
        console.print()
        print_kv("Uptime", uptime)
        print_kv("Workspace", str(ws))
        print_kv("Log file", str(get_log_file(ws)))
        print_kv("Started", start_time)
    else:
        console.print("  agentmd is not running.")
        console.print("  [dim]Start with: agentmd start -d[/dim]")
    console.print()


# ---------------------------------------------------------------------------
# agentmd stop
# ---------------------------------------------------------------------------


@app.command()
def stop(
    workspace: Path = typer.Option(None, "--workspace", "-w", help="Override workspace directory"),
):
    """Stop the background agentmd runtime."""
    from agent_md.cli.daemon import is_running, stop_daemon

    ws = _resolve_workspace(workspace)
    running, pid = is_running(ws)

    if not running:
        print_warning("agentmd is not running.")
        return

    stopped = stop_daemon(ws)
    console.print()
    if stopped:
        console.print(f"  agentmd stopped (was pid {pid})")
    else:
        print_error("Failed to stop agentmd.")
    console.print()
