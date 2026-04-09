import pytest

from agent_md.core.models import AgentConfig
from agent_md.core.path_context import PathContext
from agent_md.tools.files.read import MAX_LINES, create_file_read_tool


@pytest.fixture
def setup(tmp_path):
    ws = tmp_path / "ws"
    (ws / "agents").mkdir(parents=True)
    big = tmp_path / "big.txt"
    big.write_text("\n".join(f"line {i}" for i in range(MAX_LINES + 200)))
    ctx = PathContext(
        workspace_root=ws,
        agents_dir=ws / "agents",
        db_path=ws / "data" / "agentmd.db",
        mcp_config=ws / "mcp.json",
        tools_dir=ws / "agents" / "tools",
        skills_dir=ws / "agents" / "skills",
    )
    cfg = AgentConfig(name="t", paths={"data": str(tmp_path)})
    return ctx, cfg, big


def test_truncation_message_mentions_offset_and_limit(setup):
    ctx, cfg, big = setup
    tool = create_file_read_tool(cfg, ctx)
    out = tool.invoke({"path": str(big)})
    assert "offset=" in out
    assert "limit=" in out


def test_partial_read_includes_continuation_hint(setup):
    ctx, cfg, big = setup
    tool = create_file_read_tool(cfg, ctx)
    out = tool.invoke({"path": str(big), "offset": 1, "limit": 100})
    # Should hint that there are more lines
    assert "more lines" in out.lower() or "continue" in out.lower() or "offset=101" in out
