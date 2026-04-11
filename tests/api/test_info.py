"""Tests for /health, /info, /shutdown routes."""

import pytest
from httpx import ASGITransport, AsyncClient
from agent_md.api.app import create_app


@pytest.fixture
async def app(tmp_path):
    application = create_app(workspace=tmp_path)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_info(client):
    resp = await client.get("/info")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    assert "pid" in data
    assert "uptime_seconds" in data
    assert "agents_loaded" in data


@pytest.mark.asyncio
async def test_shutdown(client):
    resp = await client.post("/shutdown")
    assert resp.status_code == 200
    assert resp.json()["message"] == "shutting down"
