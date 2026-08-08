"""SSE meta events — initial execution_info (#3) and incremental stats (#1).

Both must be persisted so a reconnecting client sees the same frames via replay.
The bus/SSE event name is ``meta``; subtypes live in payload ``event_type``
(``execution_info`` / ``stats``) to avoid colliding with skill-context frames
that also use the ``meta`` event name with ``event_type: "meta"``.
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
from agent_md.execution.runner import _COMPLETE_SEQ, _normalize_args


class _Req:
    def __init__(self, app):
        self.app = app


def _write_agent(path: Path, *, name: str) -> Path:
    path.write_text(
        f"---\nname: {name}\nmodel:\n  provider: google\n  name: gemini-2.5-flash\n---\nYou are a test agent.\n",
        encoding="utf-8",
    )
    return path


def _complete() -> dict:
    return {"type": "complete", "seq": _COMPLETE_SEQ, "data": {"status": "success"}}


def _meta_frame(seq: int, payload: dict, *, agent_id: str = "pesquisador", display_name: str = "Research Bot") -> dict:
    return {
        "type": "meta",
        "seq": seq,
        "data": {**payload, **agent_identity_payload(agent_id, display_name)},
    }


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


@pytest.fixture
async def runner_db(tmp_path):
    """Connected Database closed in teardown even when an assertion fails first."""
    from agent_md.db.database import Database

    db = Database(tmp_path / "t.db")
    await db.connect()
    try:
        yield db
    finally:
        await db.close()


def test_normalize_args_variants():
    assert _normalize_args(["a", "b"]) == ["a", "b"]
    assert _normalize_args("solo") == ["solo"]
    assert _normalize_args("") == []


@pytest.mark.asyncio
async def test_execution_info_persisted_with_six_fields(app_client):
    """Initial meta carries the frozen contract fields and identity."""
    app, _client = app_client
    db = app.state.db
    eid = await db.create_execution("pesquisador", "chat", status="running", session_id="sess-1")
    ex_logger = ExecutionLogger(db, eid, "pesquisador", display_name="Research Bot")

    from agent_md.execution.runner import AgentRunner
    from agent_md.config.models import AgentConfig

    runner = AgentRunner(db, mcp_manager=None, path_context=None)
    config = AgentConfig(
        id="pesquisador",
        name="Research Bot",
        model={"provider": "google", "name": "gemini-2.5-flash"},
    )
    log_id = await runner._emit_execution_info(
        ex_logger,
        eid,
        event_bus=None,
        config=config,
        trigger_type="chat",
        arguments=["/vault/daily.md"],
        session_id="sess-1",
    )

    row = next(r for r in await db.get_logs(eid) if r.id == log_id)
    assert row.event_type == "meta"
    assert row.message == "execution_info"
    meta = json.loads(row.metadata)
    assert meta["event_type"] == "execution_info"
    assert meta["agent_id"] == "pesquisador"
    assert meta["display_name"] == "Research Bot"
    assert meta["agent_name"] == "pesquisador"  # mirrors id, not the label
    assert meta["model"] == "google/gemini-2.5-flash"
    assert meta["trigger"] == "chat"
    assert meta["args"] == ["/vault/daily.md"]
    assert meta["session_id"] == "sess-1"


@pytest.mark.asyncio
async def test_stats_persisted_and_grow(app_client):
    """Stats rows accumulate tokens/cost across successive AI steps."""
    app, _client = app_client
    db = app.state.db
    eid = await db.create_execution("pesquisador", "manual", status="running")
    ex_logger = ExecutionLogger(db, eid, "pesquisador", display_name="Research Bot")

    from agent_md.execution.runner import AgentRunner
    from agent_md.config.models import AgentConfig

    runner = AgentRunner(db, mcp_manager=None, path_context=None)
    config = AgentConfig(id="pesquisador", name="Research Bot", model={"provider": "google", "name": "x"})

    await runner._emit_stats(ex_logger, eid, None, config, input_tokens=100, output_tokens=20, cost_usd=0.001)
    await runner._emit_stats(ex_logger, eid, None, config, input_tokens=250, output_tokens=80, cost_usd=0.003)

    stats_rows = [r for r in await db.get_logs(eid) if r.event_type == "meta" and r.message == "stats"]
    assert len(stats_rows) == 2
    first, second = (json.loads(r.metadata) for r in stats_rows)
    assert first["event_type"] == "stats"
    assert first["total_tokens"] == 120
    assert second["input_tokens"] == 250
    assert second["output_tokens"] == 80
    assert second["total_tokens"] == 330
    assert second["cost_usd"] == 0.003
    assert second["total_tokens"] > first["total_tokens"]


@pytest.mark.asyncio
async def test_replay_before_live_keeps_meta_frames(app_client):
    """Adverse order: DB replay wins the race; live duplicates under the same seq are dropped."""
    app, _client = app_client
    db, bus = app.state.db, app.state.event_bus
    eid = await db.create_execution("pesquisador", "manual", status="running")
    ex_logger = ExecutionLogger(db, eid, "pesquisador", display_name="Research Bot")

    from agent_md.execution.runner import AgentRunner
    from agent_md.config.models import AgentConfig

    runner = AgentRunner(db, mcp_manager=None, path_context=None)
    config = AgentConfig(
        id="pesquisador",
        name="Research Bot",
        model={"provider": "google", "name": "gemini-2.5-flash"},
    )
    info_id = await runner._emit_execution_info(
        ex_logger,
        eid,
        event_bus=None,
        config=config,
        trigger_type="manual",
        arguments=["arg1"],
        session_id=None,
    )
    stats_id = await runner._emit_stats(ex_logger, eid, None, config, input_tokens=10, output_tokens=5, cost_usd=None)

    gen = stream_execution(eid, _Req(app))
    replayed_info = await anext(gen)
    replayed_stats = await anext(gen)
    assert replayed_info.event == "meta"
    assert replayed_info.data["event_type"] == "execution_info"
    assert replayed_info.data["args"] == ["arg1"]
    assert replayed_info.data["session_id"] is None
    assert replayed_info.data["agent_name"] == "pesquisador"
    assert replayed_info.data["display_name"] == "Research Bot"
    assert replayed_stats.event == "meta"
    assert replayed_stats.data["event_type"] == "stats"
    assert replayed_stats.data["total_tokens"] == 15

    # Live twins under the same seq must be deduped away.
    await bus.publish(
        eid,
        _meta_frame(
            info_id,
            {
                "event_type": "execution_info",
                "model": "google/gemini-2.5-flash",
                "trigger": "manual",
                "args": ["arg1"],
                "session_id": None,
            },
        ),
    )
    await bus.publish(
        eid,
        _meta_frame(
            stats_id,
            {"event_type": "stats", "input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "cost_usd": None},
        ),
    )
    await bus.publish(eid, _complete())
    rest = [frame async for frame in gen]
    metas = [f for f in (replayed_info, replayed_stats, *rest) if f.event == "meta"]
    assert len(metas) == 2


@pytest.mark.asyncio
async def test_live_before_replay_delivers_meta_frames(app_client):
    """Opposite order: live frames arrive first; later reconnect would replay the same bytes."""
    app, _client = app_client
    db, bus = app.state.db, app.state.event_bus
    eid = await db.create_execution("pesquisador", "chat", status="running", session_id="s-9")
    ex_logger = ExecutionLogger(db, eid, "pesquisador", display_name="Research Bot")

    from agent_md.execution.runner import AgentRunner
    from agent_md.config.models import AgentConfig

    runner = AgentRunner(db, mcp_manager=None, path_context=None)
    config = AgentConfig(
        id="pesquisador",
        name="Research Bot",
        model={"provider": "google", "name": "gemini-2.5-flash"},
    )

    # One earlier row so the generator starts draining live after that replay.
    await ex_logger._persist("system", "boot")
    gen = stream_execution(eid, _Req(app))
    first = await anext(gen)
    assert first.event == "system"

    info_id = await runner._emit_execution_info(
        ex_logger,
        eid,
        event_bus=bus,
        config=config,
        trigger_type="chat",
        arguments=["/x.md"],
        session_id="s-9",
    )
    stats_id = await runner._emit_stats(ex_logger, eid, bus, config, input_tokens=40, output_tokens=10, cost_usd=0.0001)
    await bus.publish(eid, _complete())
    rest = [frame async for frame in gen]

    live_info = next(f for f in rest if f.event == "meta" and f.data.get("event_type") == "execution_info")
    live_stats = next(f for f in rest if f.event == "meta" and f.data.get("event_type") == "stats")
    assert live_info.id == str(info_id)
    assert live_info.data["session_id"] == "s-9"
    assert live_info.data["trigger"] == "chat"
    assert live_stats.id == str(stats_id)
    assert live_stats.data["total_tokens"] == 50

    # Persisted rows a reconnect would replay match the live payloads.
    rows = {r.id: r for r in await db.get_logs(eid)}
    info_meta = json.loads(rows[info_id].metadata)
    stats_meta = json.loads(rows[stats_id].metadata)
    assert info_meta["event_type"] == "execution_info"
    assert info_meta["session_id"] == live_info.data["session_id"]
    assert stats_meta["total_tokens"] == live_stats.data["total_tokens"]


@pytest.mark.asyncio
async def test_reconnect_replays_execution_info_and_stats(app_client):
    """Finished-execution reconnect (logs -e) still gets both meta subtypes."""
    app, client = app_client
    db = app.state.db
    eid = await db.create_execution("pesquisador", "manual", status="running")
    ex_logger = ExecutionLogger(db, eid, "pesquisador", display_name="Research Bot")

    from agent_md.execution.runner import AgentRunner
    from agent_md.config.models import AgentConfig

    runner = AgentRunner(db, mcp_manager=None, path_context=None)
    config = AgentConfig(
        id="pesquisador",
        name="Research Bot",
        model={"provider": "google", "name": "gemini-2.5-flash"},
    )
    await runner._emit_execution_info(
        ex_logger,
        eid,
        None,
        config,
        trigger_type="manual",
        arguments=[],
        session_id=None,
    )
    await runner._emit_stats(ex_logger, eid, None, config, input_tokens=7, output_tokens=3, cost_usd=None)
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

    metas = [data for event, data in frames if event == "meta"]
    assert any(m["event_type"] == "execution_info" for m in metas)
    assert any(m["event_type"] == "stats" and m["total_tokens"] == 10 for m in metas)


class _NoMCP:
    async def get_tools(self, names):
        return []


@pytest.mark.asyncio
async def test_runner_emits_execution_info_then_growing_stats(tmp_path, monkeypatch, runner_db):
    """Full runner path: stream opens with execution_info; stats grow per AI message."""
    from unittest.mock import AsyncMock

    from agent_md.config.models import AgentConfig
    from agent_md.execution.event_bus import EventBus
    from agent_md.execution.runner import AgentRunner
    from agent_md.workspace.path_context import PathContext
    from langchain_core.messages import SystemMessage, ToolMessage

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
    config = AgentConfig(
        id="meta-agent",
        name="Meta Agent",
        model={"provider": "google", "name": "x"},
        history="off",
    )

    async def fake_stream(*args, **kwargs):
        first = AIMessage(content="", tool_calls=[{"id": "c1", "name": "noop", "args": {}}])
        first.usage_metadata = {"input_tokens": 100, "output_tokens": 20}
        yield first
        yield ToolMessage(content="ok", tool_call_id="c1", name="noop")
        second = AIMessage(content="done")
        second.usage_metadata = {"input_tokens": 150, "output_tokens": 40}
        yield second

    async def fake_system(*args, **kwargs):
        return SystemMessage(content="sys")

    monkeypatch.setattr(AgentRunner, "_build_graph", AsyncMock(return_value=(object(), None)))
    monkeypatch.setattr(AgentRunner, "_load_history_seed", AsyncMock(return_value=[]))
    monkeypatch.setattr("agent_md.execution.runner.stream_agent_graph", fake_stream)
    monkeypatch.setattr("agent_md.graph.builder.build_system_message_async", fake_system)

    bus = EventBus()
    eid = await db.create_execution("meta-agent", "chat", session_id="sess-r")
    queue = bus.subscribe(eid)
    try:
        result = await runner.run(
            config,
            execution_id=eid,
            event_bus=bus,
            trigger_type="chat",
            session_id="sess-r",
            arguments=["/file.md"],
        )
    finally:
        bus.unsubscribe(eid, queue)
        await runner.aclose()

    assert result["status"] == "success"

    published = []
    while not queue.empty():
        published.append(queue.get_nowait())

    metas = [e for e in published if e["type"] == "meta"]
    assert metas[0]["data"]["event_type"] == "execution_info"
    assert metas[0]["data"]["agent_id"] == "meta-agent"
    assert metas[0]["data"]["display_name"] == "Meta Agent"
    assert metas[0]["data"]["agent_name"] == "meta-agent"
    assert metas[0]["data"]["session_id"] == "sess-r"
    assert metas[0]["data"]["trigger"] == "chat"
    assert metas[0]["data"]["args"] == ["/file.md"]
    assert metas[0]["data"]["model"] == "google/x"

    stats = [e for e in metas if e["data"]["event_type"] == "stats"]
    assert len(stats) >= 2
    assert stats[0]["data"]["total_tokens"] == 120
    assert stats[-1]["data"]["total_tokens"] == 310
    assert stats[-1]["data"]["total_tokens"] > stats[0]["data"]["total_tokens"]

    rows = await db.get_logs(eid)
    assert any(r.event_type == "meta" and json.loads(r.metadata)["event_type"] == "execution_info" for r in rows)
    persisted_stats = [json.loads(r.metadata) for r in rows if r.event_type == "meta" and r.message == "stats"]
    assert len(persisted_stats) >= 2
    assert persisted_stats[-1]["total_tokens"] > persisted_stats[0]["total_tokens"]
