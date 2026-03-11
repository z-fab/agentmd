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


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, markup=True)],
    )


def _print_agents_table(agents: list[AgentConfig]) -> None:
    table = Table(title="Agents")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="dim")
    table.add_column("Provider", style="green")
    table.add_column("Model")
    table.add_column("Trigger")
    table.add_column("Tools")
    table.add_column("MCP", style="magenta")
    table.add_column("Status", justify="center")

    for config in agents:
        trigger_str = config.trigger.type
        if config.trigger.schedule:
            trigger_str += f" ({config.trigger.schedule})"
        elif config.trigger.interval:
            trigger_str += f" ({config.trigger.interval})"

        status = "[green]●[/green]" if config.enabled else "[dim]○[/dim]"

        table.add_row(
            config.name,
            config.description or "—",
            config.model.provider,
            config.model.name,
            trigger_str,
            ", ".join(config.tools) or "—",
            ", ".join(config.mcp) or "—",
            status,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# agentmd start
# ---------------------------------------------------------------------------


@app.command()
def start(
    workspace: Path = typer.Option("./workspace", "--workspace", "-w", help="Directory with .md agent files"),
    tui: bool = typer.Option(False, "--tui", help="Launch Terminal UI"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Debug logging"),
):
    """Start the Agent.md runtime (scheduler + watcher)."""
    _setup_logging(verbose)

    if tui:
        pass
        # from agent_md.tui.app import AgentMdApp
        # tui_app = AgentMdApp(workspace=workspace)
        # tui_app.run()
    else:
        asyncio.run(_start_cli(workspace))


async def _start_cli(workspace: Path) -> None:
    from agent_md.core.bootstrap import bootstrap

    runtime = await bootstrap(workspace, start_scheduler=True)

    agents = runtime.registry.all()
    enabled = [a for a in agents if a.enabled]
    scheduled = [a for a in enabled if a.trigger.type != "manual"]

    console.print()
    console.print("[bold green]Agent.md is running[/bold green]")
    console.print(f"  Workspace:  {runtime.workspace}")
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
    workspace: Path = typer.Option("./workspace", "--workspace", "-w", help="Directory with .md agent files"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Execute a single agent manually (one-shot)."""
    from agent_md.core.services import AgentNotFoundError, run_agent

    _setup_logging(verbose)

    from agent_md.core.parser import parse_agent_file

    agent_file = workspace / f"{agent.replace('.md', '')}.md"
    if not agent_file.exists():
        console.print(f"[red]Agent '{agent}' not found in workspace[/red]")
        raise typer.Exit(1)

    config = parse_agent_file(agent_file)
    console.print(
        f"[cyan]▶ {config.name}[/cyan]  {config.model.provider}/{config.model.name}  "
        f"tools: {', '.join(config.tools) or 'none'}"
        + (f"  mcp: {', '.join(config.mcp)}" if config.mcp else "")
    )
    console.print()

    try:
        _, result = asyncio.run(run_agent(agent, workspace))
    except AgentNotFoundError:
        console.print(f"[red]Agent '{agent}' not found in workspace[/red]")
        raise typer.Exit(1)

    console.print()
    if result["status"] == "success":
        tokens_info = ""
        if result.get("total_tokens"):
            tokens_info = f"  tokens: {result['input_tokens']} in / {result['output_tokens']} out / {result['total_tokens']} total"
        console.print(
            f"[green]✓ Done[/green] in {result['duration_ms']}ms{tokens_info}  [dim]execution #{result['execution_id']}[/dim]"
        )
    elif result["status"] == "timeout":
        console.print(f"[yellow]⏱ Timeout[/yellow] after {result['duration_ms']}ms — {result['error']}")
    else:
        console.print(f"[red]✗ Error[/red] after {result['duration_ms']}ms — {result['error']}")


# ---------------------------------------------------------------------------
# agentmd list
# ---------------------------------------------------------------------------


@app.command(name="list")
def list_agents(
    workspace: Path = typer.Option("./workspace", "--workspace", "-w", help="Directory with .md agent files"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """List all agents in the workspace."""
    from agent_md.core.services import list_agents as svc_list_agents

    _setup_logging(verbose)
    agents = asyncio.run(svc_list_agents(workspace))

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
    workspace: Path = typer.Option("./workspace", "--workspace", "-w"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Show recent execution history for an agent."""
    _setup_logging(verbose)

    # If --execution is provided, show the detailed messages for that run
    if execution is not None:
        from agent_md.core.services import get_execution_messages

        messages = asyncio.run(get_execution_messages(execution, workspace))

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

    executions = asyncio.run(get_agent_logs(agent, n, workspace))

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
):
    """Validate an agent file without executing it."""
    from agent_md.core.services import validate_agent

    try:
        result = validate_agent(file)
    except Exception as e:
        console.print(f"[red]✗ Validation failed:[/red] {e}")
        raise typer.Exit(1)

    config = result.config

    console.print(f"[green]✓ Valid agent:[/green] {config.name}")
    console.print(f"  Provider:     {config.model.provider}")
    console.print(f"  Model:        {config.model.name}")
    console.print(f"  Trigger:      {config.trigger.type}", end="")
    if config.trigger.schedule:
        console.print(f" ({config.trigger.schedule})")
    elif config.trigger.interval:
        console.print(f" ({config.trigger.interval})")
    else:
        console.print()
    console.print(f"  Tools:        {', '.join(config.tools) or 'none'}")
    console.print(f"  MCP Servers:  {', '.join(config.mcp) or 'none'}")
    console.print(f"  Enabled:      {config.enabled}")
    console.print(f"  Prompt:       {len(config.system_prompt)} chars")

    if result.unknown_tools:
        console.print(f"\n[yellow]⚠ Unknown tools: {', '.join(result.unknown_tools)}[/yellow]")
        console.print(f"  Available: {', '.join(result.available_tools)}")
