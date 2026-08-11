"""CLI command definitions — presentation layer only."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Annotated, Optional
from urllib.parse import quote

import typer

from agent_md.cli import app
from agent_md.cli.theme import (
    EVENT_DISPLAY,
    agent_status_dot,
    console,
    display_icon,
    format_agent_label,
    format_duration,
    format_meta_log_content,
    format_relative_time,
    format_tokens,
    format_trigger,
    make_table,
    print_check,
    print_error,
    print_kv,
    print_success,
    print_warning,
    select_agent,
)
from agent_md.config.icons import resolve_agent_icon
from agent_md.config.models import AgentConfig

# Marker for warnings produced by format_unknown_key_warning(), which `validate`
# groups under its own heading instead of the generic warnings list.
_UNKNOWN_KEY_PREFIX = "unknown frontmatter key"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _agent_path(agent: str, suffix: str = "") -> str:
    """Build an /agents/<encoded-id><suffix> request path (handles spaces)."""
    return f"/agents/{quote(agent, safe='')}{suffix}"


def _resolve_workspace(workspace: Path | None) -> Path:
    """Resolve workspace path from CLI arg or settings."""
    from agent_md.config.settings import settings

    if workspace:
        return workspace.resolve()
    ws = settings.workspace
    if ws:
        return Path(ws).expanduser().resolve()
    return Path("./workspace").resolve()


def _get_agents_for_picker(workspace: Path | None) -> list[AgentConfig]:
    """Bootstrap lightly to get agent list for interactive picker."""
    from agent_md.workspace.services import list_agents as svc_list

    return asyncio.run(svc_list(workspace))


def _lookup_agent(agent_id: str, workspace: Path | None) -> AgentConfig | None:
    """Return the agent config for a canonical id, or None if missing."""
    agents = _get_agents_for_picker(workspace)
    for cfg in agents:
        if cfg.id == agent_id:
            return cfg
    return None


def _pick_or_resolve_agent(agent: str | None, workspace: Path | None) -> str:
    """Resolve agent id: picker when omitted; validate canonical id when given.

    Display names are not accepted as aliases — the argument must be the
    filename stem (canonical id).
    """
    agents = _get_agents_for_picker(workspace)
    if not agents:
        print_error("No agents found in workspace.", "Create an agent in agents/ directory.")
        raise typer.Exit(1)

    if agent is not None:
        for cfg in agents:
            if cfg.id == agent:
                return cfg.id
        known = ", ".join(sorted(cfg.id for cfg in agents))
        print_error(
            f"Agent '{agent}' not found.",
            f"Pass a canonical id (filename stem). Available: {known}",
        )
        raise typer.Exit(1)

    selected = select_agent(agents)
    if selected is None:
        print_error("No agent selected.")
        raise typer.Exit(1)
    return selected.id


# ---------------------------------------------------------------------------
# agentmd new
# ---------------------------------------------------------------------------


def _validate_agent_name(name: str) -> str | None:
    """Return error string if name is invalid, else None."""
    import re

    if not name or name != name.strip():
        return "Agent name must be non-empty and have no leading/trailing spaces."
    if not re.match(r"^[\w \-]+$", name, re.UNICODE):
        return "Agent name may contain only letters, numbers, spaces, hyphens, and underscores."
    return None


def _can_use_ai() -> tuple[bool, str, str]:
    """Check if AI generation is available. Returns (available, provider, model)."""
    import os

    from agent_md.workspace.services import _PROVIDER_ENV_VARS
    from agent_md.config.settings import settings

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


GENERATE_PROMPT = """Generate the content of a markdown agent file for an agent named "{agent_name}" based on this description:
{description}

## File format

YAML frontmatter (between --- delimiters) followed by the system prompt in Markdown.

## Frontmatter fields

Required:
- name: {agent_name}  (may contain spaces and accents, e.g. "Daily Processor")

Optional:
- icon: an emoji that represents the agent (auto-derived from name if omitted)
- description: one-line summary
- model: object with provider and name (omit to use global default)
- trigger: manual (default), schedule (every/cron), watch (paths)
- settings: temperature, max_tokens, timeout
- history: "low" (default, remembers last 10 messages), "medium" (50), "high" (200), "off"
- paths: dict of alias: path pairs for directories the agent can access
- agents: list of agent names this agent can call via run_agent (e.g. [summarizer, formatter])
- skills: list of skill names available under agents/_config/skills/
- mcp: list of MCP server names configured in agents/_config/mcp-servers.json
- custom_tools: list of custom tool file names under agents/_config/tools/ (alias: tools)

## Built-in tools

- file_read, file_write, file_edit, file_glob, file_move, file_delete
- http_request
- memory_save, memory_append, memory_retrieve
- run_agent (requires agents: in frontmatter)
- ask_user (prompt the user for confirmation, input, or a choice)
- skill tools (available when skills: is set)

## Human-in-the-loop (HILT)

By default, file_delete and file_write ask the user for confirmation before running. You can:
- Guard more tools: `confirm: [toolname, ...]`
- Skip confirmation for specific tools: `auto_approve: [toolname, ...]` (or `auto_approve: "*"` for all)
- Control concurrency while waiting: `on_pending: skip` (default) or `on_pending: parallel`
- Set a response timeout: `confirm_timeout: 30s` / `5m` / `none`

If the agent performs destructive or sensitive actions, it can rely on the default confirmation
for file operations, and use the `ask_user` tool when it needs information only the user can provide.

## Rules

- Write ONLY the file content (starts with ---, ends after the prompt)
- System prompt must be clear, specific, and actionable
- Use path aliases ({{alias}}) for file access, not hardcoded paths
- Only include frontmatter fields that differ from defaults
- If the agent needs to remember between runs, set history or use memory tools

## Example

---
name: daily-summary
icon: 📋
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

