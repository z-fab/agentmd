"""Tests for ghost execution cleanup."""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_sweep_orphans_dead_pid():
    """Execution with a dead PID gets marked 'orphaned'."""
    from agent_md.core.bootstrap import sweep_orphans

    dead_pid = 99999999

    row = MagicMock()
    row.id = 42
    row.pid = dead_pid

    db = AsyncMock()
    db.list_running_executions = AsyncMock(return_value=[row])
    db.update_execution = AsyncMock()

    cleaned = await sweep_orphans(db)

    assert cleaned == 1
    db.update_execution.assert_called_once_with(
        execution_id=42,
        status="orphaned",
        error="process died without cleanup",
    )


@pytest.mark.asyncio
async def test_sweep_orphans_alive_pid():
    """Execution with a live PID is NOT touched."""
    from agent_md.core.bootstrap import sweep_orphans

    row = MagicMock()
    row.id = 42
    row.pid = os.getpid()

    db = AsyncMock()
    db.list_running_executions = AsyncMock(return_value=[row])
    db.update_execution = AsyncMock()

    cleaned = await sweep_orphans(db)

    assert cleaned == 0
    db.update_execution.assert_not_called()


@pytest.mark.asyncio
async def test_sweep_orphans_null_pid():
    """Execution with no PID (legacy) gets marked 'orphaned'."""
    from agent_md.core.bootstrap import sweep_orphans

    row = MagicMock()
    row.id = 42
    row.pid = None

    db = AsyncMock()
    db.list_running_executions = AsyncMock(return_value=[row])
    db.update_execution = AsyncMock()

    cleaned = await sweep_orphans(db)

    assert cleaned == 1
