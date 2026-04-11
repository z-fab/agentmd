"""Health, info, and shutdown endpoints."""

from __future__ import annotations

import asyncio
import os
import time

from fastapi import APIRouter, Request

from agent_md.api.schemas import HealthResponse, InfoResponse, ShutdownResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse()


@router.get("/info", response_model=InfoResponse)
async def info(request: Request):
    state = request.app.state
    rt = state.runtime

    scheduler_status = "off"
    if rt.scheduler:
        scheduler_status = "paused" if getattr(rt.scheduler, "_paused", False) else "running"

    running = await rt.db.list_running_executions()

    return InfoResponse(
        version=state.version,
        pid=os.getpid(),
        uptime_seconds=time.monotonic() - state.start_time,
        agents_loaded=len(rt.registry),
        agents_enabled=len(rt.registry.enabled()),
        scheduler_status=scheduler_status,
        watcher_active=rt.scheduler is not None,
        active_streams=state.event_bus.stream_count,
        active_executions=len(running),
    )


@router.post("/shutdown", response_model=ShutdownResponse)
async def shutdown(request: Request):
    state = request.app.state
    asyncio.get_event_loop().call_later(0.5, _trigger_shutdown, state)
    return ShutdownResponse()


def _trigger_shutdown(state):
    """Signal the lifecycle manager or server to stop."""
    if hasattr(state, "shutdown_event"):
        state.shutdown_event.set()
