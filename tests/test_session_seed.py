"""Session-scoped history: two conversations on one agent must not bleed into each other.

The bug these cover is silent — nothing raises, the context is just wrong — so the
assertions look at what the model actually received, not at return codes.
"""

import aiosqlite
from datetime import datetime, timedelta, timezone

from langchain_core.messages import AIMessage

from agent_md.config.models import AgentConfig
from agent_md.db.database import Database
from agent_md.execution import checkpoint_maint as cm
from agent_md.execution.runner import AgentRunner
from agent_md.workspace.path_context import PathContext


class _NoMCP:
    async def get_tools(self, names):
        return []


class _SpyModel:
    """Records every messages list passed to ainvoke; answers with a unique marker."""

    def __init__(self):
        self.seen = []  # one message-list per ainvoke call
        self.n = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.seen.append(list(messages))
        self.n += 1
        return AIMessage(content=f"answer {self.n}")


def _texts(messages) -> list[str]:
    out = []
    for m in messages:
        content = getattr(m, "content", "")
        out.append(content if isinstance(content, str) else str(content))
    return out


def _runner_for(tmp_path):
    """A runner over a freshly created DB — a dirty DB would seed the assertions."""
    db_path = tmp_path / "session.db"
    db = Database(db_path)
    pc = PathContext(
        workspace_root=tmp_path,
        agents_dir=tmp_path,
        db_path=db_path,
        mcp_config=tmp_path / "m.json",
        tools_dir=tmp_path,
        skills_dir=tmp_path,
    )
    return db, AgentRunner(db, mcp_manager=_NoMCP(), path_context=pc, db_path=str(db_path))


def _cfg(name="talker", history="low"):
    return AgentConfig(name=name, model={"provider": "google", "name": "x"}, history=history)


# --- Seed scoping (DB level) ------------------------------------------------


async def test_last_finished_is_scoped_to_its_session(db):
    none_run = await db.create_execution("a", "manual")
    await db.update_execution(none_run, status="success")
    s1 = await db.create_execution("a", "chat", session_id="sess-1")
    await db.update_execution(s1, status="success")
    s2 = await db.create_execution("a", "chat", session_id="sess-2")
    await db.update_execution(s2, status="success")

    assert (await db.get_last_finished_execution("a", session_id="sess-1")).id == s1
    assert (await db.get_last_finished_execution("a", session_id="sess-2")).id == s2
    # No session means "the sessionless line", not "whatever ran last".
    assert (await db.get_last_finished_execution("a")).id == none_run
    assert await db.get_last_finished_execution("a", session_id="unknown") is None


async def test_last_finished_still_excludes_self_and_running(db):
    e1 = await db.create_execution("a", "chat", session_id="s")
    await db.update_execution(e1, status="success")
    e2 = await db.create_execution("a", "chat", session_id="s")  # running
    assert (await db.get_last_finished_execution("a", exclude_id=e2, session_id="s")).id == e1
    assert await db.get_last_finished_execution("a", exclude_id=e1, session_id="s") is None


# --- Seed scoping (end to end, through the graph checkpointer) --------------


async def test_two_sessions_keep_independent_history(tmp_path, monkeypatch):
    """Interleaved turns of two sessions: neither sees the other's answers."""
    db, runner = _runner_for(tmp_path)
    await db.connect()
    config = _cfg()
    spy = _SpyModel()
    monkeypatch.setattr("agent_md.execution.runner.create_chat_model", lambda **kw: spy)

    try:
        try:
            # A1, B1, A2, B2 — interleaved on purpose: the old global pointer would
            # hand session A's second turn whatever session B answered just before.
            for session, message in [
                ("sess-a", "alpha one"),
                ("sess-b", "beta one"),
                ("sess-a", "alpha two"),
                ("sess-b", "beta two"),
            ]:
                res = await runner.run(config, trigger_type="chat", session_id=session, user_message=message)
                assert res["status"] == "success", res
        finally:
            await runner.aclose()

        a2_seen = " ".join(_texts(spy.seen[2]))
        b2_seen = " ".join(_texts(spy.seen[3]))

        # Turn 2 of each session sees its own first turn...
        assert "alpha one" in a2_seen
        assert "beta one" in b2_seen
        # ...and nothing from the other conversation, prompt or answer.
        assert "beta one" not in a2_seen
        assert "answer 2" not in a2_seen  # session B's first answer
        assert "alpha one" not in b2_seen
        assert "alpha two" not in b2_seen

        rows = await db.list_executions(agent_id="talker", limit=10)
        assert {r.session_id for r in rows} == {"sess-a", "sess-b"}
        assert {r.trigger for r in rows} == {"chat"}
    finally:
        await db.close()


