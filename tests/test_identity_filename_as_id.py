"""Phase 1.1 — filename-as-id identity foundation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agent_md.config.models import AgentConfig
from agent_md.workspace.parser import parse_agent_file
from agent_md.workspace.path_context import PathContext
from agent_md.workspace.registry import AgentRegistry
from agent_md.workspace.scheduler import _AgentFileHandler


def _write_agent(path: Path, *, name: str | None = None, body: str = "Hello", extra: str = "") -> Path:
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


def _path_context(tmp_path: Path) -> PathContext:
    agents = tmp_path / "agents"
    agents.mkdir(exist_ok=True)
    return PathContext(
        workspace_root=tmp_path,
        agents_dir=agents,
        db_path=tmp_path / "db.db",
        mcp_config=agents / "_config" / "mcp-servers.json",
        tools_dir=agents / "_config" / "tools",
        skills_dir=agents / "_config" / "skills",
    )


# ---------------------------------------------------------------------------
# Parser / model
# ---------------------------------------------------------------------------


def test_parse_derives_id_from_filename_stem(tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir()
    path = _write_agent(agents / "pesquisador.md", name=None)
    config = parse_agent_file(path)
    assert config.id == "pesquisador"
    assert config.name == "pesquisador"


def test_parse_uses_name_as_display_only(tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir()
    path = _write_agent(agents / "pesquisador.md", name="Research Bot")
    config = parse_agent_file(path)
    assert config.id == "pesquisador"
    assert config.name == "Research Bot"


def test_parse_rejects_frontmatter_id(tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir()
    path = agents / "x.md"
    path.write_text(
        "---\nid: hijack\nname: x\nmodel:\n  provider: google\n  name: gemini-2.5-flash\n---\nHi\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must not declare 'id'"):
        parse_agent_file(path)


def test_parse_rejects_invalid_stem(tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir()
    # Slash cannot appear in a real filename stem on disk; simulate via invalid chars.
    path = agents / "bad@name.md"
    _write_agent(path, name="ok")
    with pytest.raises(ValueError, match="Invalid agent filename stem"):
        parse_agent_file(path)


def test_model_defaults_id_from_name_for_programmatic_use():
    cfg = AgentConfig(name="legacy-helper")
    assert cfg.id == "legacy-helper"
    assert cfg.name == "legacy-helper"


def test_model_defaults_name_from_id():
    cfg = AgentConfig(id="stem-only")
    assert cfg.id == "stem-only"
    assert cfg.name == "stem-only"


# ---------------------------------------------------------------------------
# Memory path keyed by id
# ---------------------------------------------------------------------------


def test_memory_path_uses_id_not_display_name(tmp_path):
    pc = _path_context(tmp_path)
    cfg = AgentConfig(id="pesquisador", name="Research Bot", file_path=str(tmp_path / "agents" / "pesquisador.md"))
    assert pc.get_memory_file_path(cfg) == pc.agents_dir / "pesquisador.memory.md"


def test_editing_display_name_keeps_memory_path(tmp_path):
    pc = _path_context(tmp_path)
    before = AgentConfig(id="pesquisador", name="Old", file_path=str(tmp_path / "agents" / "pesquisador.md"))
    after = AgentConfig(id="pesquisador", name="New Label", file_path=str(tmp_path / "agents" / "pesquisador.md"))
    assert pc.get_memory_file_path(before) == pc.get_memory_file_path(after)


# ---------------------------------------------------------------------------
# Registry + name edit
# ---------------------------------------------------------------------------


def test_editing_name_does_not_change_registry_key(tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir()
    path = _write_agent(agents / "pesquisador.md", name="Old")
    reg = AgentRegistry()
    first = parse_agent_file(path)
    reg.register(first)

    _write_agent(path, name="New Label")
    second = parse_agent_file(path)
    reg.register(second)

    assert len(reg) == 1
    assert reg.get("pesquisador") is second
    assert reg.get("pesquisador").name == "New Label"
    assert reg.get("Old") is None
    assert reg.get("New Label") is None


# ---------------------------------------------------------------------------
# Hot-reload on_moved
# ---------------------------------------------------------------------------


def test_file_handler_on_moved_swaps_ids(tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir()
    src = _write_agent(agents / "old-agent.md", name="Display")
    dest = agents / "new-agent.md"

    reg = AgentRegistry()
    reg.register(parse_agent_file(src))

    scheduler = MagicMock()
    handler = _AgentFileHandler(reg, scheduler, loop=None, agents_dir=agents)

    src.rename(dest)
    event = MagicMock()
    event.is_directory = False
    event.src_path = str(src)
    event.dest_path = str(dest)

    handler.on_moved(event)

    assert reg.get("old-agent") is None
    assert reg.get("new-agent") is not None
    assert reg.get("new-agent").id == "new-agent"
    scheduler.unschedule_agent.assert_any_call("old-agent")
    # Destination load also unschedules/reschedules the new id (full reload path).
    scheduler.unschedule_agent.assert_any_call("new-agent")
    assert scheduler.schedule_agent.called
    scheduled = scheduler.schedule_agent.call_args[0][0]
    assert scheduled.id == "new-agent"


def test_file_handler_on_moved_out_does_not_reload_external_dest(tmp_path):
    """mv agents/a.md /tmp/a.md must drop the agent without registering the external file."""
    agents = tmp_path / "agents"
    agents.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    src = _write_agent(agents / "a.md", name="Display")
    dest = outside / "a.md"

    reg = AgentRegistry()
    reg.register(parse_agent_file(src))

    scheduler = MagicMock()
    handler = _AgentFileHandler(reg, scheduler, loop=None, agents_dir=agents)

    src.rename(dest)
    event = MagicMock()
    event.is_directory = False
    event.src_path = str(src)
    event.dest_path = str(dest)

    handler.on_moved(event)

    assert reg.get("a") is None
    assert len(reg) == 0
    scheduler.unschedule_agent.assert_called_once_with("a")
    scheduler.schedule_agent.assert_not_called()


def test_file_handler_on_moved_in_loads_destination(tmp_path):
    """mv /tmp/b.md agents/b.md must register/schedule the new agent."""
    agents = tmp_path / "agents"
    agents.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    src = _write_agent(outside / "b.md", name="Incoming")
    dest = agents / "b.md"

    reg = AgentRegistry()
    scheduler = MagicMock()
    handler = _AgentFileHandler(reg, scheduler, loop=None, agents_dir=agents)

    src.rename(dest)
    event = MagicMock()
    event.is_directory = False
    event.src_path = str(src)
    event.dest_path = str(dest)

    handler.on_moved(event)

    assert reg.get("b") is not None
    assert reg.get("b").name == "Incoming"
    assert scheduler.schedule_agent.called
    scheduled = scheduler.schedule_agent.call_args[0][0]
    assert scheduled.id == "b"


def test_file_handler_on_moved_ignores_non_agent_files(tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir()
    src = agents / "notes.txt"
    dest = agents / "notes2.txt"
    src.write_text("x", encoding="utf-8")

    reg = AgentRegistry()
    scheduler = MagicMock()
    handler = _AgentFileHandler(reg, scheduler, loop=None, agents_dir=agents)

    src.rename(dest)
    event = MagicMock()
    event.is_directory = False
    event.src_path = str(src)
    event.dest_path = str(dest)

    handler.on_moved(event)
    scheduler.unschedule_agent.assert_not_called()
    scheduler.schedule_agent.assert_not_called()


# ---------------------------------------------------------------------------
# CLI picker returns canonical id
# ---------------------------------------------------------------------------


def test_pick_or_resolve_agent_returns_id_when_display_name_differs(monkeypatch):
    from agent_md.cli import commands as cli_commands

    cfg = AgentConfig(id="pesquisador", name="Research Bot", description="docs")

    monkeypatch.setattr(cli_commands, "_get_agents_for_picker", lambda workspace: [cfg])
    monkeypatch.setattr(cli_commands, "select_agent", lambda agents: cfg)

    assert cli_commands._pick_or_resolve_agent(None, None) == "pesquisador"


def test_pick_or_resolve_agent_accepts_canonical_id(monkeypatch):
    from agent_md.cli import commands as cli_commands

    cfg = AgentConfig(id="pesquisador", name="Research Bot")
    monkeypatch.setattr(cli_commands, "_get_agents_for_picker", lambda workspace: [cfg])

    assert cli_commands._pick_or_resolve_agent("pesquisador", None) == "pesquisador"


def test_pick_or_resolve_agent_rejects_display_name(monkeypatch):
    import typer
    from agent_md.cli import commands as cli_commands

    cfg = AgentConfig(id="pesquisador", name="Research Bot")
    monkeypatch.setattr(cli_commands, "_get_agents_for_picker", lambda workspace: [cfg])

    with pytest.raises(typer.Exit):
        cli_commands._pick_or_resolve_agent("Research Bot", None)


def test_select_agent_auto_select_shows_display_and_returns_config(capsys):
    from agent_md.cli.theme import select_agent

    cfg = AgentConfig(id="pesquisador", name="Research Bot")
    selected = select_agent([cfg])
    assert selected is cfg
    assert selected.id == "pesquisador"
    out = capsys.readouterr().out
    assert "Research Bot" in out
    assert "pesquisador" in out


def test_format_agent_label_includes_both_when_distinct():
    from agent_md.cli.theme import format_agent_label

    assert format_agent_label("pesquisador", "Research Bot") == "Research Bot (pesquisador)"
    assert format_agent_label("pesquisador", "pesquisador") == "pesquisador"


# ---------------------------------------------------------------------------
# Display-name edit preserves identity / schedule / history keys
# ---------------------------------------------------------------------------


def test_on_modified_display_name_edit_reschedules_same_id(tmp_path):
    """Editing name: must not invent a new schedule key — job stays agent_{id}."""
    agents = tmp_path / "agents"
    agents.mkdir()
    path = _write_agent(agents / "pesquisador.md", name="Old Label")

    reg = AgentRegistry()
    reg.register(parse_agent_file(path))

    scheduler = MagicMock()
    handler = _AgentFileHandler(reg, scheduler, loop=None, agents_dir=agents)

    _write_agent(path, name="New Label")
    event = MagicMock()
    event.is_directory = False
    event.src_path = str(path)
    handler.on_modified(event)

    assert reg.get("pesquisador") is not None
    assert reg.get("pesquisador").name == "New Label"
    assert reg.get("Old Label") is None
    assert reg.get("New Label") is None
    scheduler.unschedule_agent.assert_called_with("pesquisador")
    scheduled = scheduler.schedule_agent.call_args[0][0]
    assert scheduled.id == "pesquisador"
    assert scheduled.name == "New Label"


@pytest.mark.asyncio
async def test_editing_display_name_keeps_execution_history_by_id(tmp_path):
    """History stays keyed by stem when only the display label changes."""
    from agent_md.db.database import Database

    agents = tmp_path / "agents"
    agents.mkdir()
    path = _write_agent(agents / "pesquisador.md", name="Old Label")
    cfg = parse_agent_file(path)
    assert cfg.id == "pesquisador"

    db = Database(tmp_path / "agentmd.db")
    await db.connect()
    try:
        eid = await db.create_execution(cfg.id, "manual", status="success")
        assert await db.count_executions_by_agent_id("pesquisador") == 1

        _write_agent(path, name="New Label")
        after = parse_agent_file(path)
        assert after.id == "pesquisador"
        assert after.name == "New Label"

        rows = await db.list_executions(agent_id="pesquisador")
        assert len(rows) == 1
        assert rows[0].id == eid
        assert await db.count_executions_by_agent_id("Old Label") == 0
        assert await db.count_executions_by_agent_id("New Label") == 0
    finally:
        await db.close()


def test_file_rename_leaves_memory_file_behind(tmp_path):
    """mv changes id/memory path; existing memory file is not moved automatically."""
    agents = tmp_path / "agents"
    agents.mkdir()
    src = _write_agent(agents / "old-id.md", name="Label")
    mem = agents / "old-id.memory.md"
    mem.write_text("# notes\n", encoding="utf-8")

    pc = _path_context(tmp_path)
    before = parse_agent_file(src)
    assert pc.get_memory_file_path(before) == mem

    dest = agents / "new-id.md"
    src.rename(dest)
    after = parse_agent_file(dest)

    assert after.id == "new-id"
    assert pc.get_memory_file_path(after) == agents / "new-id.memory.md"
    assert mem.exists()
    assert not (agents / "new-id.memory.md").exists()


def test_file_handler_atomic_save_keeps_agent_registered(tmp_path):
    """A stale delete for a file that still exists must not drop the agent.

    Atomic saves (perl -i, sed -i, vim, most editors) write a temp file and
    rename it over the original. macOS FSEvents then reports the sequence
    created/modified/moved/created/modified/**deleted** for a path that is
    very much still on disk. Trusting that delete unregisters a live agent,
    and nothing arrives afterwards to bring it back — the backend 404s on an
    agent the user can see in `agentmd list`.
    """
    agents = tmp_path / "agents"
    agents.mkdir()
    path = _write_agent(agents / "pesquisador.md", name="Research Bot")

    reg = AgentRegistry()
    reg.register(parse_agent_file(path))

    scheduler = MagicMock()
    handler = _AgentFileHandler(reg, scheduler, loop=None, agents_dir=agents)

    # The atomic save rewrote the file in place — it exists, with new content.
    _write_agent(path, name="Outro Rotulo")

    event = MagicMock()
    event.is_directory = False
    event.src_path = str(path)
    handler.on_deleted(event)

    assert reg.get("pesquisador") is not None, "agent dropped by a stale delete event"
    assert reg.get("pesquisador").name == "Outro Rotulo", "stale delete skipped the reload"
    # A full reload unschedules then reschedules; what must not happen is the
    # agent being torn down and left gone.
    scheduler.schedule_agent.assert_called_once()


def test_file_handler_real_delete_still_removes_agent(tmp_path):
    """The guard must not break genuine deletion."""
    agents = tmp_path / "agents"
    agents.mkdir()
    path = _write_agent(agents / "pesquisador.md", name="Research Bot")

    reg = AgentRegistry()
    reg.register(parse_agent_file(path))

    scheduler = MagicMock()
    handler = _AgentFileHandler(reg, scheduler, loop=None, agents_dir=agents)

    path.unlink()
    event = MagicMock()
    event.is_directory = False
    event.src_path = str(path)
    handler.on_deleted(event)

    assert reg.get("pesquisador") is None
    assert len(reg) == 0
    scheduler.unschedule_agent.assert_called_once_with("pesquisador")
