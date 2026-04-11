"""Tests for /executions endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient
from agent_md.api.app import create_app


@pytest.fixture
async def app(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    application = create_app(workspace=tmp_path)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_list_executions_empty(client):
    resp = await client.get("/executions")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_get_execution_not_found(client):
    resp = await client.get("/executions/9999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cancel_execution_not_found(client):
    resp = await client.delete("/executions/9999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_and_get_execution(app, client):
    rt = app.state.runtime
    eid = await rt.db.create_execution("test-agent", "manual")
    await rt.db.update_execution(eid, status="success", duration_ms=100)

    resp = await client.get("/executions")
    assert resp.status_code == 200
    execs = resp.json()
    assert len(execs) == 1
    assert execs[0]["id"] == eid

    resp = await client.get(f"/executions/{eid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == eid
    assert resp.json()["status"] == "success"


@pytest.mark.asyncio
async def test_get_execution_messages(app, client):
    rt = app.state.runtime
    eid = await rt.db.create_execution("test-agent", "manual")
    await rt.db.add_log(eid, "system", "System prompt")
    await rt.db.add_log(eid, "ai", "Hello")

    resp = await client.get(f"/executions/{eid}/messages")
    assert resp.status_code == 200
    msgs = resp.json()
    assert len(msgs) == 2
    assert msgs[0]["event_type"] == "system"
    assert msgs[1]["event_type"] == "ai"
