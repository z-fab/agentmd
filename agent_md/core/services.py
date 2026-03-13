"""High-level service functions — pure business logic, no CLI/TUI concerns."""

from __future__ import annotations

import importlib.util
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

from agent_md.core.bootstrap import bootstrap
from agent_md.core.models import AgentConfig
from agent_md.core.parser import parse_agent_file


@asynccontextmanager
async def _runtime(workspace: Path | None = None, **kwargs):
    """Async context manager that bootstraps and auto-closes a Runtime."""
    rt = await bootstrap(workspace, **kwargs)
    try:
        yield rt
    finally:
        await rt.aclose()


async def list_agents(workspace: Path | None = None) -> list[AgentConfig]:
    """Return every agent found in *workspace*."""
    async with _runtime(workspace) as rt:
        return rt.registry.all()


async def run_agent(
    agent_name: str,
    workspace: Path | None = None,
    on_event=None,
) -> tuple[AgentConfig, dict]:
    """Execute a single agent by name and return ``(config, result)``."""
    async with _runtime(workspace) as rt:
        config = rt.registry.get(agent_name) or rt.registry.get(agent_name.replace(".md", ""))
        if not config:
            raise AgentNotFoundError(agent_name)

        result = await rt.runner.run(config, trigger_type="manual", on_event=on_event)
        return config, result


@dataclass
class ValidationResult:
    """Result of validating an agent file."""

    config: AgentConfig
    builtin_tools: list[str] = field(default_factory=list)
    custom_tools_found: list[str] = field(default_factory=list)
    custom_tools_missing: list[str] = field(default_factory=list)
    # Deep validation fields
    read_paths_valid: list[str] = field(default_factory=list)
    read_paths_missing: list[str] = field(default_factory=list)
    write_paths_valid: list[str] = field(default_factory=list)
    write_paths_missing: list[str] = field(default_factory=list)
    mcp_servers_configured: list[str] = field(default_factory=list)
    mcp_servers_missing: list[str] = field(default_factory=list)
    custom_tools_loadable: list[str] = field(default_factory=list)
    custom_tools_load_errors: dict[str, str] = field(default_factory=dict)
    api_key_set: bool = False
    warnings: list[str] = field(default_factory=list)


