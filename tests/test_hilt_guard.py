import operator
from typing import Annotated, Sequence, TypedDict
from langchain_core.messages import BaseMessage, AIMessage
from langchain_core.tools import tool as lc_tool
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver
from agent_md.tools.guard import guard_tools


class _S(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]


@lc_tool
def danger(path: str) -> str:
    """Delete something."""
    return f"deleted {path}"


def _graph(tools):
    g = StateGraph(_S)
    g.add_node("tools", ToolNode(tools))
    g.set_entry_point("tools")
    g.add_edge("tools", END)
    return g.compile(checkpointer=MemorySaver())


async def test_guard_denied_returns_message():
    tools = guard_tools([danger], {"danger"})
    app = _graph(tools)
    cfg = {"configurable": {"thread_id": "t"}}
    ai = AIMessage(content="", tool_calls=[{"name": "danger", "args": {"path": "/x"}, "id": "1"}])
    chunks = [c async for c in app.astream({"messages": [ai]}, config=cfg)]
    assert "__interrupt__" in chunks[-1]
    payload = chunks[-1]["__interrupt__"][0].value
    assert payload["tool_name"] == "danger"
    assert payload["tool_args"] == {"path": "/x"}
    out = [c async for c in app.astream(Command(resume={"approved": False, "reason": "no"}), config=cfg)]
    msg = out[-1]["tools"]["messages"][0]
    assert "denied" in msg.content.lower()


async def test_guard_approved_runs():
    tools = guard_tools([danger], {"danger"})
    app = _graph(tools)
    cfg = {"configurable": {"thread_id": "t2"}}
    ai = AIMessage(content="", tool_calls=[{"name": "danger", "args": {"path": "/x"}, "id": "1"}])
    [c async for c in app.astream({"messages": [ai]}, config=cfg)]
    out = [c async for c in app.astream(Command(resume={"approved": True}), config=cfg)]
    assert "deleted /x" in out[-1]["tools"]["messages"][0].content


async def test_unguarded_tool_passthrough():
    tools = guard_tools([danger], set())
    assert tools[0] is danger


def test_ask_user_registered():
    from agent_md.tools.registry import resolve_builtin_tools
    from agent_md.config.models import AgentConfig
    from agent_md.workspace.path_context import PathContext
    from pathlib import Path

    cfg = AgentConfig(name="a", model={"provider": "google", "name": "x"})
    pc = PathContext(workspace_root=Path("/tmp"), agents_dir=Path("/tmp"), db_path=Path("/tmp/x.db"),
                     mcp_config=Path("/tmp/m.json"), tools_dir=Path("/tmp"), skills_dir=Path("/tmp"))
    names = {t.name for t in resolve_builtin_tools(cfg, pc)}
    assert "ask_user" in names
