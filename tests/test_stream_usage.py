"""stream_usage must be explicit wherever a custom base_url is used.

langchain-openai disables it by default when base_url is set, which silently
zeroes usage_metadata and turns max_execution_tokens / max_cost_usd into
no-ops. See docs/superpowers/specs/2026-08-11-provider-families-openrouter-design.md.
"""

from __future__ import annotations

import types
from unittest.mock import patch

import agent_md.providers.factory as factory_mod


def _capture_openai(provider: str, base_url: str | None) -> dict:
    captured: dict = {}

    class Fake:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    mod = types.ModuleType("langchain_openai")
    mod.ChatOpenAI = Fake
    with patch.dict("sys.modules", {"langchain_openai": mod}):
        factory_mod.create_chat_model(
            provider,
            "some-model",
            {"temperature": 0.1, "max_tokens": 100},
            base_url=base_url,
        )
    return captured


def test_local_provider_enables_stream_usage():
    captured = _capture_openai("local", "http://localhost:11434/v1")
    assert captured.get("stream_usage") is True


def test_openai_with_custom_base_url_enables_stream_usage():
    captured = _capture_openai("openai", "https://proxy.example.com/v1")
    assert captured.get("stream_usage") is True


def test_openai_without_base_url_does_not_force_stream_usage():
    """Official endpoint already defaults it on; passing it is harmless but
    we leave LangChain's own default in charge to avoid fighting upstream."""
    captured = _capture_openai("openai", None)
    assert "stream_usage" not in captured
