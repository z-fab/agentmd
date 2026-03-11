from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from agent_md.core.parser import parse_agent_file
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

    def stop(self):
        """Graceful shutdown of synchronous components."""
        if self.scheduler:
            self.scheduler.stop()

    async def aclose(self):
        """Async cleanup — call instead of stop() + db.close()."""
        self.stop()
        await self.db.close()


async def bootstrap(workspace: Path, db_path: Path | None = None, start_scheduler: bool = False) -> Runtime:
    """Initialize all components and load agents from workspace.

    Args:
        workspace: Directory containing .md agent files.
        db_path: Path to SQLite database. Defaults to ./data/agent_md.db
        start_scheduler: Whether to start the scheduler and file watcher.
            Set to True only for `agentmd start`. Read-only commands
            (list, logs, run) should leave this as False.

    Returns:
        A fully initialized Runtime instance.
    """
    # 1. Settings are loaded automatically by pydantic-settings (see core/settings.py)
    logger.debug(f"Settings loaded — log_level={settings.log_level}")

    # 2. Initialize database
    if db_path is None:
        db_path = workspace.parent / "data" / "agentmd.db"
        if not (workspace.parent / "data").exists():
            db_path = Path("data") / "agentmd.db"

    db = Database(db_path)
    await db.connect()

    # 3. Load MCP server configuration
    if settings.MCP_CONFIG_PATH:
        mcp_config_path = Path(settings.MCP_CONFIG_PATH)
    else:
        mcp_config_path = workspace / "mcp-servers.json"
    mcp_servers = load_mcp_config(mcp_config_path.resolve())
    mcp_manager = MCPManager(mcp_servers)

    # 4. Create core components
    registry = AgentRegistry()
    runner = AgentRunner(db, mcp_manager)
    scheduler = None

    # 5. Scan workspace for .md files
    workspace = workspace.resolve()
    if not workspace.exists():
        workspace.mkdir(parents=True)
        logger.info(f"Created workspace directory: {workspace}")

    md_files = sorted(workspace.glob("*.md"))
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

    logger.info(f"Loaded {loaded} agents ({errors} errors) from {workspace}")

    # 6. Schedule enabled agents (only when explicitly requested)
    if start_scheduler:
        scheduler = AgentScheduler(registry, runner)
        scheduler.start()
        for config in registry.enabled():
            scheduler.schedule_agent(config)

        # 7. Start file watcher for hot-reload
        scheduler.start_watcher(workspace)

    return Runtime(
        registry=registry,
        runner=runner,
        scheduler=scheduler,
        db=db,
        workspace=workspace,
        mcp_manager=mcp_manager,
    )
