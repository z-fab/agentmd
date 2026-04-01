"""Tests for simplified skill_use tool."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from agent_md.tools.skills.use import create_skill_use_tool


@pytest.fixture
def tmp_skill(tmp_path):
    """Create a minimal skill directory."""
    skill_dir = tmp_path / "review-pr"
    skill_dir.mkdir()
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        "---\nname: review-pr\ndescription: Review PRs\n---\n"
        "Review the PR $ARGUMENTS."
    )
    return tmp_path


@pytest.fixture
def agent_config():
    config = MagicMock()
    config.skills = ["review-pr"]
    return config


def test_skill_use_returns_short_confirmation(tmp_skill, agent_config):
    """skill_use returns a short activation message, not full content."""
    tool = create_skill_use_tool(agent_config, tmp_skill)
    result = tool.invoke({"skill_name": "review-pr", "arguments": "123"})

    assert "review-pr" in result
    assert "activated" in result.lower() or "ativada" in result.lower()
    # Must NOT contain the full skill instructions
    assert "Review the PR" not in result


def test_skill_use_invalid_skill(tmp_skill, agent_config):
    """Returns error for unauthorized skill."""
    tool = create_skill_use_tool(agent_config, tmp_skill)
    result = tool.invoke({"skill_name": "unknown", "arguments": ""})

    assert "not enabled" in result.lower() or "not found" in result.lower()


def test_skill_use_missing_skill_file(tmp_skill, agent_config):
    """Returns error when SKILL.md doesn't exist."""
    agent_config.skills = ["nonexistent"]
    tool = create_skill_use_tool(agent_config, tmp_skill)
    result = tool.invoke({"skill_name": "nonexistent", "arguments": ""})

    assert "not found" in result.lower()
