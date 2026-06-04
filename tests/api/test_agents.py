"""Tests for /agents endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient
from agent_md.api.app import create_app


@pytest.fixture
async def app_with_agents(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "test-agent.md").write_text(
        "---\n"
        "name: test-agent\n"
        "model:\n  provider: google\n  name: gemini-2.5-flash\n"
        "tools: [file_read, file_write]\n"
        "paths:\n  vault: ./my-vault\n"
        "---\nYou are a test agent.\n"
    )
    (agents_dir / "icon-agent.md").write_text(
        "---\n"
        "name: icon-agent\n"
        'icon: "📅"\n'
        "model:\n  provider: google\n  name: gemini-2.5-flash\n"
        "---\nYou are an agent with an icon.\n"
    )
    application = create_app(workspace=tmp_path, agents_dir=agents_dir, db_path=tmp_path / "test.db")
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


@pytest.mark.asyncio
async def test_get_agent_detail_exposes_full_config(client):
    resp = await client.get("/agents/test-agent")
    assert resp.status_code == 200
    data = resp.json()

    assert data["custom_tools"] == ["file_read", "file_write"]
    assert "vault" in data["paths"]
    assert data["paths"]["vault"].endswith("my-vault")
    assert data["mcp"] == []
    assert data["skills"] == []
    assert data["trigger_every"] is None
    assert data["trigger_cron"] is None
    assert data["trigger_paths"] == []
    assert data["source_path"] is not None
    assert data["source_path"].endswith("test-agent.md")


@pytest.mark.asyncio
async def test_list_agents_includes_icon_key(client):
    """GET /agents returns objects that include an `icon` key."""
    resp = await client.get("/agents")
    assert resp.status_code == 200
    agents = resp.json()
    assert len(agents) >= 1
    for agent in agents:
        assert "icon" in agent


@pytest.mark.asyncio
async def test_list_agents_icon_value_round_trips(client):
    """Agent with icon: '📅' returns the correct value in GET /agents."""
    resp = await client.get("/agents")
    assert resp.status_code == 200
    agents = resp.json()
    icon_agent = next((a for a in agents if a["name"] == "icon-agent"), None)
    assert icon_agent is not None
    assert icon_agent["icon"] == "📅"


@pytest.mark.asyncio
async def test_list_agents_icon_none_for_agent_without_icon(client):
    """Agent without icon returns None for icon in GET /agents."""
    resp = await client.get("/agents")
    assert resp.status_code == 200
    agents = resp.json()
    test_agent = next((a for a in agents if a["name"] == "test-agent"), None)
    assert test_agent is not None
    assert test_agent["icon"] is None


@pytest.mark.asyncio
async def test_get_agent_detail_icon_round_trips(client):
    """Agent with icon: '📅' returns the correct value in GET /agents/{name}."""
    resp = await client.get("/agents/icon-agent")
    assert resp.status_code == 200
    data = resp.json()
    assert data["icon"] == "📅"


@pytest.mark.asyncio
async def test_get_agent_detail_icon_none_when_absent(client):
    """Agent without icon returns None for icon in GET /agents/{name}."""
    resp = await client.get("/agents/test-agent")
    assert resp.status_code == 200
    data = resp.json()
    assert data["icon"] is None
