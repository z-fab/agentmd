"""Execution management and SSE streaming endpoints."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterable

from fastapi import APIRouter, HTTPException, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent

from agent_md.api.schemas import (
    CancelResponse,
    ExecutionDetail,
    ExecutionSummary,
    LogEntry,
)

router = APIRouter(prefix="/executions", tags=["executions"])


@router.get("", response_model=list[ExecutionSummary])
async def list_executions(
    request: Request,
    status: str | None = None,
    agent: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    db = request.app.state.db
    execs = await db.list_executions(agent_id=agent, status=status, limit=limit, offset=offset)
    return [
        ExecutionSummary(
            id=e.id,
            agent_id=e.agent_id,
            status=e.status,
            trigger=e.trigger,
            started_at=e.started_at,
            finished_at=e.finished_at,
            duration_ms=e.duration_ms,
            input_tokens=e.input_tokens,
            output_tokens=e.output_tokens,
            total_tokens=e.total_tokens,
            cost_usd=e.cost_usd,
            error=e.error,
        )
        for e in execs
    ]


@router.get("/{exec_id}", response_model=ExecutionDetail)
async def get_execution(exec_id: int, request: Request):
    db = request.app.state.db
    e = await db.get_execution(exec_id)
    if not e:
        raise HTTPException(status_code=404, detail="Execution not found")
    return ExecutionDetail(
        id=e.id,
        agent_id=e.agent_id,
        status=e.status,
        trigger=e.trigger,
        started_at=e.started_at,
        finished_at=e.finished_at,
        duration_ms=e.duration_ms,
        input_tokens=e.input_tokens,
        output_tokens=e.output_tokens,
        total_tokens=e.total_tokens,
        cost_usd=e.cost_usd,
        error=e.error,
        output_data=e.output_data,
    )


@router.get("/{exec_id}/messages", response_model=list[LogEntry])
async def get_messages(exec_id: int, request: Request):
    db = request.app.state.db
    e = await db.get_execution(exec_id)
    if not e:
        raise HTTPException(status_code=404, detail="Execution not found")
    logs = await db.get_logs(exec_id, limit=10000)
    return [
        LogEntry(
            id=entry.id,
            execution_id=entry.execution_id,
            timestamp=entry.timestamp,
            event_type=entry.event_type,
            message=entry.message,
            metadata=entry.metadata,
        )
        for entry in logs
    ]


@router.get("/{exec_id}/stream", response_class=EventSourceResponse)
async def stream_execution(exec_id: int, request: Request) -> AsyncIterable[ServerSentEvent]:
    db = request.app.state.db
    event_bus = request.app.state.event_bus

    e = await db.get_execution(exec_id)
    if not e:
        raise HTTPException(status_code=404, detail="Execution not found")

    async def event_generator() -> AsyncIterable[ServerSentEvent]:
        queue = event_bus.subscribe(exec_id)
        try:
            seen_seq = -1
            logs = await db.get_logs(exec_id, limit=10000)
            for log in logs:
                seen_seq = log.id
                yield ServerSentEvent(
                    data=json.dumps(
                        {
                            "event_type": log.event_type,
                            "message": log.message,
                            "timestamp": log.timestamp,
                        }
                    ),
                    event=log.event_type,
                    id=str(seen_seq),
                )

            execution = await db.get_execution(exec_id)
            if execution and execution.status not in ("running", "pending"):
                yield ServerSentEvent(
                    data=json.dumps({"status": execution.status}),
                    event="complete",
                )
                return

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    execution = await db.get_execution(exec_id)
                    if not execution or execution.status not in ("running", "pending"):
                        yield ServerSentEvent(
                            data=json.dumps({"status": execution.status if execution else "unknown"}),
                            event="complete",
                        )
                        return
                    continue

                seq = event.get("seq", 0)
                if seq <= seen_seq:
                    continue
                seen_seq = seq

                yield ServerSentEvent(
                    data=json.dumps(event["data"]),
                    event=event["type"],
                    id=str(seq),
                )
                if event["type"] == "complete":
                    break
        finally:
            event_bus.unsubscribe(exec_id, queue)

    return EventSourceResponse(event_generator())


@router.delete("/{exec_id}", response_model=CancelResponse)
async def cancel_execution(exec_id: int, request: Request):
    state = request.app.state
    db = state.db

    e = await db.get_execution(exec_id)
    if not e:
        raise HTTPException(status_code=404, detail="Execution not found")
    if e.status != "running":
        raise HTTPException(status_code=409, detail=f"Execution is {e.status}, not running")

    cancel_event = state.cancel_events.get(exec_id)
    if cancel_event:
        cancel_event.set()
        return CancelResponse(status="cancelling", execution_id=exec_id)

    raise HTTPException(status_code=409, detail="Execution not cancellable (no cancel event)")
