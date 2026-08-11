import asyncio
import fnmatch
import logging
import os
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
from agent_md.execution.self_writes import process_ledger
from agent_md.providers.keys import api_key_env_for

logger = logging.getLogger(__name__)


def _path_matches_globs(path: Path, patterns: list[str]) -> bool:
    """Return True if *path* matches any glob in *patterns*.

    Each pattern is tried against the absolute path string and the basename so
    both ``*.pdf`` and ``**/inbox/*.csv`` work without special-casing.
    """
    if not patterns:
        return False
    absolute = str(path)
    name = path.name
    for pattern in patterns:
        if fnmatch.fnmatch(absolute, pattern) or fnmatch.fnmatch(name, pattern):
            return True
        # Path.match handles ** recursively the way pathlib users expect
        try:
            if path.match(pattern):
                return True
        except ValueError:
            continue
    return False


# Trigger types the scheduler owns. Refusing one of these is what "paused" and
# "enabled: false" mean. `manual` and `chat` are deliberate acts by a human, so
# neither flag applies to them — pausing the scheduler must not disable the
# run button.
_SCHEDULER_TRIGGERS = frozenset({"schedule", "watch"})


async def check_admission(
    config: AgentConfig,
    db,
    *,
    trigger_type: str,
    paused: bool = False,
    session_id: str | None = None,
) -> str | None:
    """Decide whether an execution of *config* may start now.

    The single place the admission rules live. Returns ``None`` when the
    execution is admitted, otherwise a short reason phrased to read as the tail
    of a sentence about the agent.

    Both call sites — the trigger funnel (``AgentScheduler._execute_agent``) and
    the manual funnel (``POST /agents/{id}/run``) — consume this. How a refusal
    is *surfaced* stays with the caller, because a dropped timer tick and a
    rejected HTTP request are not the same event: the trigger path logs and
    drops, the HTTP layer answers 409. What may not diverge is the decision, and
    that is why it is only written here.

    ``on_pending: skip`` is evaluated per *conversation*, not per agent: a run is
    refused only while the conversation it belongs to is itself parked on a
    human. ``session_id`` names that conversation; ``None`` is the sessionless
    bucket shared by manual, schedule and watch runs. Agent-wide was the reading
    from before sessions existed, and it made one unanswered HILT close the agent
    to every other conversation — including chats opened afterwards, which had
    asked nothing.
    """
    if trigger_type in _SCHEDULER_TRIGGERS:
        if not config.enabled:
            return "agent is disabled"
        if paused:
            return "the scheduler is paused"
        # A timer or a file event is not a turn in anyone's dialogue. ``AgentRunner.run``
        # discards a session id on these triggers; the gate has to judge the same
        # conversation the execution will actually belong to.
        session_id = None
    if config.on_pending == "skip" and await db.has_waiting_execution(config.id, session_id):
        if session_id is None:
            return "a previous run is waiting for a response"
        return "this conversation is waiting for a response"
    return None


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
        self,
        registry: AgentRegistry,
        runner: AgentRunner,
        path_context,
        on_event=None,
        on_complete=None,
        on_start=None,
        event_bus=None,
        global_event_bus=None,
        cancel_events: dict | None = None,
    ):
        self.registry = registry
        self.runner = runner
        self.path_context = path_context
        self.on_event = on_event
        self.on_complete = on_complete
        self.on_start = on_start
        self.event_bus = event_bus
        self.global_event_bus = global_event_bus
        self.cancel_events = cancel_events if cancel_events is not None else {}
        self.scheduler = AsyncIOScheduler()
        self.observer = Observer()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._watch_handlers: dict[str, list] = {}  # agent_id -> list of watch_ids
        self._paused = False

    def schedule_agent(self, config: AgentConfig) -> str:
        """Schedule an agent based on its trigger config.

        Returns ``"scheduled"`` when a job was added, ``"missing_key"`` when the
        agent needs a credential that is not set (and so must not run
        unattended), or ``"skipped"`` for every other non-schedule case.
        """
        job_id = f"agent_{config.id}"

        if not config.enabled:
            logger.info(f"Agent '{config.id}' is disabled, skipping schedule")
            return "skipped"

        if config.trigger.type == "manual":
            logger.info(f"Agent '{config.id}' is manual-only, skipping schedule")
            return "skipped"

        if config.trigger.type == "watch":
            logger.info(f"Agent '{config.id}' is watch-only, skipping APScheduler (handled by watchdog)")
            return "skipped"

        if config.model is not None:
            env_var = api_key_env_for(
                config.model.provider,
                config.model.base_url,
                config.model.api_key_env,
            )
            if env_var is not None and not os.environ.get(env_var):
                logger.error(
                    f"Agent '{config.id}' not scheduled: {env_var} is not set "
                    f"(required by provider '{config.model.provider}')"
                )
                return "missing_key"

        if config.trigger.type == "schedule":
            if config.trigger.cron:
                trigger = CronTrigger.from_crontab(config.trigger.cron)
                trigger_desc = f"cron({config.trigger.cron})"
            elif config.trigger.every:
                kwargs = parse_interval(config.trigger.every)
                trigger = IntervalTrigger(**kwargs)
                trigger_desc = f"every({config.trigger.every})"
            else:
                logger.warning(f"Schedule trigger for '{config.id}' has neither 'every' nor 'cron'")
                return "skipped"
        else:
            logger.warning(f"Unknown trigger type: {config.trigger.type}")
            return "skipped"

        self.scheduler.add_job(
            self._execute_agent,
            trigger=trigger,
            id=job_id,
            args=[config.id, config.trigger.type],
            replace_existing=True,
            misfire_grace_time=60,
        )
        logger.info(f"Scheduled agent '{config.id}': {trigger_desc}")
        return "scheduled"

    def unschedule_agent(self, agent_id: str) -> None:
        """Remove an agent's scheduled job and watch handlers."""
        job_id = f"agent_{agent_id}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info(f"Unscheduled agent: {agent_id}")

        self._remove_watch_handlers(agent_id)

    async def _execute_agent(self, agent_id: str, trigger_type: str, trigger_context: str | None = None) -> None:
        """Callback for every trigger-driven execution — APScheduler and watchdog alike.

        Both trigger sources land here and nowhere else, which makes the
        ``check_admission`` call below the one thing standing between a trigger
        firing and an execution existing. A watch event reaching this point with
        the scheduler paused is dropped here, since stopping the ``Observer``
        itself is not an option: watchdog observers cannot be restarted.
        """
        config = self.registry.get(agent_id)
        if config is None:
            return

        reason = await check_admission(
            config,
            self.runner.db,
            trigger_type=trigger_type,
            paused=self._paused,
        )
        if reason:
            logger.info(f"Skipping '{agent_id}': {reason}")
            return

        cancel_event = asyncio.Event()
        # Pre-create execution so we can register the cancel_event
        execution_id = await self.runner.db.create_execution(agent_id=config.id, trigger=trigger_type, status="running")
        self.cancel_events[execution_id] = cancel_event
        try:
            await self.runner.run(
                config,
                trigger_type,
                trigger_context=trigger_context,
                on_event=self.on_event,
                on_start=self.on_start,
                on_complete=self.on_complete,
                event_bus=self.event_bus,
                global_event_bus=self.global_event_bus,
                cancel_event=cancel_event,
                execution_id=execution_id,
            )
        finally:
            self.cancel_events.pop(execution_id, None)

    def _add_watch_handler(self, config: AgentConfig) -> None:
        """Register watchdog handlers for a single watch agent."""
        resolved_paths = [self.path_context._resolve_relative(p) for p in config.trigger.paths]
        logger.info(f"Setting up watch for agent '{config.id}': {resolved_paths}")

        filters = config.trigger.filters
        handler = _AgentWatchHandler(
            config.id,
            resolved_paths,
            self._execute_agent,
            self._loop,
            include=list(filters.include) if filters else [],
            exclude=list(filters.exclude) if filters else [],
            debounce=config.trigger.debounce,
        )
        watch_ids = []

        for path in resolved_paths:
            if path.is_dir():
                watch_id = self.observer.schedule(handler, str(path), recursive=True)
            else:
                watch_id = self.observer.schedule(handler, str(path.parent), recursive=False)
            watch_ids.append(watch_id)

        self._watch_handlers[config.id] = watch_ids

    def _remove_watch_handlers(self, agent_id: str) -> None:
        """Unregister watchdog handlers for a watch agent."""
        if agent_id not in self._watch_handlers:
            return

        for watch_id in self._watch_handlers.pop(agent_id):
            try:
                self.observer.unschedule(watch_id)
            except Exception:
                pass  # Already unscheduled
        logger.info(f"Removed watch handlers for: {agent_id}")

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
        reload_handler = _AgentFileHandler(
            self.registry,
            self,
            self._loop,
            agents_dir=agents_dir,
            global_event_bus=self.global_event_bus,
        )
        self.observer.schedule(reload_handler, str(agents_dir), recursive=False)
        logger.info(f"Watching workspace for changes: {agents_dir}")

        # 3. Register watch handlers for agents with watch triggers
        for config in self.registry.all():
            if config.trigger.type == "watch" and config.enabled:
                self._add_watch_handler(config)

        # 4. Start observer once (all handlers already registered)
        self.observer.start()

    def get_next_run(self, agent_id: str) -> str | None:
        """Return ISO timestamp of next scheduled run for *agent_id*, or None."""
        job = self.scheduler.get_job(f"agent_{agent_id}")
        if job and job.next_run_time:
            return job.next_run_time.isoformat()
        return None

    def get_jobs(self) -> list[dict]:
        """Return list of scheduled jobs with next_run times."""
        jobs = []
        for job in self.scheduler.get_jobs():
            bare_id = job.id.removeprefix("agent_") if job.id.startswith("agent_") else job.id
            config = self.registry.get(bare_id)
            display_name = config.name if config else bare_id
            jobs.append(
                {
                    "agent_id": bare_id,
                    "display_name": display_name,
                    "agent_name": bare_id,  # schema compat alias of agent_id
                    "trigger_type": "schedule",
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                }
            )
        return jobs

    def has_active_triggers(self) -> bool:
        """True while any trigger source can still fire an execution.

        The idle-shutdown reads this. Counting only APScheduler jobs made a
        workspace whose agents are all ``trigger: watch`` look idle, so the
        five-minute timeout killed the backend and every watcher with it.

        ``any`` over the values rather than a truth test on the dict: an entry
        that registered no watch id observes nothing, and something that cannot
        fire must not hold the backend up.
        """
        if self.scheduler.get_jobs():
            return True
        return any(self._watch_handlers.values())

    def pause(self) -> None:
        """Pause every trigger source (does not cancel running jobs).

        Pausing APScheduler stops timers, but the watchdog ``Observer`` keeps
        delivering events — those are refused at admission instead. See
        ``_execute_agent``.
        """
        self.scheduler.pause()
        self._paused = True

    def resume(self) -> None:
        """Resume every trigger source."""
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
        agents_dir: Path | None = None,
        global_event_bus=None,
    ):
        self.registry = registry
        self.scheduler = scheduler
        self._loop = loop
        self.agents_dir = agents_dir.resolve() if agents_dir is not None else None
        self.global_event_bus = global_event_bus

    def _publish_event(self, event: str, agent_id: str, display_name: str | None = None) -> None:
        """Publish agents_changed event to global bus from watchdog thread.

        ``agent_name`` mirrors ``agent_id`` for SSE schema compatibility; callers
        that have the config should pass ``display_name``.
        """
        if self.global_event_bus and self._loop:
            label = display_name if display_name is not None else agent_id
            asyncio.run_coroutine_threadsafe(
                self.global_event_bus.publish(
                    {
                        "type": "agents_changed",
                        "data": {
                            "event": event,
                            "agent_id": agent_id,
                            "display_name": label,
                            "agent_name": agent_id,
                        },
                    }
                ),
                self._loop,
            )

    def _is_managed_agent_path(self, path: Path) -> bool:
        """True when *path* is an agent .md directly under the watched agents_dir."""
        if not is_agent_file(path):
            return False
        if self.agents_dir is None:
            return True
        try:
            return path.resolve().parent == self.agents_dir
        except OSError:
            return False

    def _is_agent_file(self, event) -> bool:
        return not event.is_directory and self._is_managed_agent_path(Path(event.src_path))

    def on_modified(self, event):
        if self._is_agent_file(event):
            self._reload(Path(event.src_path))

    def on_created(self, event):
        if self._is_agent_file(event):
            self._reload(Path(event.src_path))

    def on_deleted(self, event):
        if event.is_directory or not is_agent_file(Path(event.src_path)):
            return

        path = Path(event.src_path)

        # Atomic saves (perl -i, sed -i, vim, most editors) write a temp file and
        # rename it over the original. FSEvents then closes the sequence with a
        # delete for a path that is still on disk. Dropping the agent there would
        # unregister a live agent with nothing arriving afterwards to restore it.
        if path.exists():
            if self._is_managed_agent_path(path):
                self._reload(path)
            return

        existing = self.registry.get_by_path(event.src_path)
        display_name = existing.name if existing else None
        agent_id = self.registry.remove_by_path(event.src_path)
        if agent_id:
            self.scheduler.unschedule_agent(agent_id)
            logger.info(f"Agent file deleted: {agent_id}")
            self._publish_event("removed", agent_id, display_name)

    def on_moved(self, event):
        """Handle rename/move: drop the old id; reload only if dest stays in agents_dir."""
        if event.is_directory:
            return

        src = Path(event.src_path)
        dest = Path(event.dest_path)

        if is_agent_file(src):
            existing = self.registry.get_by_path(event.src_path)
            display_name = existing.name if existing else None
            old_id = self.registry.remove_by_path(event.src_path)
            if old_id:
                self.scheduler.unschedule_agent(old_id)
                logger.info(f"Agent file moved away: {old_id}")
                self._publish_event("removed", old_id, display_name)

        if self._is_managed_agent_path(dest):
            self._reload(dest)

    def _reload(self, path: Path) -> None:
        try:
            config = parse_agent_file(path)
            old = self.registry.get(config.id)

            if old and old.config_hash == config.config_hash:
                # Only the body (system prompt) changed
                self.registry.register(config)
                logger.info(f"Hot-reloaded prompt for: {config.id}")
                self._publish_event("updated", config.id, config.name)
            else:
                # Frontmatter changed — full reload (reschedule + recreate watchers)
                self.registry.register(config)
                self.scheduler.unschedule_agent(config.id)
                self.scheduler.schedule_agent(config)
                if config.trigger.type == "watch" and config.enabled:
                    self.scheduler._add_watch_handler(config)
                logger.info(f"Hot-reloaded agent (full): {config.id}")
                event_type = "loaded" if old is None else "updated"
                self._publish_event(event_type, config.id, config.name)

            if config.model and config.model.provider == "openrouter":
                from agent_md.workspace.services import openrouter_load_warnings

                for note in openrouter_load_warnings(config.model.name):
                    logger.warning(f"Agent '{config.id}': {note}")

        except Exception as e:
            logger.warning(f"Failed to reload {path.name}: {e}")


