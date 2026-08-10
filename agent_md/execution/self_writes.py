"""Self-write suppression — the local, best-effort half of the anti-loop guard.

An agent with ``trigger: watch`` over a directory it also writes to retriggers
itself: ``file_write`` produces a filesystem event, the event triggers the
agent, the agent writes again. ``path_context.get_allowed_paths`` puts watch
paths among the write paths, so the configuration that causes this is the
obvious one, not an exotic one.

Persisted ``depth`` / causation cannot break that cycle, not even in principle:
every watchdog callback arrives as a fresh root with ``depth == 0``, because the
causal chain dies in the filesystem. Nothing in the event says which execution
caused it.

What *can* break it is identity of the write. Every built-in write tool brackets
its disk mutation with :func:`self_write`, which records the path, the resulting
``st_mtime_ns`` and the agent that wrote it. The watch handler then drops an
event whose path still carries the exact mtime the *same* agent just wrote,
within :data:`SUPPRESSION_WINDOW`.

Three properties carry the design:

- **Agent-scoped.** Agent B writing into a directory agent A watches must still
  trigger A — that is a pipeline, not a loop. Only the writer's own watchers
  suppress.
- **mtime identity, not mere recency.** The ledger stores the mtime the write
  left behind and compares it against the file *as it is when the event is
  examined*. A user editing the same file right after the agent changes the
  mtime, so their edit is not suppressed even inside the window. This is what
  keeps the window from having to be short.
- **Best-effort, and declared as such.** MCP servers, custom tools and external
  processes write without passing through here, so an agent writing that way
  still retriggers itself. See ``docs/triggers.md``.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

SUPPRESSION_WINDOW = 2.0
"""Seconds a recorded self-write stays eligible for suppression.

**Lower bound — it must outlast event delivery.** The window is consumed by the
gap between the write hitting the disk and the watchdog handler seeing the
event, so it has to cover the slowest backend agentmd can end up on:

| backend | delivery latency |
|---|---|
| ``inotify`` (Linux) | sub-millisecond |
| ``FSEvents`` (macOS) | 10–19 ms measured locally over 10 writes |
| ``PollingObserver`` (network mounts, unsupported platforms) | one poll interval — watchdog's ``DEFAULT_OBSERVER_TIMEOUT``, **1.0 s** |

1.0 s is therefore the real floor; 2.0 s doubles it, which also buys headroom
for a handler thread starved by a busy execution. Note the debounce does *not*
eat into this: suppression is decided when the event arrives, before
``trigger.debounce`` is applied, so a large debounce costs the window nothing.

**Upper bound — why 2.0 s does not swallow a user edit.** It is the mtime
comparison, not the window, that protects a legitimate edit: a user saving the
file after the agent gives it a new ``st_mtime_ns``, which no longer matches the
ledger, so the event triggers normally however recent the agent's write was. The
window only bounds two things: the staleness of a (path, mtime) pair, and the
one case where identity is coarse — a *deletion*, whose recorded state is merely
"absent". Without a window, an agent deleting ``notes/x.md`` would suppress a
user's deletion of a re-created ``notes/x.md`` an hour later. 2.0 s keeps that
coincidence narrow while still clearing the 1.0 s floor.

Not exposed as configuration: it is a property of filesystem event delivery,
not of an agent's workload, and `trigger.debounce` is the knob for the latter.
"""


@dataclass(frozen=True)
class _SelfWrite:
    """One built-in write, as the ledger remembers it."""

    agent_id: str
    execution_id: int | None
    mtime_ns: int | None
    """``st_mtime_ns`` after the write, or ``None`` when the path is absent
    (``file_delete``, and the source side of ``file_move``)."""
    recorded_at: float
    settled: bool
    """``False`` between the ``begin`` and the ``commit`` of a write. An event
    landing in that gap has no mtime to compare against yet — on Linux the
    inotify callback can beat the ``stat`` that follows ``write_text`` — so an
    unsettled entry suppresses on its own."""


def _mtime_ns(path: Path) -> int | None:
    """Return ``st_mtime_ns`` for *path*, or None if it cannot be stat'd."""
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None


