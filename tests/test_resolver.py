"""Tests for internal skill content resolver."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from agent_md.tools.skills._resolver import resolve_skill_content


@pytest.fixture
def tmp_skill(tmp_path):
    """Create a minimal skill directory with SKILL.md."""
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        "---\nname: test-skill\ndescription: A test skill\n---\n"
        "Do the thing with $ARGUMENTS.\n"
        "Skill dir is ${SKILL_DIR}."
    )
    return tmp_path


@pytest.fixture
def tmp_skill_with_scripts(tmp_skill):
    """Skill directory with scripts/ subdirectory."""
    scripts_dir = tmp_skill / "test-skill" / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "run.py").write_text("print('hello')")
    return tmp_skill


@pytest.fixture
def tmp_skill_with_references(tmp_skill):
    """Skill directory with references/ subdirectory."""
    refs_dir = tmp_skill / "test-skill" / "references"
    refs_dir.mkdir()
    (refs_dir / "guide.md").write_text("# Guide")
    return tmp_skill


@pytest.fixture
def agent_config():
    """Mock agent config with test-skill enabled."""
    config = MagicMock()
    config.skills = ["test-skill"]
    return config


def test_resolve_skill_content_basic(tmp_skill, agent_config):
    """Resolves skill content with variable substitutions applied."""
    content = resolve_skill_content("test-skill", "hello world", agent_config, tmp_skill)

    assert "Do the thing with hello world." in content
    assert str(tmp_skill / "test-skill") in content
    assert "test-skill" in content


def test_resolve_skill_content_empty_arguments(tmp_skill, agent_config):
    """Works with empty arguments string."""
    content = resolve_skill_content("test-skill", "", agent_config, tmp_skill)

    assert "Do the thing with ." in content


def test_resolve_skill_content_lists_scripts(tmp_skill_with_scripts, agent_config):
    """Includes available scripts in output."""
    content = resolve_skill_content("test-skill", "", agent_config, tmp_skill_with_scripts)

    assert "run.py" in content
    assert "skill_run_script" in content


def test_resolve_skill_content_lists_references(tmp_skill_with_references, agent_config):
    """Includes available references in output."""
    content = resolve_skill_content("test-skill", "", agent_config, tmp_skill_with_references)

    assert "guide.md" in content
    assert "skill_read_file" in content


def test_resolve_skill_content_invalid_skill(tmp_skill, agent_config):
    """Returns None for a skill not in the agent's config."""
    result = resolve_skill_content("unknown-skill", "", agent_config, tmp_skill)

    assert result is None


def test_resolve_skill_content_missing_file(tmp_skill, agent_config):
    """Returns None when SKILL.md does not exist."""
    agent_config.skills = ["nonexistent"]
    result = resolve_skill_content("nonexistent", "", agent_config, tmp_skill)

    assert result is None
