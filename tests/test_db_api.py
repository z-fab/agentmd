"""Tests for database methods needed by the HTTP API."""

import pytest
from agent_md.db.database import Database


@pytest.fixture
async def db(tmp_path):
    d = Database(tmp_path / "test.db")
    await d.connect()
    yield d
    await d.close()


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
