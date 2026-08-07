"""API/runtime tests for filename-as-id public surface (ticket 02)."""

from urllib.parse import quote

import pytest
from httpx import ASGITransport, AsyncClient

from agent_md.api.app import create_app
from agent_md.config.models import AgentConfig, ModelConfig, TriggerConfig
from agent_md.execution.runner import _agent_identity_fields, _build_event_data


@pytest.fixture
async def app_with_identity(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "pesquisador.md").write_text(
        "---\nname: Pesquisador Senior\nmodel:\n  provider: google\n  name: gemini-2.5-flash\n---\nYou research.\n",
        encoding="utf-8",
    )
    (agents_dir / "Daily Processor.md").write_text(
        "---\n"
        "name: Processador Diário\n"
        "model:\n  provider: google\n  name: gemini-2.5-flash\n"
        "---\nYou process daily tasks.\n",
        encoding="utf-8",
    )
    (agents_dir / "Diário.md").write_text(
        "---\nmodel:\n  provider: google\n  name: gemini-2.5-flash\n---\nAccented stem, display defaults to id.\n",
        encoding="utf-8",
    )
    application = create_app(workspace=tmp_path, agents_dir=agents_dir, db_path=tmp_path / "test.db")
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app_with_identity):
    transport = ASGITransport(app=app_with_identity)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_list_agents_exposes_id_and_display_name(client):
    resp = await client.get("/agents")
    assert resp.status_code == 200
    agents = {a["id"]: a for a in resp.json()}
    assert agents["pesquisador"]["display_name"] == "Pesquisador Senior"
    assert agents["pesquisador"]["name"] == "Pesquisador Senior"
    assert agents["Daily Processor"]["display_name"] == "Processador Diário"
    assert agents["Diário"]["display_name"] == "Diário"


@pytest.mark.asyncio
async def test_get_agent_by_id_not_display_name(client):
    ok = await client.get("/agents/pesquisador")
    assert ok.status_code == 200
    assert ok.json()["id"] == "pesquisador"
    assert ok.json()["display_name"] == "Pesquisador Senior"

    by_display = await client.get("/agents/Pesquisador Senior")
    assert by_display.status_code == 404


@pytest.mark.asyncio
async def test_get_agent_id_with_space_url_encoded(client):
    path = f"/agents/{quote('Daily Processor', safe='')}"
    resp = await client.get(path)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "Daily Processor"
    assert data["display_name"] == "Processador Diário"


@pytest.mark.asyncio
async def test_get_agent_id_with_accent_url_encoded(client):
    path = f"/agents/{quote('Diário', safe='')}"
    resp = await client.get(path)
    assert resp.status_code == 200
    assert resp.json()["id"] == "Diário"


@pytest.mark.asyncio
async def test_run_persists_execution_agent_id(client, app_with_identity):
    """POST /agents/{id}/run stores executions.agent_id = stem, not display name."""
    from unittest.mock import AsyncMock

    rt = app_with_identity.state.runtime
    rt.runner.run = AsyncMock(
        return_value={"status": "success", "duration_ms": 1, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    )

    resp = await client.post("/agents/pesquisador/run", json={})
    assert resp.status_code == 200
    eid = resp.json()["execution_id"]

    # Background task may still be finishing; read DB row created at request time.
    rec = await rt.db.get_execution(eid)
    assert rec is not None
    assert rec.agent_id == "pesquisador"
    assert rec.agent_id != "Pesquisador Senior"

    runs = await client.get("/agents/pesquisador/runs")
    assert runs.status_code == 200
    assert any(r["id"] == eid and r["agent_id"] == "pesquisador" for r in runs.json())


@pytest.mark.asyncio
async def test_list_executions_filter_by_id_not_display_name(client, app_with_identity):
    rt = app_with_identity.state.runtime
    eid = await rt.db.create_execution("pesquisador", "manual")
    await rt.db.update_execution(eid, status="success", duration_ms=10)

    by_id = await client.get("/executions", params={"agent": "pesquisador"})
    assert by_id.status_code == 200
    assert any(e["id"] == eid for e in by_id.json())

    by_display = await client.get("/executions", params={"agent": "Pesquisador Senior"})
    assert by_display.status_code == 200
    assert by_display.json() == []


@pytest.mark.asyncio
async def test_resume_resolves_agent_by_persisted_id(client, app_with_identity, monkeypatch):
    """Respond/resume looks up the agent by executions.agent_id (stem)."""
    rt = app_with_identity.state.runtime
    eid = await rt.db.create_execution("pesquisador", "manual", status="waiting")
    await rt.db.set_pending_interrupt(eid, "req-1", {"request_id": "req-1", "kind": "confirm", "message": "ok?"})

    called = {}

    async def fake_dispatch(state, execution_id, response):
        e = await state.db.get_execution(execution_id)
        config = state.runtime.registry.get(e.agent_id)
        called["agent_id"] = e.agent_id
        called["config_id"] = config.id if config else None
        called["config_display"] = config.name if config else None

    monkeypatch.setattr("agent_md.api.routes.executions._dispatch_resume", fake_dispatch)

    resp = await client.post(
        f"/executions/{eid}/respond",
        json={"request_id": "req-1", "response": {"approved": True}},
    )
    assert resp.status_code == 200
    assert called["agent_id"] == "pesquisador"
    assert called["config_id"] == "pesquisador"
    assert called["config_display"] == "Pesquisador Senior"


def test_agent_identity_fields_separate_id_and_display():
    config = AgentConfig(
        id="stem-id",
        name="Pretty Name",
        model=ModelConfig(provider="google", name="gemini-2.5-flash"),
        trigger=TriggerConfig(type="manual"),
        system_prompt="hi",
    )
    fields = _agent_identity_fields(config)
    assert fields == {
        "agent_id": "stem-id",
        "display_name": "Pretty Name",
        "agent_name": "stem-id",
    }

    msg = type("M", (), {"content": "hello", "type": "ai", "tool_calls": []})()
    data = _build_event_data(msg, "ai", config)
    assert data["agent_id"] == "stem-id"
    assert data["display_name"] == "Pretty Name"
    assert data["agent_name"] == "stem-id"
