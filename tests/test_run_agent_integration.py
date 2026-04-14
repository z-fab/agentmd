"""Integration tests for agent-to-agent execution."""

import pytest
from unittest.mock import AsyncMock

from agent_md.config.models import AgentConfig
from agent_md.workspace.registry import AgentRegistry
from agent_md.tools.agents.run_agent import create_run_agent_tool


def _make_agent(name: str, description: str = "", agents: list[str] | None = None) -> AgentConfig:
    return AgentConfig(name=name, description=description, agents=agents or [])


@pytest.fixture
def registry():
    reg = AgentRegistry()
    reg.register(_make_agent("orchestrator", "Coordinates tasks", agents=["worker", "reviewer"]))
    reg.register(_make_agent("worker", "Does the work"))
    reg.register(_make_agent("reviewer", "Reviews results"))
    return reg


def _make_runner(result=None):
    runner = AsyncMock()
    runner.run = AsyncMock(return_value=result or {
        "status": "success",
        "output": "Task completed",
        "execution_id": 10,
        "duration_ms": 500,
        "total_tokens": 1000,
        "cost_usd": 0.005,
    })
    return runner


async def test_trigger_type_is_agent(registry):
    runner = _make_runner()
    orchestrator = registry.get("orchestrator")
    tool = create_run_agent_tool(
        caller_config=orchestrator, registry=registry, runner=runner,
        depth=0, max_depth=3,
    )
    await tool.ainvoke({"agent_name": "worker"})
    call_kwargs = runner.run.call_args.kwargs
    assert call_kwargs["trigger_type"] == "agent"
    assert "orchestrator" in call_kwargs["trigger_context"]


async def test_parent_execution_id_is_callers_execution(registry):
    runner = _make_runner()
    orchestrator = registry.get("orchestrator")
    tool = create_run_agent_tool(
        caller_config=orchestrator, registry=registry, runner=runner,
        depth=0, max_depth=3, parent_execution_id=55,
    )
    await tool.ainvoke({"agent_name": "worker"})
    call_kwargs = runner.run.call_args.kwargs
    assert call_kwargs["parent_execution_id"] == 55


async def test_depth_chain_blocks_at_limit(registry):
    runner = _make_runner()
    orchestrator = registry.get("orchestrator")

    # Depth 2 should work
    tool = create_run_agent_tool(
        caller_config=orchestrator, registry=registry, runner=runner,
        depth=2, max_depth=3,
    )
    result = await tool.ainvoke({"agent_name": "worker"})
    assert result["status"] == "success"
    assert runner.run.call_args.kwargs["depth"] == 3

    # Depth 3 should be blocked
    tool = create_run_agent_tool(
        caller_config=orchestrator, registry=registry, runner=runner,
        depth=3, max_depth=3,
    )
    result = await tool.ainvoke({"agent_name": "worker"})
    assert "error" in result


async def test_child_error_returned_to_parent(registry):
    runner = _make_runner(result={
        "status": "error",
        "error": "Something went wrong",
        "execution_id": 11,
        "duration_ms": 50,
        "total_tokens": 100,
        "cost_usd": 0.001,
    })
    orchestrator = registry.get("orchestrator")
    tool = create_run_agent_tool(
        caller_config=orchestrator, registry=registry, runner=runner,
        depth=0, max_depth=3,
    )
    result = await tool.ainvoke({"agent_name": "worker"})
    assert result["status"] == "error"
    assert result["output"] == "Something went wrong"


async def test_arguments_forwarded(registry):
    runner = _make_runner()
    orchestrator = registry.get("orchestrator")
    tool = create_run_agent_tool(
        caller_config=orchestrator, registry=registry, runner=runner,
        depth=0, max_depth=3,
    )
    await tool.ainvoke({"agent_name": "worker", "arguments": "file.txt summarize"})
    call_kwargs = runner.run.call_args.kwargs
    assert call_kwargs["arguments"] == "file.txt summarize"
