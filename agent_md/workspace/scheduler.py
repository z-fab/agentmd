import asyncio
import logging
import re
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from agent_md.workspace.parser import is_agent_file, parse_agent_file
from agent_md.workspace.registry import AgentConfig, AgentRegistry
from agent_md.execution.runner import AgentRunner

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

    def __init__(
        self, registry: AgentRegistry, runner: AgentRunner, path_context, on_event=None, on_complete=None, on_start=None
    ):
        self.registry = registry
        self.runner = runner
        self.path_context = path_context
        self.on_event = on_event
        self.on_complete = on_complete
        self.on_start = on_start
        self.scheduler = AsyncIOScheduler()
        self.observer = Observer()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._watch_handlers: dict[str, list] = {}  # agent_name -> list of (handler, watch_id)
        self._paused = False

    def schedule_agent(self, config: AgentConfig) -> None:
        """Schedule an agent based on its trigger config."""
        job_id = f"agent_{config.name}"

        if not config.enabled:
            logger.info(f"Agent '{config.name}' is disabled, skipping schedule")
            return

        if config.trigger.type == "manual":
            logger.info(f"Agent '{config.name}' is manual-only, skipping schedule")
            return

        if config.trigger.type == "watch":
            logger.info(f"Agent '{config.name}' is watch-only, skipping APScheduler (handled by watchdog)")
            return

        if config.trigger.type == "schedule":
            if config.trigger.cron:
                trigger = CronTrigger.from_crontab(config.trigger.cron)
                trigger_desc = f"cron({config.trigger.cron})"
            elif config.trigger.every:
                kwargs = parse_interval(config.trigger.every)
                trigger = IntervalTrigger(**kwargs)
                trigger_desc = f"every({config.trigger.every})"
            else:
                logger.warning(f"Schedule trigger for '{config.name}' has neither 'every' nor 'cron'")
                return
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
        """Remove an agent's scheduled job and watch handlers."""
        job_id = f"agent_{name}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info(f"Unscheduled agent: {name}")

        self._remove_watch_handlers(name)

    async def _execute_agent(self, agent_id: str, trigger_type: str, trigger_context: str | None = None) -> None:
        """Callback for scheduled execution."""
        config = self.registry.get(agent_id)
        if config and config.enabled:
            await self.runner.run(
                config,
                trigger_type,
                trigger_context=trigger_context,
                on_event=self.on_event,
                on_start=self.on_start,
                on_complete=self.on_complete,
            )
        elif config and not config.enabled:
            logger.debug(f"Skipping disabled agent: {agent_id}")

    def _add_watch_handler(self, config: AgentConfig) -> None:
        """Register watchdog handlers for a single watch agent."""
        resolved_paths = [self.path_context._resolve_relative(p) for p in config.trigger.paths]
        logger.info(f"Setting up watch for agent '{config.name}': {resolved_paths}")

        handler = _AgentWatchHandler(config.name, resolved_paths, self, self._loop)
        watch_ids = []

        for path in resolved_paths:
            if path.is_dir():
                watch_id = self.observer.schedule(handler, str(path), recursive=True)
            else:
                watch_id = self.observer.schedule(handler, str(path.parent), recursive=False)
            watch_ids.append(watch_id)

        self._watch_handlers[config.name] = watch_ids

    def _remove_watch_handlers(self, name: str) -> None:
        """Unregister watchdog handlers for a watch agent."""
        if name not in self._watch_handlers:
            return

        for watch_id in self._watch_handlers.pop(name):
            try:
                self.observer.unschedule(watch_id)
            except Exception:
                pass  # Already unscheduled
        logger.info(f"Removed watch handlers for: {name}")

    def start(self, agents_dir: Path) -> None:
        """Start scheduler, file watcher, and agent watchers.

        This is the single entry point for starting all background services.
        All watchdog handlers are registered before starting the observer.
        """
        self._loop = asyncio.get_running_loop()

        # 1. APScheduler
        self.scheduler.start()
        logger.info("Scheduler started")

        # 2. Register hot-reload handler for .md files
        reload_handler = _AgentFileHandler(self.registry, self, self._loop)
        self.observer.schedule(reload_handler, str(agents_dir), recursive=False)
        logger.info(f"Watching workspace for changes: {agents_dir}")

        # 3. Register watch handlers for agents with watch triggers
        for config in self.registry.all():
            if config.trigger.type == "watch" and config.enabled:
                self._add_watch_handler(config)

        # 4. Start observer once (all handlers already registered)
        self.observer.start()

    def get_next_run(self, agent_name: str) -> str | None:
        """Return ISO timestamp of next scheduled run for *agent_name*, or None."""
        job = self.scheduler.get_job(agent_name)
        if job and job.next_run_time:
            return job.next_run_time.isoformat()
        return None

    def get_jobs(self) -> list[dict]:
        """Return list of scheduled jobs with next_run times."""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "agent_name": job.id,
                "trigger_type": "schedule",
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            })
        return jobs

    def pause(self) -> None:
        """Pause the scheduler (does not cancel running jobs)."""
        self.scheduler.pause()
        self._paused = True

    def resume(self) -> None:
        """Resume the scheduler."""
        self.scheduler.resume()
        self._paused = False

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
        return not event.is_directory and is_agent_file(Path(event.src_path))

    def on_modified(self, event):
        if self._is_agent_file(event):
            self._reload(Path(event.src_path))

    def on_created(self, event):
        if self._is_agent_file(event):
            self._reload(Path(event.src_path))

    def on_deleted(self, event):
        if not event.is_directory and is_agent_file(Path(event.src_path)):
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
                # Frontmatter changed — full reload (reschedule + recreate watchers)
                self.registry.register(config)
                self.scheduler.unschedule_agent(config.name)
                self.scheduler.schedule_agent(config)
                if config.trigger.type == "watch" and config.enabled:
                    self.scheduler._add_watch_handler(config)
                logger.info(f"Hot-reloaded agent (full): {config.name}")

        except Exception as e:
            logger.warning(f"Failed to reload {path.name}: {e}")


