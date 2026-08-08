"""Regression: agentmd list must not N+1 on last execution."""

from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite
from typer.testing import CliRunner

from agent_md.db.database import Database
from agent_md.main import app


def _count_last_execution_queries(sql_log: list[str]) -> int:
    """Count SELECT statements that fetch last executions (batch or per-agent)."""
    count = 0
    for sql in sql_log:
        normalized = " ".join(sql.lower().split())
        if "from executions" not in normalized:
            continue
        if "row_number()" in normalized or "order by started_at desc" in normalized:
            count += 1
    return count


def _agent_md(agent_id: str) -> str:
    return f"---\nname: {agent_id}\nmodel:\n  provider: google\n  name: gemini-2.5-flash\n---\nYou are a test agent.\n"


async def _workspace_with_agents(root: Path, n: int) -> Path:
    """Create a workspace with *n* agents and one finished execution each."""
    ws = root / f"ws-{n}"
    agents_dir = ws / "agents"
    agents_dir.mkdir(parents=True)
    for i in range(n):
        agent_id = f"agent-{i}"
        (agents_dir / f"{agent_id}.md").write_text(_agent_md(agent_id), encoding="utf-8")

    db = Database(ws / "data" / "agentmd.db")
    await db.connect()
    try:
        for i in range(n):
            eid = await db.create_execution(f"agent-{i}", "manual")
            await db.update_execution(eid, status="success")
    finally:
        await db.close()
    return ws


def test_cli_list_one_last_execution_query_for_one_or_five_agents(tmp_path, monkeypatch):
    """The CLI list path (former N+1 site) must issue one last-execution query for 1 or 5 agents.

    Sync test on purpose: ``agentmd list`` calls ``asyncio.run`` internally.
    """
    from agent_md.config import settings as settings_mod

    # Isolate from the developer's config.yaml (e.g. custom agents_dir).
    monkeypatch.setattr(settings_mod.settings, "agents_dir", "agents")
    monkeypatch.setattr(settings_mod.settings, "tools_dir", "")
    monkeypatch.setattr(settings_mod.settings, "mcp_config", "")
    monkeypatch.setattr(settings_mod.settings, "db_path", "data/agentmd.db")

    ws1 = asyncio.run(_workspace_with_agents(tmp_path, 1))
    ws5 = asyncio.run(_workspace_with_agents(tmp_path, 5))

    sql_log: list[str] = []
    original = aiosqlite.Connection.execute

    async def tracking_execute(self, sql, parameters=None):
        sql_log.append(sql)
        return await original(self, sql, parameters)

    monkeypatch.setattr(aiosqlite.Connection, "execute", tracking_execute)

    runner = CliRunner()

    sql_log.clear()
    result_one = runner.invoke(app, ["list", "--workspace", str(ws1)])
    assert result_one.exit_code == 0, result_one.output
    assert "agent-0" in result_one.output
    queries_one = _count_last_execution_queries(sql_log)

    sql_log.clear()
    result_five = runner.invoke(app, ["list", "--workspace", str(ws5)])
    assert result_five.exit_code == 0, result_five.output
    for i in range(5):
        assert f"agent-{i}" in result_five.output
    queries_five = _count_last_execution_queries(sql_log)

    assert queries_one == 1
    assert queries_five == 1
    assert queries_one == queries_five
