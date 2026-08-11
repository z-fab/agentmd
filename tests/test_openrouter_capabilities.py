"""OpenRouter capability checks: strict in validate, lenient at runtime load."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agent_md.main import app as cli_app
from agent_md.workspace.bootstrap import bootstrap
from agent_md.workspace.services import openrouter_load_warnings, validate_agent

_NO_TOOLS_MODEL = "aion-labs/aion-rp-llama-3.1-8b"
_UNKNOWN_MODEL = "totally-unknown-vendor/brand-new-model-xyz"


def _write_openrouter_agent(path: Path, model: str) -> None:
    path.write_text(
        f"---\nmodel:\n  provider: openrouter\n  name: {model}\n---\nYou are a test agent.\n",
        encoding="utf-8",
    )


def test_validate_tool_calling_false_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    agent = tmp_path / "no-tools.md"
    _write_openrouter_agent(agent, _NO_TOOLS_MODEL)

    result = validate_agent(agent)
    assert any("tool calling" in e for e in result.errors)
    assert not any("tool calling" in w for w in result.warnings)


def test_validate_cli_exits_nonzero_for_no_tool_calling(tmp_path, monkeypatch):
    from agent_md.config.settings import settings

    monkeypatch.setattr(settings, "agents_dir", "agents")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    agents = tmp_path / "agents"
    agents.mkdir()
    _write_openrouter_agent(agents / "no-tools.md", _NO_TOOLS_MODEL)

    runner = CliRunner()
    cli_result = runner.invoke(cli_app, ["validate", "no-tools", "-w", str(tmp_path)])
    assert cli_result.exit_code == 1, cli_result.output
    assert "tool calling" in cli_result.output


def test_validate_unknown_model_is_a_warning_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    agent = tmp_path / "new-model.md"
    _write_openrouter_agent(agent, _UNKNOWN_MODEL)

    result = validate_agent(agent)
    assert result.errors == []
    assert any("not in the bundled profile table" in w for w in result.warnings)


def test_runtime_load_warns_on_no_tool_calling_and_is_silent_for_unknown():
    notes = openrouter_load_warnings(_NO_TOOLS_MODEL)
    assert len(notes) == 1
    assert "tool calling" in notes[0]

    assert openrouter_load_warnings(_UNKNOWN_MODEL) == []


@pytest.mark.asyncio
async def test_bootstrap_logs_runtime_warning_for_no_tool_calling(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    agents = tmp_path / "agents"
    agents.mkdir()
    _write_openrouter_agent(agents / "no-tools.md", _NO_TOOLS_MODEL)

    with caplog.at_level(logging.WARNING):
        rt = await bootstrap(
            workspace=tmp_path,
            agents_dir=agents,
            db_path=tmp_path / "test.db",
            start_scheduler=False,
        )
        await rt.aclose()

    assert any("tool calling" in r.message for r in caplog.records if r.levelno >= logging.WARNING)