async def test_schedule_and_chat_do_not_cross_seed(tmp_path, monkeypatch):
    """A scheduled run and an open chat on the same agent stay strangers."""
    db, runner = _runner_for(tmp_path)
    await db.connect()
    config = _cfg()
    spy = _SpyModel()
    monkeypatch.setattr("agent_md.execution.runner.create_chat_model", lambda **kw: spy)

    try:
        try:
            await runner.run(config, trigger_type="chat", session_id="sess-a", user_message="chat turn one")
            await runner.run(config, trigger_type="schedule")
            await runner.run(config, trigger_type="chat", session_id="sess-a", user_message="chat turn two")
            await runner.run(config, trigger_type="schedule")
        finally:
            await runner.aclose()

        first_schedule = " ".join(_texts(spy.seen[1]))
        chat_turn_two = " ".join(_texts(spy.seen[2]))
        second_schedule = " ".join(_texts(spy.seen[3]))

        # The scheduled run never inherits the chat.
        assert "chat turn one" not in first_schedule
        assert "answer 1" not in first_schedule
        assert "chat turn one" not in second_schedule
        # ...but it does chain to the previous scheduled run (sessionless history).
        assert "answer 2" in second_schedule
        # And the chat never inherits the scheduled run.
        assert "chat turn one" in chat_turn_two
        assert "answer 2" not in chat_turn_two

        triggers = {r.id: (r.trigger, r.session_id) for r in await db.list_executions(agent_id="talker", limit=10)}
        assert sorted(triggers.values()) == sorted(
            [("chat", "sess-a"), ("schedule", None), ("chat", "sess-a"), ("schedule", None)]
        )
    finally:
        await db.close()


async def test_sessionless_runs_chain_as_before(tmp_path, monkeypatch):
    """No session anywhere: seeding behaves exactly like it did before sessions."""
    db, runner = _runner_for(tmp_path)
    await db.connect()
    config = _cfg()
    spy = _SpyModel()
    monkeypatch.setattr("agent_md.execution.runner.create_chat_model", lambda **kw: spy)

    try:
        try:
            await runner.run(config, trigger_type="manual")
            await runner.run(config, trigger_type="manual")
        finally:
            await runner.aclose()

        assert "answer 1" in " ".join(_texts(spy.seen[1]))
        assert all(r.session_id is None for r in await db.list_executions(agent_id="talker", limit=10))
    finally:
        await db.close()


async def test_automatic_triggers_drop_a_session_id(tmp_path, monkeypatch):
    """Even if a caller passes one, schedule/watch runs are never part of a chat."""
    db, runner = _runner_for(tmp_path)
    await db.connect()
    config = _cfg()
    spy = _SpyModel()
    monkeypatch.setattr("agent_md.execution.runner.create_chat_model", lambda **kw: spy)

    try:
        try:
            await runner.run(config, trigger_type="chat", session_id="sess-a", user_message="chat turn one")
            await runner.run(config, trigger_type="schedule", session_id="sess-a")
        finally:
            await runner.aclose()

        scheduled = next(r for r in await db.list_executions(agent_id="talker", limit=10) if r.trigger == "schedule")
        assert scheduled.session_id is None
        assert "chat turn one" not in " ".join(_texts(spy.seen[1]))
    finally:
        await db.close()


async def test_history_off_seeds_nothing_even_with_a_session(tmp_path, monkeypatch):
    db, runner = _runner_for(tmp_path)
    await db.connect()
    config = _cfg(history="off")
    spy = _SpyModel()
    monkeypatch.setattr("agent_md.execution.runner.create_chat_model", lambda **kw: spy)

    try:
        try:
            await runner.run(config, trigger_type="chat", session_id="s", user_message="first")
            await runner.run(config, trigger_type="chat", session_id="s", user_message="second")
        finally:
            await runner.aclose()

        assert "first" not in " ".join(_texts(spy.seen[1]))
    finally:
        await db.close()


