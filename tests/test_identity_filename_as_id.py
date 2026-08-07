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


def test_pick_or_resolve_agent_passthrough_explicit_id():
    from agent_md.cli.commands import _pick_or_resolve_agent

    assert _pick_or_resolve_agent("pesquisador", None) == "pesquisador"


def test_select_agent_auto_select_shows_display_and_returns_config(capsys):
    from agent_md.cli.theme import select_agent

    cfg = AgentConfig(id="pesquisador", name="Research Bot")
    selected = select_agent([cfg])
    assert selected is cfg
    assert selected.id == "pesquisador"
    out = capsys.readouterr().out
    assert "Research Bot" in out
    assert "pesquisador" in out
