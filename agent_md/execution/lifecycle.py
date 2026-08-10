"""Lifecycle manager — idle timeout and graceful shutdown.

Periodically checks whether the backend has any active work. If all
conditions are idle for longer than ``idle_timeout``, triggers a
graceful shutdown via the shared ``shutdown_event``.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time

logger = logging.getLogger(__name__)


class LifecycleManager:
    """Monitors backend activity and triggers shutdown when idle."""

    def __init__(
        self,
        shutdown_event: asyncio.Event,
        idle_timeout: float = 300.0,
        check_interval: float = 30.0,
    ) -> None:
        self.shutdown_event = shutdown_event
        self.idle_timeout = idle_timeout
        self.check_interval = check_interval
        self.keep_alive = False
        self._idle_since: float | None = None

        # Named for trigger sources, not for APScheduler jobs: a workspace whose
        # agents are all `trigger: watch` has no job and is still not idle.
        self.has_active_triggers: callable = lambda: False
        self.has_running_executions: callable = lambda: False
        self.has_active_streams: callable = lambda: False
        # Service mode only: a HILT execution parked on a human keeps the
        # backend up. Left False for the local socket, where an abandoned
        # 'waiting' would otherwise make the backend immortal.
        self.has_waiting_executions: callable = lambda: False

    async def _is_idle(self) -> bool:
        checks = (
            self.has_active_triggers,
            self.has_running_executions,
            self.has_active_streams,
            self.has_waiting_executions,
        )
        for check in checks:
            result = check()
            if inspect.isawaitable(result):
                result = await result
            if result:
                return False
        return True

    async def run(self) -> None:
        while not self.shutdown_event.is_set():
            if self.keep_alive:
                await asyncio.sleep(self.check_interval)
                continue

            if await self._is_idle():
                if self._idle_since is None:
                    self._idle_since = time.monotonic()
                    logger.info("Backend is idle, starting timeout countdown")

                elapsed = time.monotonic() - self._idle_since
                if elapsed >= self.idle_timeout:
                    logger.info(f"Idle for {elapsed:.0f}s (timeout={self.idle_timeout}s), triggering shutdown")
                    self.shutdown_event.set()
                    return
            else:
                if self._idle_since is not None:
                    logger.info("Backend is active again, resetting idle timer")
                self._idle_since = None

            await asyncio.sleep(self.check_interval)
