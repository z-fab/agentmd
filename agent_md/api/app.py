"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from agent_md.core.bootstrap import bootstrap
from agent_md.core.event_bus import EventBus


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Startup: bootstrap runtime. Shutdown: close everything."""
    state = app.state

    rt = await bootstrap(
        workspace=state.workspace,
        start_scheduler=state.start_scheduler,
        on_event=state.on_event,
        on_start=state.on_start,
        on_complete=state.on_complete,
    )
    state.runtime = rt
    state.db = rt.db
    state.start_time = time.monotonic()
    state.shutdown_event = asyncio.Event()
    state.cancel_events: dict[int, asyncio.Event] = {}

    yield

    await rt.aclose()


def create_app(
    workspace: Path | None = None,
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
