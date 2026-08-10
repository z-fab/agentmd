"""Trigger enrichment — declared input, watch filters, and debounce.

Three constants used to live in code: hardcoded user prompts, no path filter
(so ``.DS_Store`` woke agents), and a fixed 500ms debounce. They are now
optional fields on ``TriggerConfig``. Filters decide whether a filesystem
event becomes a trigger; they do not live in ``check_admission``.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from agent_md.config.models import AgentConfig, TriggerConfig
from agent_md.execution.runner import AgentRunner
from agent_md.workspace.scheduler import _AgentWatchHandler, _path_matches_globs


# --- models ------------------------------------------------------------------


def test_trigger_defaults_preserve_prior_behaviour():
    cfg = TriggerConfig(type="manual")
    assert cfg.input is None
    assert cfg.filters is None
    assert cfg.debounce == 0.5


def test_debounce_accepts_seconds_float_and_duration_strings():
    assert TriggerConfig(type="manual", debounce=2.0).debounce == 2.0
    assert TriggerConfig(type="manual", debounce=2).debounce == 2.0
    assert TriggerConfig(type="manual", debounce="2s").debounce == 2.0
    assert TriggerConfig(type="manual", debounce="500ms").debounce == 0.5


def test_debounce_rejects_negative_and_garbage():
    with pytest.raises(ValidationError):
        TriggerConfig(type="manual", debounce=-1)
    with pytest.raises(ValidationError):
        TriggerConfig(type="manual", debounce="soon")


def test_filters_accept_string_or_list_and_nest_under_trigger():
    cfg = TriggerConfig(
        type="watch",
        paths=["./inbox"],
        filters={"include": "*.pdf", "exclude": [".DS_Store", "**/.git/**"]},
    )
    assert cfg.filters is not None
    assert cfg.filters.include == ["*.pdf"]
    assert cfg.filters.exclude == [".DS_Store", "**/.git/**"]


# --- filters in the watch handler (not the admission gate) -------------------


def _handler(watch_dir: Path, **kwargs) -> _AgentWatchHandler:
    return _AgentWatchHandler(
        "watcher",
        [watch_dir.resolve()],
        execute_fn=lambda *a, **k: None,
        loop=None,
        **kwargs,
    )


def test_without_filters_every_file_under_watch_is_relevant(tmp_path):
    watched = tmp_path / "inbox"
    watched.mkdir()
    (watched / ".DS_Store").write_text("")
    (watched / "report.pdf").write_text("x")
    handler = _handler(watched)
    assert handler._is_relevant(str(watched / ".DS_Store"))
    assert handler._is_relevant(str(watched / "report.pdf"))


def test_exclude_drops_ds_store_and_other_globs(tmp_path):
    watched = tmp_path / "inbox"
    watched.mkdir()
    (watched / ".DS_Store").write_text("")
    (watched / "scratch.tmp").write_text("")
    (watched / "report.pdf").write_text("x")
    handler = _handler(watched, exclude=[".DS_Store", "*.tmp"])
    assert not handler._is_relevant(str(watched / ".DS_Store"))
    assert not handler._is_relevant(str(watched / "scratch.tmp"))
    assert handler._is_relevant(str(watched / "report.pdf"))


def test_include_requires_a_matching_glob(tmp_path):
    watched = tmp_path / "inbox"
    watched.mkdir()
    (watched / "notes.txt").write_text("")
    (watched / "data.csv").write_text("")
    handler = _handler(watched, include=["*.csv", "*.pdf"])
    assert not handler._is_relevant(str(watched / "notes.txt"))
    assert handler._is_relevant(str(watched / "data.csv"))


def test_exclude_wins_over_include(tmp_path):
    watched = tmp_path / "inbox"
    watched.mkdir()
    (watched / "keep.csv").write_text("")
    (watched / "drop.csv").write_text("")
    handler = _handler(watched, include=["*.csv"], exclude=["drop.csv"])
    assert handler._is_relevant(str(watched / "keep.csv"))
    assert not handler._is_relevant(str(watched / "drop.csv"))


def test_path_matches_globs_on_basename_and_absolute():
    path = Path("/tmp/inbox/report.PDF")
    # basename patterns are case-sensitive via fnmatch — use exact name
    assert _path_matches_globs(Path("/tmp/inbox/report.pdf"), ["*.pdf"])
    assert _path_matches_globs(path, ["report.PDF"])
    assert not _path_matches_globs(path, ["*.csv"])


# --- debounce ----------------------------------------------------------------


class _FakeHandle:
    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class _FakeLoop:
    """Stands in for the event loop, running handovers inline.

    ``_schedule_trigger`` no longer arms the timer itself — it hands the work to
    the loop thread. Running the callback inline keeps these tests synchronous
    while exercising the real path.
    """

    def __init__(self):
        self.calls: list[tuple[float, object, tuple]] = []

    def call_later(self, delay, callback, *args):
        handle = _FakeHandle()
        self.calls.append((delay, callback, args))
        return handle

    def call_soon_threadsafe(self, callback, *args):
        callback(*args)
        return _FakeHandle()


def _make_event(path: Path, event_type: str = "modified"):
    return SimpleNamespace(
        event_type=event_type,
        src_path=str(path),
        dest_path=str(path),
        is_directory=False,
    )


def test_default_debounce_is_half_a_second(tmp_path):
    watched = tmp_path / "inbox"
    watched.mkdir()
    target = watched / "a.txt"
    target.write_text("x")
    loop = _FakeLoop()
    handler = _AgentWatchHandler("w", [watched.resolve()], lambda *a, **k: None, loop)
    handler._schedule_trigger(_make_event(target))
    assert len(loop.calls) == 1
    assert loop.calls[0][0] == 0.5


def test_declared_debounce_is_the_call_later_delay(tmp_path):
    watched = tmp_path / "inbox"
    watched.mkdir()
    target = watched / "a.txt"
    target.write_text("x")
    loop = _FakeLoop()
    handler = _AgentWatchHandler(
        "w",
        [watched.resolve()],
        lambda *a, **k: None,
        loop,
        debounce=2.0,
    )
    handler._schedule_trigger(_make_event(target))
    assert len(loop.calls) == 1
    assert loop.calls[0][0] == 2.0


def test_debounce_collapses_rapid_events_for_same_path(tmp_path):
    watched = tmp_path / "inbox"
    watched.mkdir()
    target = watched / "a.txt"
    target.write_text("x")
    loop = _FakeLoop()
    handler = _AgentWatchHandler(
        "w",
        [watched.resolve()],
        lambda *a, **k: None,
        loop,
        debounce=1.5,
    )
    handler._schedule_trigger(_make_event(target))
    first_handle = handler._debounce_timers[target.resolve()]
    handler._schedule_trigger(_make_event(target))
    assert first_handle.cancelled is True
    assert len(loop.calls) == 2
    assert all(delay == 1.5 for delay, _, _ in loop.calls)


def test_scheduler_passes_config_debounce_and_filters_to_handler(tmp_path, monkeypatch):
    """``_add_watch_handler`` must forward trigger.filters and trigger.debounce.

    A mutation that hardcodes 0.5 or drops filters here would leave unit tests
    on the handler alone green — this asserts the wiring from config.
    """
    from agent_md.workspace.path_context import PathContext
    from agent_md.workspace.registry import AgentRegistry
    from agent_md.workspace.scheduler import AgentScheduler

    agents = tmp_path / "agents"
    agents.mkdir()
    watched = tmp_path / "inbox"
    watched.mkdir()

    captured: dict = {}

    def fake_init(self, agent_id, watch_paths, execute_fn, loop, **kwargs):
        captured["include"] = kwargs.get("include")
        captured["exclude"] = kwargs.get("exclude")
        captured["debounce"] = kwargs.get("debounce")
        self.agent_id = agent_id
        self.watch_paths = watch_paths
        self._execute_fn = execute_fn
        self._loop = loop

    monkeypatch.setattr(
        "agent_md.workspace.scheduler._AgentWatchHandler.__init__",
        fake_init,
    )
    monkeypatch.setattr(
        "agent_md.workspace.scheduler.Observer.schedule",
        lambda self, handler, path, recursive=False: object(),
    )

    path_context = PathContext(
        workspace_root=tmp_path,
        agents_dir=agents,
        db_path=tmp_path / "db.db",
        mcp_config=agents / "_config" / "mcp-servers.json",
        tools_dir=agents / "_config" / "tools",
        skills_dir=agents / "_config" / "skills",
    )
    sched = AgentScheduler(registry=AgentRegistry(), runner=SimpleNamespace(), path_context=path_context)
    config = AgentConfig(
        name="watcher",
        model={"provider": "google", "name": "x"},
        trigger={
            "type": "watch",
            "paths": [str(watched)],
            "debounce": 2.5,
            "filters": {"include": ["*.pdf"], "exclude": [".DS_Store"]},
        },
    )
    sched._add_watch_handler(config)
    assert captured["debounce"] == 2.5
    assert captured["include"] == ["*.pdf"]
    assert captured["exclude"] == [".DS_Store"]


# --- arming the timer from the watchdog thread -------------------------------


IDLE_SLEEP = 1.0
"""How long the loop stays idle while a foreign thread arms the timer.

