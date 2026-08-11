"""OpenRouter adapter, plus a shim that rescues the reported cost.

langchain-openrouter 0.2.7 builds ``response_metadata["cost"]`` only in
``_convert_chunk_to_message_chunk``, which runs for chunks that carry
``choices``. OpenRouter reports usage on a terminal chunk with no choices,
built in ``_astream`` without any response_metadata — so in streaming, the
cost is assembled on one path and the data arrives on the other.

This shim wraps the SDK client to capture the raw cost, then attaches it as
the usage chunk goes past. It is debt with an expiry date.

TODO: upstream issue — langchain-openrouter drops streamed cost on the
usage-only chunk (choices path sets response_metadata["cost"]; terminal
usage chunk does not). Fill in the GitHub issue URL when filed.
``tests/test_openrouter_provider.py`` fails loudly once the fix lands, which
is the signal to delete this file's shim.
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel


class _CostCapturingChat:
    """Proxies the SDK's ``chat`` namespace, recording each reported cost."""

    def __init__(self, inner: Any, sink: list[float]) -> None:
        self._inner = inner
        self._sink = sink

    def send(self, **kwargs: Any) -> Any:
        return self._inner.send(**kwargs)

    async def send_async(self, **kwargs: Any) -> Any:
        stream = await self._inner.send_async(**kwargs)
        return self._record(stream)

    async def _record(self, stream: Any) -> Any:
        async for chunk in stream:
            usage = getattr(chunk, "usage", None)
            cost = getattr(usage, "cost", None) if usage is not None else None
            if cost is not None:
                self._sink.append(float(cost))
            yield chunk


class _CostCapturingClient:
    """Transparent proxy around the OpenRouter SDK client."""

    def __init__(self, inner: Any, sink: list[float]) -> None:
        self._inner = inner
        self.chat = _CostCapturingChat(inner.chat, sink)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def build_openrouter(model: str, settings: dict, api_key: str) -> BaseChatModel:
    """Build an OpenRouter chat model with usage and cost reporting intact."""
    try:
        from langchain_openrouter import ChatOpenRouter
    except ImportError:
        raise ImportError(
            "Provider 'openrouter' requires langchain-openrouter. "
            "Install with: pip install agentmd[openrouter]"
        )

    class CostTrackingChatOpenRouter(ChatOpenRouter):  # type: ignore[misc, valid-type]
        """Carries OpenRouter's reported cost onto the terminal usage chunk."""

        def _build_client(self) -> Any:
            self._reported_costs: list[float] = []
            return _CostCapturingClient(super()._build_client(), self._reported_costs)

        async def _astream(self, *args: Any, **kwargs: Any) -> Any:
            async for generation in super()._astream(*args, **kwargs):
                message = generation.message
                if message.usage_metadata and self._reported_costs:
                    message.response_metadata["cost"] = self._reported_costs.pop(0)
                yield generation

    kwargs: dict = {
        "model": model,
        "temperature": settings.get("temperature", 0.7),
        "max_tokens": settings.get("max_tokens", 4096),
        "api_key": api_key,
    }
    timeout = settings.get("timeout")
    if timeout is not None:
        kwargs["timeout"] = timeout
    return CostTrackingChatOpenRouter(**kwargs)
