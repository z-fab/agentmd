"""In-memory pub/sub for execution events.

The runner publishes events (message, tool_call, tool_result, meta, complete)
as each message is processed. SSE stream endpoints subscribe to receive
live events. Events are dicts with at least ``type``, ``data``, and ``seq`` keys.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict


class EventBus:
    """Lightweight pub/sub keyed by execution_id."""

    def __init__(self) -> None:
        self._subscribers: dict[int, list[asyncio.Queue]] = defaultdict(list)
        self._active_streams: int = 0

    async def publish(self, execution_id: int, event: dict) -> None:
        """Send *event* to all subscribers of *execution_id*."""
        for queue in self._subscribers.get(execution_id, []):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def subscribe(self, execution_id: int) -> asyncio.Queue:
        """Create a new subscriber queue for *execution_id*."""
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers[execution_id].append(q)
        self._active_streams += 1
        return q

    def unsubscribe(self, execution_id: int, q: asyncio.Queue) -> None:
        """Remove a subscriber queue."""
        subs = self._subscribers.get(execution_id, [])
        if q in subs:
            subs.remove(q)
            self._active_streams -= 1
        if not subs:
            self._subscribers.pop(execution_id, None)

    @property
    def stream_count(self) -> int:
        """Number of active SSE streams (for lifecycle tracking)."""
        return self._active_streams
