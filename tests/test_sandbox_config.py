"""Tests for _config/ directory blocking in sandbox."""

import pytest
from unittest.mock import MagicMock
from agent_md.workspace.path_context import PathContext


@pytest.fixture
def path_ctx(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    config_dir = agents_dir / "_config"
    config_dir.mkdir()
    (config_dir / ".env").write_text("KEY=val")
    (config_dir / "tools").mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    return PathContext(
        workspace_root=tmp_path,
        agents_dir=agents_dir,
        db_path=tmp_path / "state" / "agentmd.db",
        mcp_config=config_dir / "mcp-servers.json",
        tools_dir=config_dir / "tools",
        skills_dir=config_dir / "skills",
    )


def _make_config(paths=None):
    config = MagicMock()
    config.paths = paths or {}
    config.trigger.type = "manual"
    config.trigger.paths = []
    return config


def test_config_dir_blocked(path_ctx):
    config = _make_config()
    _, error = path_ctx.validate_path(
        str(path_ctx.agents_dir / "_config" / "tools" / "hack.py"),
        config,
    )
    assert error is not None
    assert "_config" in error


def test_config_env_blocked(path_ctx):
    config = _make_config()
    _, error = path_ctx.validate_path(
        str(path_ctx.agents_dir / "_config" / ".env"),
        config,
    )
    assert error is not None


def test_env_anywhere_blocked(path_ctx):
    config = _make_config()
    _, error = path_ctx.validate_path(
        str(path_ctx.workspace_root / ".env"),
        config,
    )
    assert error is not None
    assert ".env" in error


def test_agent_md_files_blocked(path_ctx):
    config = _make_config()
    _, error = path_ctx.validate_path(
        str(path_ctx.agents_dir / "some-agent.md"),
        config,
    )
    assert error is not None


def test_db_files_blocked(path_ctx):
    config = _make_config()
    _, error = path_ctx.validate_path(
        str(path_ctx.workspace_root / "state" / "agentmd.db"),
        config,
    )
    assert error is not None
    assert ".db" in error


def test_workspace_subdir_allowed(path_ctx):
    """Non-config subdirectories of workspace are accessible."""
    config = _make_config()
    output_dir = path_ctx.workspace_root / "output"
    output_dir.mkdir(exist_ok=True)
    resolved, error = path_ctx.validate_path(str(output_dir / "test.txt"), config)
    assert error is None
    assert resolved is not None
