"""Admission gate — the single point that decides whether a trigger may run.

Three defects lived in the absence of this gate, and each one failed silently:

1. ``pause()`` paused APScheduler and set a flag nothing read, so a
   ``trigger: watch`` agent kept firing while the API reported "paused".
2. The ``on_pending: skip`` rule was written twice — once in the scheduler, once
   in the run endpoint — so the two could drift apart without a test noticing.
3. Idle-shutdown counted APScheduler jobs only, so a watch-only workspace looked
   idle and the backend died with its watchers after five minutes.

None of the three breaks anything loudly: an agent stops firing, or fires when it
should not, and the data is simply missing later. Hence the coverage here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_md.config.models import AgentConfig
from agent_md.workspace.path_context import PathContext
from agent_md.workspace.registry import AgentRegistry
from agent_md.workspace.scheduler import AgentScheduler, check_admission

TRIGGER_DRIVEN = ("schedule", "watch")
USER_DRIVEN = ("manual", "chat")


@pytest.fixture
async def db(tmp_path):
    """A connected Database closed in teardown, never at the end of a test body.

    aiosqlite runs the connection on a non-daemon thread: a Database left open
    keeps the interpreter alive at exit, so a failing test would hang pytest
    instead of reporting the failure.
    """
    from agent_md.db.database import Database

    database = Database(tmp_path / "gate.db")
    await database.connect()
    try:
        yield database
    finally:
        await database.close()


def _agent(**kwargs) -> AgentConfig:
    kwargs.setdefault("name", "watcher")
    kwargs.setdefault("model", {"provider": "google", "name": "x"})
    return AgentConfig(**kwargs)


def _path_context(tmp_path: Path) -> PathContext:
    agents = tmp_path / "agents"
    agents.mkdir(exist_ok=True)
    return PathContext(
        workspace_root=tmp_path,
        agents_dir=agents,
        db_path=tmp_path / "db.db",
        mcp_config=agents / "_config" / "mcp-servers.json",
        tools_dir=agents / "_config" / "tools",
        skills_dir=agents / "_config" / "skills",
    )


class _RecordingRunner:
    """Stands in for AgentRunner: records what the gate let through."""

    def __init__(self, database):
        self.db = database
        self.runs: list[tuple[str, str]] = []

    async def run(self, config, trigger_type=None, **kwargs):
        self.runs.append((config.id, trigger_type))
        return {"status": "success"}


@pytest.fixture
async def make_scheduler(tmp_path, db):
    """Factory for AgentSchedulers, each shut down in teardown.

    APScheduler is started because that is its real state wherever ``pause()`` is
    reachable — it refuses to pause while stopped. The watchdog ``Observer`` is
    left unstarted: ``observer.schedule()`` only starts an emitter thread once the
    observer is alive, so watch handlers register with no thread to join.
    """
    created: list[AgentScheduler] = []

    def factory(registry=None) -> AgentScheduler:
        sched = AgentScheduler(
            registry=registry if registry is not None else AgentRegistry(),
            runner=_RecordingRunner(db),
            path_context=_path_context(tmp_path),
        )
        sched.scheduler.start()
        created.append(sched)
        return sched

    try:
        yield factory
    finally:
        for sched in created:
            sched.stop()


def _watch_agent(tmp_path: Path) -> AgentConfig:
    watched = tmp_path / "inbox"
    watched.mkdir(exist_ok=True)
    return _agent(trigger={"type": "watch", "paths": [str(watched)]})


# --- The decision itself -----------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger_type", TRIGGER_DRIVEN)
async def test_pause_refuses_every_trigger_driven_type(db, trigger_type):
    """`watch` is the one that used to slip through — it must be refused too."""
    reason = await check_admission(_agent(), db, trigger_type=trigger_type, paused=True)
    assert reason is not None
    assert "paused" in reason


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger_type", USER_DRIVEN)
async def test_pause_still_admits_user_driven_runs(db, trigger_type):
    """Pausing the scheduler must not disable the run button."""
    assert await check_admission(_agent(), db, trigger_type=trigger_type, paused=True) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger_type", TRIGGER_DRIVEN)
async def test_disabled_agent_is_refused_on_triggers(db, trigger_type):
    reason = await check_admission(_agent(enabled=False), db, trigger_type=trigger_type)
    assert reason is not None
    assert "disabled" in reason


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger_type", USER_DRIVEN)
async def test_disabled_agent_can_still_be_run_by_hand(db, trigger_type):
    """Pre-existing behaviour: POST /run never consulted `enabled`. Kept."""
    assert await check_admission(_agent(enabled=False), db, trigger_type=trigger_type) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger_type", TRIGGER_DRIVEN + USER_DRIVEN)
async def test_waiting_session_refuses_every_trigger_type_identically(db, trigger_type):
    """The concurrency rule is one rule: same answer whoever asks.

    This is the property the duplicated check could not guarantee — the scheduler
    and the endpoint each had their own copy. Everything here is sessionless, so
    every caller is asking about the same conversation.
    """
    config = _agent(on_pending="skip")
    await db.create_execution(config.id, "manual", status="waiting")

    reason = await check_admission(config, db, trigger_type=trigger_type)
    assert reason == "a previous run is waiting for a response"


@pytest.mark.asyncio
async def test_on_pending_parallel_admits_alongside_a_waiting_session(db):
    config = _agent(on_pending="parallel")
    await db.create_execution(config.id, "manual", status="waiting")

    assert await check_admission(config, db, trigger_type="schedule") is None


@pytest.mark.asyncio
async def test_admitted_when_nothing_stands_in_the_way(db):
    assert await check_admission(_agent(), db, trigger_type="schedule") is None


# --- Scope of the concurrency rule: the conversation, not the agent ----------
#
# `on_pending` predates sessions. It was written when an agent had exactly one
# line of conversation, so "a run of this agent is waiting" and "the conversation
# you are addressing is waiting" were the same sentence. Sessions split them, and
# the check kept the agent-wide reading: one unanswered HILT in a chat closed
# hours ago refused every later chat, on a session that had never asked anything.
#
# The unit is now the conversation. Sessionless executions — manual, schedule,
# watch — share one bucket, the same `session_id IS NULL` bucket history seeding
# and checkpoint retention already treat as a single line.


@pytest.mark.asyncio
async def test_a_waiting_chat_does_not_block_a_different_chat(db):
    """The reported defect: a new session inherits nothing from a stale one."""
    config = _agent(on_pending="skip")
    await db.create_execution(config.id, "chat", status="waiting", session_id="old-session")

    assert await check_admission(config, db, trigger_type="chat", session_id="new-session") is None


@pytest.mark.asyncio
async def test_a_waiting_chat_blocks_its_own_next_turn(db):
    """Within one conversation the rule stands: this dialogue is waiting on you."""
    config = _agent(on_pending="skip")
    await db.create_execution(config.id, "chat", status="waiting", session_id="s1")

    reason = await check_admission(config, db, trigger_type="chat", session_id="s1")
    assert reason == "this conversation is waiting for a response"


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger_type", TRIGGER_DRIVEN + ("manual",))
async def test_a_waiting_chat_does_not_block_sessionless_runs(db, trigger_type):
    config = _agent(on_pending="skip")
    await db.create_execution(config.id, "chat", status="waiting", session_id="s1")

    assert await check_admission(config, db, trigger_type=trigger_type) is None


@pytest.mark.asyncio
async def test_a_waiting_sessionless_run_does_not_block_a_chat(db):
    """The converse direction. A parked `agentmd run` is not this chat's business."""
    config = _agent(on_pending="skip")
    await db.create_execution(config.id, "manual", status="waiting")

    assert await check_admission(config, db, trigger_type="chat", session_id="s1") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger_type", TRIGGER_DRIVEN)
