"""Tests for AgentRegistry path-to-name reverse mapping."""

from agent_md.config.models import AgentConfig
from agent_md.workspace.registry import AgentRegistry


def _make_config(name: str, file_path: str) -> AgentConfig:
    return AgentConfig(name=name, file_path=file_path)


def test_register_stores_path_mapping():
    reg = AgentRegistry()
    cfg = _make_config("greeter", "/workspace/agents/greeter.md")
    reg.register(cfg)

    name = reg.remove_by_path("/workspace/agents/greeter.md")
    assert name == "greeter"
    assert "greeter" not in reg


def test_remove_by_path_when_name_differs_from_filename():
    reg = AgentRegistry()
    cfg = _make_config("my-cool-agent", "/workspace/agents/cool.md")
    reg.register(cfg)

    name = reg.remove_by_path("/workspace/agents/cool.md")
    assert name == "my-cool-agent"
    assert "my-cool-agent" not in reg


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
    name = reg.remove_by_path("/new/path.md")
    assert name == "agent"


def test_remove_cleans_up_path_mapping():
    reg = AgentRegistry()
    cfg = _make_config("agent", "/workspace/agent.md")
    reg.register(cfg)

    reg.remove("agent")
    # Path mapping should also be gone
    assert reg.remove_by_path("/workspace/agent.md") is None


def test_path_to_name_count():
    reg = AgentRegistry()
    reg.register(_make_config("a", "/a.md"))
    reg.register(_make_config("b", "/b.md"))
    assert len(reg) == 2

    reg.remove_by_path("/a.md")
    assert len(reg) == 1

    reg.remove("b")
    assert len(reg) == 0
