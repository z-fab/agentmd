"""Importing Settings must not manufacture config.yaml before setup runs.

``load_yaml_config`` used to call ``_ensure_default_config()``, which wrote the
file on first Settings construction. The CLI singleton is built at import time,
so a blank HOME already had a config.yaml by the time ``agentmd setup`` checked
for one — and a brand-new user pressing Enter got "Setup complete" with no
workspace.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from agent_md.config.settings import Settings


def _subprocess_env(home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["XDG_STATE_HOME"] = str(home / "state")
    # Fresh process must not inherit a developer config from the parent env.
    env.pop("AGENTMD_WORKSPACE", None)
    return env


def test_import_does_not_create_config_yaml(tmp_path):
    """A blank HOME must stay free of config.yaml after importing agent_md."""
    home = tmp_path / "home"
    home.mkdir()
    config_yaml = home / ".config" / "agentmd" / "config.yaml"
    assert not config_yaml.exists()

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import agent_md; import agent_md.config.settings",  # noqa: E501
        ],
        env=_subprocess_env(home),
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not config_yaml.exists(), f"import wrote {config_yaml}; load_yaml_config must be read-only"


def test_settings_defaults_without_config_yaml(tmp_path, monkeypatch):
    """Absence of config.yaml still yields sane in-memory defaults."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("AGENTMD_WORKSPACE", raising=False)

    assert not (home / ".config" / "agentmd" / "config.yaml").exists()
    s = Settings()
    assert s.defaults_provider == "google"
    assert s.defaults_model == "gemini-2.5-flash"
    assert s.log_level == "INFO"
    assert not (home / ".config" / "agentmd" / "config.yaml").exists()


def test_setup_runs_wizard_on_blank_home(tmp_path):
    """``agentmd setup`` on a blank HOME must enter the wizard, not bail out."""
    home = tmp_path / "home"
    home.mkdir()
    repo = Path(__file__).resolve().parents[1]
    agentmd = repo / ".venv" / "bin" / "agentmd"
    assert agentmd.is_file(), f"expected editable install at {agentmd}"
    # Enough newlines to walk past early prompts with defaults; we only need
    # to prove the wizard started rather than exiting on a phantom config.
    result = subprocess.run(
        [str(agentmd), "setup"],
        input="\n" * 40,
        env=_subprocess_env(home),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    out = result.stdout + result.stderr
    assert "Existing configuration found" not in out, out
    assert "1/4" in out or "Workspace" in out, out
