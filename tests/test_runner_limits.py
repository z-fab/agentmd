"""Tests for execution limits and LimitExceeded."""

from agent_md.core.models import SettingsConfig


def test_settings_defaults():
    """New fields have sensible defaults."""
    s = SettingsConfig()
    assert s.max_tool_calls == 50
    assert s.max_execution_tokens == 500_000
    assert s.max_cost_usd is None
    assert s.loop_detection is True


def test_settings_override():
    """Fields can be overridden."""
    s = SettingsConfig(max_tool_calls=10, max_execution_tokens=100_000, max_cost_usd=0.25, loop_detection=False)
    assert s.max_tool_calls == 10
    assert s.max_execution_tokens == 100_000
    assert s.max_cost_usd == 0.25
    assert s.loop_detection is False


def test_settings_null_disables():
    """Explicit None disables a limit."""
    s = SettingsConfig(max_tool_calls=None, max_execution_tokens=None)
    assert s.max_tool_calls is None
    assert s.max_execution_tokens is None


from agent_md.core.runner import LimitExceeded


def test_limit_exceeded_str():
    e = LimitExceeded("max_tool_calls", "50 calls reached")
    assert str(e) == "max_tool_calls: 50 calls reached"
    assert e.reason == "max_tool_calls"
    assert e.detail == "50 calls reached"


def test_limit_exceeded_no_detail():
    e = LimitExceeded("max_execution_tokens")
    assert str(e) == "max_execution_tokens"
    assert e.reason == "max_execution_tokens"
    assert e.detail == ""


import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from agent_md.core.runner import AgentRunner, LimitExceeded


def _make_config(
    *,
    max_tool_calls=50,
    max_execution_tokens=500_000,
    max_cost_usd=None,
    loop_detection=True,
    timeout=300,
):
    """Create a minimal AgentConfig-like object for testing."""
    config = MagicMock()
    config.name = "test-agent"
    config.model.provider = "google"
    config.model.name = "gemini-2.0-flash"
    config.model.base_url = None
    config.settings.temperature = 0.7
    config.settings.max_tokens = 4096
    config.settings.timeout = timeout
    config.settings.max_tool_calls = max_tool_calls
    config.settings.max_execution_tokens = max_execution_tokens
    config.settings.max_cost_usd = max_cost_usd
    config.settings.loop_detection = loop_detection
    config.settings.model_dump.return_value = {
        "temperature": 0.7,
        "max_tokens": 4096,
        "timeout": timeout,
    }
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


def _make_ai_msg(content="Hello", tool_calls=None, input_tokens=100, output_tokens=50):
    """Create a mock AI message."""
    msg = MagicMock()
    msg.type = "ai"
    msg.content = content
    msg.tool_calls = tool_calls or []
    msg.usage_metadata = {"input_tokens": input_tokens, "output_tokens": output_tokens}
    return msg


def _make_tool_call_msg(name="file_read", args=None, input_tokens=100, output_tokens=50):
    """Create a mock AI message with tool calls."""
    msg = MagicMock()
    msg.type = "ai"
    msg.content = ""
    msg.tool_calls = [{"name": name, "args": args or {}}]
    msg.usage_metadata = {"input_tokens": input_tokens, "output_tokens": output_tokens}
    return msg


def _make_tool_response(name="file_read", content="result"):
    """Create a mock tool response message."""
    msg = MagicMock()
    msg.type = "tool"
    msg.name = name
    msg.content = content
    msg.usage_metadata = None
    return msg


@pytest.mark.asyncio
async def test_max_tool_calls_aborts():
    """Execution aborts after exceeding max_tool_calls."""
    config = _make_config(max_tool_calls=2)

    # Simulate: 3 tool calls (should abort after 2)
    messages = [
        _make_tool_call_msg("file_read", input_tokens=100, output_tokens=50),
        _make_tool_response("file_read"),
        _make_tool_call_msg("file_write", input_tokens=100, output_tokens=50),
        _make_tool_response("file_write"),
        _make_tool_call_msg("http_request", input_tokens=100, output_tokens=50),  # should not reach
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
    assert "max_tool_calls" in result.get("error", "")


@pytest.mark.asyncio
async def test_max_execution_tokens_aborts():
    """Execution aborts after exceeding max_execution_tokens."""
    config = _make_config(max_execution_tokens=200)

    # Each AI msg has 100 input + 50 output = 150 tokens
    # After 2 AI messages: 300 tokens > 200 limit
    messages = [
        _make_ai_msg("thinking", tool_calls=[{"name": "t", "args": {}}], input_tokens=100, output_tokens=50),
        _make_tool_response("t"),
        _make_ai_msg("more thinking", input_tokens=100, output_tokens=50),  # total=300, should abort
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
    assert "max_execution_tokens" in result.get("error", "")


@pytest.mark.asyncio
async def test_max_cost_usd_aborts():
    """Execution aborts after exceeding max_cost_usd."""
    config = _make_config(max_cost_usd=0.01)
    config.model.provider = "openai"
    config.model.name = "gpt-4o"

    # gpt-4o: $2.50/1M input, $10.00/1M output
    # 10k input + 10k output = $0.025 + $0.10 = $0.125 > $0.01
    messages = [
        _make_ai_msg("thinking", tool_calls=[{"name": "t", "args": {}}], input_tokens=10000, output_tokens=10000),
        _make_tool_response("t"),
        _make_ai_msg("done", input_tokens=100, output_tokens=100),
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
    assert "max_cost_usd" in result.get("error", "")


@pytest.mark.asyncio
async def test_cost_warning_unknown_model():
    """When max_cost_usd is set but model pricing is unknown, execution completes with warning."""
    config = _make_config(max_cost_usd=0.50)
    config.model.provider = "google"
    config.model.name = "totally-unknown-model"

    messages = [_make_ai_msg("done", input_tokens=100, output_tokens=50)]

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
async def test_null_limits_no_abort():
    """When limits are None, no abort happens."""
    config = _make_config(max_tool_calls=None, max_execution_tokens=None)

    messages = [
        _make_tool_call_msg("t1", input_tokens=100000, output_tokens=100000),
        _make_tool_response("t1"),
        _make_ai_msg("done", input_tokens=100000, output_tokens=100000),
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