async def test_automatic_triggers_ignore_a_session_id(db, trigger_type):
    """Parity with ``AgentRunner.run``, which drops a session_id on these triggers.

    A schedule firing is not a turn in anyone's dialogue. If the gate honoured a
    session id the runner then discards, admission and execution would be judging
    two different conversations.
    """
    config = _agent(on_pending="skip")
    await db.create_execution(config.id, "manual", status="waiting")

    reason = await check_admission(config, db, trigger_type=trigger_type, session_id="s1")
    assert reason == "a previous run is waiting for a response"


@pytest.mark.asyncio
async def test_on_pending_parallel_admits_within_the_same_session(db):
    """`parallel` still means parallel — the narrower scope does not re-block it."""
    config = _agent(on_pending="parallel")
    await db.create_execution(config.id, "chat", status="waiting", session_id="s1")

    assert await check_admission(config, db, trigger_type="chat", session_id="s1") is None


# --- The funnel: _execute_agent is where both trigger sources land ------------


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger_type", TRIGGER_DRIVEN)
async def test_paused_scheduler_creates_no_execution(db, make_scheduler, trigger_type):
    """Refused before ``create_execution``: a dropped trigger leaves no row."""
    registry = AgentRegistry()
    registry.register(_agent())
    sched = make_scheduler(registry)
    sched.pause()

    await sched._execute_agent("watcher", trigger_type)

    assert sched.runner.runs == []
    assert await db.get_executions("watcher") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger_type", TRIGGER_DRIVEN)
async def test_resume_readmits_both_trigger_sources(make_scheduler, trigger_type):
    registry = AgentRegistry()
    registry.register(_agent())
    sched = make_scheduler(registry)
    sched.pause()
    await sched._execute_agent("watcher", trigger_type)
    assert sched.runner.runs == []

    sched.resume()
    await sched._execute_agent("watcher", trigger_type)

    assert sched.runner.runs == [("watcher", trigger_type)]


