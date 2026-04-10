"""Empirical validation that timeout actually interrupts execution."""

import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from agent_md.core.runner import AgentRunner


def _make_config(timeout=2):
    config = MagicMock()
    config.name = "timeout-test"
    config.model.provider = "google"
    config.model.name = "gemini-2.0-flash"
    config.model.base_url = None
    config.settings.temperature = 0.7
    config.settings.max_tokens = 4096
    config.settings.timeout = timeout
    config.settings.max_tool_calls = None
    config.settings.max_execution_tokens = None
    config.settings.max_cost_usd = None
    config.settings.loop_detection = False
    config.settings.model_dump.return_value = {"temperature": 0.7, "max_tokens": 4096, "timeout": timeout}
    config.history = "off"
    config.system_prompt = "Test."
    config.custom_tools = []
    config.mcp = []
    config.skills = []
    config.trigger = MagicMock()
    config.trigger.every = None
    config.trigger.cron = None
    config.paths = {}
    return config


@pytest.mark.asyncio
async def test_timeout_interrupts_execution():
    """Execution with timeout=2s finishes in roughly 2s, not 30s."""
    import asyncio

    config = _make_config(timeout=2)

    async def slow_stream(*args, **kwargs):
        for i in range(30):
            await asyncio.sleep(1)
            msg = MagicMock()
            msg.type = "ai"
            msg.content = f"message {i}"
            msg.tool_calls = []
            msg.usage_metadata = {"input_tokens": 10, "output_tokens": 5}
            yield msg

    db = AsyncMock()
    db.create_execution = AsyncMock(return_value=1)
    db.update_execution = AsyncMock()
    db.add_log = AsyncMock()

    runner = AgentRunner(db, MagicMock(), MagicMock())

    start = time.monotonic()

    with patch.object(runner, "_build_graph", new_callable=AsyncMock):
        with patch("agent_md.core.runner.stream_agent_graph", side_effect=slow_stream):
            result = await runner.run(config)

    elapsed = time.monotonic() - start

    assert result["status"] == "timeout"
    assert elapsed < 5, f"Timeout took {elapsed:.1f}s — expected ~2s, got >5s (event loop blocked?)"
