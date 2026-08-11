"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI

from agent_md.workspace.bootstrap import bootstrap, Runtime
from agent_md.execution.event_bus import EventBus
from agent_md.execution.global_event_bus import GlobalEventBus


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Startup: bootstrap runtime. Shutdown: close everything.

    Shutdown lives in a ``finally``, so it runs on every exit path — a startup
    that raised, a body that raised, a cancelled server — not only the clean
    one. Before that, a failed startup left the runtime's database open and the
    process hung on aiosqlite's non-daemon thread instead of exiting (#17).

    Two rules follow from running cleanup on the failure path. The runtime may
    be missing entirely (``bootstrap`` raised) or half-built, so every step is
    guarded by its own existence check; and nothing here may raise, or it would
    replace ``database is locked`` with a shutdown error and hide why startup
    failed. ``Runtime.aclose`` upholds the second rule for its own steps.
    """
    state = app.state

    # Guard: when two uvicorn servers share the same app (socket + TCP),
    # each triggers lifespan independently. Only bootstrap once.
    if getattr(state, "_bootstrapping", False) or getattr(state, "runtime", None) is not None:
        yield
        return
    state._bootstrapping = True

    state.start_time = time.monotonic()
    state.shutdown_event = asyncio.Event()
    state.cancel_events: dict[int, asyncio.Event] = {}

    rt: Runtime | None = None
    lifecycle_task: asyncio.Task | None = None
    started = False
    try:
        rt = await bootstrap(
            workspace=state.workspace,
            agents_dir=getattr(state, "agents_dir", None),
            db_path=getattr(state, "db_path", None),
            start_scheduler=state.start_scheduler,
            on_event=state.on_event,
            on_start=state.on_start,
            on_complete=state.on_complete,
            event_bus=state.event_bus,
            global_event_bus=state.global_event_bus,
            cancel_events=state.cancel_events,
        )
        state.runtime = rt
        state.db = rt.db

        # Start lifecycle manager (idle timeout)
        from agent_md.execution.lifecycle import LifecycleManager

        lifecycle = LifecycleManager(shutdown_event=state.shutdown_event)
        lifecycle.keep_alive = getattr(state, "keep_alive", False)
        lifecycle.has_active_triggers = lambda: bool(rt.scheduler and rt.scheduler.has_active_triggers())
        lifecycle.has_running_executions = lambda: bool(state.cancel_events)
        # 'waiting' (HILT) executions have no live task. On the local socket they
        # intentionally do NOT keep the backend alive — respond() rebuilds and
        # resumes on demand, and a forgotten HILT must not become an immortal
        # backend. In service mode (TCP or --keep-alive) the opposite holds: the
        # caller is remote, so parking on a human must not drop the server.
        if getattr(state, "service_mode", False):

            async def _has_waiting() -> bool:
                return bool(await rt.db.waiting_execution_ids())

            lifecycle.has_waiting_executions = _has_waiting
        lifecycle.has_active_streams = lambda: (state.event_bus.stream_count + state.global_event_bus.stream_count) > 0
        state.lifecycle = lifecycle

        lifecycle_task = asyncio.create_task(lifecycle.run())

        started = True
        yield
    except BaseException as e:
        # Recorded rather than re-derived: uvicorn swallows a failed startup into
        # a log line and a clean return, so `agentmd start` would otherwise exit 0
        # for a backend that never came up. Only failures *before* the yield
        # count — past it the backend did start, whatever went wrong later.
        if not started:
            state.startup_error = e
        raise
    finally:
        if lifecycle_task is not None:
            lifecycle_task.cancel()
            with suppress(asyncio.CancelledError):
                await lifecycle_task
        if rt is not None:
            await rt.aclose()


def create_app(
    workspace: Path | None = None,
    agents_dir: Path | None = None,
    db_path: Path | None = None,
    start_scheduler: bool = False,
    on_event=None,
    on_start=None,
    on_complete=None,
) -> FastAPI:
    """Build and return the FastAPI application."""
    from agent_md.api.routes import info, agents, executions, scheduler, events

    app = FastAPI(
        title="Agentmd",
        description="Agentmd HTTP Backend",
        lifespan=_lifespan,
    )

    app.state.workspace = workspace
    app.state.agents_dir = agents_dir
    app.state.db_path = db_path
    app.state.start_scheduler = start_scheduler
    app.state.on_event = on_event
    app.state.on_start = on_start
    app.state.on_complete = on_complete
    app.state.event_bus = EventBus()
    app.state.global_event_bus = GlobalEventBus()

    try:
        from importlib.metadata import version

        app.state.version = version("agentmd")
    except Exception:
        app.state.version = "dev"

    app.include_router(info.router)
    app.include_router(agents.router)
    app.include_router(executions.router)
    app.include_router(scheduler.router)
    app.include_router(events.router)

    return app
