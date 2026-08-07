"""Fixup: SSE live/replay identity and agents_changed display_name on remove."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from agent_md.api.app import create_app
from agent_md.config.models import AgentConfig
from agent_md.execution.logger import ExecutionLogger, agent_identity_payload
from agent_md.workspace.parser import parse_agent_file
from agent_md.workspace.registry import AgentRegistry
from agent_md.workspace.scheduler import _AgentFileHandler


def _write_agent(path: Path, *, name: str | None = None) -> Path:
    front = "---\n"
    if name is not None:
        front += f"name: {name}\n"
    front += "model:\n  provider: google\n  name: gemini-2.5-flash\n---\nYou are a test agent.\n"
    path.write_text(front, encoding="utf-8")
    return path


def _parse_sse(lines: list[str]) -> list[tuple[str, dict]]:
    """Parse SSE frames into (event, data) pairs."""
    events: list[tuple[str, dict]] = []
    event_name = "message"
    data_raw = None
    for line in lines:
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_raw = line.split(":", 1)[1].strip()
        elif line == "" and data_raw is not None:
            events.append((event_name, json.loads(data_raw)))
            event_name = "message"
            data_raw = None
    if data_raw is not None:
        events.append((event_name, json.loads(data_raw)))
    return events


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
async def test_stream_replay_includes_persisted_identity(app_client):
    """Replayed SSE events carry the same agent_id/display_name as live payloads."""
    app, client = app_client
    db = app.state.db
    eid = await db.create_execution("pesquisador", "manual", status="success")

    logger = ExecutionLogger(db, eid, "pesquisador", display_name="Research Bot")
    await logger._persist("ai", "thinking…")
    await logger._persist("final_answer", "done")

    # Durable metadata matches the live identity contract.
    logs = await db.get_logs(eid)
    assert len(logs) == 2
    for log in logs:
        meta = json.loads(log.metadata)
        assert meta == agent_identity_payload("pesquisador", "Research Bot")

    lines: list[str] = []
    async with client.stream("GET", f"/executions/{eid}/stream") as resp:
        assert resp.status_code == 200
        async for line in resp.aiter_lines():
            lines.append(line)
            if line.startswith("event:") and line.split(":", 1)[1].strip() == "complete":
                # drain remaining data/blank for the complete frame
                continue

    frames = _parse_sse(lines)
    replayed = [data for event, data in frames if event in ("ai", "final_answer")]
    assert len(replayed) == 2
    for data in replayed:
        assert data["agent_id"] == "pesquisador"
        assert data["display_name"] == "Research Bot"
        assert data["agent_name"] == "pesquisador"


@pytest.mark.asyncio
async def test_stream_replay_identity_survives_agent_removal(app_client):
    """Identity from log metadata is kept even after the agent leaves the registry."""
    app, client = app_client
    db = app.state.db
    eid = await db.create_execution("pesquisador", "manual", status="success")
    logger = ExecutionLogger(db, eid, "pesquisador", display_name="Research Bot")
    await logger._persist("ai", "hello")

    app.state.runtime.registry.remove("pesquisador")
    assert app.state.runtime.registry.get("pesquisador") is None

    lines: list[str] = []
    async with client.stream("GET", f"/executions/{eid}/stream") as resp:
        async for line in resp.aiter_lines():
            lines.append(line)

    frames = _parse_sse(lines)
    ai = next(data for event, data in frames if event == "ai")
    assert ai["agent_id"] == "pesquisador"
    assert ai["display_name"] == "Research Bot"


@pytest.mark.asyncio
async def test_terminal_frame_identity_matches_replay_after_removal(app_client):
    """Every frame of one stream agrees, including the synthetic terminal one.

    Without the durable name the replayed logs would say "Research Bot" while
    the synthetic complete fell back to the id — the same stream contradicting
    itself once the agent left the registry.
    """
    app, client = app_client
    db = app.state.db
    eid = await db.create_execution("pesquisador", "manual", status="success")
    logger = ExecutionLogger(db, eid, "pesquisador", display_name="Research Bot")
    await logger._persist("ai", "hello")

    app.state.runtime.registry.remove("pesquisador")

    lines: list[str] = []
    async with client.stream("GET", f"/executions/{eid}/stream") as resp:
        async for line in resp.aiter_lines():
            lines.append(line)

    frames = _parse_sse(lines)
    complete = next(data for event, data in frames if event == "complete")
    assert complete["display_name"] == "Research Bot"
    assert complete["agent_id"] == "pesquisador"
    assert complete["agent_name"] == "pesquisador"

    assert {data["display_name"] for _, data in frames} == {"Research Bot"}


@pytest.mark.asyncio
async def test_stream_replay_fallback_when_metadata_missing(app_client):
    """Older log rows without metadata still get identity from execution + registry."""
    app, client = app_client
    db = app.state.db
    eid = await db.create_execution("pesquisador", "manual", status="success")
    await db.add_log(eid, "ai", "legacy row without metadata")

    lines: list[str] = []
    async with client.stream("GET", f"/executions/{eid}/stream") as resp:
        async for line in resp.aiter_lines():
            lines.append(line)

    frames = _parse_sse(lines)
    ai = next(data for event, data in frames if event == "ai")
    assert ai["agent_id"] == "pesquisador"
    assert ai["display_name"] == "Research Bot"
    assert ai["agent_name"] == "pesquisador"


@pytest.mark.asyncio
async def test_live_and_replay_identity_match(app_client):
    """A consumer reconnecting sees the same identity fields as the live EventBus event."""
    app, client = app_client
    db = app.state.db
    bus = app.state.event_bus
    eid = await db.create_execution("pesquisador", "manual", status="running")

    logger = ExecutionLogger(db, eid, "pesquisador", display_name="Research Bot")
    log_id = await logger._persist("ai", "partial")
    live_payload = {
        "event_type": "ai",
        "content": "partial",
        **agent_identity_payload("pesquisador", "Research Bot"),
    }
    await bus.publish(eid, {"type": "ai", "seq": log_id, "data": live_payload})

    # Finish so a late subscriber only replays (no hang on live drain).
    await db.update_execution(eid, status="success", duration_ms=1)

    lines: list[str] = []
    async with client.stream("GET", f"/executions/{eid}/stream") as resp:
        async for line in resp.aiter_lines():
            lines.append(line)

    frames = _parse_sse(lines)
    replayed = next(data for event, data in frames if event == "ai")
    for key in ("agent_id", "display_name", "agent_name"):
        assert replayed[key] == live_payload[key]


def test_on_deleted_publishes_display_name_not_id(tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir()
    path = _write_agent(agents / "pesquisador.md", name="Research Bot")

    reg = AgentRegistry()
    reg.register(parse_agent_file(path))

    handler = _AgentFileHandler(reg, MagicMock(), loop=None, agents_dir=agents)
    handler._publish_event = MagicMock()
    event = MagicMock()
    event.is_directory = False
    event.src_path = str(path)
    path.unlink()
    handler.on_deleted(event)

    assert reg.get("pesquisador") is None
    handler._publish_event.assert_called_once_with("removed", "pesquisador", "Research Bot")


def test_on_moved_out_publishes_display_name_not_id(tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    src = _write_agent(agents / "pesquisador.md", name="Research Bot")
    dest = outside / "pesquisador.md"

    reg = AgentRegistry()
    reg.register(parse_agent_file(src))

    handler = _AgentFileHandler(reg, MagicMock(), loop=None, agents_dir=agents)
    handler._publish_event = MagicMock()
    src.rename(dest)
    event = MagicMock()
    event.is_directory = False
    event.src_path = str(src)
    event.dest_path = str(dest)
    handler.on_moved(event)

    assert reg.get("pesquisador") is None
    handler._publish_event.assert_called_once_with("removed", "pesquisador", "Research Bot")


def test_get_by_path_returns_config_before_remove():
    reg = AgentRegistry()
    cfg = AgentConfig(id="cool", name="Cool Agent", file_path="/workspace/agents/cool.md")
    reg.register(cfg)
    peeked = reg.get_by_path("/workspace/agents/cool.md")
    assert peeked is not None
    assert peeked.name == "Cool Agent"
    assert reg.remove_by_path("/workspace/agents/cool.md") == "cool"
    assert reg.get_by_path("/workspace/agents/cool.md") is None


@pytest.mark.asyncio
async def test_live_complete_event_bus_carries_identity(app_client):
    """Live per-execution complete payload includes identity (display_name != id)."""
    app, _client = app_client
    db = app.state.db
    bus = app.state.event_bus
    eid = await db.create_execution("pesquisador", "manual", status="running")
    config = app.state.runtime.registry.get("pesquisador")
    assert config is not None
    assert config.name == "Research Bot"
    assert config.name != config.id

    queue = bus.subscribe(eid)
    try:
        await app.state.runtime.runner._publish_complete(
            eid,
            {
                "status": "success",
                "duration_ms": 10,
                "total_tokens": 5,
                "cost_usd": 0.0,
                "error": None,
            },
            bus,
            None,
            config,
        )
        event = await asyncio.wait_for(queue.get(), timeout=1.0)
    finally:
        bus.unsubscribe(eid, queue)

    assert event["type"] == "complete"
    data = event["data"]
    assert data["status"] == "success"
    assert data["agent_id"] == "pesquisador"
    assert data["display_name"] == "Research Bot"
    assert data["agent_name"] == "pesquisador"
    assert data["display_name"] != data["agent_id"]


@pytest.mark.asyncio
async def test_synthetic_complete_replay_carries_identity(app_client):
    """Synthetic complete frame for an already-finished execution carries identity."""
    app, client = app_client
    db = app.state.db
    eid = await db.create_execution("pesquisador", "manual", status="success")

    lines: list[str] = []
    async with client.stream("GET", f"/executions/{eid}/stream") as resp:
        async for line in resp.aiter_lines():
            lines.append(line)

    frames = _parse_sse(lines)
    complete = next(data for event, data in frames if event == "complete")
    assert complete["status"] == "success"
    assert complete["agent_id"] == "pesquisador"
    assert complete["display_name"] == "Research Bot"
    assert complete["agent_name"] == "pesquisador"
    assert complete["display_name"] != complete["agent_id"]


@pytest.mark.asyncio
async def test_synthetic_waiting_carries_identity(app_client):
    """Synthetic waiting frame (HILT path) carries identity with display_name != id."""
    app, client = app_client
    db = app.state.db
    eid = await db.create_execution("pesquisador", "manual", status="waiting")

    lines: list[str] = []
    async with client.stream("GET", f"/executions/{eid}/stream") as resp:
        async for line in resp.aiter_lines():
            lines.append(line)

    frames = _parse_sse(lines)
    waiting = next(data for event, data in frames if event == "waiting")
    assert waiting["status"] == "waiting"
    assert waiting["agent_id"] == "pesquisador"
    assert waiting["display_name"] == "Research Bot"
    assert waiting["agent_name"] == "pesquisador"
    assert waiting["display_name"] != waiting["agent_id"]