@pytest.mark.asyncio
async def test_watch_trigger_runs_normally_when_not_paused(db, make_scheduler):
    registry = AgentRegistry()
    registry.register(_agent())
    sched = make_scheduler(registry)

    await sched._execute_agent("watcher", "watch", trigger_context="modified: /tmp/x")

    assert sched.runner.runs == [("watcher", "watch")]
    assert len(await db.get_executions("watcher")) == 1


@pytest.mark.asyncio
async def test_waiting_session_skips_the_trigger(db, make_scheduler):
    registry = AgentRegistry()
    registry.register(_agent(on_pending="skip"))
    sched = make_scheduler(registry)
    await db.create_execution("watcher", "manual", status="waiting")

    await sched._execute_agent("watcher", "schedule")

    assert sched.runner.runs == []


@pytest.mark.asyncio
async def test_disabled_agent_skips_the_trigger(make_scheduler):
    registry = AgentRegistry()
    registry.register(_agent(enabled=False))
    sched = make_scheduler(registry)

    await sched._execute_agent("watcher", "watch")

    assert sched.runner.runs == []


@pytest.mark.asyncio
async def test_unknown_agent_is_dropped(make_scheduler):
    sched = make_scheduler()

    await sched._execute_agent("ghost", "schedule")

    assert sched.runner.runs == []


# --- Liveness: what counts as an active trigger source -----------------------


@pytest.mark.asyncio
async def test_watch_only_workspace_is_not_idle(tmp_path, make_scheduler):
    """The whole point: no APScheduler job, still very much alive."""
    config = _watch_agent(tmp_path)
    registry = AgentRegistry()
    registry.register(config)
    sched = make_scheduler(registry)
    sched.schedule_agent(config)  # watch agents get no job, by design

    sched._add_watch_handler(config)

    assert sched.scheduler.get_jobs() == []
    assert sched.has_active_triggers() is True


@pytest.mark.asyncio
async def test_scheduled_agent_is_not_idle(make_scheduler):
    config = _agent(trigger={"type": "schedule", "every": "5m"})
    registry = AgentRegistry()
    registry.register(config)
    sched = make_scheduler(registry)

    sched.schedule_agent(config)

    assert sched.has_active_triggers() is True


@pytest.mark.asyncio
async def test_workspace_without_triggers_is_idle(make_scheduler):
    sched = make_scheduler()
    assert sched.has_active_triggers() is False


@pytest.mark.asyncio
async def test_removing_the_last_watcher_makes_the_workspace_idle(tmp_path, make_scheduler):
    config = _watch_agent(tmp_path)
    sched = make_scheduler()
    sched._add_watch_handler(config)
    assert sched.has_active_triggers() is True

    sched.unschedule_agent(config.id)

    assert sched.has_active_triggers() is False


@pytest.mark.asyncio
async def test_paused_workspace_stays_alive(tmp_path, make_scheduler):
    """Pause is temporary; the backend has to survive it to be resumable."""
    sched = make_scheduler()
    sched._add_watch_handler(_watch_agent(tmp_path))

    sched.pause()

    assert sched.has_active_triggers() is True


@pytest.mark.asyncio
async def test_app_lifecycle_sees_a_watch_only_workspace(tmp_path):
    """The wiring, end to end — the defect lived in the lambda, not in the class.

    A workspace whose only agent is `trigger: watch` has no APScheduler job, so
    the old ``bool(get_jobs())`` reported idle and the five-minute shutdown took
    the watchers with it.
    """
    from agent_md.api.app import create_app

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    watched = tmp_path / "inbox"
    watched.mkdir()
    (agents_dir / "watcher.md").write_text(
        "---\n"
        "name: watcher\n"
        "model:\n  provider: google\n  name: gemini-2.5-flash\n"
        f"trigger:\n  type: watch\n  paths: [{watched}]\n"
        "---\nYou watch files.\n",
        encoding="utf-8",
    )

    app = create_app(
        workspace=tmp_path,
        agents_dir=agents_dir,
        db_path=tmp_path / "app.db",
        start_scheduler=True,
    )
    async with app.router.lifespan_context(app):
        jobs = app.state.runtime.scheduler.get_jobs()
        active = app.state.lifecycle.has_active_triggers()
        idle = await app.state.lifecycle._is_idle()

    # Asserted after the lifespan closes, deliberately. `_lifespan` has no
    # try/finally around its `yield`, so an exception raised inside this `async
    # with` propagates out before `rt.aclose()` runs: the Database stays open and
    # aiosqlite's non-daemon worker thread keeps the interpreter alive. pytest
    # would print the failure in under a second and then hang forever — a stuck
    # CI job instead of a red test.
    assert jobs == []
    assert active is True
    assert idle is False
