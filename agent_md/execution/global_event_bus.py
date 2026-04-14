"""Simple pub/sub for system-wide events (no replay, no persistence).

Used by the global SSE endpoint to broadcast execution lifecycle,
scheduler state, and agent changes to connected clients.
"""

from __future__ import annotations

import asyncio


class GlobalEventBus:
    """Broadcast system-wide events to all subscribers."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []

    async def publish(self, event: dict) -> None:
        """Send *event* to all subscriber queues. Drops if full."""
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def subscribe(self) -> asyncio.Queue:
        """Create and return a new subscriber queue."""
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Remove a subscriber queue."""
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    @property
    def stream_count(self) -> int:
        """Number of active global SSE streams."""
        return len(self._subscribers)
