"""Tests for runner event publishing and cancellation."""

import pytest
from unittest.mock import MagicMock
from agent_md.execution.runner import _classify_event_type


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
