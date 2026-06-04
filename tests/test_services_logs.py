"""Tests for get_agent_logs return type and icon resolution."""

import pytest
from agent_md.config.icons import AGENT_EMOJI_PALETTE


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Isolated workspace with agents_dir forced to 'agents'."""
    monkeypatch.setattr("agent_md.config.settings.settings.agents_dir", "agents")
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    return tmp_path, agents_dir


@pytest.mark.asyncio
async def test_get_agent_logs_returns_tuple_with_icon(workspace):
    """get_agent_logs returns (list, str) and the icon is non-empty."""
    from agent_md.workspace.services import get_agent_logs

    tmp_path, agents_dir = workspace
    (agents_dir / "my-agent.md").write_text(
        "---\nname: my-agent\n---\nYou are a test agent.\n"
    )

    result = await get_agent_logs("my-agent", 5, workspace=tmp_path)

    assert isinstance(result, tuple), "get_agent_logs must return a tuple"
    executions, icon = result
    assert isinstance(executions, list)
    assert isinstance(icon, str) and icon, "icon must be a non-empty string"


@pytest.mark.asyncio
async def test_get_agent_logs_icon_uses_explicit_icon(workspace):
    """get_agent_logs uses the explicit icon declared in frontmatter."""
    from agent_md.workspace.services import get_agent_logs

    tmp_path, agents_dir = workspace
    (agents_dir / "icon-agent.md").write_text(
        '---\nname: icon-agent\nicon: "📅"\n---\nYou are a test agent.\n'
    )

    _, icon = await get_agent_logs("icon-agent", 5, workspace=tmp_path)

    assert icon == "📅"


@pytest.mark.asyncio
async def test_get_agent_logs_icon_fallback_for_unknown_agent(workspace):
    """get_agent_logs uses the deterministic hash fallback for unknown agents."""
    from agent_md.workspace.services import get_agent_logs

    tmp_path, _ = workspace

    _, icon = await get_agent_logs("nonexistent-agent", 5, workspace=tmp_path)

    assert icon in AGENT_EMOJI_PALETTE
