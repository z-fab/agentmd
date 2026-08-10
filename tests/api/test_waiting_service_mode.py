"""A parked HILT keeps the backend alive in service mode — and only there.

Local socket: a forgotten 'waiting' execution must not turn the backend
immortal; respond() rebuilds and resumes on demand. Service mode (TCP or
--keep-alive): the caller is remote, so idle-shutdown would strand them.
"""

from __future__ import annotations

import pytest

from agent_md.api.app import create_app


async def _app(tmp_path, *, service_mode: bool):
    application = create_app(workspace=tmp_path, db_path=tmp_path / "test.db")
    application.state.service_mode = service_mode
    return application


@pytest.fixture
async def local_app(tmp_path):
    application = await _app(tmp_path, service_mode=False)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def service_app(tmp_path):
    application = await _app(tmp_path, service_mode=True)
    async with application.router.lifespan_context(application):
        yield application


async def _park_execution(application) -> int:
    return await application.state.db.create_execution("agent-a", "manual", status="waiting")


async def test_service_mode_is_not_idle_while_waiting(service_app):
    await _park_execution(service_app)
    assert await service_app.state.lifecycle._is_idle() is False


async def test_service_mode_is_idle_without_waiting(service_app):
    assert await service_app.state.lifecycle._is_idle() is True


async def test_local_socket_stays_idle_while_waiting(local_app):
    await _park_execution(local_app)
    assert await local_app.state.lifecycle._is_idle() is True


async def test_local_socket_hook_is_not_wired(local_app):
    assert local_app.state.lifecycle.has_waiting_executions() is False
