"""Helpers shared by the SSE endpoints.

An SSE response is an open connection for as long as its generator keeps
yielding, and uvicorn's graceful shutdown refuses to finish while any
connection is open. So a stream that only ever waits on its queue outlives the
shutdown request: the listening socket is closed and unlinked (health checks
start failing immediately), but the process stays up, still holding the
scheduler and the watchdog observer. The next ``agentmd start`` sees a dead
socket, spawns a second backend, and every ``trigger: schedule`` agent fires
twice.

The fix is for the generators to notice the backend going down and return,
which completes the response and releases the connection.
"""

from __future__ import annotations

import asyncio
from typing import Any

# Sentinels: distinguishable from any real event, and from each other.
TIMEOUT = object()
SHUTDOWN = object()


async def next_event(
    queue: asyncio.Queue,
    shutdown_event: asyncio.Event | None,
    timeout: float,
) -> Any:
    """Await the next item on *queue*, racing it against backend shutdown.

    Returns the event, ``TIMEOUT`` if *timeout* elapsed first (the caller's
    heartbeat tick), or ``SHUTDOWN`` if the backend is going down.

    A queued event wins a tie: it has already been taken off the queue by the
    time we look, so reporting shutdown instead would drop it.
    """
    get = asyncio.ensure_future(queue.get())
    waiters = [get]
    stop = None
    if shutdown_event is not None:
        stop = asyncio.ensure_future(shutdown_event.wait())
        waiters.append(stop)

    try:
        done, _ = await asyncio.wait(waiters, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
        if get in done:
            return get.result()
        if stop is not None and stop in done:
            return SHUTDOWN
        return TIMEOUT
    finally:
        for waiter in waiters:
            if not waiter.done():
                waiter.cancel()
