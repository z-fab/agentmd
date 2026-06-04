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
