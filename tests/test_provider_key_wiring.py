"""'Does this provider need a key?' must be asked, not restated.

It used to be answered in four places: two tuples in commands.py, one in
services.py, and the _PROVIDER_ENV_VARS dict. Adding a provider meant editing
all four.
"""

from __future__ import annotations

import agent_md.workspace.services as services
from agent_md.workspace.services import validate_agent


def test_provider_env_var_table_is_gone():
    assert not hasattr(services, "_PROVIDER_ENV_VARS"), (
        "_PROVIDER_ENV_VARS is a restatement of <PROVIDER>_API_KEY; use api_key_env_for()"
    )


def _write_agent(path, provider: str, base_url: str | None = None) -> None:
    lines = [
        "---",
        "model:",
        f"  provider: {provider}",
        "  name: test-model",
    ]
    if base_url is not None:
        lines.append(f"  base_url: {base_url}")
    lines.extend(["---", "system prompt"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_ollama_reports_key_not_required(tmp_path, monkeypatch):
    """Outcome guard: ollama never needs a credential, regardless of env."""
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    agent = tmp_path / "ollama-agent.md"
    _write_agent(agent, "ollama")
    result = validate_agent(agent)
    assert result.api_key_set is True


def test_loopback_local_reports_key_not_required(tmp_path, monkeypatch):
    monkeypatch.delenv("LOCAL_API_KEY", raising=False)
    agent = tmp_path / "local-agent.md"
    _write_agent(agent, "local", base_url="http://127.0.0.1:8000/v1")
    result = validate_agent(agent)
    assert result.api_key_set is True


def test_remote_provider_reports_missing_key(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    agent = tmp_path / "openai-agent.md"
    _write_agent(agent, "openai")
    result = validate_agent(agent)
    assert result.api_key_set is False


def test_openrouter_key_is_detected(monkeypatch, tmp_path):
    from agent_md.providers.keys import api_key_env_for

    assert api_key_env_for("openrouter") == "OPENROUTER_API_KEY"