class SelfWriteLedger:
    """Per-process record of paths the built-in write tools just touched.

    Written from tool threads, read from the watchdog dispatch thread, so every
    mutation takes the lock. The stat comparison deliberately happens *outside*
    it — one blocked filesystem call must not stall a tool mid-write.
    """

    def __init__(self, window: float = SUPPRESSION_WINDOW) -> None:
        self._window = window
        self._lock = threading.Lock()
        self._entries: dict[Path, _SelfWrite] = {}

    @property
    def window(self) -> float:
        return self._window

    def begin(self, path: Path, *, agent_id: str, execution_id: int | None) -> None:
        """Claim *path* for *agent_id* before its content changes."""
        key = _key(path)
        now = time.monotonic()
        with self._lock:
            self._prune_locked(now)
            self._entries[key] = _SelfWrite(
                agent_id=agent_id,
                execution_id=execution_id,
                mtime_ns=None,
                recorded_at=now,
                settled=False,
            )

    def commit(self, path: Path, *, agent_id: str, execution_id: int | None) -> None:
        """Record the state *path* was left in, closing the claim."""
        key = _key(path)
        mtime = _mtime_ns(key)
        with self._lock:
            self._entries[key] = _SelfWrite(
                agent_id=agent_id,
                execution_id=execution_id,
                mtime_ns=mtime,
                recorded_at=time.monotonic(),
                settled=True,
            )

    def abandon(self, path: Path, *, agent_id: str) -> None:
        """Drop an unsettled claim after a write that failed.

        Only the writer's own unsettled entry is dropped: a committed entry
        describes a change that really is on disk, and another agent's entry was
        never ours to remove.
        """
        key = _key(path)
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and not entry.settled and entry.agent_id == agent_id:
                del self._entries[key]

    def is_self_write(self, path: Path, agent_id: str) -> bool:
        """True when *agent_id* is looking at a change it made itself."""
        key = _key(path)
        with self._lock:
            self._prune_locked(time.monotonic())
            entry = self._entries.get(key)
        if entry is None or entry.agent_id != agent_id:
            return False
        if not entry.settled:
            return True
        return _mtime_ns(key) == entry.mtime_ns

    def clear(self) -> None:
        """Forget every recorded write (tests, and workspace teardown)."""
        with self._lock:
            self._entries.clear()

    def _prune_locked(self, now: float) -> None:
        expired = [key for key, entry in self._entries.items() if now - entry.recorded_at > self._window]
        for key in expired:
            del self._entries[key]


def _key(path: Path) -> Path:
    """Normalise a path for ledger lookup.

    Both sides must agree: the tools hand over paths already resolved by
    ``validate_path``, while the watch handler resolves the raw event path. The
    memory tools build theirs from ``agents_dir``, which is not resolved, hence
    the second pass here. ``resolve`` is non-strict, so a deleted path still
    normalises.
    """
    return Path(path).resolve()


_LEDGER = SelfWriteLedger()


def process_ledger() -> SelfWriteLedger:
    """Return the ledger shared by this process's tools and watch handlers."""
    return _LEDGER


@contextmanager
def self_write(*paths):
    """Bracket a built-in tool's disk mutation so the writer's watchers skip it.

    A no-op outside an agent execution: a write that belongs to no agent cannot
    be a self-trigger, and there would be no ``agent_id`` to scope it to.

    Usage::

        with self_write(resolved):
            resolved.write_text(content)
    """
    from agent_md.sdk import _current_execution

    ctx = _current_execution()
    if ctx is None or getattr(ctx.agent_config, "id", None) is None:
        yield
        return

    agent_id = ctx.agent_config.id
    execution_id = ctx.execution_id
    ledger = process_ledger()
    targets = [Path(p) for p in paths]

    for target in targets:
        ledger.begin(target, agent_id=agent_id, execution_id=execution_id)
    try:
        yield
    except BaseException:
        for target in targets:
            ledger.abandon(target, agent_id=agent_id)
        raise
    else:
        for target in targets:
            ledger.commit(target, agent_id=agent_id, execution_id=execution_id)


__all__ = ["SUPPRESSION_WINDOW", "SelfWriteLedger", "process_ledger", "self_write"]
