"""Auto-spawn the backend process when needed.

The CLI detects whether the backend is alive via a health check on the
Unix socket. If it's not running, it spawns a new backend process with
stdout/stderr redirected to the log file, then polls until the socket
appears.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from agent_md.cli.client import BackendClient, get_log_path, get_socket_path, get_state_dir


def ensure_backend(client: BackendClient | None = None, workspace: Path | None = None) -> BackendClient:
    """Ensure the backend is running, spawning it if necessary.

    Returns a BackendClient connected to the running backend.
    """
    if os.environ.get("AGENTMD_NO_AUTOSPAWN") == "1":
        raise RuntimeError(
            "Backend is not running and AGENTMD_NO_AUTOSPAWN=1 is set. Start it manually with 'agentmd start'."
        )

    client = client or BackendClient()
    if client.health_check():
        return client

    _spawn_backend(workspace)

    socket_path = get_socket_path()
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if socket_path.exists() and client.health_check():
            return client
        time.sleep(0.2)

    raise RuntimeError(f"Backend failed to start within 10s. Check logs at {get_log_path()}")


def _spawn_backend(workspace: Path | None = None) -> int:
    """Spawn the backend as a detached process. Returns PID."""
    state_dir = get_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)

    log_path = get_log_path()

    cmd = [sys.executable, "-m", "agent_md.main", "start", "--internal-backend"]
    if workspace:
        cmd.extend(["--workspace", str(workspace)])

    log_file = open(log_path, "a")

    kwargs = {
        "stdout": log_file,
        "stderr": log_file,
        "stdin": subprocess.DEVNULL,
    }

    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    proc = subprocess.Popen(cmd, **kwargs)

    pid_path = state_dir / "backend.pid"
    pid_path.write_text(str(proc.pid))

    return proc.pid
