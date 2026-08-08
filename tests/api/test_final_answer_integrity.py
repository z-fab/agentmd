"""final_answer integrity — what a replay shows must equal what the live stream showed.

Regression cover for issue #2. The log row used to keep only ``content[:500]``
while the live event carried the whole answer, and ``output_data`` was cut at
10k. The SSE stream deduplicates replay against live by log id, so whichever of
the two reached the client first won: replay first meant the truncated version
stuck for good (``run --detach`` + ``logs``, any reconnect, every HILT cycle).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage

from agent_md.api.app import create_app
from agent_md.api.routes.executions import stream_execution
from agent_md.execution.logger import ExecutionLogger, agent_identity_payload
from agent_md.execution.runner import _COMPLETE_SEQ

# Longer than both historical caps (500 for the log row, 10k for output_data),
# with markers at each end so any truncation is visible in the assertion.
LONG_ANSWER = "INICIO " + ("resposta completa. " * 800) + " FIM"


def assert_whole_answer(actual: str, where: str) -> None:
    """Assert *actual* is the whole answer.

    The length check comes first on purpose: a plain ``==`` on two ~15k-char
    strings makes pytest build a character diff that takes minutes to render.
    """
    assert len(actual) == len(LONG_ANSWER), f"{where}: truncated to {len(actual)} of {len(LONG_ANSWER)} chars"
    assert actual == LONG_ANSWER, where


def _write_agent(path: Path, *, name: str) -> Path:
    path.write_text(
        f"---\nname: {name}\nmodel:\n  provider: google\n  name: gemini-2.5-flash\n---\nYou are a test agent.\n",
        encoding="utf-8",
    )
    return path


class _Req:
    """Minimal stand-in for a Starlette Request — the route only reads ``app.state``."""

    def __init__(self, app):
        self.app = app


def _live_final_answer(seq: int, content: str = LONG_ANSWER) -> dict:
    """The bus event exactly as the runner publishes it."""
    return {
        "type": "final_answer",
        "seq": seq,
        "data": {"content": content, **agent_identity_payload("pesquisador", "Research Bot")},
    }


def _complete() -> dict:
    return {"type": "complete", "seq": _COMPLETE_SEQ, "data": {"status": "success"}}


@pytest.fixture
async def app_client(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _write_agent(agents_dir / "pesquisador.md", name="Research Bot")
    application = create_app(workspace=tmp_path, agents_dir=agents_dir, db_path=tmp_path / "test.db")
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with application.router.lifespan_context(application):
            yield application, client


@pytest.mark.asyncio
async def test_final_answer_row_keeps_the_whole_answer(app_client):
    """The persisted row is the same string that was emitted, not a 500-char prefix."""
    app, _client = app_client
    db = app.state.db
    eid = await db.create_execution("pesquisador", "manual", status="running")

    emitted: list[tuple[str, dict]] = []
    ex_logger = ExecutionLogger(
        db,
        eid,
        "pesquisador",
        display_name="Research Bot",
        on_event=lambda event_type, data: emitted.append((event_type, data)),
    )
    await ex_logger.mark_final_answer(AIMessage(content=LONG_ANSWER))

    (row,) = await db.get_logs(eid)
    assert row.event_type == "final_answer"
    assert_whole_answer(row.message, "persisted final_answer row")
    assert len(row.message) > 10_000

    assert [t for t, _ in emitted] == ["final_answer"]
    assert_whole_answer(emitted[0][1]["content"], "emitted final_answer")


@pytest.mark.asyncio
async def test_replay_before_live_keeps_the_whole_answer(app_client):
    """Adverse order: the DB row is replayed first, so dedup drops the live frame.

    This is the order that used to lose — the client kept the truncated replay
    and never saw the complete event that arrived under the same ``seq``.
    """
    app, _client = app_client
    db, bus = app.state.db, app.state.event_bus
    eid = await db.create_execution("pesquisador", "manual", status="running")

    ex_logger = ExecutionLogger(db, eid, "pesquisador", display_name="Research Bot")
    log_id = await ex_logger.mark_final_answer(AIMessage(content=LONG_ANSWER))

    gen = stream_execution(eid, _Req(app))
    replayed = await anext(gen)  # replay of the row wins the race
    assert replayed.event == "final_answer"
    assert replayed.id == str(log_id)

    # The live duplicate lands afterwards under the same seq — dedup discards it.
    await bus.publish(eid, _live_final_answer(log_id))
    await bus.publish(eid, _complete())
    rest = [frame async for frame in gen]

    finals = [f for f in (replayed, *rest) if f.event == "final_answer"]
    assert len(finals) == 1, "the live frame should have been deduped away"
    assert_whole_answer(finals[0].data["content"], "replayed frame content")
    assert_whole_answer(finals[0].data["message"], "replayed frame message")


@pytest.mark.asyncio
async def test_live_before_replay_delivers_the_same_answer(app_client):
    """Opposite order: the row is not in the DB yet, so the live frame is the source.

    Both orders must hand the client the same bytes — that is the invariant.
    """
    app, _client = app_client
    db, bus = app.state.db, app.state.event_bus
    eid = await db.create_execution("pesquisador", "manual", status="running")

    ex_logger = ExecutionLogger(db, eid, "pesquisador", display_name="Research Bot")
    # One earlier row so replay yields a frame and we know it is over.
    await ex_logger._persist("ai", "pensando…")

    gen = stream_execution(eid, _Req(app))
    first = await anext(gen)
    assert first.event == "ai"

    # Only now does the answer exist; the live frame is the only way it can arrive.
    log_id = await ex_logger.mark_final_answer(AIMessage(content=LONG_ANSWER))
    await bus.publish(eid, _live_final_answer(log_id))
    await bus.publish(eid, _complete())
    rest = [frame async for frame in gen]

    finals = [f for f in rest if f.event == "final_answer"]
    assert len(finals) == 1
    assert_whole_answer(finals[0].data["content"], "live frame content")

    # replay == live: the row a later reconnect would replay holds the same bytes.
    row = next(r for r in await db.get_logs(eid) if r.event_type == "final_answer")
    assert len(row.message) == len(finals[0].data["content"])
    assert row.message == finals[0].data["content"]


@pytest.mark.asyncio
async def test_reconnect_to_finished_execution_replays_whole_answer(app_client):
    """`logs -e <id>` / a reconnect after the run ended still gets the full answer."""
    app, client = app_client
    db = app.state.db
    eid = await db.create_execution("pesquisador", "manual", status="running")
    ex_logger = ExecutionLogger(db, eid, "pesquisador", display_name="Research Bot")
    await ex_logger.mark_final_answer(AIMessage(content=LONG_ANSWER))
    await db.update_execution(eid, status="success", duration_ms=1)

    frames: list[tuple[str, dict]] = []
    event_name, data_raw = "message", None
    async with client.stream("GET", f"/executions/{eid}/stream") as resp:
        assert resp.status_code == 200
        async for line in resp.aiter_lines():
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_raw = line.split(":", 1)[1].strip()
            elif line == "" and data_raw is not None:
                frames.append((event_name, json.loads(data_raw)))
                event_name, data_raw = "message", None

    final = next(data for event, data in frames if event == "final_answer")
    assert_whole_answer(final["content"], "reconnect frame content")
    assert_whole_answer(final["message"], "reconnect frame message")


# --- runner: output_data and the published event carry the same whole answer ---


class _NoMCP:
    async def get_tools(self, names):
        return []


class _OneShotModel:
    """Chat model that answers in one turn with a very long message."""

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        return AIMessage(content=LONG_ANSWER)


@pytest.fixture
async def runner_db(tmp_path):
    """A connected Database that is closed even when the test fails.

    aiosqlite runs its connection on a non-daemon worker thread, so a Database
    left open keeps the interpreter alive at exit: pytest reports the failure and
    then hangs forever instead of returning. Closing has to happen in teardown,
    never as the last statement of the test body.
    """
    from agent_md.db.database import Database

    db = Database(tmp_path / "t.db")
    await db.connect()
    try:
        yield db
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_runner_keeps_whole_output_data_and_final_answer(tmp_path, monkeypatch, runner_db):
    """output_data, the log row and the live event are one and the same string."""
    from agent_md.config.models import AgentConfig
    from agent_md.execution.event_bus import EventBus
    from agent_md.execution.runner import AgentRunner
    from agent_md.workspace.path_context import PathContext

    db = runner_db
    pc = PathContext(
        workspace_root=tmp_path,
        agents_dir=tmp_path,
        db_path=tmp_path / "t.db",
        mcp_config=tmp_path / "m.json",
        tools_dir=tmp_path,
        skills_dir=tmp_path,
    )
    runner = AgentRunner(db, mcp_manager=_NoMCP(), path_context=pc, db_path=str(tmp_path / "t.db"))
    config = AgentConfig(id="longo", name="Longo", model={"provider": "google", "name": "x"}, history="off")
    monkeypatch.setattr("agent_md.execution.runner.create_chat_model", lambda **kw: _OneShotModel())

    bus = EventBus()
    eid = await db.create_execution("longo", "manual")
    queue = bus.subscribe(eid)
    try:
        result = await runner.run(config, execution_id=eid, event_bus=bus)
    finally:
        bus.unsubscribe(eid, queue)
        await runner.aclose()

    assert result["status"] == "success"
    assert_whole_answer(result["output"], "runner result output")

    execution = await db.get_execution(eid)
    assert_whole_answer(execution.output_data, "executions.output_data")
    assert len(execution.output_data) > 10_000

    row = next(r for r in await db.get_logs(eid) if r.event_type == "final_answer")
    assert_whole_answer(row.message, "persisted final_answer row")

    published = []
    while not queue.empty():
        published.append(queue.get_nowait())
    live = next(e for e in published if e["type"] == "final_answer")
    assert_whole_answer(live["data"]["content"], "published final_answer event")
    assert live["seq"] == row.id
