import json
import pytest
from httpx import AsyncClient, ASGITransport
from agent_md.api.app import create_app


@pytest.fixture
async def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    app = create_app(workspace=tmp_path, db_path=tmp_path / "agentmd.db")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        async with app.router.lifespan_context(app):
            yield app, client


async def test_pending_404_when_none(app_client):
    app, client = app_client
    ex = await app.state.db.create_execution("a", "manual")
    r = await client.get(f"/executions/{ex}/pending")
    assert r.status_code == 404


async def test_respond_resumes(app_client, monkeypatch):
    app, client = app_client
    ex = await app.state.db.create_execution("a", "manual", status="waiting")
    await app.state.db.set_pending_interrupt(ex, "r1", {"request_id": "r1", "kind": "confirm", "message": "ok?"})

    called = {}

    async def fake_dispatch(state, execution_id, response):
        called["id"] = execution_id
        called["response"] = response

    monkeypatch.setattr("agent_md.api.routes.executions._dispatch_resume", fake_dispatch)

    r = await client.post(f"/executions/{ex}/respond", json={"request_id": "r1", "response": {"approved": True}})
    assert r.status_code == 200
    assert r.json()["status"] == "resuming"
    assert called["id"] == ex
    assert await app.state.db.get_pending_interrupt(ex) is None


async def test_respond_stale_request_id(app_client):
    app, client = app_client
    ex = await app.state.db.create_execution("a", "manual", status="waiting")
    await app.state.db.set_pending_interrupt(ex, "r1", {"request_id": "r1", "kind": "confirm", "message": "ok?"})
    r = await client.post(f"/executions/{ex}/respond", json={"request_id": "WRONG", "response": {"approved": True}})
    assert r.status_code == 409


async def test_cancel_waiting_aborts_and_clears(app_client):
    app, client = app_client
    ex = await app.state.db.create_execution("a", "manual", status="waiting")
    await app.state.db.set_pending_interrupt(ex, "r1", {"request_id": "r1", "kind": "confirm", "message": "ok?"})
    r = await client.delete(f"/executions/{ex}")
    assert r.status_code == 200
    assert r.json()["status"] == "aborted"
    assert await app.state.db.get_pending_interrupt(ex) is None
    e = await app.state.db.get_execution(ex)
    assert e.status == "aborted"


async def test_stream_emits_waiting_frame(app_client):
    app, client = app_client
    ex = await app.state.db.create_execution("a", "manual", status="waiting")
    await app.state.db.add_log(ex, "interrupt", "ok?", {"request_id": "r1", "kind": "confirm"})
    await app.state.db.set_pending_interrupt(ex, "r1", {"request_id": "r1", "kind": "confirm", "message": "ok?"})
    seen_events = []
    async with client.stream("GET", f"/executions/{ex}/stream") as resp:
        async for line in resp.aiter_lines():
            if line.startswith("event:"):
                seen_events.append(line.split(":", 1)[1].strip())
            if "waiting" in seen_events:
                break
    assert "interrupt" in seen_events
    assert "waiting" in seen_events
