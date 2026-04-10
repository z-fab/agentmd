"""Tests for execution limits and LimitExceeded."""

from agent_md.core.models import SettingsConfig


def test_settings_defaults():
    """New fields have sensible defaults."""
    s = SettingsConfig()
    assert s.max_tool_calls == 50
    assert s.max_execution_tokens == 500_000
    assert s.max_cost_usd is None
    assert s.loop_detection is True


def test_settings_override():
    """Fields can be overridden."""
    s = SettingsConfig(max_tool_calls=10, max_execution_tokens=100_000, max_cost_usd=0.25, loop_detection=False)
    assert s.max_tool_calls == 10
    assert s.max_execution_tokens == 100_000
    assert s.max_cost_usd == 0.25
    assert s.loop_detection is False


def test_settings_null_disables():
    """Explicit None disables a limit."""
    s = SettingsConfig(max_tool_calls=None, max_execution_tokens=None)
    assert s.max_tool_calls is None
    assert s.max_execution_tokens is None


from agent_md.core.runner import LimitExceeded


def test_limit_exceeded_str():
    e = LimitExceeded("max_tool_calls", "50 calls reached")
    assert str(e) == "max_tool_calls: 50 calls reached"
    assert e.reason == "max_tool_calls"
    assert e.detail == "50 calls reached"


def test_limit_exceeded_no_detail():
    e = LimitExceeded("max_execution_tokens")
    assert str(e) == "max_execution_tokens"
