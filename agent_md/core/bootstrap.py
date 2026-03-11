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
        await self.db.close()


async def bootstrap(
    workspace: Path | None = None,
    agents_dir: Path | None = None,
    output_dir: Path | None = None,
    db_path: Path | None = None,
    mcp_config: Path | None = None,
    start_scheduler: bool = False,
    on_event=None,
    on_complete=None,
) -> Runtime:
    """Initialize all components and load agents from workspace.

    Args:
        workspace: Root workspace directory.
        agents_dir: Directory containing .md agent files. Defaults to {workspace}/agents.
        output_dir: Default output directory for agents. Defaults to {workspace}/output.
        db_path: Path to SQLite database. Defaults to ./data/agentmd.db.
        mcp_config: Path to MCP servers JSON config. Defaults to {agents_dir}/mcp-servers.json.
        start_scheduler: Whether to start the scheduler and file watcher.
        on_event: Optional callback for real-time UI updates.
        on_complete: Optional callback when execution completes.

    Returns:
        A fully initialized Runtime instance.
    """
    # 1. Settings are loaded automatically by pydantic-settings (see core/settings.py)
    logger.debug(f"Settings loaded — log_level={settings.log_level}")

    # 2. Resolve paths: CLI > env var > convention
    if workspace is None:
        workspace = Path(settings.AGENTMD_WORKSPACE) if settings.AGENTMD_WORKSPACE else Path("./workspace")
    workspace = workspace.resolve()

    if agents_dir is None:
        agents_dir = Path(settings.AGENTMD_AGENTS_DIR) if settings.AGENTMD_AGENTS_DIR else workspace / "agents"
    agents_dir = agents_dir.resolve()

    if output_dir is None:
        output_dir = Path(settings.AGENTMD_OUTPUT_DIR) if settings.AGENTMD_OUTPUT_DIR else workspace / "output"
    output_dir = output_dir.resolve()

    if db_path is None:
        if settings.AGENTMD_DB_PATH:
            db_path = Path(settings.AGENTMD_DB_PATH)
        else:
            db_path = workspace.parent / "data" / "agentmd.db"
            if not (workspace.parent / "data").exists():
                db_path = Path("data") / "agentmd.db"
    db_path = db_path.resolve()

    if mcp_config is None:
        mcp_config = (
            Path(settings.AGENTMD_MCP_CONFIG) if settings.AGENTMD_MCP_CONFIG else agents_dir / "mcp-servers.json"
        )
    mcp_config = mcp_config.resolve()

    tools_dir = (agents_dir / "tools").resolve()

    path_context = PathContext(
        workspace_root=workspace,
        agents_dir=agents_dir,
        output_dir=output_dir,
        db_path=db_path,
        mcp_config=mcp_config,
        tools_dir=tools_dir,
    )

    # 3. Ensure directories exist
    for d in (workspace, agents_dir, output_dir, db_path.parent):
        if not d.exists():
            d.mkdir(parents=True)
            logger.info(f"Created directory: {d}")

    # 4. Initialize database
    db = Database(db_path)
    await db.connect()

    # 5. Load MCP server configuration
    mcp_servers = load_mcp_config(mcp_config)
    mcp_manager = MCPManager(mcp_servers)

    # 6. Create core components
    registry = AgentRegistry()
    runner = AgentRunner(db, mcp_manager, path_context)
    scheduler = None

    # 7. Scan agents directory for .md files
    md_files = sorted(agents_dir.glob("*.md"))
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

    # 8. Schedule enabled agents (only when explicitly requested)
    if start_scheduler:
        scheduler = AgentScheduler(registry, runner, path_context, on_event=on_event, on_complete=on_complete)
        for config in registry.enabled():
            scheduler.schedule_agent(config)

        # 9. Start scheduler, file watcher, and agent watchers
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
