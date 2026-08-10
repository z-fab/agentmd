"""Regression tests for Fase 0 hardening (bugs 1–29)."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest

from agent_md.db.database import Database
from agent_md.execution.checkpoint_maint import checkpoint_db_path
from agent_md.config.substitutions import apply_substitutions, apply_substitutions_async
from agent_md.graph.builder import build_system_message, build_system_message_async


# ---------------------------------------------------------------------------
# Bug 1 — update_execution dynamic fields / no finished_at on waiting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_execution_waiting_preserves_tokens(db):
    eid = await db.create_execution("a", "manual")
    await db.update_execution(
        eid, status="running", input_tokens=100, output_tokens=50, total_tokens=150, cost_usd=0.01
    )
    # Simulate HILT pause
    await db.update_execution(
        eid, status="waiting", input_tokens=100, output_tokens=50, total_tokens=150, cost_usd=0.01
    )
    rec = await db.get_execution(eid)
    assert rec.status == "waiting"
    assert rec.finished_at is None
    assert rec.input_tokens == 100
    assert rec.output_tokens == 50
    assert rec.cost_usd == 0.01


@pytest.mark.asyncio
async def test_update_execution_terminal_sets_finished_at(db):
    eid = await db.create_execution("a", "manual")
    await db.update_execution(eid, status="success", duration_ms=10)
    rec = await db.get_execution(eid)
    assert rec.status == "success"
    assert rec.finished_at is not None


# ---------------------------------------------------------------------------
# Bug 3 — readonly connect on missing file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_readonly_connect_creates_missing_db(tmp_path):
    path = tmp_path / "fresh" / "agentmd.db"
    assert not path.exists()
    db = Database(path)
    await db.connect(readonly=True)
    try:
        assert path.exists()
        rows = await db.list_executions()
        assert rows == []
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# Bug 4 — migrate pid / cost_usd
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migrate_adds_missing_columns(tmp_path):
    path = tmp_path / "legacy.db"
    async with aiosqlite.connect(str(path)) as conn:
        await conn.execute(
            """
            CREATE TABLE executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                status TEXT NOT NULL,
                trigger TEXT NOT NULL,
                started_at TIMESTAMP NOT NULL,
                finished_at TIMESTAMP,
                duration_ms INTEGER,
                input_data TEXT,
                output_data TEXT,
                error TEXT,
                input_tokens INTEGER,
                output_tokens INTEGER,
                total_tokens INTEGER
            )
            """
        )
        await conn.commit()

    db = Database(path)
    await db.connect()
    try:
        # create_execution writes pid — would fail without migration
        eid = await db.create_execution("a", "manual")
        await db.update_execution(eid, status="success", cost_usd=1.23)
        rec = await db.get_execution(eid)
        assert rec.cost_usd == 1.23
        assert rec.pid is not None
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# Bug 5 — checkpoint path collision
# ---------------------------------------------------------------------------


def test_checkpoint_db_path_uses_stem():
    assert checkpoint_db_path("/data/agentmd.db").name == "agentmd_checkpoints.db"
    # No .db suffix must not write into the main file
    p = checkpoint_db_path("/data/agentmd")
    assert p.name == "agentmd_checkpoints.db"
    assert str(p) != "/data/agentmd"
    # Mid-name .db must not corrupt the path
    p2 = checkpoint_db_path("/data/foo.db.backup")
    assert p2.name == "foo.db_checkpoints.db"


@pytest.mark.parametrize(
    ("provider", "given", "expected"),
    [
        ("openai", "http://proxy.internal", "http://proxy.internal/v1"),
        ("local", "http://vllm.internal/", "http://vllm.internal/v1"),
        ("ollama", "http://ollama.internal:11434/", "http://ollama.internal:11434"),
        ("anthropic", "http://anthropic-proxy.internal", "http://anthropic-proxy.internal"),
    ],
)
def test_base_url_normalization_is_provider_aware(provider, given, expected):
    from agent_md.config.models import ModelConfig

    assert ModelConfig(provider=provider, name="test", base_url=given).base_url == expected


# ---------------------------------------------------------------------------
# Bug 6 — logs ordered by id, higher default limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_logs_ordered_by_id(db):
    eid = await db.create_execution("a", "manual")
    # Same-second timestamps — order must still be insertion order
    for i in range(5):
        await db.add_log(eid, "ai", f"msg-{i}")
    logs = await db.get_logs(eid, limit=3)
    assert [log.message for log in logs] == ["msg-0", "msg-1", "msg-2"]
    assert logs[0].id < logs[1].id < logs[2].id


# ---------------------------------------------------------------------------
# Bug 7 — substitutions never applied to memory/generated content
# ---------------------------------------------------------------------------


def _memory_injection_fixtures(tmp_path):
    memory = tmp_path / "agent.memory.md"
    marker = tmp_path / "PWNED"
    memory.write_text(f"# Section !`touch {marker}`\n\nbody\n", encoding="utf-8")

    agent = MagicMock()
    agent.name = "agent"
    agent.skills = []
    agent.agents = []
    agent.paths = {}
    agent.trigger = MagicMock(type="manual")

    pc = MagicMock()
    pc.workspace_root = tmp_path
    pc.skills_dir = tmp_path / "skills"
    pc.skills_dir.mkdir()
    pc.get_memory_file_path = MagicMock(return_value=memory)
    return agent, pc, marker


def test_build_system_message_does_not_run_commands_from_memory(tmp_path):
    agent, pc, marker = _memory_injection_fixtures(tmp_path)
    msg = build_system_message("Hello $ARGUMENTS", agent, pc, arguments="world")
    assert "Hello world" in msg.content
    assert not marker.exists()


@pytest.mark.asyncio
async def test_build_system_message_async_does_not_run_commands_from_memory(tmp_path):
    """Production path (runner/builder) uses the async variant — must be equally safe."""
    agent, pc, marker = _memory_injection_fixtures(tmp_path)
    msg = await build_system_message_async("Hello $ARGUMENTS", agent, pc, arguments="world")
    assert "Hello world" in msg.content
    assert not marker.exists()


# ---------------------------------------------------------------------------
# Bug 9 — async substitutions use to_thread (smoke)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_substitutions_async_runs_command(tmp_path):
    out = await apply_substitutions_async("x=!`echo hi`", cwd=str(tmp_path))
    assert "hi" in out


def test_apply_substitutions_allow_commands_false():
    out = apply_substitutions("x=!`echo hi`", allow_commands=False)
    assert out == "x=!`echo hi`"


# ---------------------------------------------------------------------------
# Bug 10 — cancel_event propagated to run_agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_agent_propagates_cancel_and_usage():
    from agent_md.tools.agents.run_agent import create_run_agent_tool

    caller = MagicMock()
    caller.name = "orch"
    caller.agents = ["worker"]
    worker = MagicMock()
    worker.name = "worker"
    worker.enabled = True
    registry = MagicMock()
    registry.get.return_value = worker
    runner = AsyncMock()
    runner.run.return_value = {
        "status": "success",
        "output": "ok",
        "execution_id": 2,
        "duration_ms": 1,
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
        "cost_usd": 0.02,
    }
    cancel = asyncio.Event()
    usage = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    tool = create_run_agent_tool(
        caller_config=caller,
        registry=registry,
        runner=runner,
        cancel_event=cancel,
        sub_agent_usage=usage,
    )
    result = await tool.ainvoke({"agent_name": "worker"})
    assert result["status"] == "success"
    assert runner.run.call_args.kwargs["cancel_event"] is cancel
    assert usage["input_tokens"] == 10
    assert usage["output_tokens"] == 5
    assert usage["cost_usd"] == 0.02


# ---------------------------------------------------------------------------
# Bug 15 — base_url / timeout passed to openai/ollama
# ---------------------------------------------------------------------------


def test_create_chat_model_passes_base_url_and_timeout_openai():
    import types

    import agent_md.providers.factory as factory_mod

    captured = {}

    class Fake:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    mod = types.ModuleType("langchain_openai")
    mod.ChatOpenAI = Fake
    with patch.dict("sys.modules", {"langchain_openai": mod}):
        factory_mod.create_chat_model(
            "openai",
            "gpt-4o",
            {"temperature": 0.1, "max_tokens": 100, "timeout": 42},
            base_url="http://localhost:9999/v1",
        )
    assert captured.get("base_url") == "http://localhost:9999/v1"
    assert captured.get("timeout") == 42
    assert captured.get("model") == "gpt-4o"


# ---------------------------------------------------------------------------
# Bug 16 — MCP connect lock + logger restore
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_connect_restores_logger_on_error():
    from agent_md.mcp.manager import MCPManager

    mgr = MCPManager({"bad": {"transport": "stdio", "command": "false"}})
    stdio_logger = logging.getLogger("mcp.client.stdio")
    before = stdio_logger.level

    with patch("agent_md.mcp.manager.MultiServerMCPClient") as Client:
        instance = Client.return_value
        instance.get_tools = AsyncMock(side_effect=RuntimeError("boom"))
        with pytest.raises(RuntimeError):
            await mgr._connect("bad")
    assert stdio_logger.level == before


@pytest.mark.asyncio
async def test_mcp_connect_serialized():
    from agent_md.mcp.manager import MCPManager

    mgr = MCPManager({"s": {"transport": "stdio", "command": "echo"}})
    calls = 0

    async def slow_get_tools():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        tool = MagicMock()
        tool.name = "t"
        return [tool]

    with patch("agent_md.mcp.manager.MultiServerMCPClient") as Client:
        instance = Client.return_value
        instance.get_tools = AsyncMock(side_effect=slow_get_tools)
        await asyncio.gather(mgr.get_tools(["s"]), mgr.get_tools(["s"]))
    assert calls == 1
    assert Client.call_count == 1


# ---------------------------------------------------------------------------
# Bug 12 — invalid mcp config does not crash bootstrap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bootstrap_survives_invalid_mcp_json(tmp_path):
    from agent_md.workspace.bootstrap import bootstrap

    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "a.md").write_text(
        "---\nname: a\nmodel:\n  provider: google\n  name: gemini-2.5-flash\n---\nHi\n",
        encoding="utf-8",
    )
    mcp = agents / "_config" / "mcp-servers.json"
    mcp.parent.mkdir(parents=True)
    mcp.write_text("{not json", encoding="utf-8")
    db = tmp_path / "db.db"
    rt = await bootstrap(workspace=tmp_path, agents_dir=agents, db_path=db, mcp_config=mcp)
    assert rt.mcp_manager.list_servers() == []
    await rt.aclose()


# ---------------------------------------------------------------------------
# Bug 18 — chat_session removed
# ---------------------------------------------------------------------------


def test_chat_session_removed():
    import agent_md.workspace.services as services

    assert not hasattr(services, "chat_session")
    assert not hasattr(services, "ChatSession")


# ---------------------------------------------------------------------------
# Bug 2 — resume seeds counters; child cost not re-priced at parent rate
# ---------------------------------------------------------------------------


def _resume_config(*, max_cost_usd=None, max_tool_calls=50, max_execution_tokens=500_000):
    from agent_md.config.pricing import estimate_cost

    config = MagicMock()
    config.id = "test-agent"
    config.name = "test-agent"
    config.model.provider = "openai"
    config.model.name = "gpt-4o"
    config.model.base_url = None
    config.settings.temperature = 0.7
    config.settings.max_tokens = 4096
    config.settings.timeout = 300
    config.settings.max_tool_calls = max_tool_calls
    config.settings.max_execution_tokens = max_execution_tokens
    config.settings.max_cost_usd = max_cost_usd
    config.settings.loop_detection = False
    config.settings.model_dump.return_value = {"temperature": 0.7, "max_tokens": 4096, "timeout": 300}
    config.history = "off"
    config.system_prompt = "test"
    config.custom_tools = []
    config.mcp = []
    config.skills = []
    config.confirm_timeout = None
    config.paths = {}
    # sanity: pricing exists for gpt-4o
    assert estimate_cost("openai", "gpt-4o", 1000, 1000) is not None
    return config


@pytest.mark.asyncio
async def test_resume_preserves_parent_and_child_cost(tmp_path, db):
    """Pause→resume must keep real child cost, not reprice child tokens at parent rate."""
    from agent_md.config.pricing import estimate_cost
    from agent_md.execution.runner import AgentRunner

    eid = await db.create_execution("test-agent", "manual")

    # Parent: 1k/1k on gpt-4o; child contributed 5k tokens at a different rate ($0.50 flat).
    parent_in, parent_out = 1000, 1000
    parent_cost = estimate_cost("openai", "gpt-4o", parent_in, parent_out)
    child_tokens = 5000
    child_cost = 0.50
    true_cost = parent_cost + child_cost

    await db.update_execution(
        eid,
        status="waiting",
        input_tokens=parent_in,
        output_tokens=parent_out,
        total_tokens=parent_in + parent_out + child_tokens,
        cost_usd=true_cost,
    )
    await db.set_pending_interrupt(eid, "r1", {"request_id": "r1", "kind": "confirm", "message": "?"})
    # Two prior tool calls
    await db.add_log(eid, "tool_call", "t1")
    await db.add_log(eid, "tool_call", "t2")

    config = _resume_config()
    runner = AgentRunner(db, MagicMock(), MagicMock(), db_path=str(db.db_path))

    # Resume segment: one more AI message with 500/500 parent tokens, no tools
    final = MagicMock()
    final.type = "ai"
    final.content = "done"
    final.tool_calls = []
    final.usage_metadata = {"input_tokens": 500, "output_tokens": 500}

    with patch.object(runner, "_build_graph", new_callable=AsyncMock) as mock_build:
        mock_build.return_value = (MagicMock(), None)
        with patch("agent_md.graph.builder._stream_state") as mock_stream:

            async def fake_stream(*args, **kwargs):
                yield final

            mock_stream.side_effect = lambda *a, **k: fake_stream()
            with patch("agent_md.execution.runner._is_final_ai_message", return_value=True):
                result = await runner.resume(config, eid, {"approved": True})

    assert result["status"] == "success"
    # Parent tokens: 1000+500 / 1000+500; child cost preserved
    expected_parent = estimate_cost("openai", "gpt-4o", 1500, 1500)
    expected_cost = expected_parent + child_cost
    assert result["cost_usd"] == pytest.approx(expected_cost, rel=1e-6)
    # Must NOT equal re-pricing all tokens (incl. child) at parent rate
    wrong = estimate_cost("openai", "gpt-4o", 1500 + child_tokens, 1500)
    assert result["cost_usd"] != pytest.approx(wrong, rel=1e-6)
    assert result["input_tokens"] == 1500 + child_tokens  # parent in + sunk child folded into total


@pytest.mark.asyncio
async def test_resume_tool_call_limit_counts_pre_pause(tmp_path, db):
    """max_tool_calls must count tool_call log rows from before the pause."""
    from agent_md.execution.runner import AgentRunner

    eid = await db.create_execution("test-agent", "manual")
    await db.update_execution(eid, status="waiting", input_tokens=0, output_tokens=0, total_tokens=0)
    await db.set_pending_interrupt(eid, "r1", {"request_id": "r1", "kind": "confirm", "message": "?"})
    for i in range(2):
        await db.add_log(eid, "tool_call", f"t{i}")

    config = _resume_config(max_tool_calls=2)
    runner = AgentRunner(db, MagicMock(), MagicMock(), db_path=str(db.db_path))

    next_call = MagicMock()
    next_call.type = "ai"
    next_call.content = ""
    next_call.tool_calls = [{"name": "x", "args": {}}]
    next_call.usage_metadata = {"input_tokens": 1, "output_tokens": 1}

    with patch.object(runner, "_build_graph", new_callable=AsyncMock) as mock_build:
        mock_build.return_value = (MagicMock(), None)
        with patch("agent_md.graph.builder._stream_state") as mock_stream:

            async def fake_stream(*args, **kwargs):
                yield next_call

            mock_stream.side_effect = lambda *a, **k: fake_stream()
            result = await runner.resume(config, eid, {"approved": True})

    assert result["status"] == "aborted"
    assert "max_tool_calls" in result.get("error", "")


# ---------------------------------------------------------------------------
# Bug 8 — start refuses live socket
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_backend_aborts_when_socket_healthy(tmp_path, monkeypatch):
    from agent_md.cli.commands import _run_backend
    from agent_md.cli.errors import BackendAlreadyRunning

    sock = tmp_path / "agentmd.sock"
    sock.write_text("")
    monkeypatch.setattr("agent_md.cli.client.get_socket_path", lambda: sock)
    monkeypatch.setattr("agent_md.cli.client.get_state_dir", lambda: tmp_path)

    with patch("agent_md.cli.client.BackendClient") as Client:
        Client.return_value.health_check.return_value = True
        with pytest.raises(BackendAlreadyRunning):
            await _run_backend(tmp_path, False, None, "127.0.0.1", None, True)
    assert sock.exists()  # must not have been unlinked


# ---------------------------------------------------------------------------
# Bug 11 — validate / run exit codes
# ---------------------------------------------------------------------------


def test_validate_exits_nonzero_on_errors(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from agent_md.main import app

    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "bad.md").write_text(
        "---\nname: bad\nmodel:\n  provider: openai\n  name: gpt-4o\ncustom_tools: [missing_tool]\n---\nHi\n",
        encoding="utf-8",
    )

    # Ensure validate sees missing custom tool as an error
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(
        "agent_md.config.settings.settings.workspace",
        str(tmp_path),
        raising=False,
    )
    # Patch settings used inside validate via services
    from agent_md.config import settings as settings_mod

    monkeypatch.setattr(settings_mod.settings, "workspace", str(tmp_path))
    monkeypatch.setattr(settings_mod.settings, "agents_dir", "agents")
    monkeypatch.setattr(settings_mod.settings, "tools_dir", "")
    monkeypatch.setattr(settings_mod.settings, "mcp_config", "")

    runner = CliRunner()
    result = runner.invoke(app, ["validate", "bad", "--workspace", str(tmp_path)])
    assert result.exit_code == 1


def test_stream_execution_returns_status_for_exit_code():
    """Bug 11 plumbing: complete events expose status for typer.Exit(1)."""
    from agent_md.cli import commands
    from rich.console import Console

    class _FakeSSE:
        def __init__(self, lines):
            self._lines = lines

        def iter_lines(self):
            return iter(self._lines)

    class _Client:
        def __init__(self, lines):
            self._lines = lines

        def stream_sse(self, path):
            import contextlib

            @contextlib.contextmanager
            def _cm():
                yield _FakeSSE(self._lines)

            return _cm()

    lines = [
        "event: complete",
        'data: {"status": "error", "error": "boom"}',
        "",
    ]
    res = commands._stream_execution(_Client(lines), 1, Console(), quiet=True)
    assert res["status"] == "error"


# ---------------------------------------------------------------------------
# Bug 13 — validate_agent tools/mcp under _config
# ---------------------------------------------------------------------------


def test_validate_agent_resolves_tools_under_config(tmp_path, monkeypatch):
    from agent_md.workspace.services import validate_agent
    from agent_md.config import settings as settings_mod

    agents = tmp_path / "agents"
    tools = agents / "_config" / "tools"
    tools.mkdir(parents=True)
    (tools / "mytool.py").write_text(
        "from langchain_core.tools import tool\n@tool\ndef mytool(x: str) -> str:\n    '''t'''\n    return x\n",
        encoding="utf-8",
    )
    (agents / "a.md").write_text(
        "---\nname: a\nmodel:\n  provider: ollama\n  name: llama3\ncustom_tools: [mytool]\n---\nHi\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_mod.settings, "workspace", str(tmp_path))
    monkeypatch.setattr(settings_mod.settings, "agents_dir", "agents")
    monkeypatch.setattr(settings_mod.settings, "tools_dir", "")
    monkeypatch.setattr(settings_mod.settings, "mcp_config", "")

    result = validate_agent("a", workspace=tmp_path)
    assert "mytool" in result.custom_tools_found
    assert "mytool" not in result.custom_tools_missing


# ---------------------------------------------------------------------------
# Bug 14 — POST /agents/reload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agents_reload_filters_memory_reschedules_removes(tmp_path):
    from httpx import ASGITransport, AsyncClient
    from agent_md.api.app import create_app

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "keep.md").write_text(
        "---\nname: keep\nmodel:\n  provider: google\n  name: gemini-2.5-flash\n---\nHi\n",
        encoding="utf-8",
    )
    (agents_dir / "gone.md").write_text(
        "---\nname: gone\nmodel:\n  provider: google\n  name: gemini-2.5-flash\n---\nHi\n",
        encoding="utf-8",
    )
    (agents_dir / "keep.memory.md").write_text("# mem\n", encoding="utf-8")

    application = create_app(workspace=tmp_path, agents_dir=agents_dir, db_path=tmp_path / "test.db")
    async with application.router.lifespan_context(application):
        # Remove gone.md, then reload
        (agents_dir / "gone.md").unlink()
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/agents/reload")
            assert resp.status_code == 200
            body = resp.json()
            assert body["agents_loaded"] == 1
            assert body["agents_removed"] >= 1
            assert body["errors"] == []
            names = {a["name"] for a in (await client.get("/agents")).json()}
            assert names == {"keep"}
            assert "gone" not in names


# ---------------------------------------------------------------------------
# Duplicate display names coexist under filename-as-id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bootstrap_allows_duplicate_display_names(tmp_path, caplog):
    from agent_md.workspace.bootstrap import bootstrap

    agents = tmp_path / "agents"
    agents.mkdir()
    for fname in ("a.md", "b.md"):
        (agents / fname).write_text(
            "---\nname: same\nmodel:\n  provider: google\n  name: gemini-2.5-flash\n---\nHi\n",
            encoding="utf-8",
        )
    with caplog.at_level(logging.WARNING):
        rt = await bootstrap(workspace=tmp_path, agents_dir=agents, db_path=tmp_path / "db.db")
    assert not any("Duplicate agent name" in r.message for r in caplog.records)
    assert len(rt.registry) == 2
    assert rt.registry.get("a").name == "same"
    assert rt.registry.get("b").name == "same"
    await rt.aclose()


# ---------------------------------------------------------------------------
# Bug 19 — checkpoint uses effective db_path
# ---------------------------------------------------------------------------


def test_checkpoint_command_uses_config_db_path(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from agent_md.main import app
    from agent_md.config import settings as settings_mod

    custom_db = tmp_path / "custom" / "mydb.db"
    custom_db.parent.mkdir()
    monkeypatch.setattr(settings_mod.settings, "db_path", str(custom_db))
    monkeypatch.setattr(settings_mod.settings, "workspace", str(tmp_path))

    runner = CliRunner()
    result = runner.invoke(app, ["checkpoint", "--stats", "--workspace", str(tmp_path)])
    assert result.exit_code == 0
    assert "mydb_checkpoints.db" in result.stdout


# ---------------------------------------------------------------------------
# Bug 20 — background tasks retained
# ---------------------------------------------------------------------------


def test_spawn_background_retains_reference():
    from agent_md.util import tasks as tasks_mod

    async def _noop():
        return 1

    async def _run():
        tasks_mod._BACKGROUND_TASKS.clear()
        t = tasks_mod.spawn_background(_noop())
        assert t in tasks_mod._BACKGROUND_TASKS
        await t
        assert t not in tasks_mod._BACKGROUND_TASKS

    asyncio.run(_run())
