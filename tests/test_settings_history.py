import pytest
from pydantic import ValidationError

from agent_md.core.models import AgentConfig


def test_history_off_string_works():
    cfg = AgentConfig(name="t", history="off")
    assert cfg.history == "off"


def test_history_false_normalized_to_off():
    cfg = AgentConfig(name="t", history=False)
    assert cfg.history == "off"


def test_history_true_raises_with_yaml_hint():
    with pytest.raises(ValidationError) as exc:
        AgentConfig(name="t", history=True)
    msg = str(exc.value)
    assert "yaml" in msg.lower() or "off" in msg.lower() or "quote" in msg.lower()


def test_history_invalid_string_rejected():
    with pytest.raises(ValidationError):
        AgentConfig(name="t", history="bogus")
