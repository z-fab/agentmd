"""A run that fails before streaming must still put the error on ``complete``.

Graph-build failures (missing API key, bad provider config) finish so fast that
the CLI's SSE client often connects after the execution is already terminal.
The stream then synthesises ``complete`` from the DB row — and used to omit
``error``, so the user saw a blank status while the real message sat only in
the backend log.
"""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from agent_md.api.app import create_app
from agent_md.config.models import AgentConfig
from agent_md.execution.runner import AgentRunner
from agent_md.workspace.path_context import PathContext


def _parse_sse(lines: list[str]) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    event_name = "message"
    data_raw = None
    for line in lines:
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_raw = line.split(":", 1)[1].strip()
        elif line == "" and data_raw is not None:
            events.append((event_name, json.loads(data_raw)))
            event_name = "message"
            data_raw = None
    if data_raw is not None:
        events.append((event_name, json.loads(data_raw)))
    return events


class _NoMCP:
    async def get_tools(self, *_a, **_k):
        return []


@pytest.mark.asyncio
async def test_synthesised_complete_includes_persisted_error(tmp_path):
    """Already-finished error row → SSE ``complete`` must carry ``error``."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "boom.md").write_text(
        "---\nmodel:\n  provider: google\n  name: gemini-2.5-flash\n---\nHi.\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "test.db"
    app = create_app(workspace=tmp_path, agents_dir=agents_dir, db_path=db_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            eid = await app.state.db.create_execution("boom", "manual", status="running")
            err = (
                "ValueError: GROQ_API_KEY is not set (required by provider 'groq'). "
                "Set it in your .env, or point `api_key_env` at the variable that holds the key."
            )
            await app.state.db.update_execution(
                execution_id=eid,
                status="error",
                duration_ms=12,
                error=err,
            )

            lines: list[str] = []
            async with client.stream("GET", f"/executions/{eid}/stream") as resp:
                assert resp.status_code == 200
                async for line in resp.aiter_lines():
                    lines.append(line)

    frames = _parse_sse(lines)
    completes = [data for event, data in frames if event == "complete"]
    assert len(completes) == 1
    assert completes[0]["status"] == "error"
    assert completes[0]["error"] == err
    assert "GROQ_API_KEY" in completes[0]["error"]


@pytest.mark.asyncio
async def test_graph_build_failure_reaches_complete_event(tmp_path, monkeypatch):
    """Missing-key failure at ``_build_graph`` must survive onto ``complete``.

    Reproduces the CLI race: run finishes with no subscriber, then the stream
    connects and synthesises ``complete`` from the DB.
    """
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "boom.md").write_text(
        "---\nmodel:\n  provider: groq\n  base_url: https://api.groq.com/openai/v1\n"
        "  name: llama-3.3-70b\n---\nSay hi.\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "test.db"
    app = create_app(workspace=tmp_path, agents_dir=agents_dir, db_path=db_path)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            db = app.state.db
            pc = PathContext(
                workspace_root=tmp_path,
                agents_dir=agents_dir,
                db_path=db_path,
                mcp_config=tmp_path / "m.json",
                tools_dir=tmp_path,
                skills_dir=tmp_path,
            )
            runner = AgentRunner(db, mcp_manager=_NoMCP(), path_context=pc, db_path=str(db_path))
            config = AgentConfig(
                id="boom",
                model={
                    "provider": "groq",
                    "name": "llama-3.3-70b",
                    "base_url": "https://api.groq.com/openai/v1",
                },
            )
            eid = await db.create_execution("boom", "manual", status="running")
            # No event_bus: the live complete never reaches a subscriber — same
            # as a CLI client that opens the stream after graph-build already failed.
            result = await runner.run(config, execution_id=eid, event_bus=None)
            await runner.aclose()

            assert result["status"] == "error"
            assert "GROQ_API_KEY" in result["error"]

            lines: list[str] = []
            async with client.stream("GET", f"/executions/{eid}/stream") as resp:
                assert resp.status_code == 200
                async for line in resp.aiter_lines():
                    lines.append(line)

    frames = _parse_sse(lines)
    completes = [data for event, data in frames if event == "complete"]
    assert len(completes) == 1, f"expected one complete, got {frames!r}"
    assert completes[0]["status"] == "error"
    assert completes[0].get("error"), "complete must carry the error text the user reads"
    assert "GROQ_API_KEY" in completes[0]["error"]
