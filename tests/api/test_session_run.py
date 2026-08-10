"""POST /agents/{id}/run — session_id, the real trigger, and context passthrough."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from agent_md.api.app import create_app


@pytest.fixture
async def app_with_agent(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "talker.md").write_text(
        "---\nmodel:\n  provider: google\n  name: gemini-2.5-flash\n---\nYou are a test agent.\n"
    )
    application = create_app(workspace=tmp_path, agents_dir=agents_dir, db_path=tmp_path / "test.db")
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app_with_agent):
    transport = ASGITransport(app=app_with_agent)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def runner_spy(app_with_agent):
    """Replace the real runner so no model is ever built; record what it was handed."""
    calls: list[dict] = []
    done = asyncio.Event()

    async def _run(config, **kwargs):
        calls.append(kwargs)
        done.set()
        return {"status": "success", "execution_id": kwargs.get("execution_id")}

    app_with_agent.state.runtime.runner.run = _run
    return calls, done


async def _post_run(client, body):
    resp = await client.post("/agents/talker/run", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()["execution_id"]


async def test_session_run_is_recorded_as_a_chat_turn(client, app_with_agent, runner_spy):
    calls, done = runner_spy
    execution_id = await _post_run(client, {"message": "hi", "session_id": "sess-1"})
    await asyncio.wait_for(done.wait(), timeout=5)

    row = await app_with_agent.state.db.get_execution(execution_id)
    assert row.session_id == "sess-1"
    assert row.trigger == "chat"
    assert calls[0]["session_id"] == "sess-1"
    assert calls[0]["trigger_type"] == "chat"


async def test_run_without_session_stays_manual_and_sessionless(client, app_with_agent, runner_spy):
    calls, done = runner_spy
    execution_id = await _post_run(client, {"args": []})
    await asyncio.wait_for(done.wait(), timeout=5)

    row = await app_with_agent.state.db.get_execution(execution_id)
    assert row.session_id is None
    assert row.trigger == "manual"
    assert calls[0]["session_id"] is None
    assert calls[0]["trigger_type"] == "manual"


async def test_context_reaches_the_runner(client, runner_spy):
    """`context` used to be accepted and silently dropped."""
    calls, done = runner_spy
    await _post_run(client, {"context": "invoice #42 arrived"})
    await asyncio.wait_for(done.wait(), timeout=5)
    assert calls[0]["trigger_context"] == "invoice #42 arrived"


async def test_blank_session_id_is_treated_as_absent(client, app_with_agent, runner_spy):
    _calls, done = runner_spy
    execution_id = await _post_run(client, {"session_id": "   "})
    await asyncio.wait_for(done.wait(), timeout=5)

    row = await app_with_agent.state.db.get_execution(execution_id)
    assert row.session_id is None
    assert row.trigger == "manual"


async def test_oversized_session_id_is_rejected(client):
    resp = await client.post("/agents/talker/run", json={"session_id": "x" * 201})
    assert resp.status_code == 422


async def test_execution_endpoints_expose_session_id(client, app_with_agent, runner_spy):
    _calls, done = runner_spy
    execution_id = await _post_run(client, {"session_id": "sess-9"})
    await asyncio.wait_for(done.wait(), timeout=5)

    detail = await client.get(f"/executions/{execution_id}")
    assert detail.json()["session_id"] == "sess-9"

    listing = await client.get("/executions")
    assert listing.json()[0]["session_id"] == "sess-9"

    runs = await client.get("/agents/talker/runs")
    assert runs.json()[0]["session_id"] == "sess-9"