# --- trigger_context ---------------------------------------------------------


def test_manual_and_chat_user_input_carry_the_trigger_context():
    runner = AgentRunner.__new__(AgentRunner)
    config = _cfg()
    assert runner._build_user_input("manual", None, config) == "Execute your task."
    assert runner._build_user_input("manual", "from a webhook", config) == "Execute your task. (from a webhook)"
    assert runner._build_user_input("chat", "from a webhook", config) == "Execute your task. (from a webhook)"


# --- Migration ---------------------------------------------------------------


async def test_pre_session_database_gains_the_column_without_losing_rows(tmp_path):
    """A DB written before sessions existed opens, migrates, and keeps its data."""
    db_path = tmp_path / "old.db"
    async with aiosqlite.connect(str(db_path)) as conn:
        await conn.execute(
            """
            CREATE TABLE executions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id      TEXT NOT NULL,
                status        TEXT NOT NULL,
                trigger       TEXT NOT NULL,
                started_at    TIMESTAMP NOT NULL,
                finished_at   TIMESTAMP,
                duration_ms   INTEGER,
                input_data    TEXT,
                output_data   TEXT,
                error         TEXT,
                input_tokens  INTEGER,
                output_tokens INTEGER,
                total_tokens  INTEGER
            )
            """
        )
        await conn.execute(
            "INSERT INTO executions (agent_id, status, trigger, started_at, output_data)"
            " VALUES ('legacy', 'success', 'manual', '2026-01-01T00:00:00+00:00', 'kept')"
        )
        await conn.commit()

    db = Database(db_path)
    await db.connect()
    try:
        rows = await db.list_executions(agent_id="legacy")
        assert len(rows) == 1
        assert rows[0].output_data == "kept"
        assert rows[0].session_id is None
        # And the migrated DB is usable for sessions right away.
        new_id = await db.create_execution("legacy", "chat", session_id="s")
        await db.update_execution(new_id, status="success")
        assert (await db.get_last_finished_execution("legacy", session_id="s")).id == new_id
    finally:
        await db.close()


# --- Checkpoint retention ----------------------------------------------------


async def _make_checkpoint_db(path, thread_ids):
    async with aiosqlite.connect(str(path)) as conn:
        await conn.execute("CREATE TABLE checkpoints (thread_id TEXT, checkpoint_id TEXT)")
        await conn.execute("CREATE TABLE checkpoint_writes (thread_id TEXT)")
        await conn.execute("CREATE TABLE checkpoint_blobs (thread_id TEXT)")
        for t in thread_ids:
            await conn.execute("INSERT INTO checkpoints VALUES (?, ?)", (str(t), "c"))
        await conn.commit()


async def test_sweep_preserves_the_latest_turn_of_every_session(db):
    """An active conversation must not lose its memory to the retention sweep.

    Keeping only the agent's newest execution is not enough: a scheduled run that
    lands after the last chat turn would leave that turn unprotected, and the next
    turn of the conversation would start blank.
    """
    old_iso = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()

    async def _finished(session_id):
        eid = await db.create_execution("a", "chat" if session_id else "schedule", session_id=session_id)
        await db.db.execute("UPDATE executions SET status='success', finished_at=? WHERE id=?", (old_iso, eid))
        await db.db.commit()
        return eid

    a1, a2 = await _finished("sess-a"), await _finished("sess-a")
    b1 = await _finished("sess-b")
    sched1, sched2 = await _finished(None), await _finished(None)

    cp = cm.checkpoint_db_path(db.db_path)
    await _make_checkpoint_db(cp, [a1, a2, b1, sched1, sched2])

    removed = await cm.sweep_old_checkpoints(db, db.db_path, retention_days=30)
    assert removed == 2  # a1 and sched1 — superseded within their own conversation

    async with aiosqlite.connect(str(cp)) as conn:
        cur = await conn.execute("SELECT DISTINCT thread_id FROM checkpoints")
        remaining = sorted(int(r[0]) for r in await cur.fetchall())
    assert remaining == sorted([a2, b1, sched2])
