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


async def test_run_pauses_then_resume_completes(tmp_path, monkeypatch):
    from agent_md.execution.runner import AgentRunner
    from agent_md.db.database import Database
    from agent_md.workspace.path_context import PathContext
    from agent_md.config.models import AgentConfig

    db = Database(tmp_path / "t.db")
    await db.connect()
    pc = PathContext(
        workspace_root=tmp_path,
        agents_dir=tmp_path,
        db_path=tmp_path / "t.db",
        mcp_config=tmp_path / "m.json",
        tools_dir=tmp_path,
        skills_dir=tmp_path,
    )
    runner = AgentRunner(db, mcp_manager=_NoMCP(), path_context=pc, db_path=str(tmp_path / "t.db"))
    config = AgentConfig(name="del", model={"provider": "google", "name": "x"}, history="off", confirm=["file_delete"])
    fake_model = _FakeModel()
    monkeypatch.setattr("agent_md.execution.runner.create_chat_model", lambda **kw: fake_model)

    ex = await db.create_execution("del", "manual")
    res = await runner.run(config, execution_id=ex)
    assert res["status"] == "waiting"
    pending = await db.get_pending_interrupt(ex)
    assert pending is not None and pending.payload_json

    res2 = await runner.resume(config, ex, {"approved": True})
    assert res2["status"] == "success"
    assert "all done" in res2["output"]
    await db.close()


async def test_resume_twice_second_is_skipped(tmp_path, monkeypatch):
    from agent_md.execution.runner import AgentRunner
    from agent_md.db.database import Database
    from agent_md.workspace.path_context import PathContext
    from agent_md.config.models import AgentConfig

    db = Database(tmp_path / "t.db")
    await db.connect()
    pc = PathContext(
        workspace_root=tmp_path,
        agents_dir=tmp_path,
        db_path=tmp_path / "t.db",
        mcp_config=tmp_path / "m.json",
        tools_dir=tmp_path,
        skills_dir=tmp_path,
    )
    runner = AgentRunner(db, mcp_manager=_NoMCP(), path_context=pc, db_path=str(tmp_path / "t.db"))
    fake_model = _FakeModel()
    config = AgentConfig(name="del", model={"provider": "google", "name": "x"}, history="off", confirm=["file_delete"])
    monkeypatch.setattr("agent_md.execution.runner.create_chat_model", lambda **kw: fake_model)

    ex = await db.create_execution("del", "manual")
    assert (await runner.run(config, execution_id=ex))["status"] == "waiting"
    first = await runner.resume(config, ex, {"approved": True})
    assert first["status"] == "success"
    # Execution is no longer waiting; a second resume must be skipped (not re-run).
    second = await runner.resume(config, ex, {"approved": True})
    assert second["status"] == "skipped"
    await db.close()


async def test_confirm_timeout_denies(tmp_path, monkeypatch):
    from agent_md.execution.runner import AgentRunner
    from agent_md.db.database import Database
    from agent_md.workspace.path_context import PathContext
    from agent_md.config.models import AgentConfig

    db = Database(tmp_path / "t.db")
    await db.connect()
    pc = PathContext(
        workspace_root=tmp_path,
        agents_dir=tmp_path,
        db_path=tmp_path / "t.db",
        mcp_config=tmp_path / "m.json",
        tools_dir=tmp_path,
        skills_dir=tmp_path,
    )
    runner = AgentRunner(db, mcp_manager=_NoMCP(), path_context=pc, db_path=str(tmp_path / "t.db"))
    config = AgentConfig(
        name="del",
        model={"provider": "google", "name": "x"},
        history="off",
        confirm=["file_delete"],
        confirm_timeout="1s",
    )
    fake_model = _FakeModel()
    monkeypatch.setattr("agent_md.execution.runner.create_chat_model", lambda **kw: fake_model)

    ex = await db.create_execution("del", "manual")
    res = await runner.run(config, execution_id=ex)
    assert res["status"] == "waiting"

    import asyncio

    await asyncio.sleep(1.5)  # let the deny-on-timeout fire and resume
    e = await db.get_execution(ex)
    assert e.status == "success"  # denied tool returns message, agent finishes
    await db.close()


class _LoopModel:
    """Pauses on the first turn, then floods unguarded tool calls on resume.

    Call 1 -> a single guarded ``file_delete`` so ``run()`` pauses (status
    "waiting"). After resume, every call returns one AI message carrying THREE
    unguarded ``file_read`` tool calls. Those three calls are counted off the AI
    message (before any tool executes), so within a single resume drive
    ``tool_call_count`` jumps to 3 and trips ``_check_limits`` with
    ``max_tool_calls=2`` -- proving limits are enforced from inside resume().
    """

    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(content="", tool_calls=[{"name": "file_delete", "args": {"path": "/x"}, "id": "d1"}])
        return AIMessage(
            content="",
            tool_calls=[
                {"name": "file_read", "args": {"path": "/x"}, "id": "r1"},
                {"name": "file_read", "args": {"path": "/y"}, "id": "r2"},
                {"name": "file_read", "args": {"path": "/z"}, "id": "r3"},
            ],
        )


