"""OpenRouter adapter + the cost shim, exercised with a fake SDK client.

The guard test at the bottom asserts the upstream shape the shim compensates
for. When it fails, langchain-openrouter has been fixed: delete the shim.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import textwrap

import pytest

from agent_md.providers.openrouter import _CostCapturingClient, _cost_sink, _reset_cost_sink


class _FakeUsage:
    def __init__(self, cost):
        self.cost = cost


class _FakeChunk:
    def __init__(self, usage=None):
        self.usage = usage


class _FakeChat:
    def __init__(self, chunks, *, pause_before_yield=None, raise_after_first=False):
        self._chunks = chunks
        self._pause_before_yield = pause_before_yield
        self._raise_after_first = raise_after_first

    async def send_async(self, **kwargs):
        async def _gen():
            for i, chunk in enumerate(self._chunks):
                if self._pause_before_yield is not None and i == 0:
                    await self._pause_before_yield.wait()
                yield chunk
                if self._raise_after_first and i == 0:
                    raise RuntimeError("mid-stream failure")

        return _gen()


class _FakeInner:
    def __init__(self, chunks, **chat_kwargs):
        self.chat = _FakeChat(chunks, **chat_kwargs)


async def _drain_with_attach(client: _CostCapturingClient) -> list[float]:
    """Mimic CostTrackingChatOpenRouter._astream: per-stream sink + attach on usage."""
    sink: list[float] = []
    token = _cost_sink.set(sink)
    costs: list[float] = []
    try:
        stream = await client.chat.send_async()
        async for chunk in stream:
            if getattr(chunk, "usage", None) is not None and sink:
                costs.append(sink.pop(0))
    finally:
        _reset_cost_sink(token)
    return costs


async def test_cost_capturing_client_records_reported_cost():
    sink: list[float] = []
    token = _cost_sink.set(sink)
    try:
        client = _CostCapturingClient(_FakeInner([_FakeChunk(), _FakeChunk(_FakeUsage(0.0042))]))
        stream = await client.chat.send_async()
        seen = [chunk async for chunk in stream]
    finally:
        _reset_cost_sink(token)

    assert len(seen) == 2, "the proxy must pass every chunk through untouched"
    assert sink == [0.0042]


async def test_cost_capturing_client_ignores_chunks_without_usage():
    sink: list[float] = []
    token = _cost_sink.set(sink)
    try:
        client = _CostCapturingClient(_FakeInner([_FakeChunk(), _FakeChunk()]))
        stream = await client.chat.send_async()
        _ = [chunk async for chunk in stream]
    finally:
        _reset_cost_sink(token)
    assert sink == []


async def test_interleaved_streams_keep_their_own_costs():
    """Two concurrent streams on one client must not swap costs via a shared sink.

    Reproduces the reviewer's sequence: stream A captures 1.0 then pauses
    *before* attaching; stream B captures 2.0 and attaches. With a per-instance
    list + pop(0), B received A's 1.0 and A received B's 2.0.
    """
    a_captured = asyncio.Event()
    release_a = asyncio.Event()

    class _SharedInner:
        def __init__(self):
            self.chat = self

        async def send_async(self, *, cost: float):
            async def _gen():
                yield _FakeChunk(_FakeUsage(cost))

            return _gen()

    client = _CostCapturingClient(_SharedInner())

    async def run_stream(*, cost: float, is_a: bool) -> float:
        sink: list[float] = []
        token = _cost_sink.set(sink)
        try:
            stream = await client.chat.send_async(cost=cost)
            async for chunk in stream:
                # Capture already happened inside send_async. Pause here — the
                # same window as upstream's on_llm_new_token — before attach.
                if is_a:
                    a_captured.set()
                    await release_a.wait()
                if chunk.usage is not None:
                    assert sink, "cost must already be in this stream's sink"
                    return sink.pop(0)
            raise AssertionError("no usage chunk")
        finally:
            _reset_cost_sink(token)

    task_a = asyncio.create_task(run_stream(cost=1.0, is_a=True))
    await a_captured.wait()
    cost_b = await run_stream(cost=2.0, is_a=False)
    release_a.set()
    cost_a = await task_a

    assert cost_a == 1.0, f"A should keep 1.0, got {cost_a}"
    assert cost_b == 2.0, f"B should keep 2.0, got {cost_b}"


async def test_failed_stream_leaves_no_cost_for_the_next():
    """A mid-stream exception must not leave a captured cost for the next request.

    Reproduces: A captures 1.0 then raises before attach; B reports 2.0 but a
    shared sink still held 1.0, so B received the stale value.
    """
    client_a = _CostCapturingClient(_FakeInner([_FakeChunk(_FakeUsage(1.0))], raise_after_first=True))
    with pytest.raises(RuntimeError, match="mid-stream failure"):
        await _drain_with_attach(client_a)

    client_b = _CostCapturingClient(_FakeInner([_FakeChunk(_FakeUsage(2.0))]))
    costs_b = await _drain_with_attach(client_b)
    assert costs_b == [2.0]
    assert _cost_sink.get() is None


async def test_cross_task_drain_does_not_raise_on_reset():
    """Consuming an _astream across tasks must not crash on ContextVar.reset.

    Reproduces: task A takes the first chunk; task B drains the rest and hits
    ``ValueError: Token ... was created in a different Context`` in finally.
    Reset must tolerate that without dropping the per-stream isolation that
    ``set`` still provides on the next call.
    """

    async def _astream_like():
        sink: list[float] = []
        token = _cost_sink.set(sink)
        try:
            sink.append(1.0)
            yield 1
            sink.append(2.0)
            yield 2
        finally:
            _reset_cost_sink(token)

    stream = _astream_like()
    assert await stream.__anext__() == 1

    async def _drain_rest():
        return [item async for item in stream]

    rest = await asyncio.create_task(_drain_rest())
    assert rest == [2]

    # A fresh stream in this task still gets an isolated sink.
    sink2: list[float] = []
    token2 = _cost_sink.set(sink2)
    try:
        assert _cost_sink.get() is sink2
        assert sink2 == []
    finally:
        _reset_cost_sink(token2)


async def test_guard_upstream_still_drops_cost_on_the_terminal_chunk():
    """Fails when langchain-openrouter starts attaching cost on the usage-only chunk.

    Two signals, both required:

    1. AST walk — every ``AIMessageChunk`` constructed with ``usage_metadata``
       in ``_astream`` must not also pass ``response_metadata``. Formatting
       alone cannot trip this.
    2. Behavioural probe — drive upstream ``_astream`` with a fake SDK client
       over a terminal usage chunk that carries ``cost``, and assert the emitted
       message still has no ``response_metadata["cost"]``. An assignment *after*
       construction (the false-pass shape for the AST check) fails this probe.
    """
    from langchain_core.messages import HumanMessage
    from langchain_openrouter import ChatOpenRouter, chat_models

    source = textwrap.dedent(inspect.getsource(chat_models.ChatOpenRouter._astream))
    tree = ast.parse(source)

    usage_only_calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name != "AIMessageChunk":
            continue
        kwargs = {kw.arg for kw in node.keywords if kw.arg}
        if "usage_metadata" in kwargs:
            usage_only_calls.append(node)

    assert usage_only_calls, (
        "langchain-openrouter._astream no longer constructs an AIMessageChunk with "
        "usage_metadata — re-check the cost shim"
    )
    for call in usage_only_calls:
        kwargs = {kw.arg for kw in call.keywords if kw.arg}
        assert "response_metadata" not in kwargs, (
            "langchain-openrouter's terminal usage chunk now carries response_metadata — "
            "re-check whether the cost shim in agent_md/providers/openrouter.py is still needed"
        )

    convert_src = inspect.getsource(chat_models._convert_chunk_to_message_chunk)
    assert "response_metadata" in convert_src and "cost" in convert_src, (
        "choices-path cost assembly disappeared — the shim's premise may no longer hold"
    )

    class _UsageOnlyChunk:
        def model_dump(self, by_alias=True):
            return {
                "choices": [],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                    "cost": 0.0042,
                },
            }

    class _FakeSdkChat:
        async def send_async(self, **kwargs):
            async def _gen():
                yield _UsageOnlyChunk()

            return _gen()

    class _FakeSdkClient:
        def __init__(self):
            self.chat = _FakeSdkChat()

    model = ChatOpenRouter(model="probe", api_key="sk-test")
    model.client = _FakeSdkClient()

    seen_cost = None
    async for generation in model._astream([HumanMessage(content="hi")]):
        seen_cost = generation.message.response_metadata.get("cost")
        break
    else:
        raise AssertionError("upstream _astream yielded nothing")

    assert seen_cost is None, (
        "langchain-openrouter now surfaces cost on the usage-only chunk — "
        "re-check whether the cost shim in agent_md/providers/openrouter.py is still needed"
    )
