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
    print_banner,
    print_error,
    print_kv,
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


def _make_console_callback():
    """Return an on_event callback that prints Rich-formatted output."""
    from datetime import datetime

    def _on_event(event_type: str, data: dict) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        emoji, style = EVENT_DISPLAY.get(event_type, ("\u2753", "white"))

        if event_type in ("ai", "tool_response"):
            content = data.get("content", "")[:200 if event_type == "ai" else 100]
            label = data.get("tool_name", "") + " \u2190 " if event_type == "tool_response" else ""
            line = f"  [dim]{ts}[/dim]  [{style}]{emoji} {label}{content}[/{style}]"
            console.print(line, overflow="ellipsis", no_wrap=True, crop=True)
        elif event_type == "tool_call":
            line = f"  [dim]{ts}[/dim]  [{style}]{emoji} {data['tool_name']}[/{style}] \u2192 {data['tool_args'][:80]}"
            console.print(line, overflow="ellipsis", no_wrap=True, crop=True)
        elif event_type == "final_answer":
            console.print()
            console.print(f"  [dim]{ts}[/dim]  [{style}]{emoji} {data['content']}[/{style}]")

    return _on_event


def _make_complete_callback():
    """Return an on_complete callback for scheduled runs."""
    from datetime import datetime

    def _on_complete(agent_name: str, result: dict) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        status = result.get("status", "unknown")
        duration = format_duration(result.get("duration_ms"))
        if status == "success":
            tokens = format_tokens(result.get("total_tokens"))
            console.print(
                f"  [dim]{ts}[/dim] [green]\u2713 {agent_name}[/green] \u2014 done in {duration} ({tokens} tokens)"
            )
        elif status == "timeout":
            console.print(f"  [dim]{ts}[/dim] [yellow]\u23f1 {agent_name}[/yellow] \u2014 timeout after {duration}")
        else:
            error = result.get("error", "unknown error")
            console.print(f"  [dim]{ts}[/dim] [red]\u2717 {agent_name}[/red] \u2014 error after {duration}: {error}")

    return _on_complete


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
    on_event = _make_console_callback() if not quiet else None
    asyncio.run(_start_foreground(ws, on_event=on_event, quiet=quiet))


async def _start_foreground(workspace: Path, on_event=None, quiet: bool = False) -> None:
    from agent_md import __version__
    from agent_md.core.bootstrap import bootstrap

    on_complete = _make_complete_callback()
    runtime = await bootstrap(workspace, start_scheduler=True, on_event=on_event, on_complete=on_complete)

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


@app.command()
def run(
    agent: str = typer.Argument(None, help="Agent name (interactive picker if omitted)"),
    workspace: Path = typer.Option(None, "--workspace", "-w", help="Override workspace directory"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress output except result"),
):
    """Execute a single agent manually (one-shot)."""
    from agent_md.core.services import AgentNotFoundError, run_agent

    agent_name = _pick_or_resolve_agent(agent, workspace)

    # Parse config for display
    from agent_md.core.parser import parse_agent_file
    from agent_md.core.services import _resolve_ws_and_agents_dir

    ws, agents_dir = _resolve_ws_and_agents_dir(workspace)

    agent_file = agents_dir / f"{agent_name.replace('.md', '')}.md"
    if not agent_file.exists():
        print_error(f"Agent '{agent_name}' not found in {agents_dir}", "Run 'agentmd list' to see available agents.")
        raise typer.Exit(1)

    config = parse_agent_file(agent_file)

    if not quiet:
        console.print()
        console.print(f"  [cyan]\u25b6 Running {config.name}[/cyan]")
        if config.model:
            console.print(f"    [dim]{config.model.provider} / {config.model.name}[/dim]")
        console.print()

    on_event = _make_console_callback() if not quiet else None

    try:
        _, result = asyncio.run(run_agent(agent_name, workspace, on_event=on_event))
    except AgentNotFoundError:
        print_error(f"Agent '{agent_name}' not found in workspace.", "Run 'agentmd list' to see available agents.")
        raise typer.Exit(1)

    console.print()
    if result["status"] == "success":
        duration = format_duration(result.get("duration_ms"))
        tokens_info = ""
        if result.get("total_tokens"):
            tokens_info = (
                f"\n    Tokens: {format_tokens(result['input_tokens'])} in / "
                f"{format_tokens(result['output_tokens'])} out / "
                f"{format_tokens(result['total_tokens'])} total"
            )
        console.print(
            f"  [green]\u2713 {config.name} completed in {duration}[/green]"
            f"{tokens_info}"
            f"\n    [dim]Execution #{result['execution_id']}[/dim]"
        )
    elif result["status"] == "timeout":
        console.print(
            f"  [yellow]\u2717 {config.name} timeout[/yellow] after {format_duration(result.get('duration_ms'))}"
        )
    else:
        console.print(
            f"  [red]\u2717 {config.name} error[/red] after {format_duration(result.get('duration_ms'))} \u2014 {result.get('error', 'unknown')}"
        )


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

    status_style = {"success": "green", "error": "red", "timeout": "yellow", "running": "cyan"}

    table = make_table(
        ("#", {"style": "dim"}),
        ("Status", {"justify": "center"}),
        ("Trigger", {}),
        ("Duration", {"justify": "right"}),
        ("Tokens", {"justify": "right"}),
        ("Started", {"style": "dim"}),
    )

    for ex in executions:
        style = status_style.get(ex.status, "white")
        started = ex.started_at
        if started and len(started) > 10:
            # Show just time portion if today
            started = started.split("T")[-1].split(".")[0] if "T" in started else started

        table.add_row(
            str(ex.id),
            f"[{style}]{ex.status}[/{style}]",
            ex.trigger or "\u2014",
            format_duration(ex.duration_ms),
            format_tokens(ex.total_tokens),
            started or "\u2014",
        )

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
            console.print(f"    [green]\u2713[/green] {t} [dim](built-in)[/dim]")
        for t in result.custom_tools_found:
            if t in result.custom_tools_loadable:
                console.print(f"    [green]\u2713[/green] {t} [dim](custom)[/dim]")
            elif t in result.custom_tools_load_errors:
                console.print(f"    [red]\u2717[/red] {t} \u2014 load error: {result.custom_tools_load_errors[t]}")
                errors += 1
            else:
                console.print(f"    [green]\u2713[/green] {t} [dim](custom)[/dim]")
        for t in result.custom_tools_missing:
            console.print(f"    [red]\u2717[/red] {t} \u2014 not found")
            errors += 1

    # MCP Servers
    if config.mcp:
        console.print("\n  [bold]MCP Servers[/bold]")
        for s in result.mcp_servers_configured:
            console.print(f"    [green]\u2713[/green] {s}")
        for s in result.mcp_servers_missing:
            console.print(f"    [red]\u2717[/red] {s} \u2014 not in mcp-servers.json")
            errors += 1

    # Paths
    if config.read or config.write:
        console.print("\n  [bold]Paths[/bold]")
        for p in result.read_paths_valid:
            console.print(f"    [green]\u2713[/green] read: {p} [dim](exists)[/dim]")
        for p in result.read_paths_missing:
            console.print(f"    [red]\u2717[/red] read: {p} [dim](not found)[/dim]")
            errors += 1
        for p in result.write_paths_valid:
            console.print(f"    [green]\u2713[/green] write: {p} [dim](exists)[/dim]")
        for p in result.write_paths_missing:
            console.print(f"    [yellow]\u26a0[/yellow] write: {p} [dim](will be created)[/dim]")

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
