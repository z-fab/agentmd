"""Edge case tests for event classification, data building, CLI display, and EventBus."""

from __future__ import annotations

import pytest
from io import StringIO
from unittest.mock import MagicMock

import re

from rich.console import Console

from agent_md.execution.runner import _classify_event_type, _build_event_data
from agent_md.execution.event_bus import EventBus
from agent_md.cli.commands import _print_event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _capture_print_event(event_type: str, data: dict) -> str:
    buf = StringIO()
    console = Console(file=buf, force_terminal=True, width=200)
    _print_event(console, event_type, data)
    return _strip_ansi(buf.getvalue())


def _make_ai_msg(tool_calls=None, content="", additional_kwargs=None):
    msg = MagicMock()
    msg.type = "ai"
    msg.tool_calls = tool_calls if tool_calls is not None else []
    msg.content = content
    msg.additional_kwargs = additional_kwargs or {}
    return msg


def _make_tool_msg(name="file_read", content="result text"):
    msg = MagicMock()
    msg.type = "tool"
    msg.name = name
    msg.content = content
    msg.additional_kwargs = {}
    return msg


def _make_system_msg(content="You are an agent."):
    msg = MagicMock()
    msg.type = "system"
    msg.content = content
    msg.additional_kwargs = {}
    return msg


def _make_unknown_msg():
    msg = MagicMock()
    msg.type = "unknown"
    msg.content = ""
    msg.additional_kwargs = {}
    return msg


# ---------------------------------------------------------------------------
# 1. _classify_event_type edge cases
# ---------------------------------------------------------------------------


def test_classify_ai_empty_tool_calls():
    """AI message with empty tool_calls list should return 'ai'."""
    msg = _make_ai_msg(tool_calls=[])
    assert _classify_event_type(msg) == "ai"


def test_classify_ai_none_tool_calls():
    """AI message with None tool_calls should return 'ai'."""
    msg = MagicMock()
    msg.type = "ai"
    msg.tool_calls = None
    msg.additional_kwargs = {}
    assert _classify_event_type(msg) == "ai"


def test_classify_system_message():
    """System message should return 'system'."""
    msg = _make_system_msg()
    assert _classify_event_type(msg) == "system"


def test_classify_unknown_type():
    """Message with unknown type should return 'unknown'."""
    msg = _make_unknown_msg()
    assert _classify_event_type(msg) == "unknown"


# ---------------------------------------------------------------------------
# 2. _build_event_data edge cases
# ---------------------------------------------------------------------------


def test_build_event_data_ai_with_tools():
    """AI message with tools should include 'tools' list with name and args."""
    msg = _make_ai_msg(tool_calls=[{"name": "file_read", "args": {"path": "/tmp/test.txt"}}])
    data = _build_event_data(msg, "tool_call", "my-agent")
    assert "tools" in data
    assert data["tools"][0]["name"] == "file_read"
    assert "path" in data["tools"][0]["args"]


def test_build_event_data_ai_without_tools():
    """Plain AI message should include 'content'."""
    msg = _make_ai_msg(content="Here is the answer.")
    data = _build_event_data(msg, "ai", "my-agent")
    assert "content" in data
    assert data["content"] == "Here is the answer."
    assert "tools" not in data


def test_build_event_data_tool_result():
    """Tool result message should include 'tool_name' and truncated 'content'."""
    msg = _make_tool_msg(name="http_request", content="200 OK")
    data = _build_event_data(msg, "tool_result", "my-agent")
    assert data["tool_name"] == "http_request"
    assert "content" in data
    assert data["content"] == "200 OK"


def test_build_event_data_ai_empty_content():
    """AI message with empty content should have content=''."""
    msg = _make_ai_msg(content="")
    data = _build_event_data(msg, "ai", "my-agent")
    assert data["content"] == ""


def test_build_event_data_meta_message():
    """Meta message should include 'content'."""
    msg = MagicMock()
    msg.type = "human"
    msg.content = "# Skill context\nSome skill info."
    msg.additional_kwargs = {"meta_type": "skill-context"}
    data = _build_event_data(msg, "meta", "my-agent")
    assert "content" in data
    assert "Skill context" in data["content"]


def test_build_event_data_tool_call_very_long_args():
    """Tool call with very long args (>200 chars) should be truncated to 200 chars."""
    long_args = {"path": "x" * 300}
    msg = _make_ai_msg(tool_calls=[{"name": "file_write", "args": long_args}])
    data = _build_event_data(msg, "tool_call", "my-agent")
    assert len(data["tools"][0]["args"]) <= 200


def test_build_event_data_tool_result_long_content():
    """Tool result with content >200 chars should be truncated to 200 chars."""
    msg = _make_tool_msg(content="A" * 300)
    data = _build_event_data(msg, "tool_result", "my-agent")
    assert len(data["content"]) <= 200


def test_build_event_data_includes_agent_name():
    """Event data should always include agent_name and event_type."""
    msg = _make_ai_msg(content="hello")
    data = _build_event_data(msg, "ai", "test-agent")
    assert data["agent_name"] == "test-agent"
    assert data["event_type"] == "ai"


