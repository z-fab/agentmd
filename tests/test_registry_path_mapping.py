"""Tests for AgentRegistry path-to-id reverse mapping."""

from agent_md.config.models import AgentConfig
from agent_md.workspace.registry import AgentRegistry


def _make_config(agent_id: str, file_path: str, name: str | None = None) -> AgentConfig:
    kwargs = {"id": agent_id, "file_path": file_path}
    if name is not None:
        kwargs["name"] = name
    return AgentConfig(**kwargs)


def test_register_stores_path_mapping():
    reg = AgentRegistry()
    cfg = _make_config("greeter", "/workspace/agents/greeter.md")
    reg.register(cfg)

    agent_id = reg.remove_by_path("/workspace/agents/greeter.md")
    assert agent_id == "greeter"
    assert "greeter" not in reg


def test_remove_by_path_when_display_name_differs_from_filename():
    """Display name is not the registry key — path maps to stem/id."""
    reg = AgentRegistry()
    cfg = _make_config("cool", "/workspace/agents/cool.md", name="my-cool-agent")
    reg.register(cfg)

    agent_id = reg.remove_by_path("/workspace/agents/cool.md")
    assert agent_id == "cool"
    assert "cool" not in reg
    assert reg.get("my-cool-agent") is None


def test_duplicate_display_names_coexist():
    reg = AgentRegistry()
    reg.register(_make_config("a", "/workspace/agents/a.md", name="same"))
    reg.register(_make_config("b", "/workspace/agents/b.md", name="same"))
    assert len(reg) == 2
    assert reg.get("a").name == "same"
    assert reg.get("b").name == "same"


def test_remove_by_path_unknown_path():
    reg = AgentRegistry()
    assert reg.remove_by_path("/no/such/file.md") is None


def test_register_updates_path_on_reregister():
    reg = AgentRegistry()
    cfg1 = _make_config("agent", "/old/path.md")
    reg.register(cfg1)

    cfg2 = _make_config("agent", "/new/path.md")
    reg.register(cfg2)

    # Old path no longer resolves
    assert reg.remove_by_path("/old/path.md") is None
    # New path works
    agent_id = reg.remove_by_path("/new/path.md")
    assert agent_id == "agent"


def test_remove_cleans_up_path_mapping():
    reg = AgentRegistry()
    cfg = _make_config("agent", "/workspace/agent.md")
    reg.register(cfg)

    reg.remove("agent")
    # Path mapping should also be gone
    assert reg.remove_by_path("/workspace/agent.md") is None


def test_path_to_id_count():
    reg = AgentRegistry()
    reg.register(_make_config("a", "/a.md"))
    reg.register(_make_config("b", "/b.md"))
    assert len(reg) == 2

    reg.remove_by_path("/a.md")
    assert len(reg) == 1

    reg.remove("b")
    assert len(reg) == 0
