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
from agent_md.api.sse import SHUTDOWN, TIMEOUT, next_event
from agent_md.execution.logger import agent_identity_payload

router = APIRouter(prefix="/executions", tags=["executions"])


def _durable_display_name(logs) -> str | None:
    """Most recent display name recorded in log metadata, if any."""
    for log in reversed(logs):
        if not log.metadata:
            continue
        try:
            display_name = json.loads(log.metadata).get("display_name")
        except Exception:
            continue
        if display_name:
            return display_name
    return None


def _execution_identity(execution, registry, logs=()) -> dict:
    """Identity for SSE replay: prefer durable log metadata; fall back here.

    The durable name keeps every frame of a stream consistent — including the
    synthetic terminal ones — after the agent is renamed or removed.
    """
    agent_id = execution.agent_id
    display_name = _durable_display_name(logs)
    if not display_name:
        config = registry.get(agent_id) if registry is not None else None
        display_name = config.name if config is not None else agent_id
    return agent_identity_payload(agent_id, display_name)


def _complete_event_data(execution, identity: dict) -> dict:
    """Build a ``complete`` payload from a finished DB row.

    Used when the client connects after the run already finished (or after an
    idle timeout) and the live bus event was missed. Must carry the same fields
    the runner publishes — especially ``error`` — or a graph-build failure
    (missing API key, bad config) shows up as a bare status with no message.
    """
    return {
        "status": execution.status,
        "duration_ms": execution.duration_ms,
        "total_tokens": execution.total_tokens,
        "cost_usd": execution.cost_usd,
        "error": execution.error,
        **identity,
    }


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
            session_id=e.session_id,
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
        session_id=e.session_id,
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
        # Replay historical logs from DB — include the same identity fields live events carry.
        seen_seq = -1
        logs = await db.get_logs(exec_id, limit=10000)
        identity = _execution_identity(e, request.app.state.runtime.registry, logs)
        for log in logs:
            seen_seq = log.id
            payload = {
                "event_type": log.event_type,
                "message": log.message,
                "timestamp": log.timestamp,
                **identity,
            }
            if log.event_type == "final_answer":
                # The live event carries the answer under "content"; a replayed
                # frame has to use the same key, or a client that reads only
                # "content" loses the answer on reconnect. The persisted row is
                # the whole answer (see logger.mark_final_answer), so replay and
                # live are now the same string under the same key — which is what
                # makes the seq dedup below safe for this event.
                payload["content"] = log.message
            if log.metadata:
                try:
                    meta = json.loads(log.metadata)
                    payload.update(meta)
                    # Keep fallback identity when older rows lack these keys.
                    for key, value in identity.items():
                        payload.setdefault(key, value)
                except Exception:
                    pass
            yield ServerSentEvent(
                data=payload,
                event=log.event_type,
                id=str(seen_seq),
            )

        # Check if already finished
        execution = await db.get_execution(exec_id)
        if execution and execution.status == "waiting":
            yield ServerSentEvent(data={"status": "waiting", **identity}, event="waiting")
            return
        if execution and execution.status not in ("running", "pending"):
            yield ServerSentEvent(data=_complete_event_data(execution, identity), event="complete")
            return

        # Drain live events (dedup against replay)
        shutdown_event = getattr(request.app.state, "shutdown_event", None)
        while True:
            event = await next_event(queue, shutdown_event, 30.0)
            if event is SHUTDOWN:
                # A still-running execution would otherwise hold this connection
                # open past `agentmd stop`, and uvicorn will not exit while a
                # connection is open. Close the response and let the backend go.
                yield ServerSentEvent(data={"status": "shutdown", **identity}, event="shutdown")
                return
            if event is TIMEOUT:
                execution = await db.get_execution(exec_id)
                if not execution or execution.status not in ("running", "pending"):
                    if execution and execution.status == "waiting":
                        yield ServerSentEvent(data={"status": "waiting", **identity}, event="waiting")
                    elif execution:
                        yield ServerSentEvent(
                            data=_complete_event_data(execution, identity),
                            event="complete",
                        )
                    else:
                        yield ServerSentEvent(data={"status": "unknown", **identity}, event="complete")
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
                config,
                execution_id,
                response,
                event_bus=state.event_bus,
                global_event_bus=state.global_event_bus,
                cancel_event=cancel_event,
            )
        finally:
            state.cancel_events.pop(execution_id, None)

    from agent_md.util.tasks import spawn_background

    spawn_background(_bg())
