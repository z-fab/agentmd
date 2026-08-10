"""A typo in the frontmatter must be visible, at parse time and in `validate`.

`triger:` used to be dropped in silence and the agent ran as `manual` with
nobody the wiser. Unknown keys warn — they never fail the parse, so a file
written for a newer agentmd still loads on an older one.
"""

from __future__ import annotations

import logging

import pytest
from typer.testing import CliRunner

from agent_md.config.models import collect_unknown_keys, format_unknown_key_warning
from agent_md.main import app as cli_app
from agent_md.workspace.parser import parse_agent_file
from agent_md.workspace.services import validate_agent

# ollama needs no API key, so `validate` grades the frontmatter and nothing else.
MODEL_BLOCK = "model:\n  provider: ollama\n  name: llama3\n"


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A workspace whose agents_dir is 'agents', regardless of local config.yaml."""
    from agent_md.config.settings import settings

    monkeypatch.setattr(settings, "agents_dir", "agents")
    (tmp_path / "agents").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _write_agent(root, frontmatter: str, stem: str = "typo-agent"):
    agents_dir = root / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    path = agents_dir / f"{stem}.md"
    path.write_text(f"---\n{MODEL_BLOCK}{frontmatter}---\nDo the thing.\n", encoding="utf-8")
    return path


# --- collection ---------------------------------------------------------------


def test_top_level_typo_is_collected():
    assert collect_unknown_keys({"triger": {"type": "schedule"}}) == ["triger"]


def test_known_keys_are_not_flagged():
    data = {
        "name": "a",
        "trigger": {"type": "schedule", "every": "1h"},
        "settings": {"temperature": 0.1},
        "model": {"provider": "google", "name": "gemini-2.5-flash"},
        "paths": {"notes": "/tmp/notes", "docs": {"path": "/tmp/docs"}},
    }
    assert collect_unknown_keys(data) == []


def test_tools_alias_is_not_flagged():
    assert collect_unknown_keys({"tools": ["my_tool"]}) == []


def test_nested_typo_is_dotted():
    assert collect_unknown_keys({"trigger": {"typ": "watch"}}) == ["trigger.typ"]


def test_computed_fields_are_not_frontmatter():
    assert collect_unknown_keys({"config_hash": "abc"}) == ["config_hash"]


def test_warning_suggests_the_intended_key():
    assert "did you mean 'trigger'?" in format_unknown_key_warning("triger")
    assert "did you mean 'trigger.type'?" in format_unknown_key_warning("trigger.typ")


def test_warning_without_a_close_match():
    message = format_unknown_key_warning("zzzzzz")
    assert "zzzzzz" in message
    assert "did you mean" not in message


# --- parse --------------------------------------------------------------------


def test_parse_records_and_logs_unknown_key(tmp_path, caplog):
    path = _write_agent(tmp_path, "triger:\n  type: schedule\n  every: 1h\n")

    with caplog.at_level(logging.WARNING, logger="agent_md.workspace.parser"):
        config = parse_agent_file(path)

    assert config.unknown_keys == ["triger"]
    assert "triger" in caplog.text
    # The typo is still ignored — the agent runs as manual, but visibly so.
    assert config.trigger.type == "manual"


def test_parse_stays_quiet_for_a_clean_file(tmp_path, caplog):
    path = _write_agent(tmp_path, "trigger:\n  type: schedule\n  every: 1h\n")

    with caplog.at_level(logging.WARNING, logger="agent_md.workspace.parser"):
        config = parse_agent_file(path)

    assert config.unknown_keys == []
    assert caplog.text == ""


def test_computed_key_in_frontmatter_does_not_crash(tmp_path):
    """Reported as unknown and dropped, rather than colliding with the kwarg."""
    path = _write_agent(tmp_path, "config_hash: forged\n")
    config = parse_agent_file(path)
    assert config.unknown_keys == ["config_hash"]
    assert config.config_hash != "forged"


# --- validate -----------------------------------------------------------------


def test_validate_warns_about_unknown_key(workspace):
    _write_agent(workspace, "triger:\n  type: schedule\n  every: 1h\n")

    result = validate_agent("typo-agent", workspace=workspace)

    assert any("triger" in w for w in result.warnings)


def test_validate_command_surfaces_the_typo(workspace):
    _write_agent(workspace, "triger:\n  type: schedule\n  every: 1h\n")

    result = CliRunner().invoke(cli_app, ["validate", "typo-agent", "-w", str(workspace)])

    assert result.exit_code == 0, result.output
    output = " ".join(result.output.split())
    assert "unknown frontmatter key 'triger'" in output
    assert "1 warning" in output


def test_unknown_key_does_not_invalidate_the_trigger(workspace):
    """A stray `cron:` at the top level must not read as a broken cron trigger."""
    _write_agent(workspace, "cron: '0 9 * * *'\n")

    result = CliRunner().invoke(cli_app, ["validate", "typo-agent", "-w", str(workspace)])

    assert result.exit_code == 0, result.output
    assert "✗" not in result.output


@pytest.mark.parametrize("key", ["triger", "modle", "setings"])
def test_common_typos_are_all_reported(tmp_path, key):
    path = _write_agent(tmp_path, f"{key}: value\n", stem=f"agent-{key}")
    assert parse_agent_file(path).unknown_keys == [key]
