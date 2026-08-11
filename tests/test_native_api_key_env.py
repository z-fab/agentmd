"""Native adapters must honour api_key_env — never let LangChain pick the wrong key.

Without an explicit api_key=, ChatOpenAI reads OPENAI_API_KEY from the
environment on its own. A user who set api_key_env to a proxy credential then
sends their real OpenAI key to that third party.
"""

from __future__ import annotations

import types
from unittest.mock import patch

import agent_md.providers.factory as factory_mod


def test_openai_api_key_env_overrides_openai_api_key(monkeypatch):
    """Reproduction: proxy key must win over OPENAI_API_KEY."""
    monkeypatch.setenv("OPENAI_API_KEY", "chave-da-openai")
    monkeypatch.setenv("MY_PROXY_KEY", "chave-do-proxy")

    captured: dict = {}

    class Fake:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    mod = types.ModuleType("langchain_openai")
    mod.ChatOpenAI = Fake
    with patch.dict("sys.modules", {"langchain_openai": mod}):
        factory_mod.create_chat_model(
            "openai",
            "gpt-4o",
            {"temperature": 0.1, "max_tokens": 100},
            base_url="https://proxy.terceiro.example/v1",
            api_key_env="MY_PROXY_KEY",
        )

    assert captured["api_key"] == "chave-do-proxy"
    assert captured["api_key"] != "chave-da-openai"
