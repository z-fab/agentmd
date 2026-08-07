"""run_agent tool — lets one agent execute another."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import StructuredTool

logger = logging.getLogger(__name__)


def create_run_agent_tool(
    *,
    caller_config,
    registry,
    runner,
    depth: int = 0,
    max_depth: int = 3,
    parent_execution_id: int | None = None,
    event_bus=None,
    global_event_bus=None,
    cancel_event=None,
    sub_agent_usage: dict | None = None,
) -> StructuredTool:
    """Create a run_agent tool bound to the caller's context."""

    async def _run_agent(agent_name: str, arguments: str = "") -> dict[str, Any]:
        # Validate allowlist
        if agent_name not in caller_config.agents:
            return {"error": f"Agent '{agent_name}' is not in the allowed agents list"}

        # Validate self-call
        if agent_name == caller_config.name:
            return {"error": "Agent cannot call itself"}

        # Validate depth
        if depth >= max_depth:
            return {"error": f"Maximum agent call depth ({max_depth}) reached"}

        # Validate target exists
        target_config = registry.get(agent_name)
        if not target_config:
            return {"error": f"Agent '{agent_name}' not found"}

        # Validate target enabled
        if not target_config.enabled:
            return {"error": f"Agent '{agent_name}' is not enabled"}

        logger.info(f"Agent '{caller_config.name}' calling '{agent_name}' (depth={depth + 1})")

        try:
            result = await runner.run(
                config=target_config,
                trigger_type="agent",
                trigger_context=f"Called by {caller_config.name}",
                arguments=arguments,
                event_bus=event_bus,
                global_event_bus=global_event_bus,
                depth=depth + 1,
                parent_execution_id=parent_execution_id,
                cancel_event=cancel_event,
            )
        except Exception as e:
            return {"error": f"Execution failed: {e}"}

        # Fold child usage into the caller's accumulator so parent limits apply.
        if sub_agent_usage is not None:
            in_tok = result.get("input_tokens") or 0
            out_tok = result.get("output_tokens") or 0
            if in_tok or out_tok:
                sub_agent_usage["input_tokens"] = sub_agent_usage.get("input_tokens", 0) + int(in_tok)
                sub_agent_usage["output_tokens"] = sub_agent_usage.get("output_tokens", 0) + int(out_tok)
            elif result.get("total_tokens"):
                # No split — count the whole total toward the parent's token limit.
                sub_agent_usage["input_tokens"] = sub_agent_usage.get("input_tokens", 0) + int(result["total_tokens"])
            child_cost = result.get("cost_usd")
            if child_cost is not None:
                sub_agent_usage["cost_usd"] = sub_agent_usage.get("cost_usd", 0.0) + float(child_cost)

        return {
            "status": result.get("status", "error"),
            "output": result.get("output", result.get("error", "")),
            "execution_id": result.get("execution_id"),
            "duration_ms": result.get("duration_ms"),
            "total_tokens": result.get("total_tokens"),
            "cost_usd": result.get("cost_usd"),
        }

    agent_names = ", ".join(caller_config.agents)

    return StructuredTool.from_function(
        coroutine=_run_agent,
        name="run_agent",
        description=(f"Execute another agent and return its result. Allowed agents: {agent_names}"),
    )
