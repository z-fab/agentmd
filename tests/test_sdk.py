"""Tests for agent_md.sdk — public utilities for custom tool authors."""

import asyncio
from pathlib import Path

import pytest

from agent_md.config.models import PathEntry
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
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


@pytest.fixture
def path_context(workspace):
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


class TestSDKOutsideExecution:
    def test_resolve_path_raises_outside_execution(self):
        from agent_md.sdk import resolve_path

        with pytest.raises(RuntimeError, match="agent execution"):
            resolve_path("some/path")

    def test_workspace_root_raises_outside_execution(self):
        from agent_md.sdk import workspace_root

        with pytest.raises(RuntimeError, match="agent execution"):
            workspace_root()

    def test_agent_name_raises_outside_execution(self):
        from agent_md.sdk import agent_name

        with pytest.raises(RuntimeError, match="agent execution"):
            agent_name()

    def test_agent_paths_raises_outside_execution(self):
        from agent_md.sdk import agent_paths

        with pytest.raises(RuntimeError, match="agent execution"):
            agent_paths()


class TestSDKWithinExecution:
    def test_resolve_path_success(self, workspace, path_context):
        from agent_md.sdk import _set_context, _reset_context, resolve_path

        config = FakeConfig()
        token = _set_context(config, path_context)
        try:
            target = workspace / "file.txt"
            target.write_text("hello")
            resolved, error = resolve_path(str(target))
            assert error is None
            assert resolved == target
        finally:
            _reset_context(token)

    def test_resolve_path_with_alias(self, workspace, path_context):
        from agent_md.sdk import _set_context, _reset_context, resolve_path

        output_dir = workspace / "output"
        output_dir.mkdir()
        config = FakeConfig(paths={"output": PathEntry(path=str(output_dir))})
        token = _set_context(config, path_context)
        try:
            resolved, error = resolve_path("{output}/report.txt")
            assert error is None
            assert resolved == output_dir / "report.txt"
        finally:
            _reset_context(token)

    def test_resolve_path_sandbox_violation(self, workspace, path_context):
        from agent_md.sdk import _set_context, _reset_context, resolve_path

        config = FakeConfig(paths={"data": PathEntry(path=str(workspace / "data"))})
        token = _set_context(config, path_context)
        try:
            resolved, error = resolve_path("/etc/passwd")
            assert resolved is None
            assert error is not None
        finally:
            _reset_context(token)

    def test_workspace_root(self, workspace, path_context):
        from agent_md.sdk import _set_context, _reset_context, workspace_root

        config = FakeConfig()
        token = _set_context(config, path_context)
        try:
            assert workspace_root() == workspace
        finally:
            _reset_context(token)

    def test_agent_name(self, workspace, path_context):
        from agent_md.sdk import _set_context, _reset_context, agent_name

        config = FakeConfig(name="my-agent")
        token = _set_context(config, path_context)
        try:
            assert agent_name() == "my-agent"
        finally:
            _reset_context(token)

    def test_agent_paths_empty(self, workspace, path_context):
        from agent_md.sdk import _set_context, _reset_context, agent_paths

        config = FakeConfig()
        token = _set_context(config, path_context)
        try:
            assert agent_paths() == {}
        finally:
            _reset_context(token)

    def test_agent_paths_with_aliases(self, workspace, path_context):
        from agent_md.sdk import _set_context, _reset_context, agent_paths

        output_dir = workspace / "output"
        data_dir = workspace / "data"
        config = FakeConfig(
            paths={
                "output": PathEntry(path=str(output_dir)),
                "data": PathEntry(path=str(data_dir)),
            }
        )
        token = _set_context(config, path_context)
        try:
            paths = agent_paths()
            assert paths["output"] == output_dir
            assert paths["data"] == data_dir
        finally:
            _reset_context(token)


class TestSDKConcurrentIsolation:
    async def test_concurrent_runs_isolated(self, workspace, path_context):
        """Two concurrent tasks see their own agent context."""
        from agent_md.sdk import _set_context, _reset_context, agent_name

        results = {}

        async def run_agent(name):
            config = FakeConfig(name=name)
            token = _set_context(config, path_context)
            try:
                await asyncio.sleep(0.01)  # yield to other task
                results[name] = agent_name()
            finally:
                _reset_context(token)

        await asyncio.gather(run_agent("agent-a"), run_agent("agent-b"))

        assert results["agent-a"] == "agent-a"
        assert results["agent-b"] == "agent-b"
