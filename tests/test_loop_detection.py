# tests/test_loop_detection.py
"""Tests for loop detection (same error repeated 3 times)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from agent_md.core.runner import AgentRunner


def _make_config(loop_detection=True, max_tool_calls=None, max_execution_tokens=None):
    config = MagicMock()
    config.name = "test-agent"
    config.model.provider = "google"
    config.model.name = "gemini-2.0-flash"
    config.model.base_url = None
    config.settings.temperature = 0.7
    config.settings.max_tokens = 4096
    config.settings.timeout = 300
    config.settings.max_tool_calls = max_tool_calls
    config.settings.max_execution_tokens = max_execution_tokens
    config.settings.max_cost_usd = None
    config.settings.loop_detection = loop_detection
    config.settings.model_dump.return_value = {"temperature": 0.7, "max_tokens": 4096, "timeout": 300}
    config.history = "off"
    config.system_prompt = "You are a test agent."
    config.custom_tools = []
    config.mcp = []
    config.skills = []
    config.trigger = MagicMock()
    config.trigger.every = None
    config.trigger.cron = None
    config.paths = {}
    return config


def _make_tool_call(name="file_read"):
    msg = MagicMock()
    msg.type = "ai"
    msg.content = ""
    msg.tool_calls = [{"name": name, "args": {}}]
    msg.usage_metadata = {"input_tokens": 10, "output_tokens": 5}
    return msg


def _make_tool_error(name="file_read", error="Error: file not found /foo.txt"):
    msg = MagicMock()
    msg.type = "tool"
    msg.name = name
    msg.content = error
    msg.usage_metadata = None
    return msg


def _make_final(content="done"):
    msg = MagicMock()
    msg.type = "ai"
    msg.content = content
    msg.tool_calls = []
    msg.usage_metadata = {"input_tokens": 10, "output_tokens": 5}
    return msg


@pytest.mark.asyncio
async def test_loop_detection_same_error_3x():
    """3 identical tool errors trigger loop_detected abort."""
    config = _make_config(loop_detection=True)

    messages = [
        _make_tool_call("file_read"),
        _make_tool_error("file_read", "Error: file not found /foo.txt"),
        _make_tool_call("file_read"),
        _make_tool_error("file_read", "Error: file not found /foo.txt"),
        _make_tool_call("file_read"),
        _make_tool_error("file_read", "Error: file not found /foo.txt"),
        _make_final("done"),
    ]

    db = AsyncMock()
    db.create_execution = AsyncMock(return_value=1)
    db.update_execution = AsyncMock()
    db.add_log = AsyncMock()

    runner = AgentRunner(db, MagicMock(), MagicMock())

    with patch.object(runner, "_build_graph", new_callable=AsyncMock):
        with patch("agent_md.core.runner.stream_agent_graph") as mock_stream:
            async def fake_stream(*args, **kwargs):
                for m in messages:
                    yield m
            mock_stream.return_value = fake_stream()

            result = await runner.run(config)

    assert result["status"] == "aborted"
    assert "loop_detected" in result.get("error", "")


@pytest.mark.asyncio
async def test_loop_detection_different_errors_no_abort():
    """3 different tool errors do NOT trigger loop detection."""
    config = _make_config(loop_detection=True)

    messages = [
        _make_tool_call("file_read"),
        _make_tool_error("file_read", "Error: file not found /a.txt"),
        _make_tool_call("file_write"),
        _make_tool_error("file_write", "Error: permission denied"),
        _make_tool_call("http_request"),
        _make_tool_error("http_request", "Error: connection timeout"),
        _make_final("done"),
    ]

    db = AsyncMock()
    db.create_execution = AsyncMock(return_value=1)
    db.update_execution = AsyncMock()
    db.add_log = AsyncMock()

    runner = AgentRunner(db, MagicMock(), MagicMock())

    with patch.object(runner, "_build_graph", new_callable=AsyncMock):
        with patch("agent_md.core.runner.stream_agent_graph") as mock_stream:
            async def fake_stream(*args, **kwargs):
                for m in messages:
                    yield m
            mock_stream.return_value = fake_stream()

            result = await runner.run(config)

    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_loop_detection_disabled():
    """loop_detection=False disables loop abort."""
    config = _make_config(loop_detection=False)

    messages = [
        _make_tool_call("file_read"),
        _make_tool_error("file_read", "Error: not found"),
        _make_tool_call("file_read"),
        _make_tool_error("file_read", "Error: not found"),
        _make_tool_call("file_read"),
        _make_tool_error("file_read", "Error: not found"),
        _make_final("done"),
    ]

    db = AsyncMock()
    db.create_execution = AsyncMock(return_value=1)
    db.update_execution = AsyncMock()
    db.add_log = AsyncMock()

    runner = AgentRunner(db, MagicMock(), MagicMock())

    with patch.object(runner, "_build_graph", new_callable=AsyncMock):
        with patch("agent_md.core.runner.stream_agent_graph") as mock_stream:
            async def fake_stream(*args, **kwargs):
                for m in messages:
                    yield m
            mock_stream.return_value = fake_stream()

            result = await runner.run(config)

    assert result["status"] == "success"