Comfortably longer than the debounce below, so a timer that fails to wake the
loop shows up as a delay of roughly this value instead of the nominal window.
"""

FAST_DEBOUNCE = 0.05
NOMINAL_WINDOW = 0.3
"""Upper bound on the measured delay: the debounce plus generous scheduling slack."""


def _record_execute(stamps: list[float], done: asyncio.Event):
    """An ``execute_fn`` that timestamps the moment ``_trigger_agent`` calls it."""

    async def _noop():
        return None

    def execute(agent_id, trigger_type, trigger_context=None):
        stamps.append(time.monotonic())
        done.set()
        return _noop()

    return execute


async def test_timer_armed_from_another_thread_fires_within_its_window(tmp_path):
    """The delay must be the debounce, not however long the loop happens to sleep.

    ``call_later`` is not thread-safe and does not wake a sleeping loop: the
    timer lands in the heap while ``select`` is still blocked on a timeout it
    computed before the timer existed. Measured on the unfixed code, a 50ms
    debounce armed against a loop sleeping for 3s fired at 3.003s.

    This asserts the *measured* delay, because a test that only checks the
    callback eventually ran passes on the broken code too.
    """
    watched = tmp_path / "inbox"
    watched.mkdir()
    target = watched / "a.txt"
    target.write_text("x")

    stamps: list[float] = []
    done = asyncio.Event()
    handler = _AgentWatchHandler(
        "w",
        [watched.resolve()],
        _record_execute(stamps, done),
        asyncio.get_running_loop(),
        debounce=FAST_DEBOUNCE,
    )

    armed: list[float] = []

    def arm():
        # Wait for the loop to be blocked in select before arming; arming before
        # it sleeps would let it fold the timer into its own timeout and hide
        # the bug.
        time.sleep(0.2)
        armed.append(time.monotonic())
        handler._schedule_trigger(_make_event(target))

    thread = threading.Thread(target=arm)
    thread.start()
    try:
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(done.wait(), IDLE_SLEEP)
    finally:
        thread.join(timeout=5)

    assert stamps, f"the timer never fired within {IDLE_SLEEP}s"
    delay = stamps[0] - armed[0]
    assert delay < NOMINAL_WINDOW, f"timer armed from another thread fired {delay:.3f}s later"


async def test_scheduling_from_another_thread_touches_no_state_in_that_thread(tmp_path):
    """``_debounce_timers`` and ``_pending_contexts`` belong to the loop thread.

    The watchdog thread only hands the event over; both dicts must still be
    untouched when its call returns, and populated once the loop has run.
    """
    watched = tmp_path / "inbox"
    watched.mkdir()
    target = watched / "a.txt"
    target.write_text("x")

    handler = _AgentWatchHandler(
        "w",
        [watched.resolve()],
        _record_execute([], asyncio.Event()),
        asyncio.get_running_loop(),
        debounce=10.0,
    )

    thread = threading.Thread(target=handler._schedule_trigger, args=(_make_event(target),))
    thread.start()
    thread.join(timeout=5)

    assert handler._debounce_timers == {}
    assert handler._pending_contexts == {}

    await asyncio.sleep(0)  # let the loop drain the handover
    assert list(handler._debounce_timers) == [target.resolve()]
    assert list(handler._pending_contexts) == [target.resolve()]

    handler._debounce_timers[target.resolve()].cancel()


async def test_rapid_events_from_the_watchdog_thread_still_collapse_to_one_timer(tmp_path):
    """The cancel moved into the loop thread; it must still cancel exactly one.

    Both events are handed over before the loop runs either handover, so this is
    the interleaving that would leave two live timers if the cancel and the arm
    were not done together inside the loop thread.
    """
    watched = tmp_path / "inbox"
    watched.mkdir()
    target = watched / "a.txt"
    target.write_text("x")

    stamps: list[float] = []
    done = asyncio.Event()
    handler = _AgentWatchHandler(
        "w",
        [watched.resolve()],
        _record_execute(stamps, done),
        asyncio.get_running_loop(),
        debounce=FAST_DEBOUNCE,
    )

    def arm_twice():
        handler._schedule_trigger(_make_event(target))
        handler._schedule_trigger(_make_event(target, "created"))

    thread = threading.Thread(target=arm_twice)
    thread.start()
    thread.join(timeout=5)

    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(done.wait(), IDLE_SLEEP)
    await asyncio.sleep(FAST_DEBOUNCE * 3)  # a second timer would have fired by now

    assert len(stamps) == 1, f"debounce armed {len(stamps)} triggers for one path"
    assert handler._debounce_timers == {}
    assert handler._pending_contexts == {}


# --- trigger.input × trigger_context -----------------------------------------


def _cfg(**trigger_kwargs) -> AgentConfig:
    trigger = {"type": "manual", **trigger_kwargs}
    return AgentConfig(name="t", model={"provider": "google", "name": "x"}, trigger=trigger)


def test_absent_input_keeps_hardcoded_prompts_and_phase3_context():
    runner = AgentRunner.__new__(AgentRunner)
    config = _cfg()
    assert runner._build_user_input("manual", None, config) == "Execute your task."
    assert runner._build_user_input("manual", "from a webhook", config) == "Execute your task. (from a webhook)"
    assert runner._build_user_input("chat", "from a webhook", config) == "Execute your task. (from a webhook)"


def test_declared_input_replaces_hardcoded_base_and_appends_context():
    """Template replaces the hardcoded string; Phase 3 context still appends."""
    runner = AgentRunner.__new__(AgentRunner)
    config = _cfg(input="Summarise the invoice.")
    assert runner._build_user_input("manual", None, config) == "Summarise the invoice."
    assert runner._build_user_input("manual", "from a webhook", config) == "Summarise the invoice. (from a webhook)"
    assert runner._build_user_input("chat", "invoice #42", config) == "Summarise the invoice. (invoice #42)"


def test_context_placeholder_absorbs_trigger_context_without_double_append():
    runner = AgentRunner.__new__(AgentRunner)
    config = _cfg(input="Handle this: {context}")
    assert runner._build_user_input("manual", "from a webhook", config) == "Handle this: from a webhook"
    assert runner._build_user_input("manual", None, config) == "Handle this: "


def test_watch_input_template_receives_event_and_path_placeholders():
    runner = AgentRunner.__new__(AgentRunner)
    config = AgentConfig(
        name="w",
        model={"provider": "google", "name": "x"},
        trigger={
            "type": "watch",
            "paths": ["./inbox"],
            "input": "Event={event} File={path} Raw={context}",
        },
    )
    out = runner._build_user_input("watch", "modified: /tmp/inbox/a.pdf", config)
    assert out == "Event=modified File=/tmp/inbox/a.pdf Raw=modified: /tmp/inbox/a.pdf"


def test_watch_input_without_placeholders_is_used_as_is():
    runner = AgentRunner.__new__(AgentRunner)
    config = AgentConfig(
        name="w",
        model={"provider": "google", "name": "x"},
        trigger={"type": "watch", "paths": ["./inbox"], "input": "Process the inbox change."},
    )
    assert runner._build_user_input("watch", "modified: /tmp/x", config) == "Process the inbox change."


def test_schedule_input_template_replaces_hardcoded_schedule_prompt():
    runner = AgentRunner.__new__(AgentRunner)
    config = AgentConfig(
        name="s",
        model={"provider": "google", "name": "x"},
        trigger={"type": "schedule", "every": "30m", "input": "Run the {schedule} digest."},
    )
    assert runner._build_user_input("schedule", None, config) == "Run the every 30m digest."
