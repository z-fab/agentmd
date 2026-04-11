"""Tests for /scheduler endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient
from agent_md.api.app import create_app


@pytest.fixture
async def app(tmp_path):
    application = create_app(workspace=tmp_path, start_scheduler=False)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_scheduler_status_no_scheduler(client):
    resp = await client.get("/scheduler")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "off"
    assert data["jobs"] == []


@pytest.mark.asyncio
async def test_scheduler_pause_no_scheduler(client):
    resp = await client.post("/scheduler/pause")
    assert resp.status_code == 409
