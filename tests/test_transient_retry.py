"""The model node must survive transient transport drops (e.g. a flaky
preview endpoint that disconnects mid-request) by retrying, instead of letting
a single `httpx.RemoteProtocolError` fail the whole execution."""

import httpx
import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from agent_md.graph.agent import with_transient_retry


async def test_retries_on_transient_transport_error():
    calls = {"n": 0}

    async def flaky(_messages):
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
        return AIMessage(content="ok")

    model = with_transient_retry(RunnableLambda(flaky))
    out = await model.ainvoke([])

    assert out.content == "ok"
    assert calls["n"] == 3  # failed twice, succeeded on the third attempt


async def test_does_not_retry_on_non_transient_error():
    calls = {"n": 0}

    async def boom(_messages):
        calls["n"] += 1
        raise ValueError("bad request")

    model = with_transient_retry(RunnableLambda(boom))
    with pytest.raises(ValueError):
        await model.ainvoke([])

    assert calls["n"] == 1  # non-transport errors are not retried
