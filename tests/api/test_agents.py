"""Tests for /agents endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient
from agent_md.api.app import create_app


@pytest.fixture
async def app_with_agents(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "test-agent.md").write_text(
        "---\nname: test-agent\nmodel:\n  provider: google\n  name: gemini-2.5-flash\n---\nYou are a test agent.\n"
    )
    application = create_app(workspace=tmp_path, db_path=tmp_path / "test.db")
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app_with_agents):
    transport = ASGITransport(app=app_with_agents)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_list_agents(client):
    resp = await client.get("/agents")
    assert resp.status_code == 200
    agents = resp.json()
    assert len(agents) >= 1
    assert any(a["name"] == "test-agent" for a in agents)


@pytest.mark.asyncio
async def test_get_agent_detail(client):
    resp = await client.get("/agents/test-agent")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "test-agent"
    assert data["model_provider"] == "google"


@pytest.mark.asyncio
async def test_get_agent_not_found(client):
    resp = await client.get("/agents/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_agent_runs_empty(client):
    resp = await client.get("/agents/test-agent/runs")
    assert resp.status_code == 200
    assert resp.json() == []
