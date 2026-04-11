"""Tests for .env loading and new default paths."""

import os
from unittest.mock import patch

from agent_md.config.settings import get_state_dir


def test_state_dir_default():
    path = get_state_dir()
    assert path.name == "agentmd"
    assert ".local/state" in str(path) or "XDG_STATE_HOME" in os.environ


def test_state_dir_xdg_override():
    with patch.dict(os.environ, {"XDG_STATE_HOME": "/tmp/xdg-state"}):
        path = get_state_dir()
        assert str(path) == "/tmp/xdg-state/agentmd"
