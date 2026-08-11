"""A scheduled agent whose key is missing must not be scheduled silently.

The whole point of resolving keys early is that an unattended 3 a.m. run
should not be the thing that discovers the credential was never set.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from agent_md.config.models import AgentConfig
from agent_md.providers.keys import resolve_api_key
from agent_md.workspace.scheduler import AgentScheduler


def _scheduled_config(
    provider: str,
    base_url: str | None = None,
    api_key_env: str | None = None,
) -> AgentConfig:
    model: dict = {"provider": provider, "name": "m"}
    if base_url is not None:
        model["base_url"] = base_url
    if api_key_env is not None:
        model["api_key_env"] = api_key_env
    return AgentConfig(
        id="nightly",
        model=model,
        trigger={"type": "schedule", "cron": "0 3 * * *"},
    )


def _make_scheduler() -> AgentScheduler:
    return AgentScheduler(
        registry=MagicMock(),
        runner=MagicMock(),
        path_context=MagicMock(),
    )


def _would_schedule(config: AgentConfig) -> bool:
    scheduler = _make_scheduler()
    scheduler.scheduler.add_job = MagicMock()
    status = scheduler.schedule_agent(config)
    called = scheduler.scheduler.add_job.called
    if status == "scheduled":
        assert called
    else:
        assert not called
    return called


def test_missing_key_blocks_scheduling(monkeypatch, caplog):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    config = _scheduled_config("groq", "https://api.groq.com/openai/v1")
    with caplog.at_level(logging.ERROR):
        assert not _would_schedule(config)
    assert "GROQ_API_KEY" in caplog.text
    assert "nightly" in caplog.text


def test_present_key_allows_scheduling(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "sk-x")
    assert _would_schedule(_scheduled_config("groq", "https://api.groq.com/openai/v1"))


def test_keyless_provider_still_schedules(monkeypatch):
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    assert _would_schedule(_scheduled_config("ollama"))


def test_loopback_still_schedules(monkeypatch):
    monkeypatch.delenv("LOCAL_API_KEY", raising=False)
    assert _would_schedule(_scheduled_config("local"))


def test_local_remote_base_url_requires_key(monkeypatch, caplog):
    monkeypatch.delenv("LOCAL_API_KEY", raising=False)
    config = _scheduled_config("local", "https://remote.example.com/v1")
    with caplog.at_level(logging.ERROR):
        assert not _would_schedule(config)
    assert "LOCAL_API_KEY" in caplog.text


def test_native_openai_missing_key_blocks(monkeypatch, caplog):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with caplog.at_level(logging.ERROR):
        assert not _would_schedule(_scheduled_config("openai"))
    assert "OPENAI_API_KEY" in caplog.text


def test_native_openai_present_key_allows(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    assert _would_schedule(_scheduled_config("openai"))


@pytest.mark.parametrize(
    ("provider", "base_url", "api_key_env", "env_var"),
    [
        # keyless adapter — api_key_env must not invent a requirement
        ("ollama", None, None, None),
        ("ollama", None, "CUSTOM_OLLAMA_KEY", None),
        # loopback local — default is keyless; explicit api_key_env is honoured
        ("local", None, None, None),
        ("local", None, "CUSTOM_LOCAL_KEY", "CUSTOM_LOCAL_KEY"),
        ("local", "http://127.0.0.1:8000/v1", None, None),
        ("local", "http://127.0.0.1:8000/v1", "CUSTOM_LOCAL_KEY", "CUSTOM_LOCAL_KEY"),
        # remote local / family B / native — default env and explicit override
        ("local", "https://remote.example.com/v1", None, "LOCAL_API_KEY"),
        ("local", "https://remote.example.com/v1", "MY_LOCAL_KEY", "MY_LOCAL_KEY"),
        ("groq", "https://api.groq.com/openai/v1", None, "GROQ_API_KEY"),
        ("groq", "https://api.groq.com/openai/v1", "MY_GROQ_KEY", "MY_GROQ_KEY"),
        ("openai", None, None, "OPENAI_API_KEY"),
        ("openai", None, "MY_OPENAI_KEY", "MY_OPENAI_KEY"),
        ("anthropic", None, None, "ANTHROPIC_API_KEY"),
        ("anthropic", None, "MY_ANTHROPIC_KEY", "MY_ANTHROPIC_KEY"),
        ("google", None, None, "GOOGLE_API_KEY"),
        ("google", None, "MY_GOOGLE_KEY", "MY_GOOGLE_KEY"),
        ("openai", "https://proxy.example.com/v1", "MY_PROXY_KEY", "MY_PROXY_KEY"),
    ],
)
def test_gate_agrees_with_resolve_api_key(monkeypatch, provider, base_url, api_key_env, env_var):
    """The schedule gate and create_chat_model's resolve_api_key must ask the same question.

    For every representative config: gate blocks iff resolve_api_key raises when
    the key is unset, and both allow when the key is set. Crosses api_key_env
    set/unset against keyless, loopback, family B, and native providers.
    """
    config = _scheduled_config(provider, base_url, api_key_env)
    model = config.model
    assert model is not None

    if env_var is None:
        if api_key_env:
            monkeypatch.delenv(api_key_env, raising=False)
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        monkeypatch.delenv("LOCAL_API_KEY", raising=False)
        assert _would_schedule(config)
        resolve_api_key(model.provider, model.base_url, model.api_key_env)
        return

    monkeypatch.delenv(env_var, raising=False)
    gate_blocks = not _would_schedule(config)
    resolve_raises = False
    try:
        resolve_api_key(model.provider, model.base_url, model.api_key_env)
    except ValueError:
        resolve_raises = True
    assert gate_blocks is True
    assert resolve_raises is True
    assert gate_blocks == resolve_raises

    monkeypatch.setenv(env_var, "sk-present")
    assert _would_schedule(config)
    resolve_api_key(model.provider, model.base_url, model.api_key_env)
