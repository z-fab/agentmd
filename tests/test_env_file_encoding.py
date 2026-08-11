"""Config files must be written and read as UTF-8, on every platform.

The bug these guard against: the setup wizard wrote ``.env`` with
``write_text()`` and no encoding, which resolves to the platform's locale
encoding — cp1252 on a Windows console. python-dotenv reads .env as UTF-8.
So ``agentmd setup`` produced a file agentmd then refused to read, and because
``agent_md.config.settings`` runs the load at import time, *every* command
crashed with ``UnicodeDecodeError: 'utf-8' codec can't decode byte 0x97``.

The em dash in the header comment was the only non-ASCII byte involved, and
0x97 is exactly what it becomes in cp1252.

These tests pass on macOS and Linux for the wrong reason if written naively —
there the locale encoding *is* UTF-8, so the implicit and explicit paths agree.
Two techniques keep them discriminating anywhere:

* the writer tests run under ``PYTHONWARNDEFAULTENCODING`` (PEP 597), which
  makes Python report every implicit-encoding file open regardless of platform;
* the reader tests write the offending bytes literally, so no Windows locale is
  needed to reproduce what a Windows locale produced.
"""

from __future__ import annotations

import locale
import logging
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# What ``"# Agentmd — API Keys"`` becomes when written on a cp1252 console.
CP1252_EM_DASH = b"\x97"


def _run_under_encoding_warnings(body: str, home: Path) -> subprocess.CompletedProcess:
    """Run ``body`` in a subprocess where implicit-encoding opens are errors.

    ``EncodingWarning`` is only emitted when the interpreter flag is on, so this
    cannot be done with ``warnings.catch_warnings()`` in-process. HOME and
    USERPROFILE are redirected so the setup writers cannot touch the real
    ``~/.config/agentmd``.
    """
    env = {
        **os.environ,
        "PYTHONWARNDEFAULTENCODING": "1",
        "HOME": str(home),
        "USERPROFILE": str(home),
    }
    return subprocess.run(
        [sys.executable, "-W", "error::EncodingWarning", "-c", textwrap.dedent(body)],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )


def test_setup_writers_never_rely_on_the_locale_encoding(tmp_path):
    """Every file the wizard writes must name its encoding.

    Without this, the bytes on disk depend on the machine that ran setup, and a
    Windows install writes a .env that agentmd itself cannot parse.
    """
    home = tmp_path / "home"
    home.mkdir()
    workspace = tmp_path / "ws"

    result = _run_under_encoding_warnings(
        f"""
        from pathlib import Path
        from agent_md.cli.setup import (
            _build_env_content,
            _create_workspace,
            _write_config_yaml,
            _write_env_file,
        )

        workspace = Path({str(workspace)!r})
        _create_workspace(workspace, "google", "gemini-2.5-flash")
        _write_config_yaml(workspace, "google", "gemini-2.5-flash")
        _write_env_file(workspace, "sk-test-key", "OPENAI_API_KEY")
        print("WROTE OK")
        """,
        home,
    )

    assert "EncodingWarning" not in result.stderr, (
        "a setup writer opened a file without an explicit encoding:\n" + result.stderr
    )
    assert result.returncode == 0, result.stderr
    assert "WROTE OK" in result.stdout


def test_settings_import_never_relies_on_the_locale_encoding(tmp_path):
    """Importing settings reads config.yaml and .env — both must name UTF-8."""
    home = tmp_path / "home"
    (home / ".config" / "agentmd").mkdir(parents=True)
    (home / ".config" / "agentmd" / ".env").write_text("OPENAI_API_KEY=k\n", encoding="utf-8")

    result = _run_under_encoding_warnings(
        """
        import agent_md.config.settings as s
        s.Settings()
        print("IMPORT OK")
        """,
        home,
    )

    assert "EncodingWarning" not in result.stderr, (
        "settings opened a config file without an explicit encoding:\n" + result.stderr
    )
    assert result.returncode == 0, result.stderr
    assert "IMPORT OK" in result.stdout


def test_env_header_is_ascii():
    """The wizard's own bytes stay ASCII.

    The user is told to hand-edit this file to paste keys. An editor that saves
    in the Windows ANSI codepage re-creates the original crash, and a decorative
    em dash in a credentials file is not worth that.
    """
    from agent_md.cli.setup import _build_env_content

    for content in (_build_env_content(None, None), _build_env_content("sk-x", "OPENAI_API_KEY")):
        content.encode("ascii")  # raises UnicodeEncodeError if it regresses


