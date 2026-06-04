import pytest
from agent_md.config.models import AgentConfig


def _cfg(**kw):
    base = {"name": "a", "model": {"provider": "google", "name": "gemini-2.5-flash"}}
    base.update(kw)
    return AgentConfig(**base)


def test_confirm_defaults_empty():
    c = _cfg()
    assert c.confirm == []
    assert c.auto_approve == []
    assert c.on_pending == "skip"
    assert c.confirm_timeout is None


def test_confirm_lists_parsed():
    c = _cfg(confirm=["file_edit"], auto_approve=["file_write"])
    assert c.confirm == ["file_edit"]
    assert c.auto_approve == ["file_write"]


def test_auto_approve_wildcard():
    assert _cfg(auto_approve="*").auto_approve == "*"
    assert _cfg(auto_approve="all").auto_approve == "all"


def test_on_pending_validated():
    assert _cfg(on_pending="parallel").on_pending == "parallel"
    with pytest.raises(ValueError):
        _cfg(on_pending="queue")


def test_confirm_timeout_grammar():
    assert _cfg(confirm_timeout="2h").confirm_timeout == "2h"
    assert _cfg(confirm_timeout="none").confirm_timeout == "none"
    with pytest.raises(ValueError):
        _cfg(confirm_timeout="soon")


def test_confirm_single_string_coerced():
    assert _cfg(confirm="file_edit").confirm == ["file_edit"]


def test_auto_approve_single_string_coerced():
    assert _cfg(auto_approve="file_write").auto_approve == ["file_write"]


from agent_md.config.models import effective_confirm_tools


def test_effective_set_union_minus():
    c = _cfg(confirm=["file_edit"], auto_approve=["file_write"])
    s = effective_confirm_tools(c, defaults=["file_delete", "file_write"])
    assert s == {"file_delete", "file_edit"}


def test_effective_set_wildcard_clears():
    c = _cfg(auto_approve="*")
    assert effective_confirm_tools(c, defaults=["file_delete", "file_write"]) == set()


def test_effective_set_default_only():
    c = _cfg()
    assert effective_confirm_tools(c, defaults=["file_delete", "file_write"]) == {"file_delete", "file_write"}
