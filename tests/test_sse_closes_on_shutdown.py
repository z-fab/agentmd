"""SSE streams must let go of their connection when the backend shuts down.

uvicorn's graceful shutdown will not finish while any connection is open, and
its default drain has no timeout at all. An SSE generator that only ever waits
on its queue therefore pinned the process open indefinitely — with the listening
socket already closed and unlinked, so `agentmd status` reported "not running"
about a backend that was still holding the scheduler.

`agent_md/cli/commands.py` also caps the drain, which would mask this: these
tests assert the stream closes *promptly*, well inside that cap.
"""

from __future__ import annotations

import asyncio
import contextlib
import tempfile
from pathlib import Path

import httpx
import pytest

from agent_md.api.sse import SHUTDOWN, TIMEOUT, next_event
from agent_md.cli.client import BackendClient
from agent_md.cli.commands import _GRACEFUL_DRAIN_SECONDS, _run_backend

BOOT_TIMEOUT = 20.0
# Comfortably below the drain cap: passing this proves the stream closed itself
# rather than being cancelled by uvicorn's backstop.
PROMPT_EXIT = _GRACEFUL_DRAIN_SECONDS / 2


# --- next_event ---------------------------------------------------------------


async def test_next_event_returns_a_queued_event():
    queue: asyncio.Queue = asyncio.Queue()
    await queue.put({"type": "x"})
    assert await next_event(queue, asyncio.Event(), 1.0) == {"type": "x"}


async def test_next_event_reports_timeout():
    assert await next_event(asyncio.Queue(), asyncio.Event(), 0.05) is TIMEOUT


async def test_next_event_reports_shutdown():
    event = asyncio.Event()
    event.set()
    assert await next_event(asyncio.Queue(), event, 10.0) is SHUTDOWN


async def test_next_event_prefers_a_queued_event_over_shutdown():
    """A tie must not silently drop the event — it is already off the queue."""
    queue: asyncio.Queue = asyncio.Queue()
    await queue.put({"type": "x"})
    event = asyncio.Event()
    event.set()
    assert await next_event(queue, event, 10.0) == {"type": "x"}


async def test_next_event_tolerates_no_shutdown_event():
    """The SDK and tests build apps that never set one."""
    queue: asyncio.Queue = asyncio.Queue()
    await queue.put(1)
    assert await next_event(queue, None, 1.0) == 1
    assert await next_event(queue, None, 0.05) is TIMEOUT


# --- the running backend ------------------------------------------------------


@pytest.fixture
def short_state_dir(monkeypatch):
    """A short XDG_STATE_HOME — AF_UNIX paths cap at ~104 bytes on macOS."""
    with tempfile.TemporaryDirectory(prefix="amd", dir="/tmp") as d:
        monkeypatch.setenv("XDG_STATE_HOME", d)
        yield Path(d)


@pytest.fixture
def created_app(monkeypatch):
    """Capture the app `_run_backend` builds, so the test can reach its state."""
    from agent_md.api import app as app_module

    holder: dict = {}
    real = app_module.create_app
    monkeypatch.setattr(app_module, "create_app", lambda **kw: holder.setdefault("app", real(**kw)))
    return holder


async def _wait_until(predicate, timeout: float = BOOT_TIMEOUT) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if await predicate():
            return
        await asyncio.sleep(0.1)
    raise AssertionError(f"condition not met within {timeout}s")


@pytest.fixture
async def backend(tmp_path, short_state_dir, created_app):
    """A backend on the local socket. Yields ``(server_task, app)``."""
    workspace = tmp_path / "ws"
    (workspace / "agents").mkdir(parents=True)

    server = asyncio.create_task(_run_backend(workspace, False, None, "127.0.0.1", None, True))
    probe = BackendClient()._async_client()

    async def _up() -> bool:
        if server.done():  # surface a boot failure instead of timing out
            server.result()
        try:
            return (await probe.get("/health")).status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, OSError):
            return False

    try:
        await _wait_until(_up)
        yield server, created_app["app"]
    finally:
        await probe.aclose()
        if not server.done():
            app = created_app.get("app")
            event = getattr(app.state, "shutdown_event", None) if app else None
            if event is not None:
                event.set()
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(asyncio.shield(server), timeout=BOOT_TIMEOUT)
        if not server.done():
            server.cancel()
            with contextlib.suppress(BaseException):
                await asyncio.wait_for(server, timeout=5.0)


async def _assert_shuts_down_promptly(server, app, path: str) -> None:
    """With a client attached to *path*, shutdown must complete promptly."""
    client = BackendClient()._async_client(timeout=None)
    try:
        async with client.stream("GET", path) as response:
            assert response.status_code == 200

            app.state.shutdown_event.set()
            await asyncio.wait_for(asyncio.shield(server), timeout=PROMPT_EXIT)
    finally:
        await client.aclose()

    assert server.done()


async def test_global_stream_does_not_hold_shutdown_open(backend):
    server, app = backend
    await _assert_shuts_down_promptly(server, app, "/events/stream")


async def test_execution_stream_does_not_hold_shutdown_open(backend):
    """The production shape: an execution stuck in `running` with a client on it.

    The per-execution stream loops until the execution finishes, so a row that
    never leaves `running` kept the connection — and the backend — alive.
    """
    server, app = backend
    exec_id = await app.state.db.create_execution(agent_id="ghost", trigger="manual", status="running")

    await _assert_shuts_down_promptly(server, app, f"/executions/{exec_id}/stream")
