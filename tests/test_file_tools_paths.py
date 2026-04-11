import pytest

from agent_md.config.models import AgentConfig
from agent_md.workspace.path_context import PathContext
from agent_md.tools.files.glob import create_file_glob_tool
from agent_md.tools.files.read import create_file_read_tool
from agent_md.tools.files.write import create_file_write_tool
from agent_md.tools.files.edit import create_file_edit_tool


@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "workspace"
    (ws / "agents").mkdir(parents=True)
    (ws / "agents" / "skills").mkdir()
    (ws / "agents" / "tools").mkdir()
    return ws


@pytest.fixture
def vault(tmp_path):
    v = tmp_path / "vault"
    v.mkdir()
    (v / "a.md").write_text("alpha")
    (v / "b.md").write_text("beta")
    sub = v / "sub"
    sub.mkdir()
    (sub / "c.md").write_text("gamma")
    return v


@pytest.fixture
def ctx(workspace):
    return PathContext(
        workspace_root=workspace,
        agents_dir=workspace / "agents",
        db_path=workspace / "data" / "agentmd.db",
        mcp_config=workspace / "mcp.json",
        tools_dir=workspace / "agents" / "tools",
        skills_dir=workspace / "agents" / "skills",
    )


@pytest.fixture
def cfg(vault):
    return AgentConfig(name="test", paths={"vault": str(vault)})


# --- file_glob ---


def test_glob_with_absolute_path(ctx, cfg, vault):
    tool = create_file_glob_tool(cfg, ctx)
    result = tool.invoke({"pattern": f"{vault}/*.md"})
    assert "a.md" in result
    assert "b.md" in result


def test_glob_with_alias_pattern(ctx, cfg, vault):
    tool = create_file_glob_tool(cfg, ctx)
    result = tool.invoke({"pattern": "{vault}/*.md"})
    assert "a.md" in result
    assert "b.md" in result


def test_glob_with_alias_recursive(ctx, cfg, vault):
    tool = create_file_glob_tool(cfg, ctx)
    result = tool.invoke({"pattern": "{vault}/**/*.md"})
    assert "c.md" in result


def test_glob_outside_sandbox_returns_no_results(ctx, cfg):
    tool = create_file_glob_tool(cfg, ctx)
    result = tool.invoke({"pattern": "/etc/*.conf"})
    assert "No files found" in result or "Access denied" in result


def test_glob_invalid_pattern_includes_aliases(ctx, cfg):
    tool = create_file_glob_tool(cfg, ctx)
    result = tool.invoke({"pattern": "[bad"})
    assert "ERROR" in result
    assert "vault" in result  # alias hint


# --- file_read ---


def test_read_with_alias(ctx, cfg, vault):
    tool = create_file_read_tool(cfg, ctx)
    result = tool.invoke({"path": "{vault}/a.md"})
    assert "alpha" in result


def test_read_with_absolute(ctx, cfg, vault):
    tool = create_file_read_tool(cfg, ctx)
    result = tool.invoke({"path": str(vault / "a.md")})
    assert "alpha" in result


def test_read_outside_sandbox_denied(ctx, cfg):
    tool = create_file_read_tool(cfg, ctx)
    result = tool.invoke({"path": "/etc/passwd"})
    assert "ERROR" in result and "denied" in result.lower()


# --- file_write ---


def test_write_with_alias(ctx, cfg, vault):
    tool = create_file_write_tool(cfg, ctx)
    result = tool.invoke({"path": "{vault}/new.md", "content": "hello"})
    assert "Created" in result or "Updated" in result
    assert (vault / "new.md").read_text() == "hello"


# --- file_edit ---


def test_edit_with_alias(ctx, cfg, vault):
    tool = create_file_edit_tool(cfg, ctx)
    result = tool.invoke({"path": "{vault}/a.md", "old_text": "alpha", "new_text": "ALPHA"})
    assert "Updated" in result
    assert (vault / "a.md").read_text() == "ALPHA"