1. Use file_glob to discover today's files in {{logs}}.
2. Read each file.
3. Generate a concise summary.
4. Write to {{output}}/summary-YYYY-MM-DD.md.
5. Use memory_save to track the last processed date.
"""


def _generate_agent_with_ai(agent_name: str, description: str, provider: str, model: str) -> str:
    """Use the configured LLM to generate the agent .md content."""
    from agent_md.providers.factory import create_chat_model

    llm = create_chat_model(provider, model, {"temperature": 0.7, "max_tokens": 4096})

    prompt = GENERATE_PROMPT.format(agent_name=agent_name, description=description)

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
    description = Prompt.ask("  [cyan]What should this agent do?[/cyan]")

    trigger_type = Prompt.ask(
        "  [cyan]Trigger[/cyan]",
        choices=["manual", "schedule", "watch"],
        default="manual",
    )
    trigger_extra = ""
    if trigger_type == "schedule":
        schedule_val = Prompt.ask("  [cyan]Schedule[/cyan] [dim](e.g. 30m, 2h, or cron expression)[/dim]")
        if schedule_val.strip():
            if " " in schedule_val.strip():
                trigger_extra = f'  cron: "{schedule_val.strip()}"'
            else:
                trigger_extra = f"  every: {schedule_val.strip()}"
    elif trigger_type == "watch":
        watch_paths = Prompt.ask("  [cyan]Paths to watch[/cyan] [dim](comma-separated)[/dim]")
        if watch_paths.strip():
            paths = [p.strip() for p in watch_paths.split(",") if p.strip()]
            trigger_extra = "  paths:\n" + "\n".join(f"    - {p}" for p in paths)

    agent_paths = Prompt.ask(
        "  [cyan]Paths[/cyan] [dim](alias=path, e.g. data=./data,output=./out)[/dim]",
        default="",
    )

    agent_agents = Prompt.ask(
        "  [cyan]Agents to call[/cyan] [dim](comma-separated agent names, or empty)[/dim]",
        default="",
    )

    # Build frontmatter
    lines = ["---", f"name: {agent_name}"]
    if description:
        lines.append(f"description: {description}")
    if trigger_type != "manual":
        lines.append("trigger:")
        lines.append(f"  type: {trigger_type}")
        if trigger_extra:
            lines.append(trigger_extra)
    if agent_paths.strip():
        lines.append("paths:")
        for pair in agent_paths.split(","):
            pair = pair.strip()
            if "=" in pair:
                alias, path = pair.split("=", 1)
                lines.append(f"  {alias.strip()}: {path.strip()}")
    if agent_agents.strip():
        lines.append("agents:")
        for name in agent_agents.split(","):
            name = name.strip()
            if name:
                lines.append(f"  - {name}")
    lines.append("---")
    lines.append("")
    lines.append(description or "You are a helpful assistant. Describe your task here.")
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
    from agent_md.workspace.services import _resolve_ws_and_agents_dir

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
            # Validate AI output before writing — fall back if the model produced junk.
            from agent_md.workspace.parser import parse_agent_file
            import tempfile

            with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as tmp:
                tmp.write(content + "\n")
                tmp_path = Path(tmp.name)
            try:
                parse_agent_file(tmp_path)
            except Exception as ve:
                print_warning(f"AI output failed validation: {ve}")
                console.print("  [dim]Falling back to interactive mode...[/dim]")
                content = _ask_agent_details(agent_name)
            finally:
                tmp_path.unlink(missing_ok=True)
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

# Cap on uvicorn's graceful drain. Its default is *no* timeout, so one open
# connection — an SSE stream is enough — keeps the process alive forever after
# the listening socket is already closed and unlinked. The streams now close
# themselves on shutdown (see agent_md/api/sse.py); this is the backstop for
# anything else that holds a connection. Past the cap uvicorn cancels the stuck
# tasks and still runs lifespan shutdown, so the database closes cleanly.
_GRACEFUL_DRAIN_SECONDS = 8.0


@app.command()
def start(
    workspace: Annotated[Optional[str], typer.Option("--workspace", "-w")] = None,
    daemon: Annotated[bool, typer.Option("--daemon", "-d")] = False,
    keep_alive: Annotated[bool, typer.Option("--keep-alive")] = False,
    port: Annotated[Optional[int], typer.Option("--port")] = None,
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    api_key: Annotated[Optional[str], typer.Option("--api-key")] = None,
    internal_backend: Annotated[bool, typer.Option("--internal-backend", hidden=True)] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q")] = False,
):
    """Start the Agentmd backend."""
    from rich.console import Console

    from agent_md.cli.errors import BackendAlreadyRunning, BackendStartupFailed, TcpRequiresApiKey

    console = Console()
    ws = Path(workspace) if workspace else None

    # Checked here, not only in _run_backend: the daemon path never gets there.
    if port and not api_key:
        console.print(f"[red]{TcpRequiresApiKey()}[/red]")
        raise typer.Exit(1)
    if api_key and not port:
        console.print(
            "[yellow]--api-key has no effect without --port (the Unix socket is guarded by file permissions).[/yellow]"
        )

    if daemon and not internal_backend:
        from agent_md.cli.spawn import _spawn_backend
        from agent_md.cli.client import BackendClient, get_log_path

        client = BackendClient()
        if client.health_check():
            console.print("[yellow]Backend is already running.[/yellow]")
            return

        pid = _spawn_backend(ws, _server_args(keep_alive, port, host, api_key))
        console.print(f"[green]Backend started[/green] (PID {pid})")
        if port:
            console.print(f"  Listening on http://{host}:{port}")
        console.print(f"  Logs: {get_log_path()}")
        return

    if not quiet and not internal_backend:
        console.print("[bold]Agentmd Backend[/bold]")

    try:
        asyncio.run(_run_backend(ws, keep_alive, port, host, api_key, quiet or internal_backend))
    except (BackendAlreadyRunning, TcpRequiresApiKey) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except BackendStartupFailed as e:
        console.print(f"[red]Backend failed to start: {e}[/red]")
        raise typer.Exit(1)


def _server_args(keep_alive: bool, port: int | None, host: str, api_key: str | None) -> list[str]:
    """Flags the detached child needs to come up in the same server mode."""
    args: list[str] = []
    if keep_alive:
        args.append("--keep-alive")
    if port:
        args.extend(["--port", str(port), "--host", host, "--api-key", api_key])
    return args


async def _run_backend(workspace, keep_alive, port, host, api_key, quiet):
    """Run the FastAPI backend with uvicorn."""
    import uvicorn
    from agent_md.api.app import create_app
    from agent_md.cli.client import BackendClient, get_socket_path, get_state_dir
    from agent_md.cli.errors import BackendAlreadyRunning, BackendStartupFailed, TcpRequiresApiKey
    from agent_md.util.tasks import spawn_background

    # Refuse an unauthenticated TCP bind before touching the socket or the runtime.
    if port and not api_key:
        raise TcpRequiresApiKey()

    socket_path = get_socket_path()
    state_dir = get_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)

    if socket_path.exists():
        # Never unlink a live backend's socket — that causes duplicate schedulers.
        if BackendClient().health_check():
            raise BackendAlreadyRunning(
                "Backend is already running. Use 'agentmd stop' first, or connect with the CLI."
            )
        socket_path.unlink()

    app = create_app(workspace=workspace, start_scheduler=True)
    app.state.keep_alive = keep_alive
    # Service mode: someone other than the local CLI may be driving the backend,
    # so a HILT execution waiting for a human must keep it alive.
    app.state.service_mode = bool(port) or keep_alive

    # The socket app is never wrapped — the local CLI sends no key and the
    # socket is already restricted to the owner (chmod 600 below).
    config = uvicorn.Config(
        app,
        uds=str(socket_path),
        log_level="warning" if quiet else "info",
        timeout_graceful_shutdown=_GRACEFUL_DRAIN_SECONDS,
    )
    server = uvicorn.Server(config)

    async def _set_socket_perms():
        while not socket_path.exists():
            await asyncio.sleep(0.1)
        socket_path.chmod(0o600)

    async def _watch_shutdown():
        while not hasattr(app.state, "shutdown_event"):
            await asyncio.sleep(0.1)
        await app.state.shutdown_event.wait()
        server.should_exit = True

    spawn_background(_set_socket_perms())
    spawn_background(_watch_shutdown())

    if port:
        from agent_md.api.auth import ApiKeyMiddleware

        # Auth lives on the TCP entrypoint only: same app, same runtime, but
        # every request that arrives over the network must carry the key.
        tcp_app = ApiKeyMiddleware(app, api_key=api_key)
        tcp_config = uvicorn.Config(
            tcp_app,
            host=host,
            port=port,
            log_level="warning" if quiet else "info",
            timeout_graceful_shutdown=_GRACEFUL_DRAIN_SECONDS,
        )
        tcp_server = uvicorn.Server(tcp_config)

        async def _watch_shutdown_tcp():
            while not hasattr(app.state, "shutdown_event"):
                await asyncio.sleep(0.1)
            await app.state.shutdown_event.wait()
            tcp_server.should_exit = True

        spawn_background(_watch_shutdown_tcp())
        await asyncio.gather(server.serve(), tcp_server.serve())
    else:
        await server.serve()

    # uvicorn turns a failed lifespan startup into a log line and a normal
    # return, so without this `agentmd start` exits 0 for a backend that came up
    # on nothing — and callers like `ensure_backend` read that as success.
    startup_error = getattr(app.state, "startup_error", None)
    if startup_error is not None:
        raise BackendStartupFailed(str(startup_error) or type(startup_error).__name__) from startup_error


# ---------------------------------------------------------------------------
# agentmd run
# ---------------------------------------------------------------------------


@app.command(context_settings={"allow_extra_args": True})
def run(
    ctx: typer.Context,
    agent: Annotated[Optional[str], typer.Argument()] = None,
    workspace: Annotated[Optional[str], typer.Option("--workspace", "-w")] = None,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Print only the final answer")] = False,
    detach: Annotated[
        bool,
        typer.Option("--detach", "-d", help="Run in the background; if it needs input it appears in 'agentmd pending'"),
    ] = False,
):
    """Execute a single agent by canonical id (filename stem)."""
    from rich.console import Console
    from agent_md.cli.spawn import ensure_backend

    console = Console()

    ws = Path(workspace) if workspace else None
    agent = _pick_or_resolve_agent(agent, ws)

    try:
        client = ensure_backend(workspace=ws)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    arguments = ctx.args
    body = {"args": arguments} if arguments else {}
    resp = client.post(_agent_path(agent, "/run"), json=body)
    if resp.status_code == 404:
        console.print(f"[red]Agent '{agent}' not found.[/red]")
        raise typer.Exit(1)
    if resp.status_code != 200:
        console.print(f"[red]Error: {resp.text}[/red]")
        raise typer.Exit(1)

    execution_id = resp.json()["execution_id"]

    if detach:
        console.print(f"[green]Execution {execution_id} started in background.[/green]")
        console.print("  [dim]Follow it with: agentmd logs  |  if it needs input: agentmd pending[/dim]")
        return

    if not quiet:
        console.print(f"[dim]Execution {execution_id} started[/dim]")

    answered: set = set()
    seen: set = set()
    final_status: str | None = None
    try:
        while True:
            result = _stream_execution(client, execution_id, console, quiet, answered, seen)
            if result and result.get("interrupt"):
                data = result["interrupt"]
                rid = data.get("request_id")
                if rid in answered:
                    break  # safety: already answered, nothing new
                _prompt_and_respond(client, execution_id, console, data)
                answered.add(rid)
                continue  # re-open the stream to observe the resume
            if result and result.get("waiting"):
                pend = client.get(f"/executions/{execution_id}/pending")
                if pend.status_code == 200 and pend.json().get("request_id") not in answered:
                    p = pend.json()
                    _prompt_and_respond(client, execution_id, console, p)
                    answered.add(p.get("request_id"))
                    continue
                break
            if result:
                final_status = result.get("status") or final_status
            break
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelling...[/yellow]")
        client.delete(f"/executions/{execution_id}")
        raise typer.Exit(130)

    # Propagate non-success terminal statuses as a non-zero exit code.
    if final_status is None:
        try:
            detail = client.get(f"/executions/{execution_id}")
            if detail.status_code == 200:
                final_status = detail.json().get("status")
        except Exception:
            pass
    if final_status and final_status not in ("success", "waiting", "running", "pending"):
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# SSE streaming helpers
# ---------------------------------------------------------------------------


def _prompt_and_respond(client, execution_id: int, console, payload: dict) -> None:
    """Render a HILT request, collect the answer, and POST it."""
    import typer

    kind = payload.get("kind", "input")
    message = payload.get("message", "Input needed")
    request_id = payload.get("request_id")
    console.print(f"\n[bold yellow]✋ {message}[/bold yellow]")
    if payload.get("tool_name"):
        console.print(f"[dim]tool: {payload['tool_name']}  args: {payload.get('tool_args')}[/dim]")

    if kind == "confirm":
        approved = typer.confirm("Approve?")
        response = {"approved": approved}
    elif kind == "choice":
        options = payload.get("options") or []
        for i, opt in enumerate(options):
            console.print(f"  {i + 1}. {opt}")
        idx = typer.prompt("Choose (number)", type=int)
        sel = options[idx - 1] if 1 <= idx <= len(options) else ""
        response = {"selected": [sel] if sel else []}
    else:
        text = typer.prompt("Your answer")
        response = {"text": text}

    client.post(f"/executions/{execution_id}/respond", json={"request_id": request_id, "response": response})


def _stream_execution(
    client, execution_id: int, console, quiet: bool, answered: set | None = None, seen: set | None = None
):
    """Stream SSE events from an execution and print them."""
    import json

    with client.stream_sse(f"/executions/{execution_id}/stream") as response:
        event_type = None
        data_buffer = ""
        event_id = None
        got_final_answer = False

        for line in response.iter_lines():
            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                data_buffer = line[5:].strip()
            elif line.startswith("id:"):
                event_id = line[3:].strip()
            elif line == "" and data_buffer:
                try:
                    data = json.loads(data_buffer)
                except json.JSONDecodeError:
                    data = {"raw": data_buffer}

                if event_type == "complete":
                    status = data.get("status", "unknown")
                    if not quiet:
                        error = data.get("error")
                        tokens = data.get("total_tokens")
                        cost = data.get("cost_usd")
                        duration_ms = data.get("duration_ms")

                        # Error/abort message
                        if status in ("aborted", "error", "timeout", "cancelled") and error:
                            console.print(f"\n\u274c {error}")
                        elif not got_final_answer and status == "success":
                            console.print("\n[dim]\u2014 No final response[/dim]")

                        # Summary line — always shown
                        style = "red" if status in ("aborted", "error", "timeout", "cancelled") else "green"
                        parts = [f"[bold {style}]{status}[/bold {style}]"]
                        if duration_ms:
                            secs = duration_ms / 1000
                            parts.append(f"{secs:.1f}s")
                        if tokens:
                            parts.append(f"{tokens} tokens")
                        if cost:
                            parts.append(f"${cost:.4f}")
                        console.print(f"\n[dim]{'  |  '.join(parts)}[/dim]")
                    return {"status": status, **data}
                elif event_type == "final_answer":
                    got_final_answer = True
                    already_seen = seen is not None and event_id is not None and event_id in seen
                    if not already_seen:
                        if quiet:
                            # Quiet mode: print only the final answer, undecorated (pipe-friendly).
                            console.print(str(data.get("content", data.get("message", ""))))
                        else:
                            _print_event(console, event_type, data)
                        if seen is not None and event_id is not None:
                            seen.add(event_id)
                elif event_type == "interrupt":
                    rid = data.get("request_id")
                    if answered is not None and rid in answered:
                        # already handled this pause on a previous pass; skip and keep reading
                        data_buffer = ""
                        event_type = None
                        event_id = None
                        continue
                    return {"interrupt": data}
                elif event_type == "waiting":
                    return {"waiting": True}
                elif not quiet:
                    already_seen = seen is not None and event_id is not None and event_id in seen
                    if not already_seen:
                        _print_event(console, event_type, data)
                        if seen is not None and event_id is not None:
                            seen.add(event_id)

                data_buffer = ""
                event_type = None
                event_id = None

    return None


def _stream_chat_turn(client, execution_id: int, console, answered: set | None = None, seen: set | None = None) -> dict:
    """Stream a single chat turn — discrete display, return stats.

    Shows tools and thinking in dim gray; only the final answer is prominent.
    Returns the complete event data dict for stats accumulation.
    """
    import json

    stats: dict = {}
    got_final = False
    last_ai_content = ""
    with client.stream_sse(f"/executions/{execution_id}/stream") as response:
        event_type = None
        data_buffer = ""
        event_id = None

        for line in response.iter_lines():
            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                data_buffer = line[5:].strip()
            elif line.startswith("id:"):
                event_id = line[3:].strip()
            elif line == "" and data_buffer:
                try:
                    data = json.loads(data_buffer)
                except json.JSONDecodeError:
                    data = {"raw": data_buffer}

                if event_type == "complete":
                    stats = data
                    # If no final_answer arrived, show the last AI message as the response
                    if not got_final and last_ai_content:
                        console.print(last_ai_content)
                    error = data.get("error")
                    status = data.get("status", "unknown")
                    if status in ("aborted", "error", "timeout", "cancelled") and error:
                        console.print(f"  [red]{error}[/red]")
                    break
                elif event_type == "interrupt":
                    rid = data.get("request_id")
                    if answered is not None and rid in answered:
                        # already handled this pause on a previous pass; skip and keep reading
                        data_buffer = ""
                        event_type = None
                        event_id = None
                        continue
                    return {"interrupt": data}
                elif event_type == "waiting":
                    return {"waiting": True}
                elif event_type == "final_answer":
                    already_seen = seen is not None and event_id is not None and event_id in seen
                    if not already_seen:
                        content = str(data.get("content", data.get("message", "")))
                        if content:
                            console.print(content)
                        if seen is not None and event_id is not None:
                            seen.add(event_id)
                    got_final = True
                elif event_type == "tool_call":
                    already_seen = seen is not None and event_id is not None and event_id in seen
                    if not already_seen:
                        tools = data.get("tools", [])
                        if tools:
                            names = ", ".join(t.get("name", "?") for t in tools)
                            console.print(f"  [dim]{names}...[/dim]")
                        else:
                            msg = str(data.get("content", data.get("message", "")))[:60]
                            if msg:
                                console.print(f"  [dim]{msg}...[/dim]")
                        if seen is not None and event_id is not None:
                            seen.add(event_id)
                elif event_type == "ai":
                    already_seen = seen is not None and event_id is not None and event_id in seen
                    if not already_seen:
                        # Buffer AI content — only show if no final_answer follows
                        last_ai_content = str(data.get("content", data.get("message", "")))
                        if seen is not None and event_id is not None:
                            seen.add(event_id)
                # tool_result, system, human, meta — silent in chat mode

                data_buffer = ""
                event_type = None
                event_id = None

    return stats


def _print_event(console, event_type: str, data: dict):
    """Format and print a single SSE event to the console.

    Handles both live event format (from EventBus) and DB replay format
    (from execution logs). Live events have structured fields like ``tools``;
    DB replay events have a ``message`` string.
    """
    content = str(data.get("content", data.get("message", "")))

    if event_type == "tool_call":
        tools = data.get("tools", [])
        if tools:
            # Live event format
            for tool in tools:
                name = tool.get("name", "unknown")
                args = tool.get("args", "")[:80]
                console.print(f"  [cyan]\U0001f527 >> {name}[/cyan] [dim]({args})[/dim]")
        elif content:
            # DB replay format: "file_write — args: {'path': '...'}"
            console.print(f"  [cyan]\U0001f527 >> {content[:120]}[/cyan]")
    elif event_type == "tool_result":
        tool_name = data.get("tool_name", "")
        result = content[:120].replace("\n", " ")
        if tool_name:
            console.print(f"  [dim]\U0001f4ce << {tool_name} \u2192 {result}[/dim]")
        else:
            # DB replay format: "file_write — Updated ..."
            console.print(f"  [dim]\U0001f4ce << {result}[/dim]")
    elif event_type == "ai":
        if content:
            console.print(f"  [white]\U0001f916 {content[:200]}[/white]")
    elif event_type == "final_answer":
        console.print(f"\n\u2705 {content}")
    elif event_type in ("system", "human", "meta"):
        pass  # silently ignore


# ---------------------------------------------------------------------------
# agentmd chat
# ---------------------------------------------------------------------------


@app.command()
def chat(
    agent: Annotated[Optional[str], typer.Argument()] = None,
    workspace: Annotated[Optional[str], typer.Option("--workspace", "-w")] = None,
):
    """Start an interactive chat session with an agent by canonical id."""
    from rich.console import Console
    from agent_md.cli.spawn import ensure_backend

    console = Console()

    ws = Path(workspace) if workspace else None
    agent = _pick_or_resolve_agent(agent, ws)
    local = _lookup_agent(agent, ws)
    agent_label = format_agent_label(agent, local.name if local else None)

    try:
        client = ensure_backend(workspace=ws)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    resp = client.get(_agent_path(agent))
    if resp.status_code == 404:
        console.print(f"[red]Agent '{agent_label}' not found.[/red]")
        raise typer.Exit(1)
    agent_info = resp.json()
    model_info = f"{agent_info.get('model_provider', '')}/{agent_info.get('model_name', '')}"
    # One UUID for this process: every turn reuses it so the server seeds history
    # from this conversation only. Closing and reopening chat starts a new session.
    session_id = str(uuid.uuid4())
    console.print(f"[bold]Chat with {agent_label}[/bold] [dim]({model_info})[/dim]")
    console.print("[dim]Type /exit to end the session[/dim]\n")

    turns = 0
    total_tokens = 0
    total_cost = 0.0
    total_duration_ms = 0

    try:
        while True:
            try:
                user_input = console.input("[bold green]> [/bold green]")
            except EOFError:
                break

            if user_input.strip().lower() in ("/exit", "/quit"):
                break
            if not user_input.strip():
                continue

            resp = client.post(
                _agent_path(agent, "/run"),
                json={"message": user_input, "session_id": session_id},
            )
            if resp.status_code != 200:
                console.print(f"[red]Error: {resp.text}[/red]")
                break

            execution_id = resp.json()["execution_id"]
            turns += 1

            answered: set = set()
            seen: set = set()
            turn_stats: dict = {}
            try:
                while True:
                    res = _stream_chat_turn(client, execution_id, console, answered, seen)
                    if res and res.get("interrupt"):
                        data = res["interrupt"]
                        rid = data.get("request_id")
                        if rid in answered:
                            break
                        _prompt_and_respond(client, execution_id, console, data)
                        answered.add(rid)
                        continue
                    if res and res.get("waiting"):
                        pend = client.get(f"/executions/{execution_id}/pending")
                        if pend.status_code == 200 and pend.json().get("request_id") not in answered:
                            p = pend.json()
                            _prompt_and_respond(client, execution_id, console, p)
                            answered.add(p.get("request_id"))
                            continue
                        break
                    turn_stats = res or {}
                    break
                total_tokens += turn_stats.get("total_tokens") or 0
                total_cost += turn_stats.get("cost_usd") or 0
                total_duration_ms += turn_stats.get("duration_ms") or 0
            except KeyboardInterrupt:
                console.print("\n[yellow]Cancelling...[/yellow]")
                client.delete(f"/executions/{execution_id}")

            console.print()
    except KeyboardInterrupt:
        pass
    finally:
        parts = [f"{turns} turns"]
        if total_duration_ms:
            parts.append(f"{total_duration_ms / 1000:.1f}s")
        if total_tokens:
            parts.append(f"{total_tokens} tokens")
        if total_cost:
            parts.append(f"${total_cost:.4f}")
        console.print(f"\n[dim]{'  |  '.join(parts)}[/dim]")


# ---------------------------------------------------------------------------
# agentmd list
# ---------------------------------------------------------------------------


@app.command(name="list")
def list_agents(
    workspace: Path = typer.Option(None, "--workspace", "-w", help="Override workspace directory"),
):
    """List all agents in the workspace."""
    from agent_md.workspace.services import _runtime

    async def _list_with_last_runs():
        async with _runtime(workspace) as rt:
            agents = rt.registry.all()
            last_by_id = await rt.db.get_last_executions([a.id for a in agents])
            last_runs = {aid: ex.started_at for aid, ex in last_by_id.items()}
            return agents, last_runs

    agents, last_runs = asyncio.run(_list_with_last_runs())

    if not agents:
        print_warning("No agents found in workspace.")
        console.print("  [dim]Create an agent .md file in agents/ directory.[/dim]")
        return

    console.print()

    table = make_table(
        ("", {}),
        ("Id", {"style": "cyan"}),
        ("Display Name", {}),
        ("Trigger", {}),
        ("Last Run", {"style": "dim"}),
        ("Status", {"justify": "center"}),
    )

    for config in agents:
        last_run = format_relative_time(last_runs.get(config.id))
        icon = display_icon(resolve_agent_icon(config.id, config.icon))
        display = config.name if config.name != config.id else "\u2014"
        table.add_row(
            icon,
            config.id,
            display,
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
    agent: str = typer.Argument(None, help="Agent id / filename stem (required unless -e/-f)"),
    last: int = typer.Option(10, "--last", "-n", help="Number of recent executions"),
    execution: int = typer.Option(None, "--execution", "-e", help="Show details for execution ID"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output in real-time"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full system prompt in execution detail"),
    workspace: Path = typer.Option(None, "--workspace", "-w", help="Override workspace directory"),
):
    """Show recent execution history for an agent by canonical id."""

    # Follow mode
    if follow:
        resolved = _pick_or_resolve_agent(agent, workspace) if agent else None
        _follow_logs(workspace, agent=resolved)
        return

    # Execution detail mode
    if execution is not None:
        _show_execution_detail(execution, workspace, verbose=verbose)
        return

    # List executions
    if agent is None:
        print_error("Agent id required for execution list.", "Usage: agentmd logs <agent-id>")
        raise typer.Exit(1)

    agent = _pick_or_resolve_agent(agent, workspace)
    local = _lookup_agent(agent, workspace)
    agent_label = format_agent_label(agent, local.name if local else None)

    from agent_md.workspace.services import get_agent_logs

    executions, agent_icon = asyncio.run(get_agent_logs(agent, last, workspace))

    if not executions:
        print_warning(f"No executions found for '{agent_label}'.")
        return

    console.print(f"\n  [bold]Recent executions \u2014 {display_icon(agent_icon)} {agent_label}[/bold]\n")

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


def _show_execution_detail(execution_id: int, workspace: Path | None, verbose: bool = False) -> None:
    """Show detailed messages for a specific execution."""
    from agent_md.workspace.services import get_execution_messages

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
            if verbose:
                console.print(f"  [dim]{ts}  {emoji}  System prompt:[/dim]")
                console.print(f"  [dim]{log.message or ''}[/dim]")
            else:
                chars = len(log.message) if log.message else 0
                console.print(f"  [dim]{ts}  {emoji}  System prompt ({chars:,} chars)[/dim]")
        elif log.event_type == "human":
            console.print(f"  [dim]{ts}  {emoji}  {log.message}[/dim]")
        elif log.event_type == "meta":
            # Payload lives in metadata JSON; message is only the subtype label.
            # Stats are shown always: `logs -e` is the detail view, and each
            # line is a compact one-liner (see format_meta_log_content).
            content = format_meta_log_content(log.metadata, log.message)
            console.print(f"  [dim]{ts}[/dim]  [{style}]{emoji} {content}[/{style}]")
        else:
            content = log.message or ""
            console.print(f"  [dim]{ts}[/dim]  [{style}]{emoji} {content}[/{style}]")

    console.print()


def _follow_logs(workspace: Path | None, agent: str | None = None) -> None:
    """Tail the backend log file in real-time.

    When *agent* is set, only lines that mention that agent name are shown.
    """
    from agent_md.cli.client import BackendClient, get_log_path

    client = BackendClient()
    if not client.health_check():
        print_warning("Backend is not running.")
        console.print("  [dim]Start with: agentmd start[/dim]")
        return

    log_file = get_log_path()
    if not log_file.exists():
        print_warning(f"Log file not found: {log_file}")
        return

    import time

    filter_hint = f" (filter: {agent})" if agent else ""
    console.print(f"  [dim]Following {log_file}{filter_hint} (Ctrl+C to stop)[/dim]\n")
    try:
        with open(log_file, encoding="utf-8", errors="replace") as f:
            # Seek to end
            f.seek(0, 2)
            while True:
                line = f.readline()
                if line:
                    if agent and agent not in line:
                        continue
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
    agent: str = typer.Argument(None, help="Agent id / filename stem (interactive picker if omitted)"),
    workspace: Path = typer.Option(None, "--workspace", "-w", help="Override workspace directory"),
):
    """Validate an agent file without executing it."""
    from agent_md.workspace.services import validate_agent

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
    agent_label = format_agent_label(config.id, config.name)

    console.print()
    console.print(f"  [green]\u2713[/green] [bold]{agent_label}[/bold]")
    console.print()

    # Model + API key
    model_str = f"{config.model.provider} / {config.model.name}" if config.model else "default"
    api_status = "[green]\u2713 API key set[/green]" if result.api_key_set else "[red]\u2717 API key missing[/red]"
    if not result.api_key_set and config.model and config.model.provider not in ("ollama", "local"):
        errors += 1
    print_kv("Model", f"{model_str}         {api_status}")

    # History (session memory)
    if result.history_level != "off":
        from agent_md.config.models import HISTORY_LIMITS

        limit = HISTORY_LIMITS[result.history_level]
        print_kv("History", f"{result.history_level} (last {limit} messages)")
    else:
        print_kv("History", "off [dim](stateless)[/dim]")

    # Trigger
    trigger_str = format_trigger(config)
    trigger_valid = "[green]\u2713 Valid[/green]"
    for w in result.warnings:
        if w.startswith(_UNKNOWN_KEY_PREFIX):
            continue
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

    # Unknown frontmatter keys — a typo like `triger:` is ignored at parse time,
    # so this is the only place it becomes visible before the agent misbehaves.
    unknown_warnings = [w for w in result.warnings if w.startswith(_UNKNOWN_KEY_PREFIX)]
    if unknown_warnings:
        console.print("\n  [bold]Frontmatter[/bold]")
        for w in unknown_warnings:
            print_check(w, "warn")

    # Other warnings (not already surfaced above)
    _surfaced = {"cron", "watch path", "path:"}
    other_warnings = [
        w for w in result.warnings if w not in unknown_warnings and not any(k in w.lower() for k in _surfaced)
    ]
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

    if errors:
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# agentmd pending
# ---------------------------------------------------------------------------


@app.command()
def pending(
    workspace: Annotated[Optional[str], typer.Option("--workspace", "-w")] = None,
):
    """List executions waiting for a HILT response."""
    from rich.console import Console
    from agent_md.cli.spawn import ensure_backend

    console = Console()
    try:
        client = ensure_backend(workspace=Path(workspace) if workspace else None)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    resp = client.get("/executions", params={"status": "waiting", "limit": 100})
    rows = resp.json() if resp.status_code == 200 else []
    if not rows:
        console.print("[dim]No executions waiting for a response.[/dim]")
        return

    # Resolve labels/icons from local registry by canonical id (API still exposes display name only).
    ws = Path(workspace) if workspace else None
    local_by_id = {cfg.id: cfg for cfg in _get_agents_for_picker(ws)}

    console.print()
    table = make_table(
        ("#", {"style": "dim"}),
        ("", {}),
        ("Agent", {"style": "cyan"}),
        ("Question", {}),
    )
    for r in rows:
        pend = client.get(f"/executions/{r['id']}/pending")
        q = pend.json().get("message", "") if pend.status_code == 200 else ""
        agent_id = r["agent_id"]
        cfg = local_by_id.get(agent_id)
        label = format_agent_label(agent_id, cfg.name if cfg else None)
        icon = display_icon(resolve_agent_icon(agent_id, cfg.icon if cfg else None))
        table.add_row(str(r["id"]), icon, label, q[:60])
    console.print(table)
    console.print()


@app.command()
def respond(
    execution_id: Annotated[int, typer.Argument()],
    yes: Annotated[bool, typer.Option("--yes")] = False,
    no: Annotated[bool, typer.Option("--no")] = False,
    reason: Annotated[Optional[str], typer.Option("--reason")] = None,
    text: Annotated[Optional[str], typer.Option("--text")] = None,
    choice: Annotated[Optional[str], typer.Option("--choice")] = None,
    workspace: Annotated[Optional[str], typer.Option("--workspace", "-w")] = None,
):
    """Respond to a waiting execution (interactive, or via flags)."""
    from rich.console import Console
    from agent_md.cli.spawn import ensure_backend

    console = Console()
    try:
        client = ensure_backend(workspace=Path(workspace) if workspace else None)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    pend = client.get(f"/executions/{execution_id}/pending")
    if pend.status_code != 200:
        console.print(f"[red]No pending request for execution {execution_id}.[/red]")
        raise typer.Exit(1)
    payload = pend.json()

    if yes or no:
        response = {"approved": bool(yes), "reason": reason}
    elif text is not None:
        response = {"text": text}
    elif choice is not None:
        response = {"selected": [choice]}
    else:
        _prompt_and_respond(client, execution_id, console, payload)
        console.print("[green]Response sent.[/green]")
        return

    r = client.post(
        f"/executions/{execution_id}/respond", json={"request_id": payload["request_id"], "response": response}
    )
    if r.status_code == 200:
        console.print("[green]Response sent.[/green]")
    else:
        console.print(f"[red]{r.text}[/red]")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# agentmd status
# ---------------------------------------------------------------------------


@app.command()
def status(
    workspace: Annotated[Optional[str], typer.Option("--workspace", "-w")] = None,
):
    """Check the Agentmd backend status."""
    from rich.console import Console
    from rich.table import Table
    from agent_md.cli.client import BackendClient, get_log_path

    console = Console()
    client = BackendClient()

    if not client.health_check():
        console.print("[dim]Backend is not running.[/dim]")
        console.print("  Start with: [bold]agentmd start[/bold]")
        return

    try:
        resp = client.get("/info")
        info = resp.json()

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style="dim")
        table.add_column()

        table.add_row("Status", "[green]running[/green]")
        table.add_row("PID", str(info["pid"]))

        secs = int(info["uptime_seconds"])
        hours, remainder = divmod(secs, 3600)
        minutes, secs = divmod(remainder, 60)
        uptime = f"{hours}h {minutes}m {secs}s" if hours else f"{minutes}m {secs}s"
        table.add_row("Uptime", uptime)
        table.add_row("Version", info["version"])
        table.add_row("Agents", f"{info['agents_enabled']} enabled / {info['agents_loaded']} loaded")
        table.add_row("Scheduler", info["scheduler_status"])
        table.add_row("Active executions", str(info["active_executions"]))
        table.add_row("SSE streams", str(info["active_streams"]))
        table.add_row("Log file", str(get_log_path()))

        console.print(table)
    except Exception as e:
        console.print(f"[red]Error getting status: {e}[/red]")


# ---------------------------------------------------------------------------
# agentmd stop
# ---------------------------------------------------------------------------


@app.command()
def checkpoint(
    stats: Annotated[bool, typer.Option("--stats")] = False,
    purge: Annotated[bool, typer.Option("--purge")] = False,
    agent: Annotated[Optional[str], typer.Option("--agent")] = None,
    force: Annotated[bool, typer.Option("--force")] = False,
    workspace: Annotated[Optional[str], typer.Option("--workspace", "-w")] = None,
):
    """Inspect or purge the LangGraph checkpoint database."""
    import asyncio
    from rich.console import Console
    from agent_md.db.database import Database
    from agent_md.config.settings import settings
    from agent_md.cli.setup import _effective_db_paths
    from agent_md.execution import checkpoint_maint as cm

    console = Console()
    ws = (
        Path(workspace).expanduser().resolve()
        if workspace
        else (Path(settings.workspace).expanduser().resolve() if settings.workspace else Path("./workspace").resolve())
    )
    db_path, _ = _effective_db_paths(settings.db_path, ws)

    async def _go():
        db = Database(db_path)
        await db.connect()
        try:
            if purge:
                removed = await cm.purge_checkpoints(db, db_path, agent=agent, force=force)
                console.print(f"[green]Removed {removed} checkpoint thread(s).[/green]")
            else:
                s = await cm.checkpoint_stats(db, db_path)
                console.print(f"[bold]Checkpoint DB[/bold]: {s['path']}")
                console.print(f"Size: {s['size_bytes'] / 1024:.1f} KiB  |  Threads: {s['threads']}")
                for ag, n in sorted(s["per_agent"].items()):
                    console.print(f"  {ag}: {n}")
        finally:
            await db.close()

    if not stats and not purge:
        stats = True
    asyncio.run(_go())


# Escalation budget for `agentmd stop`. The graceful window has to cover the
# whole orderly path — uvicorn's connection drain (_GRACEFUL_DRAIN_SECONDS)
# plus lifespan shutdown, whose slowest step is the watchdog observer's 5s
# join — or we would SIGTERM a backend that was about to exit cleanly and skip
# its own cleanup. Everything after that is escalation, and each rung is only
# long enough to observe the process go away.
_STOP_GRACE_SECONDS = 15.0
_STOP_SIGTERM_SECONDS = 5.0
_STOP_SIGKILL_SECONDS = 3.0
_POLL_INTERVAL = 0.1


def _pid_alive(pid: int) -> bool:
    """True while a process with *pid* exists.

    Deliberately not imported from ``workspace.bootstrap``: that module pulls in
    the runner, scheduler and parser at import time, and ``stop`` must stay a
    cheap CLI command.
    """
    import os

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    except OSError:
        return False
    return True


def _reap(pid: int) -> None:
    """Reap *pid* if it happens to be our own child.

    An exited child that nobody waits on stays a zombie, and a zombie still
    answers ``kill(pid, 0)`` — so without this, a backend spawned by this same
    process would look immortal all the way past SIGKILL. Normally the backend
    is reparented to init and this is a no-op.
    """
    import os

    try:
        os.waitpid(pid, os.WNOHANG)
    except (ChildProcessError, OSError, AttributeError):
        pass


def _signal_pid(pid: int, sig, console) -> bool:
    """Send *sig* to *pid*. False if the process was already gone."""
    import os

    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        return False
    except OSError as e:
        console.print(f"[red]Could not signal PID {pid}: {e}[/red]")
        raise typer.Exit(1)
    return True


def _wait_for_exit(pid: int, timeout: float) -> bool:
    """Poll until *pid* is gone. True if it exited within *timeout*."""
    import time

    deadline = time.monotonic() + timeout
    while True:
        _reap(pid)
        if not _pid_alive(pid):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(_POLL_INTERVAL)


def _backend_pid(client) -> int | None:
    """The running backend's PID, or None if it cannot be determined.

    ``/info`` is authoritative — it is ``os.getpid()`` reported by the very
    process answering on our socket. The pid file is only a fallback for a
    backend that answers ``/health`` but not ``/info``; it can in principle
    name a recycled PID, which is why it is not the primary source.
    """
    from agent_md.cli.client import get_pid_path

    try:
        resp = client.get("/info")
        if resp.status_code == 200:
            return int(resp.json()["pid"])
    except Exception:
        pass

    try:
        return int(get_pid_path().read_text().strip())
    except (OSError, ValueError):
        return None


@app.command()
def stop(
    workspace: Annotated[Optional[str], typer.Option("--workspace", "-w")] = None,
    timeout: Annotated[
        float,
        typer.Option("--timeout", help="Seconds to wait for a graceful exit before escalating"),
    ] = _STOP_GRACE_SECONDS,
):
    """Stop the Agentmd backend, and confirm the process actually exited."""
    import signal

    from rich.console import Console
    from agent_md.cli.client import BackendClient, get_pid_path

    console = Console()
    client = BackendClient()

    if not client.health_check():
        console.print("[yellow]Backend is not running.[/yellow]")
        return

    # Read the PID before asking it to go: once shutdown starts, the socket is
    # closed and unlinked, and /info stops answering long before the process is
    # actually gone. That gap is what used to make `stop` report success while a
    # second backend was already free to spawn beside the first.
    pid = _backend_pid(client)

    try:
        resp = client.post("/shutdown")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if resp.status_code != 200:
        console.print(f"[red]Shutdown failed: {resp.text}[/red]")
        raise typer.Exit(1)

    if pid is None:
        console.print(
            "[yellow]Shutdown requested, but the backend PID is unknown — "
            "cannot confirm it exited. Check with: agentmd status[/yellow]"
        )
        raise typer.Exit(1)

    def _done(how: str) -> None:
        console.print(f"[green]Backend stopped{how}.[/green]")
        # A stale pid file would otherwise outlive the backend and, after PID
        # reuse, point the fallback above at an unrelated process.
        try:
            get_pid_path().unlink(missing_ok=True)
        except OSError:
            pass

    if _wait_for_exit(pid, timeout):
        _done("")
        return

    console.print(f"[yellow]PID {pid} did not exit within {timeout:.0f}s — sending SIGTERM.[/yellow]")
    if not _signal_pid(pid, signal.SIGTERM, console):
        _done(" (exited before SIGTERM)")
        return
    if _wait_for_exit(pid, _STOP_SIGTERM_SECONDS):
        _done(" (SIGTERM)")
        return

    sigkill = getattr(signal, "SIGKILL", None)
    if sigkill is None:  # Windows: os.kill(SIGTERM) already means TerminateProcess
        console.print(f"[red]Backend PID {pid} survived the shutdown request. Investigate manually.[/red]")
        raise typer.Exit(1)

    console.print(f"[yellow]PID {pid} survived SIGTERM — sending SIGKILL.[/yellow]")
    if not _signal_pid(pid, sigkill, console):
        _done(" (exited before SIGKILL)")
        return
    if _wait_for_exit(pid, _STOP_SIGKILL_SECONDS):
        _done(" (SIGKILL)")
        return

    console.print(f"[red]Backend PID {pid} is still alive after SIGKILL. Investigate manually.[/red]")
    raise typer.Exit(1)
