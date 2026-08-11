"""OpenRouter adapter + the cost shim, exercised with a fake SDK client.

The guard test at the bottom asserts the upstream shape the shim compensates
for. When it fails, langchain-openrouter has been fixed: delete the shim.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

from agent_md.providers.openrouter import _CostCapturingClient


class _FakeUsage:
    def __init__(self, cost):
        self.cost = cost


class _FakeChunk:
    def __init__(self, usage=None):
        self.usage = usage


class _FakeChat:
    def __init__(self, chunks):
        self._chunks = chunks

    async def send_async(self, **kwargs):
        async def _gen():
            for chunk in self._chunks:
                yield chunk

        return _gen()


class _FakeInner:
    def __init__(self, chunks):
        self.chat = _FakeChat(chunks)


async def test_cost_capturing_client_records_reported_cost():
    sink: list[float] = []
    client = _CostCapturingClient(_FakeInner([_FakeChunk(), _FakeChunk(_FakeUsage(0.0042))]), sink)

    stream = await client.chat.send_async()
    seen = [chunk async for chunk in stream]

    assert len(seen) == 2, "the proxy must pass every chunk through untouched"
    assert sink == [0.0042]


async def test_cost_capturing_client_ignores_chunks_without_usage():
    sink: list[float] = []
    client = _CostCapturingClient(_FakeInner([_FakeChunk(), _FakeChunk()]), sink)
    stream = await client.chat.send_async()
    _ = [chunk async for chunk in stream]
    assert sink == []


def test_guard_upstream_still_drops_cost_on_the_terminal_chunk():
    """Fails when langchain-openrouter starts attaching cost on the usage-only chunk.

    Robust to whitespace/formatting: walks the AST of ``_astream`` for
    ``AIMessageChunk`` constructors that carry ``usage_metadata`` (the
    terminal usage-only path) and asserts none of them also pass
    ``response_metadata``. Combined with a check that the choices path still
    writes ``cost`` into ``response_metadata``, that is exactly the split the
    shim compensates for.
    """
    from langchain_openrouter import chat_models

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
