"""Global SSE event stream endpoint."""

from __future__ import annotations

from collections.abc import AsyncIterable
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent

from agent_md.api.sse import SHUTDOWN, TIMEOUT, next_event

router = APIRouter(prefix="/events", tags=["events"])

_HEARTBEAT_TIMEOUT = 10.0  # seconds of inactivity before heartbeat


@router.get("/stream", response_class=EventSourceResponse)
async def global_event_stream(request: Request) -> AsyncIterable[ServerSentEvent]:
    """Stream all backend state changes as Server-Sent Events."""
    global_bus = request.app.state.global_event_bus
    shutdown_event = getattr(request.app.state, "shutdown_event", None)
    queue = global_bus.subscribe()
    try:
        while True:
            event = await next_event(queue, shutdown_event, _HEARTBEAT_TIMEOUT)
            if event is SHUTDOWN:
                # Ending the generator completes the response, which is what
                # lets uvicorn's graceful shutdown drain this connection.
                yield ServerSentEvent(data={"reason": "backend shutting down"}, event="shutdown")
                return
            if event is TIMEOUT:
                yield ServerSentEvent(
                    data={"timestamp": datetime.now(timezone.utc).isoformat()},
                    event="heartbeat",
                )
                continue
            yield ServerSentEvent(
                data=event["data"],
                event=event["type"],
            )
    finally:
        global_bus.unsubscribe(queue)
