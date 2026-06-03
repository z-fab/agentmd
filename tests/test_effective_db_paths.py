"""Tests for _effective_db_paths — the DB path resolution shown in `agentmd info`."""

from agent_md.cli.setup import _effective_db_paths


def test_absolute_db_path_kept_as_is(tmp_path):
    abs_db = tmp_path / "custom" / "mydb.db"
    db, checkpoints = _effective_db_paths(str(abs_db), tmp_path / "workspace")
    assert db == abs_db.resolve()
    assert checkpoints == abs_db.parent / "mydb_checkpoints.db"


def test_relative_db_path_resolved_against_workspace(tmp_path):
    workspace = tmp_path / "vault"
    db, checkpoints = _effective_db_paths(".agentmd/agentmd.db", workspace)
    assert db == (workspace / ".agentmd" / "agentmd.db").resolve()
    assert checkpoints == (workspace / ".agentmd" / "agentmd_checkpoints.db").resolve()


def test_empty_db_path_uses_state_dir(tmp_path, monkeypatch):
    state = tmp_path / "state" / "agentmd"
    monkeypatch.setattr("agent_md.config.settings.get_state_dir", lambda: state)
    db, checkpoints = _effective_db_paths("", tmp_path / "workspace")
    assert db == (state / "agentmd.db").resolve()
    assert checkpoints == (state / "agentmd_checkpoints.db").resolve()
