"""CLI command definitions — presentation layer only."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Optional

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
    make_table,
    print_check,
    print_error,
    print_kv,
    print_success,
    print_warning,
    select_agent,
)
from agent_md.config.models import AgentConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    workspace: Annotated[Optional[str], typer.Option("--workspace", "-w")] = None,
    daemon: Annotated[bool, typer.Option("--daemon", "-d")] = False,
    keep_alive: Annotated[bool, typer.Option("--keep-alive")] = False,
    port: Annotated[Optional[int], typer.Option("--port")] = None,
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    api_key: Annotated[Optional[str], typer.Option("--api-key")] = None,
    internal_backend: Annotated[bool, typer.Option("--internal-backend", hidden=True)] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q")] = False,
):
    """Start the AgentMD backend."""
    from rich.console import Console

    console = Console()
    ws = Path(workspace) if workspace else None

    if daemon and not internal_backend:
        from agent_md.cli.spawn import _spawn_backend
        from agent_md.cli.client import BackendClient, get_log_path

        client = BackendClient()
        if client.health_check():
            console.print("[yellow]Backend is already running.[/yellow]")
            return

        pid = _spawn_backend(ws)
        console.print(f"[green]Backend started[/green] (PID {pid})")
        console.print(f"  Logs: {get_log_path()}")
        return

    if not quiet and not internal_backend:
        console.print("[bold]AgentMD Backend[/bold]")

    asyncio.run(_run_backend(ws, keep_alive, port, host, api_key, quiet or internal_backend))


async def _run_backend(workspace, keep_alive, port, host, api_key, quiet):
    """Run the FastAPI backend with uvicorn."""
    import uvicorn
    from agent_md.api.app import create_app
    from agent_md.cli.client import get_socket_path, get_state_dir

    app = create_app(workspace=workspace, start_scheduler=True)
    app.state.keep_alive = keep_alive

    socket_path = get_socket_path()
    state_dir = get_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)

    if socket_path.exists():
        socket_path.unlink()

    if api_key and port:
        from agent_md.api.auth import ApiKeyMiddleware

        app.add_middleware(ApiKeyMiddleware, api_key=api_key)

    config = uvicorn.Config(app, uds=str(socket_path), log_level="warning" if quiet else "info")
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

    asyncio.create_task(_set_socket_perms())
    asyncio.create_task(_watch_shutdown())

    if port:
        tcp_config = uvicorn.Config(app, host=host, port=port, log_level="warning" if quiet else "info")
        tcp_server = uvicorn.Server(tcp_config)

        async def _watch_shutdown_tcp():
            while not hasattr(app.state, "shutdown_event"):
                await asyncio.sleep(0.1)
            await app.state.shutdown_event.wait()
            tcp_server.should_exit = True

        asyncio.create_task(_watch_shutdown_tcp())
        await asyncio.gather(server.serve(), tcp_server.serve())
    else:
        await server.serve()


# ---------------------------------------------------------------------------
# agentmd run
# ---------------------------------------------------------------------------


@app.command(context_settings={"allow_extra_args": True})
def run(
    ctx: typer.Context,
    agent: Annotated[Optional[str], typer.Argument()] = None,
    workspace: Annotated[Optional[str], typer.Option("--workspace", "-w")] = None,
    quiet: Annotated[bool, typer.Option("--quiet", "-q")] = False,
):
    """Execute a single agent."""
    from rich.console import Console
    from agent_md.cli.spawn import ensure_backend

    console = Console()

    if not agent:
        ws = Path(workspace) if workspace else None
        agent = _pick_or_resolve_agent(None, ws)
        if not agent:
            return

    try:
        client = ensure_backend(workspace=Path(workspace) if workspace else None)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    arguments = ctx.args
    body = {"args": arguments} if arguments else {}
    resp = client.post(f"/agents/{agent}/run", json=body)
    if resp.status_code == 404:
        console.print(f"[red]Agent '{agent}' not found.[/red]")
        raise typer.Exit(1)
    if resp.status_code != 200:
        console.print(f"[red]Error: {resp.text}[/red]")
        raise typer.Exit(1)

    execution_id = resp.json()["execution_id"]
    if not quiet:
        console.print(f"[dim]Execution {execution_id} started[/dim]")

    try:
        _stream_execution(client, execution_id, console, quiet)
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelling...[/yellow]")
        client.delete(f"/executions/{execution_id}")


# ---------------------------------------------------------------------------
# SSE streaming helpers
# ---------------------------------------------------------------------------


def _stream_execution(client, execution_id: int, console, quiet: bool):
    """Stream SSE events from an execution and print them."""
    import json

    with client.stream_sse(f"/executions/{execution_id}/stream") as response:
        event_type = None
        data_buffer = ""
        got_final_answer = False

        for line in response.iter_lines():
            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                data_buffer = line[5:].strip()
            elif line == "" and data_buffer:
                try:
                    data = json.loads(data_buffer)
                except json.JSONDecodeError:
                    data = {"raw": data_buffer}

                if event_type == "complete":
                    if not quiet:
                        status = data.get("status", "unknown")
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
                    break
                elif event_type == "final_answer":
                    got_final_answer = True
                    if not quiet:
                        _print_event(console, event_type, data)
                elif not quiet:
                    _print_event(console, event_type, data)

                data_buffer = ""
                event_type = None


def _stream_chat_turn(client, execution_id: int, console) -> dict:
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

        for line in response.iter_lines():
            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                data_buffer = line[5:].strip()
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
                elif event_type == "final_answer":
                    content = str(data.get("content", data.get("message", "")))
                    if content:
                        console.print(content)
                    got_final = True
                elif event_type == "tool_call":
                    tools = data.get("tools", [])
                    if tools:
                        names = ", ".join(t.get("name", "?") for t in tools)
                        console.print(f"  [dim]{names}...[/dim]")
                    else:
                        msg = str(data.get("content", data.get("message", "")))[:60]
                        if msg:
                            console.print(f"  [dim]{msg}...[/dim]")
                elif event_type == "ai":
                    # Buffer AI content — only show if no final_answer follows
                    last_ai_content = str(data.get("content", data.get("message", "")))
                # tool_result, system, human, meta — silent in chat mode

                data_buffer = ""
                event_type = None

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
    elif event_type in ("tool_result", "tool_response"):
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
    """Start an interactive chat session with an agent."""
    from rich.console import Console
    from agent_md.cli.spawn import ensure_backend

    console = Console()

    if not agent:
        ws = Path(workspace) if workspace else None
        agent = _pick_or_resolve_agent(None, ws)
        if not agent:
            return

    try:
        client = ensure_backend(workspace=Path(workspace) if workspace else None)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    resp = client.get(f"/agents/{agent}")
    if resp.status_code == 404:
        console.print(f"[red]Agent '{agent}' not found.[/red]")
        raise typer.Exit(1)
    agent_info = resp.json()
    model_info = f"{agent_info.get('model_provider', '')}/{agent_info.get('model_name', '')}"
    console.print(f"[bold]Chat with {agent}[/bold] [dim]({model_info})[/dim]")
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

            resp = client.post(f"/agents/{agent}/run", json={"message": user_input})
            if resp.status_code != 200:
                console.print(f"[red]Error: {resp.text}[/red]")
                break

            execution_id = resp.json()["execution_id"]
            turns += 1

            try:
                turn_stats = _stream_chat_turn(client, execution_id, console)
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

    from agent_md.workspace.services import get_agent_logs

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
    """Tail the backend log file in real-time."""
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
        from agent_md.config.models import HISTORY_LIMITS

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
    workspace: Annotated[Optional[str], typer.Option("--workspace", "-w")] = None,
):
    """Check the AgentMD backend status."""
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
def stop(
    workspace: Annotated[Optional[str], typer.Option("--workspace", "-w")] = None,
):
    """Stop the AgentMD backend."""
    from rich.console import Console
    from agent_md.cli.client import BackendClient

    console = Console()
    client = BackendClient()

    if not client.health_check():
        console.print("[yellow]Backend is not running.[/yellow]")
        return

    try:
        resp = client.post("/shutdown")
        if resp.status_code == 200:
            console.print("[green]Backend is shutting down.[/green]")
        else:
            console.print(f"[red]Shutdown failed: {resp.text}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
