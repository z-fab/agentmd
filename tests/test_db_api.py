"""Tests for database methods needed by the HTTP API."""

import pytest


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


@pytest.mark.asyncio
async def test_get_last_executions_returns_latest_per_agent(db):
    e1 = await db.create_execution("alpha", "manual")
    await db.update_execution(e1, status="error")
    e2 = await db.create_execution("alpha", "manual")
    await db.update_execution(e2, status="success")
    e3 = await db.create_execution("beta", "schedule")
    await db.update_execution(e3, status="success")

    result = await db.get_last_executions(["alpha", "beta", "gamma"])
    assert set(result) == {"alpha", "beta"}
    assert result["alpha"].id == e2
    assert result["alpha"].status == "success"
    assert result["beta"].id == e3
    assert "gamma" not in result


@pytest.mark.asyncio
async def test_get_last_executions_empty_ids_skips_query(db, monkeypatch):
    calls: list[str] = []
    original = db.db.execute

    async def tracking_execute(sql, parameters=()):
        calls.append(sql)
        return await original(sql, parameters)

    monkeypatch.setattr(db.db, "execute", tracking_execute)
    assert await db.get_last_executions([]) == {}
    assert calls == []


@pytest.mark.asyncio
async def test_get_last_executions_one_query_for_one_or_five_agents(db, monkeypatch):
    """Acceptance: last-execution lookup issues one query regardless of agent count."""
    for i in range(5):
        eid = await db.create_execution(f"agent-{i}", "manual")
        await db.update_execution(eid, status="success")

    sql_log: list[str] = []
    original = db.db.execute

    async def tracking_execute(sql, parameters=()):
        sql_log.append(sql)
        return await original(sql, parameters)

    monkeypatch.setattr(db.db, "execute", tracking_execute)

    sql_log.clear()
    one = await db.get_last_executions(["agent-0"])
    queries_one = _count_last_execution_queries(sql_log)

    sql_log.clear()
    five = await db.get_last_executions([f"agent-{i}" for i in range(5)])
    queries_five = _count_last_execution_queries(sql_log)

    assert queries_one == 1
    assert queries_five == 1
    assert queries_one == queries_five
    assert one["agent-0"].status == "success"
    assert len(five) == 5


@pytest.mark.asyncio
async def test_get_execution_by_id(db):
    eid = await db.create_execution("agent-1", "manual")
    result = await db.get_execution(eid)
    assert result is not None
    assert result.id == eid
    assert result.agent_id == "agent-1"


@pytest.mark.asyncio
async def test_get_execution_not_found(db):
    result = await db.get_execution(9999)
    assert result is None


@pytest.mark.asyncio
async def test_list_executions_all(db):
    await db.create_execution("agent-1", "manual")
    await db.create_execution("agent-2", "schedule")
    results = await db.list_executions()
    assert len(results) == 2


@pytest.mark.asyncio
async def test_list_executions_filter_agent(db):
    await db.create_execution("agent-1", "manual")
    await db.create_execution("agent-2", "schedule")
    results = await db.list_executions(agent_id="agent-1")
    assert len(results) == 1
    assert results[0].agent_id == "agent-1"


@pytest.mark.asyncio
async def test_list_executions_filter_status(db):
    eid = await db.create_execution("agent-1", "manual")
    await db.update_execution(eid, status="success")
    await db.create_execution("agent-1", "manual")  # still running
    results = await db.list_executions(status="running")
    assert len(results) == 1


@pytest.mark.asyncio
async def test_list_executions_pagination(db):
    for i in range(5):
        await db.create_execution(f"agent-{i}", "manual")
    results = await db.list_executions(limit=2, offset=1)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_add_log_returns_id(db):
    eid = await db.create_execution("agent-1", "manual")
    log_id = await db.add_log(eid, "ai", "hello world")
    assert isinstance(log_id, int)
    assert log_id > 0
    log_id_2 = await db.add_log(eid, "tool_call", "some call")
    assert log_id_2 > log_id
