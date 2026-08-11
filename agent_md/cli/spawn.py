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

from agent_md.cli.client import BackendClient, get_log_path, get_pid_path, get_socket_path, get_state_dir

# Rotate backend.log when it exceeds this size (bytes).
_LOG_ROTATE_BYTES = 5 * 1024 * 1024
_LOG_BACKUP_COUNT = 3


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


def _rotate_log_if_needed(log_path: Path) -> None:
    """Size-based rotation: backend.log → .1 → .2 → …; drop the oldest."""
    try:
        if not log_path.exists() or log_path.stat().st_size < _LOG_ROTATE_BYTES:
            return
    except OSError:
        return

    oldest = Path(f"{log_path}.{_LOG_BACKUP_COUNT}")
    try:
        if oldest.exists():
            oldest.unlink()
    except OSError:
        pass

    for i in range(_LOG_BACKUP_COUNT - 1, 0, -1):
        src = Path(f"{log_path}.{i}")
        dst = Path(f"{log_path}.{i + 1}")
        if src.exists():
            try:
                src.rename(dst)
            except OSError:
                pass

    try:
        log_path.rename(Path(f"{log_path}.1"))
    except OSError:
        pass


def _spawn_backend(workspace: Path | None = None, extra_args: list[str] | None = None) -> int:
    """Spawn the backend as a detached process. Returns PID.

    ``extra_args`` carries the server-mode flags of an explicit
    ``agentmd start -d`` (--keep-alive, --port, --host, --api-key). Autospawn
    passes none: it only ever needs the local socket.
    """
    state_dir = get_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)

    log_path = get_log_path()
    _rotate_log_if_needed(log_path)

    cmd = [sys.executable, "-m", "agent_md.main", "start", "--internal-backend"]
    if workspace:
        cmd.extend(["--workspace", str(workspace)])
    if extra_args:
        cmd.extend(extra_args)

    # Open for the child, then close the parent's fd so we don't leak it.
    log_file = open(log_path, "a", encoding="utf-8")  # noqa: SIM115

    kwargs = {
        "stdout": log_file,
        "stderr": log_file,
        "stdin": subprocess.DEVNULL,
    }

    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen(cmd, **kwargs)
    finally:
        log_file.close()

    get_pid_path().write_text(str(proc.pid), encoding="utf-8")

    return proc.pid
