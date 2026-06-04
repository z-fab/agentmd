import operator
from typing import Annotated, Sequence, TypedDict

import pytest

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command

from agent_md.tools.hilt import REQUEST_KINDS, build_request


def test_build_request_confirm():
    req = build_request("confirm", "Delete file?", tool_name="file_delete", tool_args={"path": "/x"})
    assert req["kind"] == "confirm"
    assert req["message"] == "Delete file?"
    assert req["tool_name"] == "file_delete"
    assert req["tool_args"] == {"path": "/x"}
    assert isinstance(req["request_id"], str) and req["request_id"]


def test_build_request_choice():
    req = build_request("choice", "Pick", options=["a", "b"], multi=True)
    assert req["kind"] == "choice"
    assert req["options"] == ["a", "b"]
    assert req["multi"] is True


def test_request_kinds():
    assert REQUEST_KINDS == ("confirm", "input", "choice")


class _S(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]


async def test_sdk_request_input_roundtrip():
    from agent_md.sdk import request_input

    def node(state):
        text = request_input("Your name?")
        return {"messages": [AIMessage(content=f"hi {text}")]}

    g = StateGraph(_S)
    g.add_node("n", node)
    g.set_entry_point("n")
    g.add_edge("n", END)
    app = g.compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t"}}

    chunks = [c async for c in app.astream({"messages": [HumanMessage(content="x")]}, config=cfg)]
    assert "__interrupt__" in chunks[-1]
    payload = chunks[-1]["__interrupt__"][0].value
    assert payload["kind"] == "input"

    out = [c async for c in app.astream(Command(resume={"text": "Ana"}), config=cfg)]
    assert out[-1]["n"]["messages"][0].content == "hi Ana"


async def test_stream_state_raises_graph_paused():
    from agent_md.graph.builder import _stream_state, GraphPaused
    from agent_md.sdk import request_confirmation

    def node(state):
        request_confirmation("ok?", tool_name="x", tool_args={})
        return {"messages": [AIMessage(content="done")]}

    g = StateGraph(_S)
    g.add_node("n", node)
    g.set_entry_point("n")
    g.add_edge("n", END)
    app = g.compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t2"}}

    with pytest.raises(GraphPaused) as exc:
        async for _ in _stream_state(app, {"messages": [HumanMessage(content="x")]}, config=cfg):
            pass
    assert exc.value.request["kind"] == "confirm"
    assert exc.value.request["tool_name"] == "x"


class _NoMCP:
    async def get_tools(self, names):
        return []


class _FakeModel:
    """Minimal chat model: first call asks file_delete, second returns text."""

    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(content="", tool_calls=[{"name": "file_delete", "args": {"path": "/x"}, "id": "tc1"}])
        return AIMessage(content="all done")


@pytest.mark.skip(reason="needs guard from Task 9")
async def test_run_pauses_then_resume_completes(tmp_path, monkeypatch):
    from agent_md.execution.runner import AgentRunner
    from agent_md.db.database import Database
    from agent_md.workspace.path_context import PathContext
    from agent_md.config.models import AgentConfig

    db = Database(tmp_path / "t.db")
    await db.connect()
    pc = PathContext(workspace_root=tmp_path, agents_dir=tmp_path, db_path=tmp_path / "t.db",
                     mcp_config=tmp_path / "m.json", tools_dir=tmp_path, skills_dir=tmp_path)
    runner = AgentRunner(db, mcp_manager=_NoMCP(), path_context=pc, db_path=str(tmp_path / "t.db"))
    config = AgentConfig(name="del", model={"provider": "google", "name": "x"}, history="off",
                         confirm=["file_delete"])
    monkeypatch.setattr("agent_md.execution.runner.create_chat_model", lambda **kw: _FakeModel())

    ex = await db.create_execution("del", "manual")
    res = await runner.run(config, execution_id=ex)
    assert res["status"] == "waiting"
    pending = await db.get_pending_interrupt(ex)
    assert pending is not None and pending.payload_json

    res2 = await runner.resume(config, ex, {"approved": True})
    assert res2["status"] == "success"
    assert "all done" in res2["output"]
    await db.close()
