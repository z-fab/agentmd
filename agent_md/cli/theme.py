"""Centralized design system — visual helpers, palette, and interactive pickers."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from agent_md.config.models import AgentConfig

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


def print_check(label: str, status: str = "ok", detail: str = "") -> None:
    """Print a check-list item with ✓/✗/⚠ indicator.

    Args:
        label: Item text.
        status: ``"ok"``, ``"error"``, or ``"warn"``.
        detail: Optional suffix shown dimmed (for ok/warn) or after a dash (for error).
    """
    suffix = f" [dim]({detail})[/dim]" if detail else ""
    if status == "error":
        suffix = f" \u2014 {detail}" if detail else ""
        console.print(f"    [red]\u2717[/red] {label}{suffix}")
    elif status == "warn":
        console.print(f"    [yellow]\u26a0[/yellow] {label}{suffix}")
    else:
        console.print(f"    [green]\u2713[/green] {label}{suffix}")


def print_banner(version: str) -> None:
    """Print a one-line brand banner."""
    console.print(f"  [bold]agentmd[/bold] v{version}")


def print_chat_header(agent_name: str, model_info: str) -> None:
    """Print the chat session header with model info and exit hint."""
    console.print()
    console.print(f"  [bold cyan]Chat with {agent_name}[/bold cyan]")
    console.print(f"    [dim]{model_info}[/dim]")
    console.print("    [dim]Type /exit or Ctrl+C to end session[/dim]")
    console.print()


def print_chat_summary(turns: int, input_tokens: int, output_tokens: int, duration_ms: int, execution_id: int) -> None:
    """Print end-of-session summary stats."""
    total = input_tokens + output_tokens
    console.print()
    console.print(
        f"  [dim]Session ended: {turns} turn{'s' if turns != 1 else ''}, "
        f"{format_tokens(total)} tokens "
        f"({format_tokens(input_tokens)} in / {format_tokens(output_tokens)} out), "
        f"{format_duration(duration_ms)}[/dim]"
    )
    console.print(f"  [dim]Execution #{execution_id}[/dim]")
    console.print()


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


def display_icon(icon: str) -> str:
    """Normalise an agent icon for terminal display.

    Single-codepoint BMP symbols (e.g. ``\u2600`` sun, ``\u2699`` gear) default to a
    *text* presentation that many terminals render one cell wide, which knocks
    table columns out of alignment. Appending the emoji variation selector
    (``U+FE0F``) forces the two-cell emoji presentation so icon columns line up.
    Multi-codepoint emoji (which already carry a selector or are in the
    supplementary plane) are returned unchanged.
    """
    if len(icon) == 1 and 0x2000 <= ord(icon) < 0x1F000:
        return icon + "\ufe0f"
    return icon


# ---------------------------------------------------------------------------
# Event display mapping (emoji + Rich style per event type)
# ---------------------------------------------------------------------------

EVENT_DISPLAY: dict[str, tuple[str, str]] = {
    "system": ("\u2699\ufe0f", "dim"),
    "human": ("\U0001f464", "dim"),
    "ai": ("\U0001f916", "cyan"),
    "tool_call": ("\U0001f527", "yellow"),
    "tool_result": ("\U0001f4ce", "green"),
    "final_answer": ("\u2705", "bold green"),
    # Informational channel (execution_info / stats / skill-context).
    "meta": ("\u2139\ufe0f", "blue"),
}


# ---------------------------------------------------------------------------
# Content helpers
# ---------------------------------------------------------------------------


def sanitize_event_content(text: str) -> str:
    """Replace newlines and collapse whitespace for single-line event display."""
    return " ".join(text.replace("\n", " ").split())


def format_meta_log_content(metadata: str | None, message: str | None = None) -> str:
    """Build a one-line summary for a persisted ``meta`` log row.

    Reads only fields present in *metadata* JSON — never invents values.
    Subtypes are discriminated by payload ``event_type``:

    - ``execution_info`` — model / trigger / agent / args / session
    - ``stats`` — token counts and cost
    - ``meta`` (skill-context) — truncated ``content``

    Falls back to *message* (the DB label) when metadata is missing or
    unparseable.
    """
    import json

    payload: dict | None = None
    if metadata:
        try:
            parsed = json.loads(metadata)
            if isinstance(parsed, dict):
                payload = parsed
        except (json.JSONDecodeError, TypeError):
            payload = None

    if payload is None:
        return message or ""

    subtype = payload.get("event_type") or message or "meta"

    if subtype == "execution_info":
        parts: list[str] = []
        model = payload.get("model")
        if model:
            parts.append(str(model))
        trigger = payload.get("trigger")
        if trigger:
            parts.append(str(trigger))
        display_name = payload.get("display_name")
        agent_id = payload.get("agent_id")
        if display_name and agent_id and display_name != agent_id:
            parts.append(f"{display_name} ({agent_id})")
        elif display_name:
            parts.append(str(display_name))
        elif agent_id:
            parts.append(str(agent_id))
        args = payload.get("args")
        # Only render args when the list is non-empty (empty is the default).
        if isinstance(args, list) and args:
            parts.append(f"args={list(args)!r}")
        # session_id is meaningful when set; omit null (common outside chat).
        if "session_id" in payload and payload["session_id"] is not None:
            parts.append(f"session={payload['session_id']}")
        return " · ".join(parts) if parts else (message or "execution_info")
    if subtype == "stats":
        parts = []
        total = payload.get("total_tokens")
        inp = payload.get("input_tokens")
        out = payload.get("output_tokens")
        if total is not None:
            detail = format_tokens(total if isinstance(total, int) else None)
            if inp is not None and out is not None:
                parts.append(f"{detail} tokens ({format_tokens(inp)} in / {format_tokens(out)} out)")
            else:
                parts.append(f"{detail} tokens")
        elif inp is not None or out is not None:
            bits = []
            if inp is not None:
                bits.append(f"{format_tokens(inp)} in")
            if out is not None:
                bits.append(f"{format_tokens(out)} out")
            parts.append(" / ".join(bits))
        if "cost_usd" in payload:
            cost = payload["cost_usd"]
            if cost is None:
                parts.append("cost unknown")
            else:
                try:
                    parts.append(f"${float(cost):.4f}")
                except (TypeError, ValueError):
                    parts.append(f"cost={cost!r}")
        return " · ".join(parts) if parts else (message or "stats")

    # Skill-context (event_type "meta") and any other meta payload.
    content = payload.get("content")
    if content:
        return sanitize_event_content(str(content))[:200]
    return message or subtype


# ---------------------------------------------------------------------------
# Agent lifecycle callbacks (on_start / on_event / on_complete)
# ---------------------------------------------------------------------------


def _print_agent_line(emoji: str, agent_name: str, style: str, detail: str) -> None:
    """Print a formatted agent lifecycle line (start / complete / error).

    Centralises the layout so every lifecycle message looks identical::

        \\n  HH:MM:SS  {emoji} {agent_name}  {detail}\\n
    """
    from datetime import datetime

    ts = datetime.now().strftime("%H:%M:%S")
    console.print(f"\n  [dim]{ts}[/dim] [{style}]{emoji} [bold]{agent_name}[/bold][/{style}]  [dim]{detail}[/dim]\n")


def print_agent_start(agent_name: str, model_info: str) -> None:
    """Print agent execution start line. Used as ``on_start`` hook."""
    _print_agent_line("\u25b6", agent_name, "cyan", model_info)


def print_agent_complete(agent_name: str, result: dict) -> None:
    """Print agent execution result line. Used as ``on_complete`` hook."""
    status = result.get("status", "unknown")
    duration = format_duration(result.get("duration_ms"))
    if status == "success":
        tokens = format_tokens(result.get("total_tokens"))
        _print_agent_line("\u2713", agent_name, "green", f"{duration}  {tokens} tokens")
    elif status == "timeout":
        _print_agent_line("\u23f1", agent_name, "red", f"timeout after {duration}")
    else:
        error = result.get("error", "unknown error")
        _print_agent_line("\u2717", agent_name, "red", f"{duration}  {error}")


def print_agent_event(event_type: str, data: dict, *, include_final_answer: bool = True) -> None:
    """Print a streaming agent event line. Used as ``on_event`` hook.

    Args:
        event_type: Event type string (ai, tool_call, tool_result, final_answer).
        data: Event data dict with content/tool info.
        include_final_answer: When *False* the ``final_answer`` event is
            silently ignored (used by ``chat`` where the response is rendered
            separately as Markdown).
    """
    from datetime import datetime

    ts = datetime.now().strftime("%H:%M:%S")
    emoji, style = EVENT_DISPLAY.get(event_type, ("\u2753", "white"))
    indent = "    "  # 4-space indent for hierarchy under header

    if event_type in ("ai", "tool_result"):
        limit = 200 if event_type == "ai" else 100
        content = sanitize_event_content(data.get("content", ""))[:limit]
        label = data.get("tool_name", "") + " \u2190 " if event_type == "tool_result" else ""
        line = f"{indent}[dim]{ts}[/dim]  [{style}]{emoji} {label}{content}[/{style}]"
        console.print(line, overflow="ellipsis", no_wrap=True, crop=True)
    elif event_type == "tool_call":
        args = sanitize_event_content(data.get("tool_args", ""))[:80]
        line = f"{indent}[dim]{ts}[/dim]  [{style}]{emoji} {data['tool_name']}[/{style}] [dim]\u2192 {args}[/dim]"
        console.print(line, overflow="ellipsis", no_wrap=True, crop=True)
    elif event_type == "final_answer" and include_final_answer:
        content = sanitize_event_content(data.get("content", ""))[:200]
        line = f"{indent}[dim]{ts}[/dim]  [{style}]{emoji} {content}[/{style}]"
        console.print(line, overflow="ellipsis", no_wrap=True, crop=True)


def print_markdown(text: str, indent: int = 4) -> None:
    """Render text as Rich Markdown with left padding."""
    md = Markdown(text)
    console.print(Padding(md, (1, 0, 1, indent)))


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


def format_agent_label(agent_id: str, display_name: str | None = None) -> str:
    """Return an unequivocal agent label: display name plus id when they differ."""
    name = display_name if display_name is not None else agent_id
    if name == agent_id:
        return agent_id
    return f"{name} ({agent_id})"


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

    Always shows id; when display name differs from id, both appear
    (``Display Name (id)``). Falls back to text input when stdin is not a TTY.
    """
    if not agents:
        return None

    if len(agents) == 1:
        only = agents[0]
        label = format_agent_label(only.id, only.name)
        console.print(f"  Auto-selected [bold]{label}[/bold]")
        return only

    # Build choices — visible text is id (+ display when different); value via agent_map.
    choices = []
    agent_map: dict[str, AgentConfig] = {}
    visible_labels = [format_agent_label(a.id, a.name) for a in agents]

    max_name = max(len(v) for v in visible_labels)
    for a, visible in zip(agents, visible_labels, strict=True):
        label = f"{visible:<{max_name}}  {a.description}" if a.description else visible
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
