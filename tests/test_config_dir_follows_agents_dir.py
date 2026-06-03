"""The _config dir (skills/tools/mcp) should live inside the configured agents_dir,
not in a separate top-level `agents/` folder."""

import pytest

from agent_md.workspace.bootstrap import bootstrap


@pytest.mark.asyncio
async def test_config_dir_derived_from_custom_agents_dir(tmp_path, monkeypatch):
    # Ensure no explicit overrides leak in from the host config.yaml.
    from agent_md.config import settings as settings_mod

    monkeypatch.setattr(settings_mod.settings, "mcp_config", "", raising=False)
    monkeypatch.setattr(settings_mod.settings, "tools_dir", "", raising=False)
    monkeypatch.setattr(settings_mod.settings, "skills_dir", "", raising=False)

    workspace = tmp_path / "vault"
    workspace.mkdir()
    agents_dir = workspace / "99. Agents"

    rt = await bootstrap(
        workspace=workspace,
        agents_dir=agents_dir,
        db_path=tmp_path / "state" / "agentmd.db",
        start_scheduler=False,
    )
    try:
        pc = rt.path_context
        assert pc.skills_dir == (agents_dir / "_config" / "skills").resolve()
        assert pc.tools_dir == (agents_dir / "_config" / "tools").resolve()
        assert pc.mcp_config == (agents_dir / "_config" / "mcp-servers.json").resolve()
        # No spurious top-level `agents/` folder is created in the workspace.
        assert not (workspace / "agents").exists()
    finally:
        await rt.aclose()


@pytest.mark.asyncio
async def test_explicit_config_paths_still_override(tmp_path, monkeypatch):
    from agent_md.config import settings as settings_mod

    workspace = tmp_path / "vault"
    workspace.mkdir()
    agents_dir = workspace / "99. Agents"
    monkeypatch.setattr(settings_mod.settings, "skills_dir", "custom/skills", raising=False)
    monkeypatch.setattr(settings_mod.settings, "tools_dir", "", raising=False)
    monkeypatch.setattr(settings_mod.settings, "mcp_config", "", raising=False)

    rt = await bootstrap(
        workspace=workspace,
        agents_dir=agents_dir,
        db_path=tmp_path / "state" / "agentmd.db",
        start_scheduler=False,
    )
    try:
        pc = rt.path_context
        # Explicit relative override resolves against the workspace.
        assert pc.skills_dir == (workspace / "custom" / "skills").resolve()
        # Unset ones still derive from agents_dir.
        assert pc.tools_dir == (agents_dir / "_config" / "tools").resolve()
    finally:
        await rt.aclose()
