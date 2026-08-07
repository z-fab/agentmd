"""Helpers for fire-and-forget asyncio tasks that must not be GC'd."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

# Strong references so create_task results are not garbage-collected mid-flight.
_BACKGROUND_TASKS: set[asyncio.Task] = set()


def spawn_background(coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
    """Schedule *coro* and keep a reference until it completes."""
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return task