# Map provider to environment variable name
_PROVIDER_ENV_VARS = {
    "google": "GOOGLE_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


def _resolve_relative(path: str, workspace: Path) -> Path:
    """Resolve a potentially relative path against a workspace root."""
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = workspace / p
    return p.resolve()


def _resolve_ws_and_agents_dir(workspace: Path | None) -> tuple[Path, Path]:
    """Resolve workspace and agents_dir from settings, deduplicating the pattern."""
    from agent_md.core.settings import settings

    ws = workspace
    if ws is None:
        ws = Path(settings.workspace).expanduser() if settings.workspace else Path("./workspace")
    ws = ws.resolve()
    agents_dir = _resolve_relative(settings.agents_dir, ws)
    return ws, agents_dir


def validate_agent(agent_name_or_file: str | Path, workspace: Path | None = None) -> ValidationResult:
    """Parse and validate an agent file, returning structured results.

    Accepts an agent name (resolved via workspace) or a direct file path.
    """
    from agent_md.core.settings import settings
    from agent_md.tools.registry import list_builtin_tools

    ws, agents_dir = _resolve_ws_and_agents_dir(workspace)

    # Resolve to file path
    file_path = Path(agent_name_or_file)
    if not file_path.suffix and "/" not in str(agent_name_or_file):
        file_path = agents_dir / f"{agent_name_or_file}.md"
    elif str(agent_name_or_file).endswith(".md") and "/" not in str(agent_name_or_file):
        file_path = agents_dir / str(agent_name_or_file)

    config = parse_agent_file(file_path)
    builtins = list_builtin_tools()
    tools_dir = agents_dir / "tools"

    # Check custom tools exist on disk + loadable
    found = []
    missing = []
    loadable = []
    load_errors: dict[str, str] = {}
    if config.custom_tools:
        for name in config.custom_tools:
            tool_file = tools_dir / f"{name}.py"
            if tool_file.exists():
                found.append(name)
                # Try to load the module
                try:
                    spec = importlib.util.spec_from_file_location(name, tool_file)
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(mod)
                        loadable.append(name)
                except Exception as e:
                    load_errors[name] = str(e)
            else:
                missing.append(name)

    # Check read paths
    read_valid = []
    read_missing = []
    for rp in config.read:
        p = _resolve_relative(rp, ws)
        if p.exists():
            read_valid.append(rp)
        else:
            read_missing.append(rp)

    # Check write paths
    write_valid = []
    write_missing = []
    warnings = []
    for wp in config.write:
        p = _resolve_relative(wp, ws)
        if p.exists():
            write_valid.append(wp)
        else:
            write_missing.append(wp)
            warnings.append(f"write: {wp} (will be created)")

    # Check MCP servers
    mcp_configured = []
    mcp_missing = []
    if config.mcp:
        mcp_config_path = _resolve_relative(settings.mcp_config, ws)
        try:
            import json

            servers = json.loads(mcp_config_path.read_text()) if mcp_config_path.exists() else {}
        except Exception:
            servers = {}
        for server_name in config.mcp:
            if server_name in servers:
                mcp_configured.append(server_name)
            else:
                mcp_missing.append(server_name)

    # Check API key
    api_key_set = False
    if config.model:
        env_var = _PROVIDER_ENV_VARS.get(config.model.provider)
        if env_var:
            api_key_set = bool(os.environ.get(env_var))
        elif config.model.provider in ("ollama", "local"):
            api_key_set = True  # No key needed

    # Validate trigger
    if config.trigger.type == "schedule" and config.trigger.cron:
        try:
            from apscheduler.triggers.cron import CronTrigger

            CronTrigger.from_crontab(config.trigger.cron)
        except Exception as e:
            warnings.append(f"Invalid cron expression: {e}")
    if config.trigger.type == "watch":
        for wp in config.trigger.paths:
            p = _resolve_relative(wp, ws)
            if not p.exists():
                warnings.append(f"Watch path does not exist: {wp}")

    return ValidationResult(
        config=config,
        builtin_tools=builtins,
        custom_tools_found=found,
        custom_tools_missing=missing,
        read_paths_valid=read_valid,
        read_paths_missing=read_missing,
        write_paths_valid=write_valid,
        write_paths_missing=write_missing,
        mcp_servers_configured=mcp_configured,
        mcp_servers_missing=mcp_missing,
        custom_tools_loadable=loadable,
        custom_tools_load_errors=load_errors,
        api_key_set=api_key_set,
        warnings=warnings,
    )


async def get_agent_logs(
    agent_name: str,
    n: int,
    workspace: Path | None = None,
) -> list:
    """Return the *n* most recent executions for *agent_name*."""
    async with _runtime(workspace) as rt:
        return await rt.db.get_executions(agent_name, limit=n)


async def get_execution_messages(
    execution_id: int,
    workspace: Path | None = None,
) -> list:
    """Return the step-by-step log messages for a specific execution."""
    async with _runtime(workspace) as rt:
        return await rt.db.get_logs(execution_id)


async def get_last_execution(
    agent_name: str,
    workspace: Path | None = None,
) -> object | None:
    """Return the most recent execution for an agent, or None."""
    async with _runtime(workspace) as rt:
        return await rt.db.get_last_execution(agent_name)


class AgentNotFoundError(Exception):
    """Raised when an agent cannot be found in the registry."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Agent '{name}' not found in workspace")


# ---------------------------------------------------------------------------
# Interactive chat session
# ---------------------------------------------------------------------------


@dataclass
class ChatSession:
    """Holds state for a multi-turn interactive chat session."""

    config: AgentConfig
    execution_id: int
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    turns: int = 0

    # Internal — set by chat_session() context manager
    _messages: list = field(default_factory=list)
    _graph: object = None
    _runner: object = None
    _ex_logger: object = None
    _timeout: float = 300

    async def send(self, user_input: str) -> str:
        """Send a user message and return the agent's text response."""
        from langchain_core.messages import HumanMessage

        from agent_md.core.execution_logger import _extract_text
        from agent_md.core.runner import _is_final_ai_message

        human_msg = HumanMessage(content=user_input)
        self._messages.append(human_msg)
        await self._ex_logger.log_message(human_msg)

        new_msgs, in_tok, out_tok = await self._runner.chat_turn(
            self._graph, self._messages, self._ex_logger, self._timeout,
        )

        self._messages.extend(new_msgs)
        self.total_input_tokens += in_tok
        self.total_output_tokens += out_tok
        self.turns += 1

        # Extract text from the last AI message without tool calls
        for msg in reversed(new_msgs):
            if _is_final_ai_message(msg):
                raw = getattr(msg, "content", None)
                return _extract_text(raw) if raw is not None else ""
        return ""


@asynccontextmanager
async def chat_session(
    agent_name: str,
    workspace: Path | None = None,
    on_event=None,
):
    """Async context manager that bootstraps a multi-turn chat session.

    Creates one execution record (trigger="chat") for the entire session.
    Yields a ChatSession; on exit finalizes the execution with accumulated stats.
    """
    import time

    from agent_md.core.execution_logger import ExecutionLogger
    from agent_md.graph.builder import build_system_message

    async with _runtime(workspace) as rt:
        config = rt.registry.get(agent_name) or rt.registry.get(agent_name.replace(".md", ""))
        if not config:
            raise AgentNotFoundError(agent_name)

        # One execution record for the whole chat session
        execution_id = await rt.db.create_execution(
            agent_id=config.name,
            trigger="chat",
            status="running",
        )

        ex_logger = ExecutionLogger(rt.db, execution_id, config.name, on_event=on_event)
        graph = await rt.runner.prepare_agent(config)

        # Build system message and seed conversation
        system_msg = build_system_message(config.system_prompt, config, rt.path_context)
        messages = [system_msg]
        await ex_logger.log_message(system_msg)

        session = ChatSession(
            config=config,
            execution_id=execution_id,
            _messages=messages,
            _graph=graph,
            _runner=rt.runner,
            _ex_logger=ex_logger,
            _timeout=config.settings.timeout,
        )

        start_time = time.monotonic()
        try:
            yield session
        finally:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            await rt.runner._finish_execution(
                execution_id,
                "success",
                duration_ms,
                session.total_input_tokens,
                session.total_output_tokens,
                output_data=f"Chat session: {session.turns} turns",
            )
