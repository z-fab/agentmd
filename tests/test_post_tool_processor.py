"""Tests for post_tool_processor graph node."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent_md.graph.post_tool_processor import create_post_tool_processor


@pytest.fixture
def tmp_skill(tmp_path):
    """Create a minimal skill directory."""
    skill_dir = tmp_path / "review-pr"
    skill_dir.mkdir()
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        "---\nname: review-pr\ndescription: Review PRs\n---\n"
        "Review the PR $ARGUMENTS carefully."
    )
    return tmp_path


@pytest.fixture
def agent_config():
    config = MagicMock()
    config.skills = ["review-pr"]
    return config


def test_injects_meta_message_on_skill_use(tmp_skill, agent_config):
    """When skill_use is in the tool messages, injects a HumanMessage with skill-context."""
    processor = create_post_tool_processor(agent_config, tmp_skill)

    state = {
        "messages": [
            HumanMessage(content="Review PR 123"),
            AIMessage(
                content="",
                tool_calls=[{"id": "call_1", "name": "skill_use", "args": {"skill_name": "review-pr", "arguments": "123"}}],
            ),
            ToolMessage(
                content="Skill 'review-pr' activated successfully. Instructions will follow.",
                tool_call_id="call_1",
                name="skill_use",
            ),
        ]
    }

    result = processor(state)
    new_msgs = result["messages"]

    assert len(new_msgs) == 1
    meta_msg = new_msgs[0]
    assert isinstance(meta_msg, HumanMessage)
    assert "<skill-context name=" in meta_msg.content
    assert "review-pr" in meta_msg.content
    assert "Review the PR 123 carefully." in meta_msg.content
    assert meta_msg.additional_kwargs["meta_type"] == "skill-context"
    assert meta_msg.additional_kwargs["skill_name"] == "review-pr"


def test_no_injection_for_non_skill_tools(tmp_skill, agent_config):
    """Does nothing when no skill_use tool was called."""
    processor = create_post_tool_processor(agent_config, tmp_skill)

    state = {
        "messages": [
            HumanMessage(content="Read the file"),
            AIMessage(
                content="",
                tool_calls=[{"id": "call_1", "name": "file_read", "args": {"path": "/tmp/x.py"}}],
            ),
            ToolMessage(content="file contents here", tool_call_id="call_1", name="file_read"),
        ]
    }

    result = processor(state)
    assert result["messages"] == []


def test_no_injection_when_skill_validation_fails(tmp_skill, agent_config):
    """Does not inject if the skill cannot be resolved (e.g., missing file)."""
    processor = create_post_tool_processor(agent_config, tmp_skill)

    state = {
        "messages": [
            HumanMessage(content="Use unknown skill"),
            AIMessage(
                content="",
                tool_calls=[{"id": "call_1", "name": "skill_use", "args": {"skill_name": "nonexistent", "arguments": ""}}],
            ),
            ToolMessage(
                content="Skill 'nonexistent' is not enabled for this agent.",
                tool_call_id="call_1",
                name="skill_use",
            ),
        ]
    }

    result = processor(state)
    assert result["messages"] == []


def test_handles_multiple_tools_with_one_skill(tmp_skill, agent_config):
    """When multiple tools run and one is skill_use, only injects for that one."""
    processor = create_post_tool_processor(agent_config, tmp_skill)

    state = {
        "messages": [
            HumanMessage(content="Do stuff"),
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "call_1", "name": "file_read", "args": {"path": "/tmp/x.py"}},
                    {"id": "call_2", "name": "skill_use", "args": {"skill_name": "review-pr", "arguments": "456"}},
                ],
            ),
            ToolMessage(content="file contents", tool_call_id="call_1", name="file_read"),
            ToolMessage(content="Skill 'review-pr' activated successfully.", tool_call_id="call_2", name="skill_use"),
        ]
    }

    result = processor(state)
    new_msgs = result["messages"]

    assert len(new_msgs) == 1
    assert "review-pr" in new_msgs[0].content
    assert "456" in new_msgs[0].content
