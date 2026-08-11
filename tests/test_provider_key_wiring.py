"""'Does this provider need a key?' must be asked, not restated.

It used to be answered in four places: two tuples in commands.py, one in
services.py, and the _PROVIDER_ENV_VARS dict. Adding a provider meant editing
all four.
"""

from __future__ import annotations

import agent_md.workspace.services as services


def test_provider_env_var_table_is_gone():
    assert not hasattr(services, "_PROVIDER_ENV_VARS"), (
        "_PROVIDER_ENV_VARS is a restatement of <PROVIDER>_API_KEY; use api_key_env_for()"
    )


def test_no_hardcoded_keyless_tuples_remain():
    from pathlib import Path

    for rel in ("agent_md/cli/commands.py", "agent_md/workspace/services.py"):
        source = Path(rel).read_text(encoding="utf-8")
        assert '("ollama", "local")' not in source, f"{rel} still hardcodes the keyless provider list"


def test_openrouter_key_is_detected(monkeypatch, tmp_path):
    from agent_md.providers.keys import api_key_env_for

    assert api_key_env_for("openrouter") == "OPENROUTER_API_KEY"
