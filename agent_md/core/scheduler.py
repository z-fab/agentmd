import asyncio
import logging
import re
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from agent_md.core.parser import parse_agent_file
from agent_md.core.registry import AgentConfig, AgentRegistry
from agent_md.core.runner import AgentRunner

logger = logging.getLogger(__name__)


def parse_interval(interval_str: str) -> dict:
    """Convert '30s', '5m', '2h', '1d' to IntervalTrigger kwargs."""
    match = re.match(r"^(\d+)([smhd])$", interval_str)
    if not match:
        raise ValueError(f"Invalid interval format: '{interval_str}'")
    value = int(match.group(1))
    unit = match.group(2)
    mapping = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
    return {mapping[unit]: value}


class AgentScheduler:
    """Manages APScheduler jobs and Watchdog file monitoring."""

    def __init__(self, registry: AgentRegistry, runner: AgentRunner, on_event=None, on_complete=None):
        self.registry = registry
        self.runner = runner
        self.on_event = on_event
        self.on_complete = on_complete
        self.scheduler = AsyncIOScheduler()
        self.observer = Observer()
        self._loop: asyncio.AbstractEventLoop | None = None

    def schedule_agent(self, config: AgentConfig) -> None:
        """Schedule an agent based on its trigger config."""
        job_id = f"agent_{config.name}"

        if not config.enabled:
            logger.info(f"Agent '{config.name}' is disabled, skipping schedule")
            return

        if config.trigger.type == "manual":
            logger.info(f"Agent '{config.name}' is manual-only, skipping schedule")
            return

        if config.trigger.type == "cron":
            trigger = CronTrigger.from_crontab(config.trigger.schedule)
            trigger_desc = f"cron({config.trigger.schedule})"
        elif config.trigger.type == "interval":
            kwargs = parse_interval(config.trigger.interval)
            trigger = IntervalTrigger(**kwargs)
            trigger_desc = f"interval({config.trigger.interval})"
        else:
            logger.warning(f"Unknown trigger type: {config.trigger.type}")
            return

        self.scheduler.add_job(
            self._execute_agent,
            trigger=trigger,
            id=job_id,
            args=[config.name, config.trigger.type],
            replace_existing=True,
            misfire_grace_time=60,
        )
        logger.info(f"Scheduled agent '{config.name}': {trigger_desc}")

    def unschedule_agent(self, name: str) -> None:
        """Remove an agent's scheduled job."""
        job_id = f"agent_{name}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info(f"Unscheduled agent: {name}")

    async def _execute_agent(self, agent_id: str, trigger_type: str) -> None:
        """Callback for scheduled execution."""
        config = self.registry.get(agent_id)
        if config and config.enabled:
            result = await self.runner.run(config, trigger_type, on_event=self.on_event)
            if self.on_complete:
                self.on_complete(config.name, result)
        elif config and not config.enabled:
            logger.debug(f"Skipping disabled agent: {agent_id}")

    def start_watcher(self, workspace: Path) -> None:
        """Start the Watchdog observer for hot-reload."""
        handler = _AgentFileHandler(self.registry, self, self._loop)
        self.observer.schedule(handler, str(workspace), recursive=False)
        self.observer.start()
        logger.info(f"Watching workspace for changes: {workspace}")

    def start(self) -> None:
        """Start the scheduler."""
        self._loop = asyncio.get_running_loop()
        self.scheduler.start()
        logger.info("Scheduler started")

    def stop(self) -> None:
        """Stop scheduler and watcher gracefully."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join(timeout=5)
            logger.info("File watcher stopped")


class _AgentFileHandler(FileSystemEventHandler):
    """Watchdog handler that reloads agents when .md files change."""

    def __init__(
        self,
        registry: AgentRegistry,
        scheduler: AgentScheduler,
        loop: asyncio.AbstractEventLoop | None,
    ):
        self.registry = registry
        self.scheduler = scheduler
        self._loop = loop

    def _is_agent_file(self, event) -> bool:
        return event.src_path.endswith(".md") and not event.is_directory

    def on_modified(self, event):
        if self._is_agent_file(event):
            self._reload(Path(event.src_path))

    def on_created(self, event):
        if self._is_agent_file(event):
            self._reload(Path(event.src_path))

    def on_deleted(self, event):
        if event.src_path.endswith(".md") and not event.is_directory:
            name = Path(event.src_path).stem
            self.registry.remove(name)
            self.scheduler.unschedule_agent(name)
            logger.info(f"Agent file deleted: {name}")

    def _reload(self, path: Path) -> None:
        try:
            config = parse_agent_file(path)
            old = self.registry.get(config.name)

            if old and old.config_hash == config.config_hash:
                # Only the body (system prompt) changed
                self.registry.register(config)
                logger.info(f"Hot-reloaded prompt for: {config.name}")
            else:
                # Frontmatter changed — reschedule
                self.registry.register(config)
                self.scheduler.schedule_agent(config)
                logger.info(f"Hot-reloaded agent (full): {config.name}")

        except Exception as e:
            logger.warning(f"Failed to reload {path.name}: {e}")
