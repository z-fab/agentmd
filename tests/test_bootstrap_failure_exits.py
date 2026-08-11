"""A `start` that fails during bootstrap must die, not hang holding the database.

The production failure (#17): `agentmd start` lost a race for the database,
printed ``sqlite3.OperationalError: database is locked`` followed by uvicorn's
"Application startup failed. Exiting." — and then stayed alive for minutes,
still holding the file. The next `start` hit the same lock, in cascade.

The mechanism is aiosqlite's connection thread. It is a plain non-daemon
``Thread``: once ``aiosqlite.connect()`` has returned, the interpreter joins
that thread at exit and blocks forever unless someone closes the connection.
Three places dropped it on the floor:

* ``Database.connect()`` opened the connection and then ran ``PRAGMA`` /
  ``executescript`` / ``_migrate``. A failure in any of those propagated with
  the connection — and its thread — still open.
* ``bootstrap()`` held the only reference to a connected ``Database`` until it
  returned a ``Runtime``; anything that raised in between lost it.
* ``_lifespan`` had no ``try``/``finally`` around its ``yield``, so a startup
  that raised never reached ``rt.aclose()``.

The acceptance criterion is wall clock, not wording: an error message proves
nothing while the process that printed it is still running. So the last test
here spawns a real backend against a locked database and asserts the *process*
is gone, with a non-zero exit status.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from agent_md.api.app import create_app
from agent_md.db.database import Database
from agent_md.workspace import bootstrap as bootstrap_mod

# aiosqlite inherits sqlite3's 5s busy timeout, so the failure is not instant.
# This only has to outlast that plus a cold interpreter start; a backend that
# hangs fails the test rather than stalling CI.
START_EXIT_TIMEOUT = 45.0


# --- helpers ------------------------------------------------------------------


def _aiosqlite_threads() -> set[threading.Thread]:
    """Live aiosqlite connection worker threads.

    Identified by target function rather than by name: they are unnamed
    ``Thread-N`` workers, and counting all threads would be hostage to whatever
    else the suite happens to have running.
    """
    from aiosqlite.core import _connection_worker_thread

    return {t for t in threading.enumerate() if getattr(t, "_target", None) is _connection_worker_thread}


def _assert_no_leaked_connection(before: set[threading.Thread], *, timeout: float = 5.0) -> None:
    """No aiosqlite worker outlives the failure — that thread is what hangs exit."""
    deadline = time.monotonic() + timeout
    leaked = _aiosqlite_threads() - before
    while leaked and time.monotonic() < deadline:
        time.sleep(0.05)
        leaked = _aiosqlite_threads() - before
    assert not leaked, (
        f"{len(leaked)} aiosqlite connection thread(s) survived the failure; "
        "each one is non-daemon and will block interpreter shutdown"
    )


def _lock_exclusively(db_path: Path) -> sqlite3.Connection:
    """Hold an EXCLUSIVE lock on *db_path*, the way a competing backend would.

    ``journal_mode=DELETE`` is deliberate: it is what makes the victim's very
    first statement — ``PRAGMA journal_mode=WAL`` — fail, which is exactly where
    the reported traceback lands.
    """
    holder = sqlite3.connect(str(db_path))
    holder.execute("PRAGMA journal_mode=DELETE")
    holder.execute("BEGIN EXCLUSIVE")
    holder.execute("CREATE TABLE IF NOT EXISTS lock_probe(a)")
    return holder


@pytest.fixture
def impatient_sqlite(monkeypatch):
    """Cut sqlite's 5s busy retry to 0.2s.

    In-process only, and never for the subprocess test — how long sqlite waits
    before giving up is not what any of this is about, but paid four times over
    it is most of these tests' runtime.
    """
    import aiosqlite

    real_connect = aiosqlite.connect

    def _quick(*args, **kwargs):
        kwargs.setdefault("timeout", 0.2)
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(aiosqlite, "connect", _quick)


@pytest.fixture
def locked_db(tmp_path, impatient_sqlite):
    """A database file another connection holds exclusively. Yields its path."""
    db_path = tmp_path / "locked.db"
    holder = _lock_exclusively(db_path)
    try:
        yield db_path
    finally:
        holder.rollback()
        holder.close()


@pytest.fixture
def bootstrapped_databases(monkeypatch):
    """Every ``Database`` bootstrap builds, kept referenced. Yields the list.

    The reference matters. An abandoned ``aiosqlite.Connection`` stops its own
    worker thread from ``__del__``, so a test that only counted live threads
    would go green whenever CPython happened to collect the leak first — passing
    against the exact bug it exists to catch.
    """
    created: list[Database] = []

    class _Tracked(Database):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self)

    monkeypatch.setattr(bootstrap_mod, "Database", _Tracked)
    return created


def _assert_all_closed(databases: list[Database]) -> None:
    assert databases, "nothing was constructed — the test is not exercising what it thinks"
    open_ones = [d for d in databases if d._db is not None]
    assert not open_ones, f"{len(open_ones)} Database(s) left connected after the failure: {open_ones}"


# --- Database.connect ---------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_closes_the_connection_it_opened_when_a_pragma_fails(locked_db):
    """The reported entry point: `PRAGMA journal_mode=WAL` on a busy database."""
    before = _aiosqlite_threads()
    database = Database(locked_db)

    with pytest.raises(sqlite3.OperationalError, match="locked"):
        await database.connect()

    _assert_no_leaked_connection(before)


@pytest.mark.asyncio
async def test_connect_closes_the_connection_when_migration_fails(tmp_path, monkeypatch):
    """The last step of connect() is as capable of failing as the first."""

    class Boom(Exception):
        pass

    async def _explode(self, db):
        raise Boom("migration failed")

    monkeypatch.setattr(Database, "_migrate", _explode)

    before = _aiosqlite_threads()
    database = Database(tmp_path / "t.db")

    with pytest.raises(Boom, match="migration failed"):
        await database.connect()

    _assert_no_leaked_connection(before)


@pytest.mark.asyncio
async def test_connect_reports_the_original_error_even_when_the_close_fails(tmp_path, monkeypatch):
    """Cleanup must never become the error the user sees.

    If closing the half-open connection is allowed to raise on the way out, it
    replaces ``database is locked`` with something unrelated and the operator
    debugs the wrong thing.
    """
    import aiosqlite

    class Boom(Exception):
        pass

    opened: list[aiosqlite.Connection] = []
    real_close = aiosqlite.Connection.close

    async def _refuse_to_close(self):
        opened.append(self)
        raise RuntimeError("close is broken too")

    async def _explode(self, db):
        raise Boom("original")

    monkeypatch.setattr(Database, "_migrate", _explode)
    monkeypatch.setattr(aiosqlite.Connection, "close", _refuse_to_close)

    database = Database(tmp_path / "t.db")
    try:
        with pytest.raises(Boom, match="original"):
            await database.connect()
    finally:
        # The close genuinely failed, so nothing else will reap these threads.
        monkeypatch.undo()
        for conn in opened:
            await real_close(conn)


@pytest.mark.asyncio
async def test_connect_leaves_no_half_open_database_behind(locked_db):
    """After a failed connect the object must look unconnected, not half-open."""
    database = Database(locked_db)

    with pytest.raises(sqlite3.OperationalError):
        await database.connect()

    with pytest.raises(RuntimeError, match="not connected"):
        _ = database.db


# --- bootstrap ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_bootstrap_closes_the_database_when_a_later_step_fails(tmp_path, monkeypatch, bootstrapped_databases):
    """`Database.connect()` succeeding is not the end of the risk window.

    Everything bootstrap does after it — the orphan sweep, the scheduler — can
    raise, and until the ``Runtime`` is returned nobody else holds a reference
    with which to close the database.
    """

    class Boom(Exception):
        pass

    async def _explode(_db):
        raise Boom("sweep failed")

    monkeypatch.setattr(bootstrap_mod, "sweep_orphans", _explode)

    before = _aiosqlite_threads()

    with pytest.raises(Boom, match="sweep failed"):
        await bootstrap_mod.bootstrap(workspace=tmp_path, db_path=tmp_path / "t.db")

    _assert_all_closed(bootstrapped_databases)
    _assert_no_leaked_connection(before)


@pytest.mark.asyncio
async def test_runtime_aclose_closes_the_database_even_when_a_component_fails(tmp_path):
    """A broken runner must not cost us the database close.

    ``aclose()`` runs over a runtime assembled from parts in unknown states.
    Sequencing the steps so that one failure skips the rest is how a shutdown
    path turns into the very leak it exists to prevent.
    """
    rt = await bootstrap_mod.bootstrap(workspace=tmp_path, db_path=tmp_path / "t.db")

    async def _explode():
        raise RuntimeError("runner refused to close")

    rt.runner.aclose = _explode

    await rt.aclose()

    assert rt.db._db is None, "the database stayed open because an earlier cleanup step failed"


# --- _lifespan ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_lifespan_shuts_down_when_the_body_raises(tmp_path):
    """Cleanup belongs in `finally`, not after the `yield`.

    This is also why tests were told never to assert inside ``async with
    lifespan_context(...)``: the failed assertion propagated through the
    generator and the backend's ``Database`` was never closed.
    """

    class Boom(Exception):
        pass

    app = create_app(workspace=tmp_path, db_path=tmp_path / "t.db")

    with pytest.raises(Boom):
        async with app.router.lifespan_context(app):
            raise Boom()

    assert app.state.runtime.db._db is None, "lifespan skipped shutdown because the body raised"


@pytest.mark.asyncio
async def test_lifespan_startup_failure_surfaces_the_original_error(tmp_path, bootstrapped_databases, impatient_sqlite):
    """A locked database must be reported as a locked database.

    Shutdown now runs on the failure path too, and anything it raises would be
    layered on top of — and hide — the reason startup failed.
    """
    before = _aiosqlite_threads()
    db_path = tmp_path / "t.db"
    app = create_app(workspace=tmp_path, db_path=db_path)

    holder = _lock_exclusively(db_path)
    try:
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            async with app.router.lifespan_context(app):
                pass
    finally:
        holder.rollback()
        holder.close()

    _assert_all_closed(bootstrapped_databases)
    _assert_no_leaked_connection(before)


# --- the real process ---------------------------------------------------------


def test_start_exits_when_the_database_is_locked(tmp_path):
    """The acceptance criterion, measured on the process itself.

    Asserting on the error text would pass with the bug fully present: the old
    build printed every word correctly and then sat there holding the file.
    Only the process actually terminating tells the two apart.
    """
    home = tmp_path / "home"
    state = tmp_path / "state"
    workspace = tmp_path / "ws"
    for d in (home, state / "agentmd", workspace / "agents"):
        d.mkdir(parents=True)

    holder = _lock_exclusively(state / "agentmd" / "agentmd.db")
    env = {**os.environ, "HOME": str(home), "XDG_STATE_HOME": str(state)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "agent_md.main", "start", "--internal-backend", "--workspace", str(workspace)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    started = time.monotonic()
    try:
        try:
            output = proc.communicate(timeout=START_EXIT_TIMEOUT)[0]
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            pytest.fail(
                f"`start` never exited: still alive {START_EXIT_TIMEOUT}s after failing to open a locked database"
            )
    finally:
        if proc.poll() is None:
            proc.kill()
        holder.rollback()
        holder.close()

    elapsed = time.monotonic() - started
    assert proc.returncode != 0, f"a backend that never started reported success (rc=0) after {elapsed:.1f}s:\n{output}"
    assert "database is locked" in output, f"the original error did not survive the shutdown path:\n{output}"
