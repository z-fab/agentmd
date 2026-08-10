"""End-to-end transport tests for ``agentmd start --port``.

Boots the real backend (Unix socket + TCP, one shared app) and checks both
doors: the local CLI keeps working unauthenticated over the socket while the
TCP listener rejects requests without the key.
"""

from __future__ import annotations

import asyncio
import contextlib
import socket as socketlib
import tempfile
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from agent_md.cli.client import BackendClient
from agent_md.cli.commands import _run_backend
from agent_md.cli.errors import TcpRequiresApiKey
from agent_md.main import app as cli_app

API_KEY = "e2e-secret-key"
BOOT_TIMEOUT = 20.0
# Graceful shutdown normally lands in well under a second. The budget only has
# to be generous enough for a loaded machine — never so generous that a backend
# that *cannot* be stopped gracefully turns a red test into a stalled CI job.
SHUTDOWN_TIMEOUT = 10.0
CANCEL_TIMEOUT = 5.0


@pytest.fixture
def short_state_dir(monkeypatch):
    """A short XDG_STATE_HOME — AF_UNIX paths cap at ~104 bytes on macOS."""
    with tempfile.TemporaryDirectory(prefix="amd", dir="/tmp") as d:
        monkeypatch.setenv("XDG_STATE_HOME", d)
        yield Path(d)


def _free_port() -> int:
    with socketlib.socket(socketlib.AF_INET, socketlib.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _wait_until(predicate, timeout: float = BOOT_TIMEOUT) -> None:
    """Poll *predicate* (async) until true, or fail once *timeout* elapses."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if await predicate():
            return
        await asyncio.sleep(0.1)
    raise AssertionError(f"condition not met within {timeout}s")


async def _stop_backend(server: asyncio.Task, socket_client: httpx.AsyncClient) -> None:
    """Stop the backend, bounded at every step.

    `POST /shutdown` travels over the socket, so it is exactly the call that
    stops working when auth is wired to the shared app instead of the TCP
    entrypoint. Waiting on a graceful exit that answered 401 would convert a
    wiring bug into a stalled job, so the status code decides: no 200, no wait.
    """
    if server.done():
        return

    graceful = False
    with contextlib.suppress(Exception):
        graceful = (await socket_client.post("/shutdown")).status_code == 200

    if graceful:
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(server), timeout=SHUTDOWN_TIMEOUT)

    if not server.done():
        server.cancel()
        with contextlib.suppress(BaseException):
            await asyncio.wait_for(server, timeout=CANCEL_TIMEOUT)

    assert server.done(), "backend ignored both /shutdown and cancellation"


@pytest.fixture
async def backend(tmp_path, short_state_dir):
    """Run the backend on a socket + TCP port; yield ``(socket_client, base_url)``."""
    workspace = tmp_path / "ws"
    (workspace / "agents").mkdir(parents=True)

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    server = asyncio.create_task(
        _run_backend(workspace, False, port, "127.0.0.1", API_KEY, True),
    )

    socket_client = BackendClient()._async_client()
    tcp_probe = httpx.AsyncClient(base_url=base_url, timeout=5.0)

    async def _both_up() -> bool:
        if server.done():  # surface a boot failure instead of timing out
            server.result()
        try:
            await socket_client.get("/health")
            await tcp_probe.get("/health")
        except (httpx.ConnectError, httpx.TimeoutException, OSError):
            return False
        return True

    try:
        await _wait_until(_both_up)

        # Precondition, not a courtesy: every test in this file runs against a
        # backend whose socket door is open. Asserting it here is what makes the
        # TCP tests — whose own subject the mutation leaves untouched — report a
        # shared-app middleware instead of passing while the local CLI 401s.
        probe = await socket_client.get("/info")
        assert probe.status_code == 200, (
            f"the Unix socket answered {probe.status_code} to an unauthenticated request; "
            "auth must wrap the TCP entrypoint only, never the shared app"
        )

        yield socket_client, base_url
    finally:
        await tcp_probe.aclose()
        await _stop_backend(server, socket_client)
        await socket_client.aclose()


async def test_socket_transport_works_without_key(backend):
    """The regression the naive fix causes: local CLI commands answering 401."""
    socket_client, _ = backend
    resp = await socket_client.get("/info")
    assert resp.status_code == 200
    assert (await socket_client.get("/agents")).status_code == 200


async def test_tcp_transport_rejects_missing_key(backend):
    _, base_url = backend
    async with httpx.AsyncClient(base_url=base_url, timeout=5.0) as c:
        assert (await c.get("/info")).status_code == 401
        assert (await c.post("/agents/anything/run", json={})).status_code == 401


async def test_tcp_transport_accepts_valid_key(backend):
    _, base_url = backend
    async with httpx.AsyncClient(base_url=base_url, timeout=5.0) as c:
        resp = await c.get("/info", headers={"X-API-Key": API_KEY})
        assert resp.status_code == 200


async def test_tcp_health_stays_public(backend):
    _, base_url = backend
    async with httpx.AsyncClient(base_url=base_url, timeout=5.0) as c:
        assert (await c.get("/health")).status_code == 200


async def test_port_without_api_key_is_refused(tmp_path, short_state_dir):
    """No key, no TCP bind — and nothing else starts either."""
    with pytest.raises(TcpRequiresApiKey):
        await _run_backend(tmp_path / "ws", False, _free_port(), "127.0.0.1", None, True)
    assert not (short_state_dir / "agentmd" / "agentmd.sock").exists()


def test_cli_start_port_without_key_exits(tmp_path, short_state_dir):
    result = CliRunner().invoke(cli_app, ["start", "--port", str(_free_port()), "-w", str(tmp_path / "ws")])
    assert result.exit_code == 1
    assert "--api-key" in result.output


# --- daemon mode --------------------------------------------------------------


@pytest.fixture
def spawned(monkeypatch):
    """Capture what `start -d` would launch, without launching it."""
    from agent_md.cli import spawn

    calls: list[tuple] = []
    monkeypatch.setattr(spawn.BackendClient, "health_check", lambda self: False)
    monkeypatch.setattr(spawn, "_spawn_backend", lambda ws=None, extra=None: calls.append((ws, extra)) or 4242)
    return calls


def test_daemon_forwards_server_flags(tmp_path, short_state_dir, spawned):
    """`start -d --port` used to drop every server flag on the floor."""
    port = _free_port()
    result = CliRunner().invoke(
        cli_app,
        ["start", "-d", "--keep-alive", "--port", str(port), "--host", "0.0.0.0", "--api-key", API_KEY],
    )

    assert result.exit_code == 0, result.output
    _, extra = spawned[0]
    assert extra == ["--keep-alive", "--port", str(port), "--host", "0.0.0.0", "--api-key", API_KEY]


def test_daemon_without_server_flags_passes_none(tmp_path, short_state_dir, spawned):
    result = CliRunner().invoke(cli_app, ["start", "-d"])

    assert result.exit_code == 0, result.output
    assert spawned[0][1] == []


def test_daemon_refuses_port_without_key(tmp_path, short_state_dir, spawned):
    result = CliRunner().invoke(cli_app, ["start", "-d", "--port", str(_free_port())])

    assert result.exit_code == 1
    assert "--api-key" in result.output
    assert spawned == []
