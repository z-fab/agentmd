"""Shared pytest fixtures for Agentmd tests.

Teardown conventions — a hang looks like broken CI, not a red test:

- ``Database``: prefer the ``db`` fixture. A hand-built ``Database`` must be
  closed in ``try``/``finally`` (or fixture teardown), never after assertions.
  aiosqlite's connection thread is non-daemon; skipping ``close()`` leaves the
  process stuck in ``threading._shutdown()``.
- Stream / event waits: always bound with ``asyncio.wait_for`` (or equivalent).
- Backend servers: stop via the internal path (e.g. ``shutdown_event.set()``),
  never via HTTP the test itself may have broken — cancelling the uvicorn task
  skips lifespan shutdown and leaks the backend's ``Database``.
"""

from __future__ import annotations

import pytest

from agent_md.db.database import Database


@pytest.fixture
async def db(tmp_path):
    """Connected Database closed in teardown, never at the end of a test body."""
    database = Database(tmp_path / "t.db")
    await database.connect()
    try:
        yield database
    finally:
        await database.close()