class _AgentWatchHandler(FileSystemEventHandler):
    """Watchdog handler that triggers agents when watched paths change."""

    def __init__(
        self,
        agent_name: str,
        watch_paths: list[Path],
        scheduler: AgentScheduler,
        loop: asyncio.AbstractEventLoop | None,
    ):
        self.agent_name = agent_name
        self.watch_paths = watch_paths
        self.scheduler = scheduler
        self._loop = loop
        self._debounce_timers: dict[Path, asyncio.TimerHandle] = {}
        self._pending_contexts: dict[Path, str] = {}

    def _is_relevant(self, event_path: str) -> bool:
        """Check if event path is within watched paths."""
        path = Path(event_path).resolve()
        for watch_path in self.watch_paths:
            if watch_path.is_dir():
                try:
                    path.relative_to(watch_path)
                    return True
                except ValueError:
                    continue
            else:
                if path == watch_path:
                    return True
        return False

    def _build_context(self, event) -> str:
        """Build trigger context string from event."""
        if event.event_type == "moved":
            return f"moved: {event.src_path} -> {event.dest_path}"
        path = Path(event.src_path).resolve()
        return f"{event.event_type}: {path}"

    def _trigger_agent(self, path: Path) -> None:
        """Trigger agent execution with the pending context for a path."""
        context = self._pending_contexts.pop(path, None)
        self._debounce_timers.pop(path, None)

        if context and self._loop:
            asyncio.run_coroutine_threadsafe(
                self.scheduler._execute_agent(self.agent_name, "watch", trigger_context=context),
                self._loop,
            )
            logger.info(f"Triggered agent '{self.agent_name}': {context}")

    def _schedule_trigger(self, event) -> None:
        """Schedule agent trigger with debounce based on file path.

        Multiple events for the same file within 500ms are collapsed into one trigger.
        For moved events, the debounce key is the destination path.
        """
        if event.event_type == "moved":
            path = Path(event.dest_path).resolve()
        else:
            path = Path(event.src_path).resolve()

        # Cancel existing timer for this path
        old_timer = self._debounce_timers.get(path)
        if old_timer:
            old_timer.cancel()

        self._pending_contexts[path] = self._build_context(event)

        if self._loop:
            self._debounce_timers[path] = self._loop.call_later(0.5, self._trigger_agent, path)

    def on_created(self, event):
        if not event.is_directory and self._is_relevant(event.src_path):
            self._schedule_trigger(event)

    def on_modified(self, event):
        if not event.is_directory and self._is_relevant(event.src_path):
            self._schedule_trigger(event)

    def on_deleted(self, event):
        if not event.is_directory and self._is_relevant(event.src_path):
            self._schedule_trigger(event)

    def on_moved(self, event):
        if not event.is_directory and (self._is_relevant(event.src_path) or self._is_relevant(event.dest_path)):
            self._schedule_trigger(event)
