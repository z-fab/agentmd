"""Phase 1.3 — CLI by canonical id + agentmd migrate."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from agent_md.cli import app
from agent_md.db.database import Database
from agent_md.workspace.migrate import migrate_workspace
from agent_md.workspace.parser import parse_agent_file
from agent_md.workspace.path_context import PathContext


def _write_agent(
    path: Path,
    *,
    name: str | None = None,
    body: str = "Hello",
    extra: str = "",
) -> Path:
    lines = ["---"]
    if name is not None:
        lines.append(f"name: {name}")
    lines.append("model:")
    lines.append("  provider: google")
    lines.append("  name: gemini-2.5-flash")
    if extra:
        lines.append(extra.rstrip("\n"))
    lines.append("---")
    lines.append(body)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def ws(tmp_path, monkeypatch):
    """Isolated workspace with its own state dir / DB."""
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "_config").mkdir()
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setattr("agent_md.config.settings.get_state_dir", lambda: state)
    monkeypatch.setattr("agent_md.config.settings.settings.agents_dir", "agents")
    monkeypatch.setattr("agent_md.config.settings.settings.db_path", "")
    return tmp_path


def _db(ws: Path) -> Database:
    from agent_md.config.settings import get_state_dir

    return Database(get_state_dir() / "agentmd.db")


# ---------------------------------------------------------------------------
# CLI resolution / display
# ---------------------------------------------------------------------------


def test_list_shows_id_and_display_name(ws):
    _write_agent(ws / "agents" / "pesquisador.md", name="Research Bot")
    _write_agent(ws / "agents" / "helper.md", name=None)

    runner = CliRunner()
    result = runner.invoke(app, ["list", "--workspace", str(ws)])
    assert result.exit_code == 0, result.output
    assert "pesquisador" in result.output
    assert "Research Bot" in result.output
    assert "helper" in result.output
    assert "Id" in result.output
    assert "Display Name" in result.output


def test_validate_by_id_with_distinct_display(ws, monkeypatch):
    _write_agent(ws / "agents" / "pesquisador.md", name="Research Bot")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

    runner = CliRunner()
    result = runner.invoke(app, ["validate", "pesquisador", "--workspace", str(ws)])
    assert result.exit_code == 0, result.output
    assert "Research Bot" in result.output
    assert "pesquisador" in result.output


def test_validate_rejects_display_name_alias(ws):
    _write_agent(ws / "agents" / "pesquisador.md", name="Research Bot")

    runner = CliRunner()
    result = runner.invoke(app, ["validate", "Research Bot", "--workspace", str(ws)])
    assert result.exit_code != 0
    assert "not found" in result.output.lower() or "canonical id" in result.output.lower()


def test_validate_id_with_spaces(ws, monkeypatch):
    _write_agent(ws / "agents" / "meu agente.md", name="Meu Agente")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

    runner = CliRunner()
    result = runner.invoke(app, ["validate", "meu agente", "--workspace", str(ws)])
    assert result.exit_code == 0, result.output
    assert "meu agente" in result.output


def test_validate_id_with_accents(ws, monkeypatch):
    _write_agent(ws / "agents" / "análise.md", name="Análise")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

    runner = CliRunner()
    result = runner.invoke(app, ["validate", "análise", "--workspace", str(ws)])
    assert result.exit_code == 0, result.output
    assert "análise" in result.output


def test_logs_header_shows_id_and_display(ws):
    agents = ws / "agents"
    _write_agent(agents / "pesquisador.md", name="Research Bot")

    async def _seed():
        db = _db(ws)
        await db.connect()
        eid = await db.create_execution("pesquisador", "manual")
        await db.update_execution(eid, status="success", duration_ms=10)
        await db.close()

    import asyncio

    asyncio.run(_seed())

    runner = CliRunner()
    result = runner.invoke(app, ["logs", "pesquisador", "--workspace", str(ws)])
    assert result.exit_code == 0, result.output
    assert "Research Bot" in result.output
    assert "pesquisador" in result.output


# ---------------------------------------------------------------------------
# migrate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migrate_populated_db_and_memory(ws):
    agents = ws / "agents"
    _write_agent(agents / "pesquisador.md", name="Research Bot")
    old_mem = agents / "Research Bot.memory.md"
    old_mem.write_text("# legacy memory\n", encoding="utf-8")

    db = _db(ws)
    await db.connect()
    eid = await db.create_execution("Research Bot", "manual")
    await db.update_execution(eid, status="success", duration_ms=5)
    await db.close()

    report = await migrate_workspace(ws, dry_run=False)
    assert report.ok
    assert any(i.kind == "rekey" for i in report.actions)
    assert any(i.kind == "rename_memory" for i in report.actions)

    db = _db(ws)
    await db.connect()
    rows = await db.get_executions("pesquisador", limit=10)
    assert len(rows) == 1
    assert await db.count_executions_by_agent_id("Research Bot") == 0
    await db.close()

    assert not old_mem.exists()
    assert (agents / "pesquisador.memory.md").exists()
    assert (agents / "pesquisador.memory.md").read_text(encoding="utf-8") == "# legacy memory\n"
    # Agent markdown untouched
    assert "name: Research Bot" in (agents / "pesquisador.md").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_migrate_dry_run_does_not_modify(ws):
    agents = ws / "agents"
    _write_agent(agents / "pesquisador.md", name="Research Bot")
    old_mem = agents / "Research Bot.memory.md"
    old_mem.write_text("mem\n", encoding="utf-8")

    db = _db(ws)
    await db.connect()
    await db.create_execution("Research Bot", "manual")
    await db.close()

    report = await migrate_workspace(ws, dry_run=True)
    assert report.dry_run
    assert report.actions

    db = _db(ws)
    await db.connect()
    assert await db.count_executions_by_agent_id("Research Bot") == 1
    assert await db.count_executions_by_agent_id("pesquisador") == 0
    await db.close()
    assert old_mem.exists()
    assert not (agents / "pesquisador.memory.md").exists()


@pytest.mark.asyncio
async def test_migrate_idempotent_second_run(ws):
    agents = ws / "agents"
    _write_agent(agents / "pesquisador.md", name="Research Bot")
    (agents / "Research Bot.memory.md").write_text("m\n", encoding="utf-8")

    db = _db(ws)
    await db.connect()
    await db.create_execution("Research Bot", "manual")
    await db.close()

    first = await migrate_workspace(ws, dry_run=False)
    assert first.actions
    second = await migrate_workspace(ws, dry_run=False)
    assert second.actions == []


@pytest.mark.asyncio
async def test_migrate_name_equals_id_no_db_or_memory_action(ws):
    agents = ws / "agents"
    _write_agent(agents / "helper.md", name=None)
    (agents / "helper.memory.md").write_text("m\n", encoding="utf-8")

    db = _db(ws)
    await db.connect()
    await db.create_execution("helper", "manual")
    await db.close()

    report = await migrate_workspace(ws, dry_run=False)
    assert report.actions == []
    assert (agents / "helper.memory.md").exists()


@pytest.mark.asyncio
async def test_migrate_memory_collision_safe(ws):
    agents = ws / "agents"
    _write_agent(agents / "pesquisador.md", name="Research Bot")
    (agents / "Research Bot.memory.md").write_text("old\n", encoding="utf-8")
    (agents / "pesquisador.memory.md").write_text("new\n", encoding="utf-8")

    report = await migrate_workspace(ws, dry_run=False)
    assert not report.ok
    assert any(i.kind == "collision" for i in report.errors)
    assert (agents / "Research Bot.memory.md").read_text(encoding="utf-8") == "old\n"
    assert (agents / "pesquisador.memory.md").read_text(encoding="utf-8") == "new\n"


@pytest.mark.asyncio
async def test_migrate_reports_allowlist_display_names(ws):
    agents = ws / "agents"
    _write_agent(agents / "pesquisador.md", name="Research Bot")
    _write_agent(
        agents / "orquestrador.md",
        name="Orquestrador",
        extra="agents:\n  - Research Bot\n",
    )
    before = (agents / "orquestrador.md").read_text(encoding="utf-8")

    report = await migrate_workspace(ws, dry_run=False)
    assert any(i.kind == "allowlist" for i in report.warnings)
    assert "pesquisador" in " ".join(i.message for i in report.warnings)
    assert (agents / "orquestrador.md").read_text(encoding="utf-8") == before


@pytest.mark.asyncio
async def test_migrate_duplicate_display_name_blocks_rekey_and_memory(ws):
    """Shared display name must not move history/memory to an arbitrary stem."""
    agents = ws / "agents"
    _write_agent(agents / "alpha.md", name="Shared")
    _write_agent(agents / "beta.md", name="Shared")
    mem = agents / "Shared.memory.md"
    mem.write_text("shared-mem\n", encoding="utf-8")
    alpha_md = (agents / "alpha.md").read_text(encoding="utf-8")
    beta_md = (agents / "beta.md").read_text(encoding="utf-8")

    db = _db(ws)
    await db.connect()
    for _ in range(3):
        await db.create_execution("Shared", "manual")
    await db.close()

    dry = await migrate_workspace(ws, dry_run=True)
    real = await migrate_workspace(ws, dry_run=False)

    for report in (dry, real):
        assert not report.ok
        assert report.actions == []
        errs = [i for i in report.errors if i.kind == "ambiguous"]
        assert {i.agent_id for i in errs} >= {"alpha", "beta"}
        joined = " ".join(i.message for i in errs)
        assert "Shared" in joined
        assert "alpha" in joined and "beta" in joined

    db = _db(ws)
    await db.connect()
    assert await db.count_executions_by_agent_id("Shared") == 3
    assert await db.count_executions_by_agent_id("alpha") == 0
    assert await db.count_executions_by_agent_id("beta") == 0
    await db.close()

    assert mem.exists()
    assert mem.read_text(encoding="utf-8") == "shared-mem\n"
    assert not (agents / "alpha.memory.md").exists()
    assert not (agents / "beta.memory.md").exists()
    assert (agents / "alpha.md").read_text(encoding="utf-8") == alpha_md
    assert (agents / "beta.md").read_text(encoding="utf-8") == beta_md


def test_migrate_cli_dry_run(ws):
    agents = ws / "agents"
    _write_agent(agents / "pesquisador.md", name="Research Bot")
    (agents / "Research Bot.memory.md").write_text("m\n", encoding="utf-8")

    import asyncio

    async def _seed():
        db = _db(ws)
        await db.connect()
        await db.create_execution("Research Bot", "manual")
        await db.close()

    asyncio.run(_seed())

    runner = CliRunner()
    result = runner.invoke(app, ["migrate", "--dry-run", "--workspace", str(ws)])
    assert result.exit_code == 0, result.output
    assert "dry-run" in result.output.lower() or "would" in result.output.lower()
    assert (agents / "Research Bot.memory.md").exists()

    result2 = runner.invoke(app, ["migrate", "--workspace", str(ws)])
    assert result2.exit_code == 0, result2.output
    assert (agents / "pesquisador.memory.md").exists()
    assert not (agents / "Research Bot.memory.md").exists()


@pytest.mark.asyncio
async def test_path_context_memory_uses_stem_after_migrate(ws):
    agents = ws / "agents"
    path = _write_agent(agents / "pesquisador.md", name="Research Bot")
    (agents / "Research Bot.memory.md").write_text("legacy\n", encoding="utf-8")

    await migrate_workspace(ws, dry_run=False)

    cfg = parse_agent_file(path)
    from agent_md.config.settings import get_state_dir

    ctx = PathContext(
        workspace_root=ws,
        agents_dir=agents,
        db_path=get_state_dir() / "agentmd.db",
        mcp_config=agents / "_config" / "mcp-servers.json",
        tools_dir=agents / "_config" / "tools",
        skills_dir=agents / "_config" / "skills",
    )
    assert ctx.get_memory_file_path(cfg) == agents / "pesquisador.memory.md"
    assert ctx.get_memory_file_path(cfg).read_text(encoding="utf-8") == "legacy\n"
