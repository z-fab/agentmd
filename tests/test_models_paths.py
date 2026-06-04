import pytest
from pydantic import ValidationError

from agent_md.config.models import AgentConfig, PathEntry


def _make(paths):
    return AgentConfig(name="test", paths=paths)


def test_paths_dict_with_string_shorthand():
    cfg = _make({"vault": "/Users/x/vault"})
    assert isinstance(cfg.paths["vault"], PathEntry)
    assert cfg.paths["vault"].path == "/Users/x/vault"
    assert cfg.paths["vault"].description is None


def test_paths_dict_with_full_form():
    cfg = _make({"vault": {"path": "/Users/x/vault", "description": "main"}})
    assert cfg.paths["vault"].description == "main"


def test_paths_legacy_list_format_raises():
    with pytest.raises(ValidationError) as exc:
        _make(["/Users/x/vault", "/Users/x/inbox"])
    msg = str(exc.value)
    assert "dict" in msg.lower() or "mapping" in msg.lower()


def test_paths_alias_must_be_lowercase_identifier():
    with pytest.raises(ValidationError):
        _make({"Vault": "/Users/x/vault"})
    with pytest.raises(ValidationError):
        _make({"1bad": "/Users/x/vault"})


def test_paths_reserved_alias_rejected():
    with pytest.raises(ValidationError) as exc:
        _make({"workspace": "/Users/x/vault"})
    assert "reserved" in str(exc.value).lower()


def test_paths_default_is_empty_dict():
    cfg = AgentConfig(name="test")
    assert cfg.paths == {}


# ---------------------------------------------------------------------------
# Agent name validation
# ---------------------------------------------------------------------------


def test_name_with_space_accepted():
    cfg = AgentConfig(name="Daily Processor")
    assert cfg.name == "Daily Processor"


def test_name_with_accented_letters_accepted():
    cfg = AgentConfig(name="Diário")
    assert cfg.name == "Diário"


def test_name_leading_space_rejected():
    with pytest.raises(ValidationError) as exc:
        AgentConfig(name=" x")
    assert "leading" in str(exc.value).lower() or "trailing" in str(exc.value).lower() or "strip" in str(exc.value).lower()


def test_name_trailing_space_rejected():
    with pytest.raises(ValidationError) as exc:
        AgentConfig(name="x ")
    assert "leading" in str(exc.value).lower() or "trailing" in str(exc.value).lower() or "strip" in str(exc.value).lower()


def test_name_with_slash_rejected():
    with pytest.raises(ValidationError):
        AgentConfig(name="a/b")


def test_name_with_backslash_rejected():
    with pytest.raises(ValidationError):
        AgentConfig(name="a\\b")


def test_name_empty_rejected():
    with pytest.raises(ValidationError):
        AgentConfig(name="")
