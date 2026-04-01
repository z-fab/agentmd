"""Tests for expanded _trim_messages with smart compaction."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from agent_md.graph.agent import _trim_messages


def test_compacts_skill_context_to_breadcrumb():
    """skill-context meta messages become skill-breadcrumb after trimming."""
    messages = [
        SystemMessage(content="system"),
        HumanMessage(content="do stuff"),
        AIMessage(
            content="",
            tool_calls=[{"id": "c1", "name": "skill_use", "args": {"skill_name": "review-pr"}}],
        ),
        ToolMessage(content="Skill activated", tool_call_id="c1", name="skill_use"),
        HumanMessage(
            content='<skill-context name="review-pr">\nLong skill instructions here...\n</skill-context>',
            additional_kwargs={"meta_type": "skill-context", "skill_name": "review-pr"},
        ),
        AIMessage(content="I'll review the PR now."),
    ]

    result = _trim_messages(messages, limit=100)

    # Find the meta message in the result
    meta_msgs = [m for m in result if m.additional_kwargs.get("meta_type") == "skill-breadcrumb"]
    assert len(meta_msgs) == 1
    assert "review-pr" in meta_msgs[0].content
    assert "<skill-breadcrumb" in meta_msgs[0].content
    # Original skill-context should be gone
    context_msgs = [m for m in result if m.additional_kwargs.get("meta_type") == "skill-context"]
    assert len(context_msgs) == 0


def test_truncates_large_tool_results():
    """Tool results exceeding threshold are truncated."""
    large_content = "x" * 1000
    messages = [
        SystemMessage(content="system"),
        HumanMessage(content="read file"),
        AIMessage(
            content="",
            tool_calls=[{"id": "c1", "name": "file_read", "args": {"path": "/tmp/big.py"}}],
        ),
        ToolMessage(content=large_content, tool_call_id="c1", name="file_read"),
        AIMessage(content="Got it."),
    ]

    result = _trim_messages(messages, limit=100)

    tool_msgs = [m for m in result if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1
    assert len(tool_msgs[0].content) < len(large_content)
    assert "file_read" in tool_msgs[0].content or "[truncated]" in tool_msgs[0].content


def test_preserves_small_tool_results():
    """Tool results under the threshold are kept intact."""
    messages = [
        SystemMessage(content="system"),
        HumanMessage(content="read file"),
        AIMessage(
            content="",
            tool_calls=[{"id": "c1", "name": "file_read", "args": {"path": "/tmp/small.py"}}],
        ),
        ToolMessage(content="print('hi')", tool_call_id="c1", name="file_read"),
        AIMessage(content="Simple file."),
    ]

    result = _trim_messages(messages, limit=100)

    tool_msgs = [m for m in result if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].content == "print('hi')"


def test_preserves_skill_breadcrumbs():
    """Existing breadcrumbs are not modified."""
    messages = [
        SystemMessage(content="system"),
        HumanMessage(
            content='<skill-breadcrumb name="review-pr">Skill review-pr was activated in a previous run</skill-breadcrumb>',
            additional_kwargs={"meta_type": "skill-breadcrumb", "skill_name": "review-pr"},
        ),
        AIMessage(content="Noted."),
        HumanMessage(content="new task"),
        AIMessage(content="On it."),
    ]

    result = _trim_messages(messages, limit=100)

    breadcrumbs = [m for m in result if m.additional_kwargs.get("meta_type") == "skill-breadcrumb"]
    assert len(breadcrumbs) == 1
    assert breadcrumbs[0].content == messages[1].content


def test_count_limit_still_applies():
    """After compaction, count-based limit is still enforced."""
    messages = [SystemMessage(content="system")]
    for i in range(20):
        messages.append(HumanMessage(content=f"msg {i}"))
        messages.append(AIMessage(content=f"reply {i}"))

    result = _trim_messages(messages, limit=10)

    non_system = [m for m in result if not isinstance(m, SystemMessage)]
    assert len(non_system) <= 12  # 10 + possible walk-back to HumanMessage


def test_message_ordering_invariants():
    """First non-system message is always HumanMessage after trimming."""
    messages = [SystemMessage(content="system")]
    for i in range(30):
        messages.append(HumanMessage(content=f"msg {i}"))
        messages.append(AIMessage(content=f"reply {i}"))

    result = _trim_messages(messages, limit=6)

    non_system = [m for m in result if not isinstance(m, SystemMessage)]
    assert isinstance(non_system[0], HumanMessage)


def test_compact_false_preserves_skill_context():
    """When compact=False, skill-context is NOT converted to breadcrumb."""
    messages = [
        SystemMessage(content="system"),
        HumanMessage(content="do stuff"),
        AIMessage(
            content="",
            tool_calls=[{"id": "c1", "name": "skill_use", "args": {"skill_name": "review-pr"}}],
        ),
        ToolMessage(content="Skill activated", tool_call_id="c1", name="skill_use"),
        HumanMessage(
            content='<skill-context name="review-pr">\nFull instructions here\n</skill-context>',
            additional_kwargs={"meta_type": "skill-context", "skill_name": "review-pr"},
        ),
        AIMessage(content="Following the skill."),
    ]

    result = _trim_messages(messages, limit=100, compact=False)

    # skill-context should be preserved (not converted to breadcrumb)
    context_msgs = [m for m in result if m.additional_kwargs.get("meta_type") == "skill-context"]
    assert len(context_msgs) == 1
    assert "Full instructions here" in context_msgs[0].content
    breadcrumb_msgs = [m for m in result if m.additional_kwargs.get("meta_type") == "skill-breadcrumb"]
    assert len(breadcrumb_msgs) == 0


def test_compact_false_preserves_large_tool_results():
    """When compact=False, large tool results are NOT truncated."""
    large_content = "x" * 1000
    messages = [
        SystemMessage(content="system"),
        HumanMessage(content="read"),
        AIMessage(
            content="",
            tool_calls=[{"id": "c1", "name": "file_read", "args": {"path": "/tmp/big.py"}}],
        ),
        ToolMessage(content=large_content, tool_call_id="c1", name="file_read"),
        AIMessage(content="Got it."),
    ]

    result = _trim_messages(messages, limit=100, compact=False)

    tool_msgs = [m for m in result if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].content == large_content


def test_tool_call_pairs_preserved():
    """AIMessage with tool_calls always has its ToolMessages kept together."""
    messages = [
        SystemMessage(content="system"),
        HumanMessage(content="start"),
        AIMessage(content="thinking"),
        HumanMessage(content="do tool thing"),
        AIMessage(
            content="",
            tool_calls=[{"id": "c1", "name": "file_read", "args": {"path": "/tmp/x"}}],
        ),
        ToolMessage(content="contents", tool_call_id="c1", name="file_read"),
        AIMessage(content="done"),
    ]

    result = _trim_messages(messages, limit=100)

    # Find AIMessage with tool_calls
    ai_with_tools = [m for m in result if hasattr(m, "tool_calls") and m.tool_calls]
    for ai_msg in ai_with_tools:
        for tc in ai_msg.tool_calls:
            tool_msgs = [m for m in result if isinstance(m, ToolMessage) and m.tool_call_id == tc["id"]]
            assert len(tool_msgs) == 1
