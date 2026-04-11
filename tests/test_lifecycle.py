"""Tests for the lifecycle manager (idle timeout)."""

import asyncio
import pytest
from agent_md.core.lifecycle import LifecycleManager


@pytest.fixture
def lifecycle():
    shutdown_event = asyncio.Event()
    return LifecycleManager(
        shutdown_event=shutdown_event,
        idle_timeout=1,
        check_interval=0.2,
    )


@pytest.mark.asyncio
async def test_idle_triggers_shutdown(lifecycle):
    lifecycle.has_scheduled_agents = lambda: False
    lifecycle.has_running_executions = lambda: False
    lifecycle.has_active_streams = lambda: False

    task = asyncio.create_task(lifecycle.run())
    await asyncio.sleep(1.5)
    assert lifecycle.shutdown_event.is_set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_keep_alive_prevents_shutdown(lifecycle):
    lifecycle.keep_alive = True
    lifecycle.has_scheduled_agents = lambda: False
    lifecycle.has_running_executions = lambda: False
    lifecycle.has_active_streams = lambda: False

    task = asyncio.create_task(lifecycle.run())
    await asyncio.sleep(1.5)
    assert not lifecycle.shutdown_event.is_set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_scheduler_prevents_shutdown(lifecycle):
    lifecycle.has_scheduled_agents = lambda: True
    lifecycle.has_running_executions = lambda: False
    lifecycle.has_active_streams = lambda: False

    task = asyncio.create_task(lifecycle.run())
    await asyncio.sleep(1.5)
    assert not lifecycle.shutdown_event.is_set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_active_streams_prevent_shutdown(lifecycle):
    lifecycle.has_scheduled_agents = lambda: False
    lifecycle.has_running_executions = lambda: False
    lifecycle.has_active_streams = lambda: True

    task = asyncio.create_task(lifecycle.run())
    await asyncio.sleep(1.5)
    assert not lifecycle.shutdown_event.is_set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
