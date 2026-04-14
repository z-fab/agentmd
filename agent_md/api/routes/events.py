"""Global SSE event stream endpoint."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent

router = APIRouter(prefix="/events", tags=["events"])

_HEARTBEAT_TIMEOUT = 10.0  # seconds of inactivity before heartbeat


@router.get("/stream", response_class=EventSourceResponse)
async def global_event_stream(request: Request) -> AsyncIterable[ServerSentEvent]:
    """Stream all backend state changes as Server-Sent Events."""
    global_bus = request.app.state.global_event_bus
    queue = global_bus.subscribe()
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=_HEARTBEAT_TIMEOUT)
                yield ServerSentEvent(
                    data=event["data"],
                    event=event["type"],
                )
            except asyncio.TimeoutError:
                yield ServerSentEvent(
                    data={"timestamp": datetime.now(timezone.utc).isoformat()},
                    event="heartbeat",
                )
    finally:
        global_bus.unsubscribe(queue)
