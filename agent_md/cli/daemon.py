"""Background process management — PID file, start/stop daemon."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def get_pid_file(workspace: Path) -> Path:
    return workspace / "data" / "agentmd.pid"


def get_log_file(workspace: Path) -> Path:
    return workspace / "data" / "agentmd.log"


def is_running(workspace: Path) -> tuple[bool, int | None]:
    """Check if the daemon is running. Returns (is_running, pid).

    Cleans up stale PID files automatically.
    """
    pid_file = get_pid_file(workspace)
    if not pid_file.exists():
        return False, None

    try:
        pid = int(pid_file.read_text().strip())
    except (ValueError, OSError):
        pid_file.unlink(missing_ok=True)
        return False, None

    # Check if process exists
    try:
        os.kill(pid, 0)
        return True, pid
    except (ProcessLookupError, PermissionError):
        # Stale PID file
        pid_file.unlink(missing_ok=True)
        return False, None


def start_daemon(workspace: Path, extra_args: list[str] | None = None) -> int:
    """Start agentmd as a background process. Returns the PID."""
    running, pid = is_running(workspace)
    if running:
        raise RuntimeError(f"agentmd is already running (pid {pid})")

    pid_file = get_pid_file(workspace)
    log_file = get_log_file(workspace)

    # Ensure data directory exists
    pid_file.parent.mkdir(parents=True, exist_ok=True)

    cmd = [sys.executable, "-m", "agent_md.main", "start", "--workspace", str(workspace)]
    if extra_args:
        cmd.extend(extra_args)

    log_fh = open(log_file, "a")

    kwargs: dict = {
        "stdout": log_fh,
        "stderr": log_fh,
    }

    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    proc = subprocess.Popen(cmd, **kwargs)
    log_fh.close()  # child inherits the fd; parent no longer needs it
    pid_file.write_text(str(proc.pid))

    return proc.pid


def stop_daemon(workspace: Path) -> bool:
    """Stop the background daemon. Returns True if stopped."""
    running, pid = is_running(workspace)
    if not running or pid is None:
        return False

    pid_file = get_pid_file(workspace)

    try:
        os.kill(pid, signal.SIGTERM)

        # Wait up to 5 seconds for graceful shutdown
        for _ in range(50):
            try:
                os.kill(pid, 0)
                time.sleep(0.1)
            except (ProcessLookupError, PermissionError):
                break
        else:
            # Force kill
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
    except (ProcessLookupError, PermissionError):
        pass

    pid_file.unlink(missing_ok=True)
    return True


def get_daemon_start_time(workspace: Path) -> str | None:
    """Return the daemon start time from the PID file's mtime."""
    pid_file = get_pid_file(workspace)
    if not pid_file.exists():
        return None
    try:
        from datetime import datetime, timezone

        mtime = pid_file.stat().st_mtime
        dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
        return dt.isoformat()
    except OSError:
        return None


def get_daemon_uptime(workspace: Path) -> str | None:
    """Return a human-readable uptime string."""
    start = get_daemon_start_time(workspace)
    if not start:
        return None
    from datetime import datetime, timezone

    try:
        dt = datetime.fromisoformat(start)
        delta = datetime.now(timezone.utc) - dt
        secs = int(delta.total_seconds())
        if secs < 60:
            return f"{secs}s"
        if secs < 3600:
            return f"{secs // 60}m {secs % 60}s"
        hours = secs // 3600
        mins = (secs % 3600) // 60
        return f"{hours}h {mins}m"
    except (ValueError, TypeError):
        return None
