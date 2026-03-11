"""High-level service functions — pure business logic, no CLI/TUI concerns."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_md.core.bootstrap import bootstrap
from agent_md.core.models import AgentConfig
from agent_md.core.parser import parse_agent_file


async def list_agents(
    workspace: Path,
    agents_dir: Path | None = None,
    output_dir: Path | None = None,
    db_path: Path | None = None,
    mcp_config: Path | None = None,
) -> list[AgentConfig]:
    """Return every agent found in *workspace*."""
    runtime = await bootstrap(workspace, agents_dir=agents_dir, output_dir=output_dir, db_path=db_path, mcp_config=mcp_config)
    agents = runtime.registry.all()
    await runtime.aclose()
    return agents


async def run_agent(
    agent_name: str,
    workspace: Path,
    agents_dir: Path | None = None,
    output_dir: Path | None = None,
    db_path: Path | None = None,
    mcp_config: Path | None = None,
    on_event=None,
) -> tuple[AgentConfig, dict]:
    """Execute a single agent by name and return ``(config, result)``."""
    runtime = await bootstrap(workspace, agents_dir=agents_dir, output_dir=output_dir, db_path=db_path, mcp_config=mcp_config)

    config = runtime.registry.get(agent_name)
    if not config:
        config = runtime.registry.get(agent_name.replace(".md", ""))
    if not config:
        await runtime.aclose()
        raise AgentNotFoundError(agent_name)

    result = await runtime.runner.run(config, trigger_type="manual", on_event=on_event)

    await runtime.aclose()
    return config, result


@dataclass
class ValidationResult:
    """Result of validating an agent file."""

    config: AgentConfig
    builtin_tools: list[str]
    custom_tools_found: list[str]
    custom_tools_missing: list[str]


def validate_agent(file: Path, tools_dir: Path | None = None) -> ValidationResult:
    """Parse and validate an agent file, returning structured results."""
    from agent_md.tools.registry import list_builtin_tools

    config = parse_agent_file(file)
    builtins = list_builtin_tools()

    # Check custom tools exist on disk
    found = []
    missing = []
    if config.custom_tools and tools_dir:
        for name in config.custom_tools:
            tool_file = tools_dir / f"{name}.py"
            if tool_file.exists():
                found.append(name)
            else:
                missing.append(name)
    elif config.custom_tools:
        missing = list(config.custom_tools)

    return ValidationResult(
        config=config,
        builtin_tools=builtins,
        custom_tools_found=found,
        custom_tools_missing=missing,
    )


async def get_agent_logs(
    agent_name: str,
    n: int,
    workspace: Path,
    agents_dir: Path | None = None,
    output_dir: Path | None = None,
    db_path: Path | None = None,
    mcp_config: Path | None = None,
) -> list:
    """Return the *n* most recent executions for *agent_name*."""
    runtime = await bootstrap(workspace, agents_dir=agents_dir, output_dir=output_dir, db_path=db_path, mcp_config=mcp_config)
    executions = await runtime.db.get_executions(agent_name, limit=n)
    await runtime.aclose()
    return executions


async def get_execution_messages(
    execution_id: int,
    workspace: Path,
    agents_dir: Path | None = None,
    output_dir: Path | None = None,
    db_path: Path | None = None,
    mcp_config: Path | None = None,
) -> list:
    """Return the step-by-step log messages for a specific execution."""
    runtime = await bootstrap(workspace, agents_dir=agents_dir, output_dir=output_dir, db_path=db_path, mcp_config=mcp_config)
    logs = await runtime.db.get_logs(execution_id)
    await runtime.aclose()
    return logs


class AgentNotFoundError(Exception):
    """Raised when an agent cannot be found in the registry."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Agent '{name}' not found in workspace")
