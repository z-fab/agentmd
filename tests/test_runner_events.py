"""Tests for runner event publishing and cancellation."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from agent_md.execution.runner import _classify_event_type
from agent_md.execution.logger import ExecutionLogger


@pytest.mark.asyncio
async def test_classify_event_type_ai_with_tools():
    msg = MagicMock()
    msg.type = "ai"
    msg.tool_calls = [{"name": "file_read"}]
    msg.additional_kwargs = {}
    assert _classify_event_type(msg) == "tool_call"


@pytest.mark.asyncio
async def test_classify_event_type_ai_no_tools():
    msg = MagicMock()
    msg.type = "ai"
    msg.tool_calls = []
    msg.additional_kwargs = {}
    assert _classify_event_type(msg) == "ai"


@pytest.mark.asyncio
async def test_classify_event_type_tool():
    msg = MagicMock()
    msg.type = "tool"
    msg.additional_kwargs = {}
    assert _classify_event_type(msg) == "tool_result"


@pytest.mark.asyncio
async def test_classify_event_type_meta():
    msg = MagicMock()
    msg.type = "human"
    msg.additional_kwargs = {"meta_type": "skill-context"}
    assert _classify_event_type(msg) == "meta"


@pytest.mark.asyncio
async def test_classify_event_type_human():
    msg = MagicMock()
    msg.type = "human"
    msg.additional_kwargs = {}
    assert _classify_event_type(msg) == "human"


@pytest.mark.asyncio
async def test_logger_tool_message_emits_tool_result():
    """ExecutionLogger must emit and persist 'tool_result', never 'tool_response'."""
    db = MagicMock()
    db.add_log = AsyncMock(return_value=1)

    emitted: list[tuple[str, dict]] = []

    logger = ExecutionLogger(
        db=db,
        execution_id=1,
        agent_name="test-agent",
        on_event=lambda event_type, data: emitted.append((event_type, data)),
    )

    msg = MagicMock()
    msg.type = "tool"
    msg.name = "file_read"
    msg.content = "file contents here"

    await logger.log_message(msg)

    assert emitted, "on_event was never called"
    event_types = [e[0] for e in emitted]
    assert "tool_result" in event_types, f"Expected 'tool_result' in emitted events, got {event_types}"
    assert "tool_response" not in event_types, f"'tool_response' must not be emitted, got {event_types}"

    persisted_types = [
        call.kwargs.get("event_type", call.args[1] if len(call.args) > 1 else None)
        for call in db.add_log.call_args_list
    ]
    assert "tool_result" in persisted_types, f"Expected 'tool_result' persisted, got {persisted_types}"
    assert "tool_response" not in persisted_types, f"'tool_response' must not be persisted, got {persisted_types}"
