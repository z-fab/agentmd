"""Execution management and SSE streaming endpoints."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterable

from fastapi import APIRouter, HTTPException, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent  # noqa: F401 - EventSourceResponse used in response_class

from agent_md.api.schemas import (
    CancelResponse,
    ExecutionDetail,
    ExecutionSummary,
    LogEntry,
    PendingResponse,
    RespondRequest,
    RespondResponse,
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
            parent_execution_id=e.parent_execution_id,
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
        parent_execution_id=e.parent_execution_id,
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

    # Validate before first yield — HTTPException propagates normally
    e = await db.get_execution(exec_id)
    if not e:
        raise HTTPException(status_code=404, detail="Execution not found")

    # Subscribe BEFORE replay to avoid missing live events
    queue = event_bus.subscribe(exec_id)
    try:
        # Replay historical logs from DB
        seen_seq = -1
        logs = await db.get_logs(exec_id, limit=10000)
        for log in logs:
            seen_seq = log.id
            yield ServerSentEvent(
                data={
                    "event_type": log.event_type,
                    "message": log.message,
                    "timestamp": log.timestamp,
                },
                event=log.event_type,
                id=str(seen_seq),
            )

        # Check if already finished
        execution = await db.get_execution(exec_id)
        if execution and execution.status == "waiting":
            yield ServerSentEvent(data={"status": "waiting"}, event="waiting")
            return
        if execution and execution.status not in ("running", "pending"):
            yield ServerSentEvent(data={"status": execution.status}, event="complete")
            return

        # Drain live events (dedup against replay)
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                execution = await db.get_execution(exec_id)
                if not execution or execution.status not in ("running", "pending"):
                    ev = "waiting" if execution and execution.status == "waiting" else "complete"
                    yield ServerSentEvent(
                        data={"status": execution.status if execution else "unknown"},
                        event=ev,
                    )
                    return
                continue

            seq = event.get("seq", 0)
            if seq <= seen_seq:
                continue
            seen_seq = seq

            yield ServerSentEvent(
                data=event["data"],
                event=event["type"],
                id=str(seq),
            )
            if event["type"] == "complete":
                break
            if event["type"] == "interrupt":
                break
    finally:
        event_bus.unsubscribe(exec_id, queue)


@router.get("/{exec_id}/pending", response_model=PendingResponse)
async def get_pending(exec_id: int, request: Request):
    db = request.app.state.db
    rec = await db.get_pending_interrupt(exec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="No pending request")
    payload = json.loads(rec.payload_json)
    return PendingResponse(
        execution_id=exec_id,
        request_id=rec.request_id,
        kind=payload.get("kind", "input"),
        message=payload.get("message", ""),
        tool_name=payload.get("tool_name"),
        tool_args=payload.get("tool_args"),
        options=payload.get("options"),
        multi=payload.get("multi", False),
        created_at=rec.created_at,
    )


@router.post("/{exec_id}/respond", response_model=RespondResponse)
async def respond(exec_id: int, body: RespondRequest, request: Request):
    state = request.app.state
    db = state.db
    e = await db.get_execution(exec_id)
    if not e:
        raise HTTPException(status_code=404, detail="Execution not found")
    if e.status != "waiting":
        raise HTTPException(status_code=409, detail=f"Execution is '{e.status}', not waiting")
    rec = await db.get_pending_interrupt(exec_id)
    if not rec or rec.request_id != body.request_id:
        raise HTTPException(status_code=409, detail="Stale or unknown request_id")

    await db.clear_pending_interrupt(exec_id)
    await _dispatch_resume(state, exec_id, body.response)
    return RespondResponse(status="resuming", execution_id=exec_id)


@router.delete("/{exec_id}", response_model=CancelResponse)
async def cancel_execution(exec_id: int, request: Request):
    state = request.app.state
    db = state.db
    e = await db.get_execution(exec_id)
    if not e:
        raise HTTPException(status_code=404, detail="Execution not found")

    if e.status == "waiting":
        await db.clear_pending_interrupt(exec_id)
        await db.update_execution(execution_id=exec_id, status="aborted", error="cancelled while waiting")
        return CancelResponse(status="aborted", execution_id=exec_id)

    if e.status not in ("running", "pending"):
        return CancelResponse(status=e.status, execution_id=exec_id)

    cancel_event = state.cancel_events.get(exec_id)
    if cancel_event:
        cancel_event.set()
        return CancelResponse(status="cancelling", execution_id=exec_id)
    return CancelResponse(status=e.status, execution_id=exec_id)


async def _dispatch_resume(state, execution_id: int, response) -> None:
    """Rebuild the agent and spawn a background resume task."""
    rt = state.runtime
    e = await state.db.get_execution(execution_id)
    config = rt.registry.get(e.agent_id) if e else None
    if config is None:
        await state.db.update_execution(execution_id=execution_id, status="error", error="agent not found for resume")
        return

    cancel_event = asyncio.Event()
    state.cancel_events[execution_id] = cancel_event

    async def _bg():
        try:
            await rt.runner.resume(
                config, execution_id, response,
                event_bus=state.event_bus, global_event_bus=state.global_event_bus,
                cancel_event=cancel_event,
            )
        finally:
            state.cancel_events.pop(execution_id, None)

    asyncio.create_task(_bg())
