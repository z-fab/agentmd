"""Family A = native adapters. Family B = one config-driven OpenAI-compatible path.

A known name routes to its designated family — `local` is a known name that
belongs to family B, so "known" does not imply "native".
"""

from __future__ import annotations

import types
from unittest.mock import patch

import pytest

import agent_md.providers.factory as factory_mod
from agent_md.config.models import ModelConfig


def _capture(provider, base_url, monkeypatch, **extra):
    captured: dict = {}

    class Fake:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    mod = types.ModuleType("langchain_openai")
    mod.ChatOpenAI = Fake
    monkeypatch.setenv("GROQ_API_KEY", "sk-groq")
    with patch.dict("sys.modules", {"langchain_openai": mod}):
        factory_mod.create_chat_model(
            provider,
            "some-model",
            {"temperature": 0.2, "max_tokens": 64},
            base_url=base_url,
            **extra,
        )
    return captured


def test_unknown_provider_with_base_url_builds_openai_compatible(monkeypatch):
    captured = _capture("groq", "https://api.groq.com/openai/v1", monkeypatch)
    assert captured["base_url"] == "https://api.groq.com/openai/v1"
    assert captured["api_key"] == "sk-groq"
    assert captured["stream_usage"] is True
    assert captured["model"] == "some-model"


def test_unknown_provider_without_base_url_is_rejected():
    with pytest.raises(ValueError) as exc:
        ModelConfig(provider="opeai", name="gpt-4o")
    assert "opeai" in str(exc.value)


def test_known_typo_protection_survives():
    """A misspelled native provider with no base_url is still a config error."""
    with pytest.raises(ValueError):
        ModelConfig(provider="anthropci", name="claude-sonnet-4")


def test_unknown_provider_with_base_url_is_accepted():
    cfg = ModelConfig(provider="groq", name="llama-3.3-70b", base_url="https://api.groq.com/openai/v1")
    assert cfg.provider == "groq"


def test_v1_appended_for_family_b():
    cfg = ModelConfig(provider="groq", name="m", base_url="https://api.groq.com/openai")
    assert cfg.base_url == "https://api.groq.com/openai/v1"


def test_v1_not_doubled():
    cfg = ModelConfig(provider="groq", name="m", base_url="https://api.groq.com/openai/v1")
    assert cfg.base_url == "https://api.groq.com/openai/v1"


def test_api_key_env_override_is_used(monkeypatch):
    monkeypatch.setenv("MY_CUSTOM_KEY", "sk-custom")
    captured = _capture(
        "gemini-proxy",
        "https://proxy.example.com/v1",
        monkeypatch,
        api_key_env="MY_CUSTOM_KEY",
    )
    assert captured["api_key"] == "sk-custom"


def test_stream_usage_can_be_disabled(monkeypatch):
    captured = _capture(
        "oldendpoint",
        "https://old.example.com/v1",
        monkeypatch,
        api_key_env="GROQ_API_KEY",
        stream_usage=False,
    )
    assert captured["stream_usage"] is False


def test_model_config_defaults():
    cfg = ModelConfig(provider="openai", name="gpt-4o")
    assert cfg.api_key_env is None
    assert cfg.stream_usage is True
