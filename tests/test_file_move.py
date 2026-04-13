"""Tests for file_move tool."""

from pathlib import Path

import pytest

from agent_md.tools.files.move import create_file_move_tool
from agent_md.workspace.path_context import PathContext
from agent_md.config.models import PathEntry


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


class TestFileMoveSuccess:
    def test_move_file(self, workspace, path_context):
        """Move a file from one location to another."""
        config = FakeConfig()
        tool = create_file_move_tool(config, path_context)

        src = workspace / "hello.txt"
        src.write_text("hello")
        dest = workspace / "moved.txt"

        result = tool.invoke({"source": str(src), "destination": str(dest)})
        assert "Moved" in result
        assert not src.exists()
        assert dest.read_text() == "hello"

    def test_move_creates_parent_dirs(self, workspace, path_context):
        """Move creates destination parent directories if needed."""
        config = FakeConfig()
        tool = create_file_move_tool(config, path_context)

        src = workspace / "file.txt"
        src.write_text("data")
        dest = workspace / "sub" / "deep" / "file.txt"

        result = tool.invoke({"source": str(src), "destination": str(dest)})
        assert "Moved" in result
        assert dest.read_text() == "data"
        assert not src.exists()

    def test_move_with_relative_paths(self, workspace, path_context):
        """Move works with relative paths resolved from workspace root."""
        config = FakeConfig()
        tool = create_file_move_tool(config, path_context)

        src = workspace / "a.txt"
        src.write_text("content")

        result = tool.invoke({"source": "a.txt", "destination": "b.txt"})
        assert "Moved" in result
        assert not src.exists()
        assert (workspace / "b.txt").read_text() == "content"


class TestFileMoveErrors:
    def test_source_not_found(self, workspace, path_context):
        """Error when source file does not exist."""
        config = FakeConfig()
        tool = create_file_move_tool(config, path_context)

        result = tool.invoke({"source": str(workspace / "nope.txt"), "destination": str(workspace / "dest.txt")})
        assert "ERROR" in result
        assert "not found" in result.lower() or "does not exist" in result.lower()

    def test_source_is_directory(self, workspace, path_context):
        """Error when source is a directory."""
        config = FakeConfig()
        tool = create_file_move_tool(config, path_context)

        d = workspace / "mydir"
        d.mkdir()

        result = tool.invoke({"source": str(d), "destination": str(workspace / "dest")})
        assert "ERROR" in result

    def test_source_blocked_by_sandbox(self, workspace, path_context):
        """Error when source is outside allowed paths."""
        config = FakeConfig(paths={"output": PathEntry(path=str(workspace / "output"))})
        tool = create_file_move_tool(config, path_context)

        src = workspace / "secret.txt"
        src.write_text("secret")

        result = tool.invoke({"source": str(src), "destination": str(workspace / "output" / "moved.txt")})
        assert "ERROR" in result
        assert "denied" in result.lower() or "outside" in result.lower()

    def test_destination_blocked_by_sandbox(self, workspace, path_context):
        """Error when destination is outside allowed paths."""
        config = FakeConfig(paths={"data": PathEntry(path=str(workspace / "data"))})
        tool = create_file_move_tool(config, path_context)

        data_dir = workspace / "data"
        data_dir.mkdir()
        src = data_dir / "file.txt"
        src.write_text("data")

        result = tool.invoke({"source": str(src), "destination": "/tmp/evil.txt"})
        assert "ERROR" in result

    def test_move_env_file_blocked(self, workspace, path_context):
        """Cannot move .env files."""
        config = FakeConfig()
        tool = create_file_move_tool(config, path_context)

        env_file = workspace / ".env"
        env_file.write_text("SECRET=123")

        result = tool.invoke({"source": str(env_file), "destination": str(workspace / "env_backup")})
        assert "ERROR" in result

    def test_move_db_file_blocked(self, workspace, path_context):
        """Cannot move .db files."""
        config = FakeConfig()
        tool = create_file_move_tool(config, path_context)

        db_file = workspace / "data.db"
        db_file.write_text("fake db")

        result = tool.invoke({"source": str(db_file), "destination": str(workspace / "backup.db")})
        assert "ERROR" in result

    def test_move_into_config_blocked(self, workspace, path_context):
        """Cannot move files into _config/ directory."""
        config = FakeConfig()
        tool = create_file_move_tool(config, path_context)

        src = workspace / "file.txt"
        src.write_text("data")
        dest = workspace / "agents" / "_config" / "file.txt"

        result = tool.invoke({"source": str(src), "destination": str(dest)})
        assert "ERROR" in result
