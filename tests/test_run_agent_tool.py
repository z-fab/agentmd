"""Tests for the run_agent tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from agent_md.tools.agents.run_agent import create_run_agent_tool


@pytest.fixture
def caller_config():
    cfg = MagicMock()
    cfg.name = "orchestrator"
    cfg.agents = ["worker-a", "worker-b"]
    return cfg


@pytest.fixture
def worker_a_config():
    cfg = MagicMock()
    cfg.name = "worker-a"
    cfg.enabled = True
    return cfg


@pytest.fixture
def worker_b_config():
    cfg = MagicMock()
    cfg.name = "worker-b"
    cfg.enabled = True
    return cfg


@pytest.fixture
def disabled_config():
    cfg = MagicMock()
    cfg.name = "disabled-agent"
    cfg.enabled = False
    return cfg


@pytest.fixture
def registry(worker_a_config, worker_b_config, disabled_config):
    reg = MagicMock()
    configs = {
        "worker-a": worker_a_config,
        "worker-b": worker_b_config,
        "disabled-agent": disabled_config,
    }
    reg.get.side_effect = lambda name: configs.get(name)
    return reg


@pytest.fixture
def runner():
    r = AsyncMock()
    r.run.return_value = {
        "status": "success",
        "output": "Hello from worker-a",
        "execution_id": 42,
        "duration_ms": 1500,
        "total_tokens": 100,
        "cost_usd": 0.01,
    }
    return r


@pytest.mark.asyncio
async def test_call_allowed_agent(caller_config, registry, runner):
    tool = create_run_agent_tool(
        caller_config=caller_config,
        registry=registry,
        runner=runner,
        parent_execution_id=10,
    )
    result = await tool.ainvoke({"agent_name": "worker-a"})

    runner.run.assert_called_once()
    call_kwargs = runner.run.call_args.kwargs
    assert call_kwargs["trigger_type"] == "agent"
    assert call_kwargs["depth"] == 1
    assert call_kwargs["parent_execution_id"] == 10
    assert result["status"] == "success"
    assert result["output"] == "Hello from worker-a"
    assert result["execution_id"] == 42


@pytest.mark.asyncio
async def test_call_with_arguments(caller_config, registry, runner):
    tool = create_run_agent_tool(
        caller_config=caller_config,
        registry=registry,
        runner=runner,
    )
    await tool.ainvoke({"agent_name": "worker-a", "arguments": "some input"})

    call_kwargs = runner.run.call_args.kwargs
    assert call_kwargs["arguments"] == "some input"


@pytest.mark.asyncio
async def test_call_agent_not_in_allowlist(caller_config, registry, runner):
    tool = create_run_agent_tool(
        caller_config=caller_config,
        registry=registry,
        runner=runner,
    )
    result = await tool.ainvoke({"agent_name": "unknown-agent"})

    assert "error" in result
    assert "not in the allowed agents list" in result["error"]
    runner.run.assert_not_called()


@pytest.mark.asyncio
async def test_call_nonexistent_agent(caller_config, registry, runner):
    # Add to allowlist but registry doesn't have it
    caller_config.agents = ["worker-a", "worker-b", "ghost"]
    tool = create_run_agent_tool(
        caller_config=caller_config,
        registry=registry,
        runner=runner,
    )
    result = await tool.ainvoke({"agent_name": "ghost"})

    assert "error" in result
    assert "not found" in result["error"]
    runner.run.assert_not_called()


@pytest.mark.asyncio
async def test_call_disabled_agent(caller_config, registry, runner):
    caller_config.agents = ["worker-a", "disabled-agent"]
    tool = create_run_agent_tool(
        caller_config=caller_config,
        registry=registry,
        runner=runner,
    )
    result = await tool.ainvoke({"agent_name": "disabled-agent"})

    assert "error" in result
    assert "not enabled" in result["error"]
    runner.run.assert_not_called()


@pytest.mark.asyncio
async def test_call_self(caller_config, registry, runner):
    caller_config.agents = ["orchestrator"]
    tool = create_run_agent_tool(
        caller_config=caller_config,
        registry=registry,
        runner=runner,
    )
    result = await tool.ainvoke({"agent_name": "orchestrator"})

    assert "error" in result
    assert "cannot call itself" in result["error"]
    runner.run.assert_not_called()


@pytest.mark.asyncio
async def test_max_depth_reached(caller_config, registry, runner):
    tool = create_run_agent_tool(
        caller_config=caller_config,
        registry=registry,
        runner=runner,
        depth=3,
        max_depth=3,
    )
    result = await tool.ainvoke({"agent_name": "worker-a"})

    assert "error" in result
    assert "Maximum agent call depth" in result["error"]
    runner.run.assert_not_called()


@pytest.mark.asyncio
async def test_depth_propagated(caller_config, registry, runner):
    tool = create_run_agent_tool(
        caller_config=caller_config,
        registry=registry,
        runner=runner,
        depth=2,
        max_depth=5,
        parent_execution_id=99,
    )
    await tool.ainvoke({"agent_name": "worker-a"})

    call_kwargs = runner.run.call_args.kwargs
    assert call_kwargs["depth"] == 3
    assert call_kwargs["parent_execution_id"] == 99