async def test_resume_enforces_limits(tmp_path, monkeypatch):
    from agent_md.execution.runner import AgentRunner
    from agent_md.db.database import Database
    from agent_md.workspace.path_context import PathContext
    from agent_md.config.models import AgentConfig

    db = Database(tmp_path / "t.db")
    await db.connect()
    pc = PathContext(
        workspace_root=tmp_path,
        agents_dir=tmp_path,
        db_path=tmp_path / "t.db",
        mcp_config=tmp_path / "m.json",
        tools_dir=tmp_path,
        skills_dir=tmp_path,
    )
    runner = AgentRunner(db, mcp_manager=_NoMCP(), path_context=pc, db_path=str(tmp_path / "t.db"))
    model = _LoopModel()
    config = AgentConfig(
        name="loopy",
        model={"provider": "google", "name": "x"},
        history="off",
        confirm=["file_delete"],
    )
    config.settings.max_tool_calls = 2
    monkeypatch.setattr("agent_md.execution.runner.create_chat_model", lambda **kw: model)

    ex = await db.create_execution("loopy", "manual")
    # Initial run pauses on the first guarded file_delete.
    assert (await runner.run(config, execution_id=ex))["status"] == "waiting"

    # Approve the delete. On resume the model emits 3 unguarded tool calls in one
    # message; tool_call_count (3) exceeds max_tool_calls (2), so _check_limits
    # inside resume()'s _drive loop must abort the execution.
    res = await runner.resume(config, ex, {"approved": True})

    assert res["status"] == "aborted"
    e = await db.get_execution(ex)
    assert e.status == "aborted"
    assert "max_tool_calls" in (e.error or "")
    await db.close()


class _SeedSpyModel:
    """Records every messages list passed to ainvoke; returns a plain AIMessage each time."""

    def __init__(self):
        self.seen = []  # list of message-lists, one per ainvoke call
        self.n = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.seen.append(list(messages))
        self.n += 1
        return AIMessage(content=f"answer {self.n}")


def _text(msg) -> str:
    """Return message content as a plain string regardless of content type."""
    content = getattr(msg, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(str(part.get("text", part)))
        return " ".join(parts)
    return str(content)


async def test_history_seed_injects_prior_run(tmp_path, monkeypatch):
    """End-to-end: run 1 completes, run 2 receives run-1 messages as seed."""
    from agent_md.execution.runner import AgentRunner
    from agent_md.db.database import Database
    from agent_md.workspace.path_context import PathContext
    from agent_md.config.models import AgentConfig

    db = Database(tmp_path / "seed.db")
    await db.connect()
    pc = PathContext(
        workspace_root=tmp_path,
        agents_dir=tmp_path,
        db_path=tmp_path / "seed.db",
        mcp_config=tmp_path / "m.json",
        tools_dir=tmp_path,
        skills_dir=tmp_path,
    )
    runner = AgentRunner(db, mcp_manager=_NoMCP(), path_context=pc, db_path=str(tmp_path / "seed.db"))
    # history="low" enables seeding (history != "off")
    config = AgentConfig(name="seeder", model={"provider": "google", "name": "x"}, history="low")

    spy = _SeedSpyModel()
    monkeypatch.setattr("agent_md.execution.runner.create_chat_model", lambda **kw: spy)

    try:
        # Run 1: model returns "answer 1" immediately — no tool calls, status success
        ex1 = await db.create_execution("seeder", "manual")
        res1 = await runner.run(config, execution_id=ex1)
        assert res1["status"] == "success", f"Run 1 expected success, got: {res1}"

        # Run 2: should be seeded with run-1's checkpoint messages
        ex2 = await db.create_execution("seeder", "manual")
        res2 = await runner.run(config, execution_id=ex2)
        assert res2["status"] == "success", f"Run 2 expected success, got: {res2}"
    finally:
        await runner.aclose()
        await db.close()

    # spy.seen[0] = run 1's single ainvoke
    # spy.seen[1] = run 2's single ainvoke (first and only call of that run)
    assert len(spy.seen) >= 2, f"Expected at least 2 ainvoke calls; got {len(spy.seen)}"

    run1_msgs = spy.seen[0]
    run2_msgs = spy.seen[1]

    # Run 2 must have received MORE messages than run 1, because it was seeded
    # with run 1's conversation (human + AI messages from the checkpoint).
    assert len(run2_msgs) > len(run1_msgs), (
        f"Run 2 should receive more messages than run 1 (seeding); "
        f"run1={len(run1_msgs)} msgs, run2={len(run2_msgs)} msgs"
    )

    # The run-1 AI answer ("answer 1") must be present in the seeded messages
    # passed to the spy on run 2's first ainvoke.
    run2_texts = [_text(m) for m in run2_msgs]
    assert any("answer 1" in t for t in run2_texts), (
        f"'answer 1' (run-1 AI response) not found in run-2 seeded messages. Run-2 message contents: {run2_texts}"
    )
