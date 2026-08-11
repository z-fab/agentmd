"""API-key env resolution: api_key_env if given, else <PROVIDER>_API_KEY.

Every provider's own default already follows that pattern (GOOGLE_API_KEY,
OPENAI_API_KEY, ANTHROPIC_API_KEY, OPENROUTER_API_KEY), so there is no table
to maintain — the table always was the pattern written out by hand.
"""

from __future__ import annotations

import pytest

from agent_md.providers.keys import (
    DEFAULT_LOCAL_BASE_URL,
    SENTINEL_API_KEY,
    api_key_env_for,
    derive_key_env,
    is_loopback,
    resolve_api_key,
)


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        ("google", "GOOGLE_API_KEY"),
        ("openai", "OPENAI_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("openrouter", "OPENROUTER_API_KEY"),
        ("groq", "GROQ_API_KEY"),
        ("together-ai", "TOGETHER_AI_API_KEY"),
    ],
)
def test_derive_key_env(provider, expected):
    assert derive_key_env(provider) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://localhost:11434/v1", True),
        ("http://127.0.0.1:8000/v1", True),
        ("http://[::1]:8000/v1", True),
        ("http://127.0.0.2:8000/v1", True),
        ("http://[0:0:0:0:0:0:0:1]:8000/v1", True),
        ("http://localhost.:8000/v1", True),
        ("http://LOCALHOST:8000/v1", True),
        ("https://api.groq.com/openai/v1", False),
        ("http://0.0.0.0:8000/v1", False),
        ("localhost:8000", False),  # missing scheme — not a parseable URL host
        ("http://[::1", False),  # malformed — must not raise
        (None, False),
    ],
)
def test_is_loopback(url, expected):
    assert is_loopback(url) is expected


def test_explicit_api_key_env_wins():
    assert api_key_env_for("gemini", api_key_env="GOOGLE_API_KEY") == "GOOGLE_API_KEY"


def test_ollama_needs_no_key():
    assert api_key_env_for("ollama") is None


def test_loopback_needs_no_key():
    assert api_key_env_for("local", base_url="http://localhost:11434/v1") is None


def test_local_without_base_url_needs_no_key():
    """Factory defaults local to loopback; key resolution must agree when base_url is omitted."""
    assert api_key_env_for("local") is None


def test_remote_unknown_provider_needs_derived_key():
    assert api_key_env_for("groq", base_url="https://api.groq.com/openai/v1") == "GROQ_API_KEY"


def test_resolve_returns_key_from_env(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "sk-abc")
    assert resolve_api_key("groq", base_url="https://api.groq.com/openai/v1") == "sk-abc"


def test_resolve_returns_sentinel_for_loopback(monkeypatch):
    monkeypatch.delenv("LOCAL_API_KEY", raising=False)
    assert resolve_api_key("local", base_url="http://localhost:8000/v1") == SENTINEL_API_KEY


def test_resolve_returns_sentinel_for_local_without_base_url(monkeypatch):
    monkeypatch.delenv("LOCAL_API_KEY", raising=False)
    assert resolve_api_key("local") == SENTINEL_API_KEY


def test_factory_uses_shared_local_default():
    """The factory must import DEFAULT_LOCAL_BASE_URL, not restate the URL literal."""
    from pathlib import Path

    source = Path("agent_md/providers/factory.py").read_text(encoding="utf-8")
    assert "DEFAULT_LOCAL_BASE_URL" in source
    assert 'http://localhost:11434/v1' not in source
    assert DEFAULT_LOCAL_BASE_URL == "http://localhost:11434/v1"


def test_resolve_raises_when_key_missing(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ValueError) as exc:
        resolve_api_key("groq", base_url="https://api.groq.com/openai/v1")
    assert "GROQ_API_KEY" in str(exc.value)
