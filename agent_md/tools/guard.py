"""Name-based tool guard: require human confirmation before a tool runs."""

from __future__ import annotations

from langchain_core.tools import BaseTool, StructuredTool
from langgraph.types import interrupt

from agent_md.tools.hilt import build_request


def _guard(tool: BaseTool) -> BaseTool:
    """Wrap *tool* so it asks for confirmation (via interrupt) before executing."""

    async def _arun(**kwargs):
        request = build_request("confirm", f"Approve {tool.name}?", tool_name=tool.name, tool_args=kwargs)
        answer = interrupt(request)
        approved = bool(answer.get("approved")) if isinstance(answer, dict) else bool(answer)
        if not approved:
            reason = answer.get("reason") if isinstance(answer, dict) else None
            suffix = f": {reason}" if reason else "."
            return f"Action denied by user{suffix} ({tool.name} was not executed)"
        return await tool.ainvoke(kwargs)

    def _run(**kwargs):
        request = build_request("confirm", f"Approve {tool.name}?", tool_name=tool.name, tool_args=kwargs)
        answer = interrupt(request)
        approved = bool(answer.get("approved")) if isinstance(answer, dict) else bool(answer)
        if not approved:
            reason = answer.get("reason") if isinstance(answer, dict) else None
            suffix = f": {reason}" if reason else "."
            return f"Action denied by user{suffix} ({tool.name} was not executed)"
        return tool.invoke(kwargs)

    return StructuredTool(
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
        func=_run,
        coroutine=_arun,
    )


def guard_tools(tools: list[BaseTool], confirm_names: set[str]) -> list[BaseTool]:
    """Return *tools* with any whose name is in *confirm_names* wrapped by the guard."""
    if not confirm_names:
        return tools
    return [_guard(t) if t.name in confirm_names else t for t in tools]
