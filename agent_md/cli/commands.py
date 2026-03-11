"""CLI command definitions — presentation layer only."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from agent_md.cli import app
from agent_md.core.models import AgentConfig

console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_logging(verbosity: int = 0) -> None:
    """Configure root logger based on verbosity level.

    0-1 → WARNING (suppress INFO), 2 → INFO, 3 → DEBUG.
    """
    if verbosity >= 3:
        level = logging.DEBUG
    elif verbosity >= 2:
        level = logging.INFO
    else:
        level = logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, markup=True)],
    )


def _resolve_verbosity(quiet: bool, verbose: int, default: int) -> int:
    """Compute effective verbosity level."""
    if quiet:
        return 0
    if verbose > 0:
        return verbose
    return default


def _make_console_callback(con: Console):
    """Return an on_event callback that prints Rich-formatted output.

    All events except final_answer are single-line with timestamp and agent name.
    Content is truncated to avoid line wrapping.
    """
    from datetime import datetime

    def _on_event(event_type: str, data: dict) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        agent = data.get("agent_name", "")
        prefix = f"[dim]{ts}[/dim] [bold]{agent}[/bold]"

        if event_type == "ai":
            line = f"{prefix} [cyan]🤖 {data['content'][:200]}[/cyan]"
            con.print(line, overflow="ellipsis", no_wrap=True, crop=True)
        elif event_type == "tool_call":
            line = f"{prefix} [yellow]🔧 {data['tool_name']}[/yellow] → {data['tool_args'][:80]}"
            con.print(line, overflow="ellipsis", no_wrap=True, crop=True)
        elif event_type == "tool_response":
            line = f"{prefix} [green]📎 {data['tool_name']}[/green] ← {data['content'][:100]}"
            con.print(line, overflow="ellipsis", no_wrap=True, crop=True)
        elif event_type == "final_answer":
            con.print()
            con.print(f"{prefix} [bold green]✅ Final answer:[/bold green]")
            con.print(f"  {data['content']}")

    return _on_event


def _print_agents_table(agents: list[AgentConfig]) -> None:
    table = Table(title="Agents")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="dim")
    table.add_column("Provider", style="green")
    table.add_column("Model")
    table.add_column("Trigger")
    table.add_column("Custom Tools")
    table.add_column("MCP", style="magenta")
    table.add_column("Status", justify="center")

    for config in agents:
        trigger_str = config.trigger.type
        if config.trigger.type == "schedule":
            if config.trigger.cron:
                trigger_str += f" (cron: {config.trigger.cron})"
            elif config.trigger.every:
                trigger_str += f" (every: {config.trigger.every})"
        elif config.trigger.type == "watch":
            paths_str = ", ".join(config.trigger.paths[:2])  # Show first 2 paths
            if len(config.trigger.paths) > 2:
                paths_str += "..."
            trigger_str += f" ({paths_str})"

        status = "[green]●[/green]" if config.enabled else "[dim]○[/dim]"

        table.add_row(
            config.name,
            config.description or "—",
            config.model.provider,
            config.model.name,
            trigger_str,
            ", ".join(config.custom_tools) or "—",
            ", ".join(config.mcp) or "—",
            status,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# agentmd start
# ---------------------------------------------------------------------------


@app.command()
def start(
    workspace: Path = typer.Option(None, "--workspace", "-w", help="Root workspace directory"),
    agents_dir: Path = typer.Option(None, "--agents-dir", help="Directory with .md agent files"),
    output_dir: Path = typer.Option(None, "--output-dir", help="Default output directory for agents"),
    db_path: Path = typer.Option(None, "--db-path", help="Path to SQLite database"),
    mcp_config: Path = typer.Option(None, "--mcp-config", help="Path to MCP servers JSON config"),
    tui: bool = typer.Option(False, "--tui", help="Launch Terminal UI"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress all output except errors"),
    verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="Increase verbosity (-v, -vv, -vvv)"),
):
    """Start the Agent.md runtime (scheduler + watcher)."""
    verbosity = _resolve_verbosity(quiet, verbose, default=0)
    _setup_logging(verbosity)

    on_event = _make_console_callback(console) if verbosity >= 1 else None

    if tui:
        pass
        # from agent_md.tui.app import AgentMdApp
        # tui_app = AgentMdApp(workspace=workspace)
        # tui_app.run()
    else:
        asyncio.run(
            _start_cli(workspace, agents_dir=agents_dir, output_dir=output_dir, db_path=db_path, mcp_config=mcp_config, on_event=on_event)
        )


def _make_complete_callback(con: Console):
    """Return an on_complete callback that prints a summary line per scheduled run."""
    from datetime import datetime

    def _on_complete(agent_name: str, result: dict) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        status = result.get("status", "unknown")
        duration = result.get("duration_ms", 0)
        if status == "success":
            tokens = result.get("total_tokens", 0)
            con.print(f"[dim]{ts}[/dim] [green]✓ {agent_name}[/green] — done in {duration}ms ({tokens} tokens)")
        elif status == "timeout":
            con.print(f"[dim]{ts}[/dim] [yellow]⏱ {agent_name}[/yellow] — timeout after {duration}ms")
        else:
            error = result.get("error", "unknown error")
            con.print(f"[dim]{ts}[/dim] [red]✗ {agent_name}[/red] — error after {duration}ms: {error}")

    return _on_complete


async def _start_cli(
    workspace: Path,
    agents_dir: Path | None = None,
    output_dir: Path | None = None,
    db_path: Path | None = None,
    mcp_config: Path | None = None,
    on_event=None,
) -> None:
    from agent_md.core.bootstrap import bootstrap

    on_complete = _make_complete_callback(console)
    runtime = await bootstrap(
        workspace,
        agents_dir=agents_dir,
        output_dir=output_dir,
        db_path=db_path,
        mcp_config=mcp_config,
        start_scheduler=True,
        on_event=on_event,
        on_complete=on_complete,
    )

    agents = runtime.registry.all()
    enabled = [a for a in agents if a.enabled]
    scheduled = [a for a in enabled if a.trigger.type != "manual"]

    ctx = runtime.path_context
    console.print()
    console.print("[bold green]Agent.md is running[/bold green]")
    console.print(f"  Workspace:  {ctx.workspace_root}")
    console.print(f"  Agents dir: {ctx.agents_dir}")
    console.print(f"  Output dir: {ctx.output_dir}")
    console.print(f"  Agents:     {len(agents)} loaded, {len(enabled)} enabled, {len(scheduled)} scheduled")
    console.print()

    if agents:
        _print_agents_table(agents)

    console.print("[dim]Press Ctrl+C to stop[/dim]")

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")
        await runtime.aclose()
        console.print("[green]Agent.md stopped.[/green]")


# ---------------------------------------------------------------------------
# agentmd run
# ---------------------------------------------------------------------------


@app.command()
def run(
    agent: str = typer.Argument(help="Agent name or .md filename"),
    workspace: Path = typer.Option(None, "--workspace", "-w", help="Root workspace directory"),
    agents_dir: Path = typer.Option(None, "--agents-dir", help="Directory with .md agent files"),
    output_dir: Path = typer.Option(None, "--output-dir", help="Default output directory for agents"),
    db_path: Path = typer.Option(None, "--db-path", help="Path to SQLite database"),
    mcp_config: Path = typer.Option(None, "--mcp-config", help="Path to MCP servers JSON config"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress event output"),
    verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="Increase verbosity (-v, -vv, -vvv)"),
):
    """Execute a single agent manually (one-shot)."""
    from agent_md.core.services import AgentNotFoundError, run_agent
    from agent_md.core.settings import settings

    verbosity = _resolve_verbosity(quiet, verbose, default=1)
    _setup_logging(verbosity)

    # Resolve agents_dir for file lookup
    resolved_agents_dir = agents_dir
    if resolved_agents_dir is None:
        if settings.AGENTMD_AGENTS_DIR:
            resolved_agents_dir = Path(settings.AGENTMD_AGENTS_DIR)
        else:
            ws = workspace or (Path(settings.AGENTMD_WORKSPACE) if settings.AGENTMD_WORKSPACE else Path("./workspace"))
            resolved_agents_dir = ws / "agents"

    from agent_md.core.parser import parse_agent_file

    agent_file = resolved_agents_dir / f"{agent.replace('.md', '')}.md"
    if not agent_file.exists():
        console.print(f"[red]Agent '{agent}' not found in {resolved_agents_dir}[/red]")
        raise typer.Exit(1)

    config = parse_agent_file(agent_file)
    console.print(
        f"[cyan]▶ Running {config.name}[/cyan]  {config.model.provider}/{config.model.name}  "
        f"custom_tools: {', '.join(config.custom_tools) or 'none'}" + (f"  mcp: {', '.join(config.mcp)}" if config.mcp else "")
    )
    console.print()

    on_event = _make_console_callback(console) if verbosity >= 1 else None

    try:
        _, result = asyncio.run(
            run_agent(
                agent, workspace, agents_dir=agents_dir, output_dir=output_dir, db_path=db_path, mcp_config=mcp_config, on_event=on_event
            )
        )
    except AgentNotFoundError:
        console.print(f"[red]Agent '{agent}' not found in workspace[/red]")
        raise typer.Exit(1)

    console.print()
    if result["status"] == "success":
        tokens_info = ""
        if result.get("total_tokens"):
            tokens_info = f"  tokens: {result['input_tokens']} in / {result['output_tokens']} out / {result['total_tokens']} total"
        console.print(
            f"[green]✓ {config.name} done[/green] in {result['duration_ms']}ms{tokens_info}  [dim]execution #{result['execution_id']}[/dim]"
        )
    elif result["status"] == "timeout":
        console.print(f"[yellow]⏱ {config.name} timeout[/yellow] after {result['duration_ms']}ms — {result['error']}")
    else:
        console.print(f"[red]✗ {config.name} error[/red] after {result['duration_ms']}ms — {result['error']}")


# ---------------------------------------------------------------------------
# agentmd list
# ---------------------------------------------------------------------------


@app.command(name="list")
def list_agents(
    workspace: Path = typer.Option(None, "--workspace", "-w", help="Root workspace directory"),
    agents_dir: Path = typer.Option(None, "--agents-dir", help="Directory with .md agent files"),
    output_dir: Path = typer.Option(None, "--output-dir", help="Default output directory for agents"),
    db_path: Path = typer.Option(None, "--db-path", help="Path to SQLite database"),
    mcp_config: Path = typer.Option(None, "--mcp-config", help="Path to MCP servers JSON config"),
):
    """List all agents in the workspace."""
    from agent_md.core.services import list_agents as svc_list_agents

    _setup_logging(0)
    agents = asyncio.run(svc_list_agents(workspace, agents_dir=agents_dir, output_dir=output_dir, db_path=db_path, mcp_config=mcp_config))

    if not agents:
        console.print("[yellow]No agents found in workspace[/yellow]")
        return

    _print_agents_table(agents)


# ---------------------------------------------------------------------------
# agentmd logs  (placeholder — db not wired yet)
# ---------------------------------------------------------------------------


@app.command()
def logs(
    agent: str = typer.Argument(help="Agent name"),
    n: int = typer.Option(10, "--n", "-n", help="Number of recent executions"),
    execution: int = typer.Option(None, "--execution", "-e", help="Show messages for a specific execution ID"),
    workspace: Path = typer.Option(None, "--workspace", "-w", help="Root workspace directory"),
    agents_dir: Path = typer.Option(None, "--agents-dir", help="Directory with .md agent files"),
    output_dir: Path = typer.Option(None, "--output-dir", help="Default output directory for agents"),
    db_path: Path = typer.Option(None, "--db-path", help="Path to SQLite database"),
    mcp_config: Path = typer.Option(None, "--mcp-config", help="Path to MCP servers JSON config"),
):
    """Show recent execution history for an agent."""
    _setup_logging(0)

    # If --execution is provided, show the detailed messages for that run
    if execution is not None:
        from agent_md.core.services import get_execution_messages

        messages = asyncio.run(
            get_execution_messages(execution, workspace, agents_dir=agents_dir, output_dir=output_dir, db_path=db_path, mcp_config=mcp_config)
        )

        if not messages:
            console.print(f"[yellow]No messages found for execution #{execution}[/yellow]")
            return

        event_display = {
            "system": ("⚙️", "dim"),
            "human": ("👤", "dim"),
            "ai": ("🤖", "cyan"),
            "tool_call": ("🔧", "yellow"),
            "tool_response": ("📎", "green"),
            "final_answer": ("✅", "bold green"),
        }

        table = Table(title=f"Execution #{execution} — messages")
        table.add_column("Timestamp", style="dim", max_width=22)
        table.add_column("Event", justify="center", min_width=8)
        table.add_column("Message", overflow="fold")

        for log in messages:
            emoji, style = event_display.get(log.event_type, ("❓", "white"))
            table.add_row(
                log.timestamp or "—",
                f"{emoji} [{style}]{log.event_type}[/{style}]",
                log.message,
            )

        console.print(table)
        return

    # Default: show list of recent executions
    from agent_md.core.services import get_agent_logs

    executions = asyncio.run(
        get_agent_logs(agent, n, workspace, agents_dir=agents_dir, output_dir=output_dir, db_path=db_path, mcp_config=mcp_config)
    )

    if not executions:
        console.print(f"[yellow]No executions found for '{agent}'[/yellow]")
        return

    status_style = {"success": "green", "error": "red", "timeout": "yellow", "running": "cyan"}

    table = Table(title=f"Recent executions — {agent}")
    table.add_column("#", style="dim")
    table.add_column("Status", justify="center")
    table.add_column("Trigger")
    table.add_column("Duration")
    table.add_column("Input Tokens", justify="right")
    table.add_column("Output Tokens", justify="right")
    table.add_column("Total Tokens", justify="right")
    table.add_column("Started at")
    table.add_column("Output / Error", max_width=60)

    for ex in executions:
        style = status_style.get(ex.status, "white")
        duration = f"{ex.duration_ms}ms" if ex.duration_ms is not None else "—"
        preview = (ex.output_data or ex.error or "—")[:80]
        in_tok = str(ex.input_tokens) if ex.input_tokens is not None else "—"
        out_tok = str(ex.output_tokens) if ex.output_tokens is not None else "—"
        tot_tok = str(ex.total_tokens) if ex.total_tokens is not None else "—"

        table.add_row(
            str(ex.id),
            f"[{style}]{ex.status}[/{style}]",
            ex.trigger,
            duration,
            in_tok,
            out_tok,
            tot_tok,
            ex.started_at or "—",
            preview,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# agentmd validate
# ---------------------------------------------------------------------------


@app.command()
def validate(
    file: Path = typer.Argument(help="Path to the .md agent file"),
    agents_dir: Path = typer.Option(None, "--agents-dir", help="Directory with .md agent files (used to locate tools/)"),
):
    """Validate an agent file without executing it."""
    from agent_md.core.services import validate_agent
    from agent_md.core.settings import settings

    # Resolve tools_dir for custom tool validation
    resolved_agents_dir = agents_dir
    if resolved_agents_dir is None:
        if settings.AGENTMD_AGENTS_DIR:
            resolved_agents_dir = Path(settings.AGENTMD_AGENTS_DIR)
        else:
            ws = Path(settings.AGENTMD_WORKSPACE) if settings.AGENTMD_WORKSPACE else Path("./workspace")
            resolved_agents_dir = ws / "agents"
    tools_dir = resolved_agents_dir / "tools"

    try:
        result = validate_agent(file, tools_dir=tools_dir)
    except Exception as e:
        console.print(f"[red]✗ Validation failed:[/red] {e}")
        raise typer.Exit(1)

    config = result.config

    console.print(f"[green]✓ Valid agent:[/green] {config.name}")
    console.print(f"  Provider:     {config.model.provider}")
    console.print(f"  Model:        {config.model.name}")
    console.print(f"  Trigger:      {config.trigger.type}", end="")
    if config.trigger.type == "schedule":
        if config.trigger.cron:
            console.print(f" (cron: {config.trigger.cron})")
        elif config.trigger.every:
            console.print(f" (every: {config.trigger.every})")
        else:
            console.print()
    elif config.trigger.type == "watch":
        console.print(f" (paths: {', '.join(config.trigger.paths)})")
    else:
        console.print()
    console.print(f"  Built-in:     {', '.join(result.builtin_tools)}")
    console.print(f"  Custom tools: {', '.join(config.custom_tools) or 'none'}")
    console.print(f"  MCP Servers:  {', '.join(config.mcp) or 'none'}")
    console.print(f"  Read paths:   {', '.join(config.read) or 'default (workspace)'}")
    console.print(f"  Write paths:  {', '.join(config.write) or 'default (output)'}")
    console.print(f"  Enabled:      {config.enabled}")
    console.print(f"  Prompt:       {len(config.system_prompt)} chars")

    if result.custom_tools_missing:
        console.print(f"\n[yellow]⚠ Missing custom tools: {', '.join(result.custom_tools_missing)}[/yellow]")
        console.print(f"  Expected in: {tools_dir}")
