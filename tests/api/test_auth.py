"""Tests for the API key middleware itself.

The socket and TCP servers share one FastAPI app, so auth must guard the TCP
entrypoint only — the local CLI talks over the Unix socket and sends no key.

Scope: these tests wrap the app by hand and check the middleware's behaviour.
They say nothing about which entrypoint `agentmd start` wraps, and they pass
unchanged if the socket server is wired to the guarded app by mistake. The
wiring itself is covered end to end in tests/test_start_transport_auth.py.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from agent_md.api.app import create_app
from agent_md.api.auth import ApiKeyMiddleware

API_KEY = "test-secret-key"


@pytest.fixture
async def app(tmp_path):
    """The shared app, as served on the Unix socket (no auth)."""
    application = create_app(workspace=tmp_path, db_path=tmp_path / "test.db")
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def socket_client(app):
    """A client on the bare app — stands in for the local CLI over the UDS."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def tcp_client(app):
    """A client on the wrapped app — stands in for a network caller."""
    transport = ASGITransport(app=ApiKeyMiddleware(app, api_key=API_KEY))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health_no_auth_required(tcp_client):
    resp = await tcp_client.get("/health")
    assert resp.status_code == 200


async def test_info_requires_auth(tcp_client):
    resp = await tcp_client.get("/info")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid or missing API key"


async def test_info_with_valid_key(tcp_client):
    resp = await tcp_client.get("/info", headers={"X-API-Key": API_KEY})
    assert resp.status_code == 200


async def test_info_with_wrong_key(tcp_client):
    resp = await tcp_client.get("/info", headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 401


async def test_key_of_different_length_is_rejected(tcp_client):
    resp = await tcp_client.get("/info", headers={"X-API-Key": API_KEY + "extra"})
    assert resp.status_code == 401


async def test_socket_transport_needs_no_key(socket_client):
    """The trap: guarding the shared app would 401 every local CLI command."""
    resp = await socket_client.get("/info")
    assert resp.status_code == 200


async def test_socket_transport_still_open_while_tcp_is_guarded(socket_client, tcp_client):
    """Same app instance, same runtime — only the TCP entrypoint authenticates."""
    assert (await tcp_client.get("/agents")).status_code == 401
    assert (await socket_client.get("/agents")).status_code == 200


async def test_post_run_is_guarded_on_tcp(tcp_client):
    """The endpoint that executes arbitrary agents must never answer unauthenticated."""
    resp = await tcp_client.post("/agents/whatever/run", json={})
    assert resp.status_code == 401
