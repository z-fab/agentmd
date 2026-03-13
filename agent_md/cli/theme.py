"""Centralized design system — visual helpers, palette, and interactive pickers."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from agent_md.core.models import AgentConfig

console = Console()

# ---------------------------------------------------------------------------
# Semantic print helpers
# ---------------------------------------------------------------------------


def print_kv(key: str, value: str, indent: int = 2, key_width: int = 14) -> None:
    """Print an aligned key-value pair."""
    pad = " " * indent
    console.print(f"{pad}[bold]{key:<{key_width}}[/bold] {value}")


def print_success(msg: str) -> None:
    console.print(f"  [green]{msg}[/green]")


def print_error(msg: str, hint: str | None = None) -> None:
    console.print(f"  [red]error:[/red] {msg}")
    if hint:
        console.print(f"  [dim]{hint}[/dim]")


def print_warning(msg: str) -> None:
    console.print(f"  [yellow]warning:[/yellow] {msg}")


def print_banner(version: str) -> None:
    """Print a one-line brand banner."""
    console.print(f"  [bold]agentmd[/bold] v{version}")


# ---------------------------------------------------------------------------
# Rich component factories
# ---------------------------------------------------------------------------


def make_table(*columns: tuple[str, dict]) -> Table:
    """Create a table with SIMPLE_HEAD box style.

    Each column is (name, kwargs) passed to ``Table.add_column``.
    """
    table = Table(box=box.SIMPLE_HEAD, padding=(0, 2))
    for name, kwargs in columns:
        table.add_column(name, **kwargs)
    return table


def make_panel(content, title: str | None = None, border_style: str = "dim") -> Panel:
    """Create a panel with rounded borders and dim border by default."""
    return Panel(content, title=title, box=box.ROUNDED, border_style=border_style)


def agent_status_dot(enabled: bool) -> str:
    """Return a coloured status dot."""
    if not enabled:
        return "[dim]\u25cb[/dim]"
    return "[green]\u25cf[/green]"


# ---------------------------------------------------------------------------
# Event display mapping (emoji + Rich style per event type)
# ---------------------------------------------------------------------------

EVENT_DISPLAY: dict[str, tuple[str, str]] = {
    "system": ("\u2699\ufe0f", "dim"),
    "human": ("\U0001f464", "dim"),
    "ai": ("\U0001f916", "cyan"),
    "tool_call": ("\U0001f527", "yellow"),
    "tool_response": ("\U0001f4ce", "green"),
    "final_answer": ("\u2705", "bold green"),
}


# ---------------------------------------------------------------------------
# Trigger formatting
# ---------------------------------------------------------------------------


def format_trigger(config: AgentConfig) -> str:
    """Return a short human-readable trigger string."""
    t = config.trigger
    if t.type == "manual":
        return "manual"
    if t.type == "schedule":
        if t.cron:
            return f"cron ({t.cron})"
        if t.every:
            return f"every {t.every}"
    if t.type == "watch":
        paths_str = ", ".join(t.paths[:2])
        if len(t.paths) > 2:
            paths_str += "..."
        return f"watch ({paths_str})"
    return t.type or "manual"


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def format_duration(ms: int | None) -> str:
    """Format milliseconds into a compact human-readable string."""
    if ms is None:
        return "\u2014"
    if ms < 1000:
        return f"{ms}ms"
    secs = ms / 1000
    if secs < 60:
        return f"{secs:.1f}s"
    mins = secs / 60
    return f"{mins:.1f}m"


def format_tokens(n: int | None) -> str:
    """Format a token count with thousands separator."""
    if n is None:
        return "\u2014"
    return f"{n:,}"


def format_relative_time(iso_str: str | None) -> str:
    """Convert an ISO timestamp to a relative time string like '2h ago'."""
    if not iso_str:
        return "never"
    from datetime import datetime, timezone

    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - dt
        secs = int(delta.total_seconds())
        if secs < 0:
            return "just now"
        if secs < 60:
            return f"{secs}s ago"
        if secs < 3600:
            return f"{secs // 60}m ago"
        if secs < 86400:
            return f"{secs // 3600}h ago"
        days = secs // 86400
        return f"{days}d ago"
    except (ValueError, TypeError):
        return iso_str


# ---------------------------------------------------------------------------
# Interactive agent picker
# ---------------------------------------------------------------------------


def select_agent(agents: list[AgentConfig], prompt: str = "Select an agent") -> AgentConfig | None:
    """Interactive agent picker using questionary.

    Falls back to text input when stdin is not a TTY.
    """
    if not agents:
        return None

    if len(agents) == 1:
        console.print(f"  Auto-selected [bold]{agents[0].name}[/bold]")
        return agents[0]

    # Build choices
    choices = []
    agent_map: dict[str, AgentConfig] = {}
    max_name = max(len(a.name) for a in agents)
    for a in agents:
        label = f"{a.name:<{max_name}}  {a.description}" if a.description else a.name
        choices.append(label)
        agent_map[label] = a

    if not sys.stdin.isatty():
        # Non-interactive fallback
        console.print(f"\n  {prompt}:")
        for i, c in enumerate(choices, 1):
            console.print(f"    {i}. {c}")
        return None

    try:
        import questionary

        answer = questionary.select(prompt, choices=choices).ask()
        if answer is None:
            return None
        return agent_map[answer]
    except ImportError:
        # questionary not installed — basic fallback
        console.print(f"\n  {prompt}:")
        for i, c in enumerate(choices, 1):
            console.print(f"    {i}. {c}")
        try:
            idx = int(input("  Enter number: ")) - 1
            if 0 <= idx < len(choices):
                return agent_map[choices[idx]]
        except (ValueError, EOFError, KeyboardInterrupt):
            pass
        return None