class _AgentWatchHandler(FileSystemEventHandler):
    """Watchdog handler that triggers agents when watched paths change."""

    def __init__(
        self,
        agent_id: str,
        watch_paths: list[Path],
        execute_fn,
        loop: asyncio.AbstractEventLoop | None,
        *,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        debounce: float = 0.5,
        self_writes=None,
    ):
        self.agent_id = agent_id
        self.watch_paths = watch_paths
        self._execute_fn = execute_fn  # async fn(agent_id, trigger_type, trigger_context)
        self._loop = loop
        self._include = list(include or [])
        self._exclude = list(exclude or [])
        self._debounce = debounce
        self._self_writes = self_writes if self_writes is not None else process_ledger()
        self._debounce_timers: dict[Path, asyncio.TimerHandle] = {}
        self._pending_contexts: dict[Path, str] = {}

    def _passes_filters(self, path: Path) -> bool:
        """Apply trigger.filters include/exclude globs to a candidate path."""
        if self._exclude and _path_matches_globs(path, self._exclude):
            return False
        if self._include and not _path_matches_globs(path, self._include):
            return False
        return True

    def _is_own_write(self, path: Path) -> bool:
        """True when this agent's own built-in write produced the event.

        The local anti-loop guard. An agent watching a directory it writes to
        would otherwise retrigger itself forever, and no amount of persisted
        depth would stop it — the event arrives as a root cause. Scoped to this
        agent, so another agent writing into the same directory still triggers
        us. Best-effort: MCP and custom tools write without leaving a record.
        """
        if self._self_writes.is_self_write(path, self.agent_id):
            logger.debug(f"Suppressed self-written path for '{self.agent_id}': {path}")
            return True
        return False

    def _is_relevant(self, event_path: str) -> bool:
        """Check if event path is within watched paths, passes filters, and is not ours."""
        path = Path(event_path).resolve()
        in_watch = False
        for watch_path in self.watch_paths:
            if watch_path.is_dir():
                try:
                    path.relative_to(watch_path)
                    in_watch = True
                    break
                except ValueError:
                    continue
            else:
                if path == watch_path:
                    in_watch = True
                    break
        if not in_watch:
            return False
        if not self._passes_filters(path):
            return False
        return not self._is_own_write(path)

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
                self._execute_fn(self.agent_id, "watch", trigger_context=context),
                self._loop,
            )
            logger.info(f"Triggered agent '{self.agent_id}': {context}")

    def _arm_debounce(self, path: Path, context: str) -> None:
        """Restart the debounce window for *path*. Runs in the event loop thread.

        Cancelling the previous timer and arming the new one happen together in
        this one callback. ``call_soon_threadsafe`` delivers handovers in FIFO
        order onto a single thread, so two events for the same path are two
        sequential runs of this function — never two live timers.
        """
        old_timer = self._debounce_timers.pop(path, None)
        if old_timer:
            old_timer.cancel()

        self._pending_contexts[path] = context
        self._debounce_timers[path] = self._loop.call_later(self._debounce, self._trigger_agent, path)

    def _schedule_trigger(self, event) -> None:
        """Schedule agent trigger with debounce based on file path.

        Multiple events for the same file within the debounce window are
        collapsed into one trigger. For moved events, the debounce key is the
        destination path. The window defaults to 0.5s and is overridable via
        ``trigger.debounce``.

        Called from the watchdog's thread, which hands the event to the loop and
        touches no handler state: ``call_later`` is not thread-safe and, worse,
        does not wake a sleeping loop — the timer lands in the heap while
        ``select`` is still blocked on a timeout computed before it existed, so
        the trigger waits for whatever else wakes the loop next.
        """
        if event.event_type == "moved":
            path = Path(event.dest_path).resolve()
        else:
            path = Path(event.src_path).resolve()

        if not self._loop:
            return

        context = self._build_context(event)
        try:
            self._loop.call_soon_threadsafe(self._arm_debounce, path, context)
        except RuntimeError:
            # The loop is closed — the workspace is shutting down under us.
            logger.debug(f"Dropped watch event for '{self.agent_id}', loop is gone: {context}")

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
