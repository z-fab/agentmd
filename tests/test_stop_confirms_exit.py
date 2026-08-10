"""`agentmd stop` must confirm the backend actually died.

The production failure this covers: ``stop`` printed "Backend is shutting down"
and returned. The backend closed and unlinked its socket but stayed alive for
minutes, holding an SSE connection open. The next ``agentmd start`` saw a dead
socket, spawned a second backend, and both schedulers began firing the same
``trigger: schedule`` agents.

Two layers are tested here:

* the escalation policy (graceful wait → SIGTERM → SIGKILL → loud failure),
  driven against a fake process so it is fast and deterministic; and
* the real thing — a spawned backend, an SSE client attached, ``stop``, and an
  assertion that the PID is gone.
"""

from __future__ import annotations

import os
import signal
import tempfile
import time
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from agent_md.cli import commands as cmd
from agent_md.main import app as cli_app

BACKEND_PID = 4242

# A real spawned backend has to boot, load a workspace and open its socket.
BOOT_TIMEOUT = 30.0
# `stop` itself is bounded by _STOP_GRACE_SECONDS + escalation; this only has to
# outlast that, so a hung backend fails the test instead of stalling CI.
STOP_TIMEOUT = 60.0


@pytest.fixture
def short_state_dir(monkeypatch):
    """A short XDG_STATE_HOME — AF_UNIX paths cap at ~104 bytes on macOS."""
    with tempfile.TemporaryDirectory(prefix="amd", dir="/tmp") as d:
        monkeypatch.setenv("XDG_STATE_HOME", d)
        yield Path(d)


# --- escalation policy --------------------------------------------------------


class FakeProcess:
    """A backend that dies only once *dies_on* has been sent to it.

    ``dies_on=None`` models the worst case: a process that outlives even
    SIGKILL, which `stop` must report as a failure rather than as success.
    """

    def __init__(self, dies_on: int | None):
        self.dies_on = dies_on
        self.alive = True
        self.signals: list[int] = []

    def kill(self, pid: int, sig: int) -> None:
        assert pid == BACKEND_PID
        if sig == 0:  # liveness probe
            if not self.alive:
                raise ProcessLookupError(pid)
            return
        self.signals.append(sig)
        if self.dies_on is not None and sig == self.dies_on:
            self.alive = False


@pytest.fixture
def stubborn(monkeypatch):
    """Wire the CLI to a FakeProcess and collapse every wait to a single poll."""

    def _build(dies_on: int | None) -> FakeProcess:
        proc = FakeProcess(dies_on)
        monkeypatch.setattr(os, "kill", proc.kill)
        # The escalation *order* is the subject; the real budgets would only
        # make the test 23 seconds slower without testing anything more.
        monkeypatch.setattr(cmd, "_STOP_GRACE_SECONDS", 0.0)
        monkeypatch.setattr(cmd, "_STOP_SIGTERM_SECONDS", 0.0)
        monkeypatch.setattr(cmd, "_STOP_SIGKILL_SECONDS", 0.0)
        monkeypatch.setattr(cmd, "_POLL_INTERVAL", 0.0)

        class _Resp:
            status_code = 200
            text = ""

            @staticmethod
            def json():
                return {"pid": BACKEND_PID}

        class _Client:
            def __init__(self, *a, **kw):
                pass

            def health_check(self):
                return True

            def get(self, path, **kw):
                return _Resp()

            def post(self, path, **kw):
                return _Resp()

        monkeypatch.setattr("agent_md.cli.client.BackendClient", _Client)
        return proc

    return _build


def _run_stop(*extra: str):
    return CliRunner().invoke(cli_app, ["stop", "--timeout", "0", *extra])


def test_stop_reports_success_only_when_the_process_is_gone(stubborn, short_state_dir):
    """The happy path: it went away on its own, no signals sent."""
    proc = stubborn(dies_on=0)
    proc.alive = False  # already exited by the time we look

    result = _run_stop()

    assert result.exit_code == 0, result.output
    assert "Backend stopped" in result.output
    assert proc.signals == [], "a backend that exited on its own must not be signalled"


def test_stop_escalates_to_sigterm(stubborn, short_state_dir):
    proc = stubborn(dies_on=signal.SIGTERM)

    result = _run_stop()

    assert result.exit_code == 0, result.output
    assert proc.signals == [signal.SIGTERM]
    assert "SIGTERM" in result.output


