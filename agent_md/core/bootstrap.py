from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from agent_md.core.parser import parse_agent_file
from agent_md.core.path_context import PathContext
from agent_md.core.registry import AgentRegistry
from agent_md.core.runner import AgentRunner
from agent_md.core.scheduler import AgentScheduler
from agent_md.core.settings import settings
from agent_md.db.database import Database
from agent_md.mcp.config import load_mcp_config
from agent_md.mcp.manager import MCPManager

logger = logging.getLogger(__name__)


@dataclass
class Runtime:
    """Holds all runtime components for the application."""

    registry: AgentRegistry
    runner: AgentRunner
    scheduler: AgentScheduler | None
    db: Database
    workspace: Path
    mcp_manager: MCPManager
    path_context: PathContext

    def stop(self):
        """Graceful shutdown of synchronous components."""
        if self.scheduler:
            self.scheduler.stop()

    async def aclose(self):
        """Async cleanup — call instead of stop() + db.close()."""
        self.stop()
        await self.runner.aclose()
        await self.db.close()


def _resolve_path(value: str, workspace: Path) -> Path:
    """Resolve a path: absolute paths kept as-is, relative resolved against workspace."""
    p = Path(value).expanduser()
    if p.is_absolute():
        return p.resolve()
    return (workspace / p).resolve()


async def bootstrap(
    workspace: Path | None = None,
    agents_dir: Path | None = None,
    output_dir: Path | None = None,
    db_path: Path | None = None,
    mcp_config: Path | None = None,
    start_scheduler: bool = False,
    on_event=None,
    on_complete=None,
    on_start=None,
) -> Runtime:
    """Initialize all components and load agents from workspace.

    Args:
        workspace: Root workspace directory.
        agents_dir: Directory containing .md agent files. Defaults to {workspace}/agents.
        output_dir: Default output directory for agents. Defaults to {workspace}/output.
        db_path: Path to SQLite database. Defaults to {workspace}/data/agentmd.db.
        mcp_config: Path to MCP servers JSON config. Defaults to {agents_dir}/mcp-servers.json.
        start_scheduler: Whether to start the scheduler and file watcher.
        on_event: Optional callback for real-time UI updates.
        on_complete: Optional callback when execution completes.

    Returns:
        A fully initialized Runtime instance.
    """
    logger.debug(f"Settings loaded — log_level={settings.log_level}")

    # Resolve workspace: CLI > config.yaml > default
    if workspace is None:
        workspace = Path(settings.workspace).expanduser() if settings.workspace else Path("./workspace")
    workspace = workspace.resolve()

    # Resolve sub-paths: CLI arg > config.yaml value (relative to workspace)
    if agents_dir is None:
        agents_dir = _resolve_path(settings.agents_dir, workspace)
    agents_dir = agents_dir.resolve()

    if output_dir is None:
        output_dir = _resolve_path(settings.output_dir, workspace)
    output_dir = output_dir.resolve()

    if db_path is None:
        db_path = _resolve_path(settings.db_path, workspace)
    db_path = db_path.resolve()

    if mcp_config is None:
        mcp_config = _resolve_path(settings.mcp_config, workspace)
    mcp_config = mcp_config.resolve()

    tools_dir = (agents_dir / "tools").resolve()
    skills_dir = (agents_dir / "skills").resolve()

    path_context = PathContext(
        workspace_root=workspace,
        agents_dir=agents_dir,
        output_dir=output_dir,
        db_path=db_path,
        mcp_config=mcp_config,
        tools_dir=tools_dir,
        skills_dir=skills_dir,
    )

    # Ensure directories exist
    for d in (workspace, agents_dir, output_dir, db_path.parent, skills_dir):
        if not d.exists():
            d.mkdir(parents=True)
            logger.info(f"Created directory: {d}")

    # Initialize database
    db = Database(db_path)
    await db.connect()

    # Load MCP server configuration
    mcp_servers = load_mcp_config(mcp_config)
    mcp_manager = MCPManager(mcp_servers)

    # Create core components
    registry = AgentRegistry()
    runner = AgentRunner(db, mcp_manager, path_context, db_path=str(db_path))
    scheduler = None

    # Scan agents directory for .md files
    md_files = sorted(f for f in agents_dir.glob("*.md") if not f.name.endswith(".memory.md"))
    loaded = 0
    errors = 0

    for md_file in md_files:
        try:
            config = parse_agent_file(md_file)
            registry.register(config)
            loaded += 1
        except Exception as e:
            logger.error(f"Failed to load {md_file.name}: {e}")
            errors += 1

    logger.info(f"Loaded {loaded} agents ({errors} errors) from {agents_dir}")

    # Scan skills directory for SKILL.md files
    if skills_dir.exists():
        from agent_md.skills.parser import parse_skill_metadata

        skill_dirs = sorted(d for d in skills_dir.iterdir() if d.is_dir())
        skills_loaded = 0
        skills_errors = 0

        for skill_dir in skill_dirs:
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            try:
                parse_skill_metadata(skill_file)
                skills_loaded += 1
            except Exception as e:
                logger.error(f"Failed to load skill {skill_dir.name}: {e}")
                skills_errors += 1

        if skills_loaded or skills_errors:
            logger.info(f"Discovered {skills_loaded} skills ({skills_errors} errors) from {skills_dir}")

    # Schedule enabled agents (only when explicitly requested)
    if start_scheduler:
        scheduler = AgentScheduler(registry, runner, path_context, on_event=on_event, on_complete=on_complete, on_start=on_start)
        for config in registry.enabled():
            scheduler.schedule_agent(config)

        scheduler.start(agents_dir)

    return Runtime(
        registry=registry,
        runner=runner,
        scheduler=scheduler,
        db=db,
        workspace=workspace,
        mcp_manager=mcp_manager,
        path_context=path_context,
    )
