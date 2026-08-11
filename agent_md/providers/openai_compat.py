"""Family B — one code path for every OpenAI-compatible endpoint.

There is deliberately no table of known endpoints. A table is maintenance, and
avoiding per-provider maintenance is the whole point: Groq, Together, DeepSeek,
xAI, Fireworks, vLLM and LM Studio all work from config alone.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel


def build_openai_compatible(
    model: str,
    settings: dict,
    base_url: str,
    api_key: str,
    stream_usage: bool = True,
) -> BaseChatModel:
    """Build a ChatOpenAI pointed at an OpenAI-compatible endpoint."""
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        raise ImportError(
            "OpenAI-compatible providers require langchain-openai. Install with: pip install agentmd[openai]"
        )

    kwargs: dict = {
        "model": model,
        "temperature": settings.get("temperature", 0.7),
        "max_tokens": settings.get("max_tokens", 4096),
        "base_url": base_url,
        "api_key": api_key,
        # Never leave this to LangChain's default: it turns stream_usage off
        # whenever base_url is set, which empties usage_metadata and disarms
        # max_execution_tokens and max_cost_usd.
        "stream_usage": stream_usage,
    }
    timeout = settings.get("timeout")
    if timeout is not None:
        kwargs["timeout"] = timeout
    return ChatOpenAI(**kwargs)
