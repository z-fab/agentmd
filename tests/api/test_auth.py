"""Tests for API key authentication middleware."""

import pytest
from httpx import ASGITransport, AsyncClient
from agent_md.api.app import create_app
from agent_md.api.auth import ApiKeyMiddleware


@pytest.fixture
async def secured_app(tmp_path):
    application = create_app(workspace=tmp_path, db_path=tmp_path / "test.db")
    application.add_middleware(ApiKeyMiddleware, api_key="test-secret-key")
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(secured_app):
    transport = ASGITransport(app=secured_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health_no_auth_required(client):
    resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_info_requires_auth(client):
    resp = await client.get("/info")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_info_with_valid_key(client):
    resp = await client.get("/info", headers={"X-API-Key": "test-secret-key"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_info_with_wrong_key(client):
    resp = await client.get("/info", headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 401
