"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from agent_md.workspace.bootstrap import bootstrap
from agent_md.execution.event_bus import EventBus


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Startup: bootstrap runtime. Shutdown: close everything."""
    state = app.state

    state.start_time = time.monotonic()
    state.shutdown_event = asyncio.Event()
    state.cancel_events: dict[int, asyncio.Event] = {}

    rt = await bootstrap(
        workspace=state.workspace,
        db_path=getattr(state, "db_path", None),
        start_scheduler=state.start_scheduler,
        on_event=state.on_event,
        on_start=state.on_start,
        on_complete=state.on_complete,
        event_bus=state.event_bus,
        cancel_events=state.cancel_events,
    )
    state.runtime = rt
    state.db = rt.db

    # Start lifecycle manager (idle timeout)
    from agent_md.execution.lifecycle import LifecycleManager

    lifecycle = LifecycleManager(shutdown_event=state.shutdown_event)
    lifecycle.keep_alive = getattr(state, "keep_alive", False)
    lifecycle.has_scheduled_agents = lambda: bool(rt.scheduler and rt.scheduler.get_jobs())
    lifecycle.has_running_executions = lambda: bool(state.cancel_events)
    lifecycle.has_active_streams = lambda: state.event_bus.stream_count > 0
    state.lifecycle = lifecycle

    lifecycle_task = asyncio.create_task(lifecycle.run())

    yield

    lifecycle_task.cancel()
    try:
        await lifecycle_task
    except asyncio.CancelledError:
        pass
    await rt.aclose()


def create_app(
    workspace: Path | None = None,
    db_path: Path | None = None,
    start_scheduler: bool = False,
    on_event=None,
    on_start=None,
    on_complete=None,
) -> FastAPI:
    """Build and return the FastAPI application."""
    from agent_md.api.routes import info, agents, executions, scheduler

    app = FastAPI(
        title="AgentMD",
        description="Agent.md HTTP Backend",
        lifespan=_lifespan,
    )

    app.state.workspace = workspace
    app.state.db_path = db_path
    app.state.start_scheduler = start_scheduler
    app.state.on_event = on_event
    app.state.on_start = on_start
    app.state.on_complete = on_complete
    app.state.event_bus = EventBus()

    try:
        from importlib.metadata import version

        app.state.version = version("agentmd")
    except Exception:
        app.state.version = "dev"

    app.include_router(info.router)
    app.include_router(agents.router)
    app.include_router(executions.router)
    app.include_router(scheduler.router)

    return app