# ---------------------------------------------------------------------------
# 3. _print_event display edge cases
# ---------------------------------------------------------------------------


def test_print_event_tool_call_live_format():
    """tool_call with live format (has 'tools' list) shows wrench >> name (args)."""
    data = {"tools": [{"name": "file_read", "args": "{'path': '/tmp/x.txt'}"}]}
    output = _capture_print_event("tool_call", data)
    assert "file_read" in output
    assert ">>" in output


def test_print_event_tool_call_db_replay_format():
    """tool_call with DB replay format (has 'message' only) shows wrench >> message."""
    data = {"message": "file_write — args: {'path': '/tmp/out.txt'}"}
    output = _capture_print_event("tool_call", data)
    assert "file_write" in output
    assert ">>" in output


def test_print_event_tool_result_live_format():
    """tool_result with live format (has 'tool_name') shows paperclip << name -> result."""
    data = {"tool_name": "file_read", "content": "file contents here"}
    output = _capture_print_event("tool_result", data)
    assert "file_read" in output
    assert "file contents here" in output
    assert "<<" in output


def test_print_event_tool_result_db_replay_format():
    """tool_result with DB replay format (no 'tool_name') shows paperclip << result."""
    data = {"content": "file_write — Updated /tmp/out.txt"}
    output = _capture_print_event("tool_result", data)
    assert "<<" in output
    assert "file_write" in output


def test_print_event_ai_with_content():
    """ai event with content shows robot + content."""
    data = {"content": "The answer is 42."}
    output = _capture_print_event("ai", data)
    assert "The answer is 42." in output


def test_print_event_ai_empty_content():
    """ai event with empty content shows nothing."""
    data = {"content": ""}
    output = _capture_print_event("ai", data)
    assert output.strip() == ""


def test_print_event_final_answer_with_content():
    """final_answer with content shows checkmark + content."""
    data = {"content": "Task complete."}
    output = _capture_print_event("final_answer", data)
    assert "Task complete." in output
    assert "\u2705" in output


def test_print_event_final_answer_empty_content():
    """final_answer with empty content shows checkmark (still prints)."""
    data = {"content": ""}
    output = _capture_print_event("final_answer", data)
    assert "\u2705" in output


def test_print_event_system_silent():
    """system event is silently ignored — no output."""
    data = {"content": "You are a helpful agent."}
    output = _capture_print_event("system", data)
    assert output.strip() == ""


def test_print_event_human_silent():
    """human event is silently ignored — no output."""
    data = {"content": "Execute your task."}
    output = _capture_print_event("human", data)
    assert output.strip() == ""


def test_print_event_meta_silent():
    """meta event is silently ignored — no output."""
    data = {"content": "# Skill instructions"}
    output = _capture_print_event("meta", data)
    assert output.strip() == ""


def test_print_event_complete_not_handled():
    """complete event is not handled by _print_event (handled in _stream_execution)."""
    data = {"status": "success", "total_tokens": 1000}
    output = _capture_print_event("complete", data)
    assert output.strip() == ""


def test_print_event_tool_result_alias():
    """tool_response alias for tool_result is handled the same way."""
    data = {"content": "some tool output"}
    output = _capture_print_event("tool_response", data)
    assert "<<" in output
    assert "some tool output" in output


# ---------------------------------------------------------------------------
# 4. EventBus edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_double_unsubscribe_no_error():
    """Double unsubscribe of the same queue should not raise and counter stays correct."""
    bus = EventBus()
    q = bus.subscribe(1)
    assert bus.stream_count == 1
    bus.unsubscribe(1, q)
    assert bus.stream_count == 0
    # Second unsubscribe — queue is no longer in the list, should be a no-op
    bus.unsubscribe(1, q)
    assert bus.stream_count == 0


@pytest.mark.asyncio
async def test_publish_after_all_unsubscribed():
    """Publishing after all subscribers unsubscribed should not raise."""
    bus = EventBus()
    q = bus.subscribe(1)
    bus.unsubscribe(1, q)
    # Should not raise
    await bus.publish(1, {"type": "ai", "seq": 1, "data": {}})


@pytest.mark.asyncio
async def test_subscribe_same_execution_id_twice():
    """Two subscriptions for the same execution_id both receive events."""
    bus = EventBus()
    q1 = bus.subscribe(42)
    q2 = bus.subscribe(42)
    event = {"type": "ai", "seq": 1, "data": {"content": "hello"}}
    await bus.publish(42, event)
    assert q1.get_nowait() == event
    assert q2.get_nowait() == event


@pytest.mark.asyncio
async def test_double_unsubscribe_does_not_decrement_below_zero():
    """Stream count must never go below zero after a double unsubscribe."""
    bus = EventBus()
    q = bus.subscribe(5)
    bus.unsubscribe(5, q)
    bus.unsubscribe(5, q)
    assert bus.stream_count >= 0