def test_stop_escalates_to_sigkill(stubborn, short_state_dir):
    proc = stubborn(dies_on=signal.SIGKILL)

    result = _run_stop()

    assert result.exit_code == 0, result.output
    assert proc.signals == [signal.SIGTERM, signal.SIGKILL]
    assert "SIGKILL" in result.output


def test_stop_fails_loudly_when_the_process_survives_everything(stubborn, short_state_dir):
    """Never report success for a backend that is still running.

    This is the whole point: a `stop` that exits 0 while the process lives is
    what lets the next `start` add a second scheduler.
    """
    proc = stubborn(dies_on=None)

    result = _run_stop()

    assert result.exit_code == 1
    assert "still alive" in result.output.lower()
    assert proc.signals == [signal.SIGTERM, signal.SIGKILL]


def test_stop_clears_the_pid_file_once_confirmed(stubborn, short_state_dir):
    """A stale pid file survives into the next PID and misdirects the fallback."""
    from agent_md.cli.client import get_pid_path

    proc = stubborn(dies_on=0)
    proc.alive = False
    pid_path = get_pid_path()
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(BACKEND_PID))

    assert _run_stop().exit_code == 0
    assert not pid_path.exists()


def test_stop_refuses_to_claim_success_without_a_pid(monkeypatch, short_state_dir):
    """No PID means no confirmation possible — say so, do not print success."""

    class _Resp:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            raise ValueError("no pid here")

    class _Client:
        def __init__(self, *a, **kw):
            pass

        def health_check(self):
            return True

        def get(self, path, **kw):
            return _Resp()

        def post(self, path, **kw):
            return _Resp()

    monkeypatch.setattr("agent_md.cli.client.BackendClient", _Client)

    result = _run_stop()

    assert result.exit_code == 1
    assert "cannot confirm" in result.output.lower()


# --- the real backend ---------------------------------------------------------


def _wait_until(predicate, timeout: float, what: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.1)
    raise AssertionError(f"{what} did not happen within {timeout}s")


def _pid_gone(pid: int) -> bool:
    return not cmd._pid_alive(pid)


@pytest.fixture
def spawned_backend(short_state_dir, tmp_path):
    """A real detached backend process. Yields its PID."""
    from agent_md.cli.client import BackendClient
    from agent_md.cli.spawn import _spawn_backend

    workspace = tmp_path / "ws"
    (workspace / "agents").mkdir(parents=True)

    pid = _spawn_backend(workspace)
    client = BackendClient()
    try:
        _wait_until(client.health_check, BOOT_TIMEOUT, "backend boot")
        yield pid
    finally:
        # Belt and braces: never leave a stray backend behind, whatever the
        # test did or failed to do.
        if cmd._pid_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass


def test_stop_kills_a_backend_with_an_sse_client_attached(spawned_backend, short_state_dir):
    """The reported bug, end to end.

    An attached SSE stream used to keep uvicorn's graceful drain open forever,
    so the process outlived `stop` by minutes while its socket was already
    gone. The stream must now close itself and the process must actually exit.

    A 200 on the stream is the precondition that matters: the connection is
    accepted and counted by uvicorn from that moment, which is what used to
    make the drain hang. Waiting for a first event would only buy a heartbeat.
    """
    from agent_md.cli.client import get_socket_path

    pid = spawned_backend
    transport = httpx.HTTPTransport(uds=str(get_socket_path()))
    stream_client = httpx.Client(base_url="http://agentmd-backend", transport=transport, timeout=None)

    with stream_client, stream_client.stream("GET", "/events/stream") as response:
        assert response.status_code == 200

        result = CliRunner().invoke(cli_app, ["stop"])

        assert result.exit_code == 0, result.output
        assert "Backend stopped" in result.output
        _wait_until(lambda: _pid_gone(pid), STOP_TIMEOUT, "backend exit")

        # Escalation is the safety net, not the plan. If SIGTERM was needed here
        # the backend is still failing to shut itself down with a client
        # attached — the actual bug — and only the CLI is hiding it.
        assert "SIGTERM" not in result.output and "SIGKILL" not in result.output, (
            f"backend needed to be signalled to die:\n{result.output}"
        )


def test_stop_confirms_exit_of_an_idle_backend(spawned_backend, short_state_dir):
    pid = spawned_backend

    result = CliRunner().invoke(cli_app, ["stop"])

    assert result.exit_code == 0, result.output
    assert cmd._pid_alive(pid) is False, "stop reported success while the backend was still running"
