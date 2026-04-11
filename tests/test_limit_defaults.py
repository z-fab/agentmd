"""Tests for global limit defaults from config.yaml."""

from unittest.mock import patch


def test_config_yaml_max_tool_calls():
    """config.yaml defaults.max_tool_calls overrides hardcoded default."""
    from agent_md.core.models import SettingsConfig

    with patch("agent_md.core.models._get_global_limit_defaults", return_value={"max_tool_calls": 25}):
        s = SettingsConfig()
        assert s.max_tool_calls == 25


def test_config_yaml_max_execution_tokens():
    """config.yaml defaults.max_execution_tokens overrides hardcoded default."""
    from agent_md.core.models import SettingsConfig

    with patch("agent_md.core.models._get_global_limit_defaults", return_value={"max_execution_tokens": 200_000}):
        s = SettingsConfig()
        assert s.max_execution_tokens == 200_000


def test_config_yaml_loop_detection():
    """config.yaml defaults.loop_detection=false disables loop detection."""
    from agent_md.core.models import SettingsConfig

    with patch("agent_md.core.models._get_global_limit_defaults", return_value={"loop_detection": False}):
        s = SettingsConfig()
        assert s.loop_detection is False


def test_frontmatter_overrides_config_yaml():
    """Agent frontmatter values override config.yaml defaults."""
    from agent_md.core.models import SettingsConfig

    with patch("agent_md.core.models._get_global_limit_defaults", return_value={"max_tool_calls": 25}):
        s = SettingsConfig(max_tool_calls=100)
        assert s.max_tool_calls == 100


def test_no_config_yaml_uses_hardcoded():
    """When config.yaml has no limit defaults, hardcoded defaults apply."""
    from agent_md.core.models import SettingsConfig

    with patch("agent_md.core.models._get_global_limit_defaults", return_value={}):
        s = SettingsConfig()
        assert s.max_tool_calls == 50
        assert s.max_execution_tokens == 500_000
        assert s.max_cost_usd is None
        assert s.loop_detection is True
