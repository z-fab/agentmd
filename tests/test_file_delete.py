"""Tests for file_delete tool."""

import pytest

from agent_md.tools.files.delete import create_file_delete_tool
from agent_md.workspace.path_context import PathContext


class FakeConfig:
    def __init__(self, name="test-agent", paths=None):
        self.name = name
        self.paths = paths or {}

        class FakeTrigger:
            type = "manual"
            paths = []

        self.trigger = FakeTrigger()


@pytest.fixture
def workspace(tmp_path):
    return tmp_path / "workspace"


@pytest.fixture
def path_context(workspace):
    workspace.mkdir()
    agents_dir = workspace / "agents"
    agents_dir.mkdir()
    return PathContext(
        workspace_root=workspace,
        agents_dir=agents_dir,
        db_path=workspace / "data" / "agentmd.db",
        mcp_config=agents_dir / "_config" / "mcp-servers.json",
        tools_dir=agents_dir / "_config" / "tools",
        skills_dir=agents_dir / "_config" / "skills",
    )


def test_delete_file(workspace, path_context):
    config = FakeConfig()
    tool = create_file_delete_tool(config, path_context)
    target = workspace / "bye.txt"
    target.write_text("x")
    result = tool.invoke({"path": str(target)})
    assert "Deleted" in result
    assert not target.exists()


def test_delete_missing_file_is_graceful(workspace, path_context):
    config = FakeConfig()
    tool = create_file_delete_tool(config, path_context)
    result = tool.invoke({"path": str(workspace / "nope.txt")})
    assert "not found" in result.lower()
    assert "ERROR" not in result


def test_delete_outside_sandbox_rejected(workspace, path_context):
    config = FakeConfig()
    tool = create_file_delete_tool(config, path_context)
    result = tool.invoke({"path": "/etc/passwd"})
    assert "ERROR" in result


def test_delete_directory_rejected(workspace, path_context):
    config = FakeConfig()
    tool = create_file_delete_tool(config, path_context)
    subdir = workspace / "adir"
    subdir.mkdir()
    result = tool.invoke({"path": str(subdir)})
    assert "ERROR" in result
    assert subdir.exists()
