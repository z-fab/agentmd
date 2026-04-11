"""FastAPI dependency injection helpers."""

from __future__ import annotations

from fastapi import Request

from agent_md.execution.event_bus import EventBus
from agent_md.db.database import Database


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_event_bus(request: Request) -> EventBus:
    return request.app.state.event_bus


def get_runtime(request: Request):
    return request.app.state.runtime
