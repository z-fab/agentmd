from pathlib import Path

import pytest

from agent_md.core.models import AgentConfig
from agent_md.core.path_context import PathContext


@pytest.fixture
def ctx(tmp_path):
    ws = tmp_path / "workspace"
    (ws / "agents").mkdir(parents=True)
    return PathContext(
        workspace_root=ws,
        agents_dir=ws / "agents",
        db_path=ws / "data" / "agentmd.db",
        mcp_config=ws / "mcp.json",
        tools_dir=ws / "agents" / "tools",
        skills_dir=ws / "agents" / "skills",
    )


@pytest.fixture
def cfg_with_aliases(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    return AgentConfig(
        name="test",
        paths={
            "vault": str(vault),
            "inbox": str(inbox),
        },
    )


def test_resolve_alias_returns_absolute(ctx, cfg_with_aliases, tmp_path):
    resolved = ctx.resolve_alias("vault", cfg_with_aliases)
    assert resolved == (tmp_path / "vault").resolve()


def test_resolve_alias_unknown_raises(ctx, cfg_with_aliases):
    with pytest.raises(KeyError):
        ctx.resolve_alias("nope", cfg_with_aliases)


def test_expand_alias(ctx, cfg_with_aliases, tmp_path):
    out = ctx.expand("{vault}/notes/x.md", cfg_with_aliases)
    assert out == (tmp_path / "vault" / "notes" / "x.md").resolve()


def test_expand_alias_only(ctx, cfg_with_aliases, tmp_path):
    out = ctx.expand("{vault}", cfg_with_aliases)
    assert out == (tmp_path / "vault").resolve()


def test_expand_absolute(ctx, cfg_with_aliases):
    out = ctx.expand("/etc/passwd", cfg_with_aliases)
    assert out == Path("/etc/passwd").resolve()


def test_expand_relative_uses_workspace(ctx, cfg_with_aliases):
    out = ctx.expand("foo/bar.md", cfg_with_aliases)
    assert out == (ctx.workspace_root / "foo" / "bar.md").resolve()


def test_validate_path_inside_alias(ctx, cfg_with_aliases, tmp_path):
    (tmp_path / "vault" / "x.md").write_text("hi")
    resolved, error = ctx.validate_path("{vault}/x.md", cfg_with_aliases)
    assert error is None
    assert resolved == (tmp_path / "vault" / "x.md").resolve()


def test_validate_path_outside_sandbox_rejected(ctx, cfg_with_aliases):
    resolved, error = ctx.validate_path("/etc/passwd", cfg_with_aliases)
    assert resolved is None
    assert error is not None
    assert "outside" in error.lower() or "denied" in error.lower()


def test_validate_path_traversal_rejected(ctx, cfg_with_aliases):
    resolved, error = ctx.validate_path("{vault}/../../etc/passwd", cfg_with_aliases)
    assert resolved is None
    assert error is not None