def test_written_env_round_trips_through_the_real_loader(tmp_path, monkeypatch):
    """What setup writes, python-dotenv must be able to read back."""
    from dotenv import dotenv_values

    from agent_md.cli.setup import _write_env_file

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

    ws_env, global_env = _write_env_file(tmp_path / "ws", "sk-secret", "OPENAI_API_KEY")

    for path in (ws_env, global_env):
        path.read_bytes().decode("utf-8")  # the loader's own codec
        assert dotenv_values(str(path))["OPENAI_API_KEY"] == "sk-secret"


def test_legacy_cp1252_env_still_loads(tmp_path, monkeypatch, caplog):
    """An install already broken by the old wizard must recover on upgrade.

    Fixing only the writer leaves those machines crashing forever: the bad file
    is already on disk, and nothing rewrites it. The loader has to cope.
    """
    from agent_md.config.settings import _load_env_file

    env = tmp_path / ".env"
    env.write_bytes("# Agentmd — API Keys\nOPENAI_API_KEY=sk-legacy\n".encode("cp1252"))
    assert CP1252_EM_DASH in env.read_bytes()  # the exact byte from the report

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(locale, "getencoding", lambda: "cp1252")

    with caplog.at_level(logging.WARNING):
        _load_env_file(str(env), override=True)  # must not raise

    assert os.environ["OPENAI_API_KEY"] == "sk-legacy"
    assert "UTF-8" in caplog.text


def test_undecodable_env_warns_instead_of_killing_every_command(tmp_path, monkeypatch, caplog):
    """A .env we cannot read at all must not take the whole CLI down with it.

    This module is imported by every command, so an exception here is not a
    failed load — it is an unusable install with a traceback for a help message.
    """
    from agent_md.config.settings import _load_env_file

    env = tmp_path / ".env"
    env.write_bytes(b"OPENAI_API_KEY=\xff\xfe\x00\x00\x81\x8d\n")

    monkeypatch.setattr(locale, "getencoding", lambda: "utf-8")

    with caplog.at_level(logging.WARNING):
        _load_env_file(str(env), override=True)  # must not raise

    assert str(env) in caplog.text


def _import_settings_with_home(home: Path, locale_encoding: str) -> subprocess.CompletedProcess:
    """Import settings for real, the way every agentmd command does."""
    body = f"""
        import locale
        locale.getencoding = lambda: {locale_encoding!r}
        import os
        import agent_md.config.settings as s
        s.Settings()
        print("KEY=" + str(os.environ.get("OPENAI_API_KEY")))
        print("IMPORT OK")
        """
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}
    for stale in ("OPENAI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY"):
        env.pop(stale, None)
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(body)],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )


def test_import_survives_a_cp1252_env_left_by_an_older_setup(tmp_path):
    """The end-to-end regression: the exact file 0.17.2 wrote on Windows.

    Guarding only ``_load_env_file`` is not enough — pydantic-settings reads the
    same path again through its own ``env_file`` source, so the crash has two
    independent origins and a unit test of the loader alone misses the second.
    """
    home = tmp_path / "home"
    (home / ".config" / "agentmd").mkdir(parents=True)
    (home / ".config" / "agentmd" / ".env").write_bytes(
        "# Agentmd — API Keys\nOPENAI_API_KEY=sk-legacy\n".encode("cp1252")
    )

    result = _import_settings_with_home(home, "cp1252")

    assert "UnicodeDecodeError" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr
    assert "IMPORT OK" in result.stdout
    assert "KEY=sk-legacy" in result.stdout, result.stdout


def test_import_survives_an_env_that_decodes_in_no_encoding(tmp_path):
    """A hopeless .env degrades to a warning, never to an unusable CLI."""
    home = tmp_path / "home"
    (home / ".config" / "agentmd").mkdir(parents=True)
    (home / ".config" / "agentmd" / ".env").write_bytes(b"OPENAI_API_KEY=\xff\xfe\x00\x00\x81\x8d\n")

    result = _import_settings_with_home(home, "utf-8")

    assert "UnicodeDecodeError" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr
    assert "IMPORT OK" in result.stdout


@pytest.mark.parametrize("missing", ["nope/.env"])
def test_missing_env_file_is_silent(tmp_path, caplog, missing):
    """Absence is normal and must not warn — only undecodable files do."""
    from agent_md.config.settings import _load_env_file

    with caplog.at_level(logging.WARNING):
        _load_env_file(str(tmp_path / missing), override=True)

    assert caplog.text == ""
