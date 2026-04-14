"""Agent management endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request

from agent_md.api.schemas import (
    AgentDetail,
    AgentSummary,
    ExecutionSummary,
    ReloadResponse,
    RunRequest,
    RunResponse,
)

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[AgentSummary])
async def list_agents(request: Request):
    rt = request.app.state.runtime
    return [
        AgentSummary(
            name=c.name,
            description=c.description,
            enabled=c.enabled,
            trigger_type=c.trigger.type,
            model_provider=c.model.provider if c.model else None,
            model_name=c.model.name if c.model else None,
        )
        for c in rt.registry.all()
    ]


@router.get("/{name}", response_model=AgentDetail)
async def get_agent(name: str, request: Request):
    rt = request.app.state.runtime
    config = rt.registry.get(name)
    if not config:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")

    last_exec = await rt.db.get_last_execution(name)
    next_run = None
    if rt.scheduler and config.trigger.type == "schedule":
        next_run = rt.scheduler.get_next_run(name)

    return AgentDetail(
        name=config.name,
        description=config.description,
        enabled=config.enabled,
        trigger_type=config.trigger.type,
        model_provider=config.model.provider if config.model else None,
        model_name=config.model.name if config.model else None,
        last_run=last_exec.started_at if last_exec else None,
        next_run=next_run,
        history=config.history,
        settings=config.settings.model_dump(),
    )


@router.post("/reload", response_model=ReloadResponse)
async def reload_agents(request: Request):
    rt = request.app.state.runtime
    from agent_md.workspace.parser import parse_agent_file

    agents_dir = rt.path_context.agents_dir
    count = 0
    for f in sorted(agents_dir.glob("*.md")):
        try:
            config = parse_agent_file(f)
            rt.registry.register(config)
            count += 1
        except Exception:
            pass

    return ReloadResponse(agents_loaded=count)


@router.post("/{name}/run", response_model=RunResponse)
async def run_agent(name: str, request: Request, body: RunRequest | None = None):
    """Start an agent execution."""
    rt = request.app.state.runtime
    state = request.app.state
    config = rt.registry.get(name)
    if not config:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")

    body = body or RunRequest()
    arguments = body.args or []

    cancel_event = asyncio.Event()
    execution_id = await rt.db.create_execution(agent_id=config.name, trigger="manual", status="running")
    state.cancel_events[execution_id] = cancel_event

    model_info = f"{config.model.provider}/{config.model.name}" if config.model else None

    asyncio.create_task(_run_in_background(rt, config, execution_id, state, arguments, body.message, cancel_event))
    return RunResponse(execution_id=execution_id, model=model_info)


async def _run_in_background(rt, config, execution_id, state, arguments, message, cancel_event):
    """Run agent execution as a background task."""
    try:
        await rt.runner.run(
            config,
            trigger_type="manual",
            arguments=arguments,
            event_bus=state.event_bus,
            global_event_bus=state.global_event_bus,
            cancel_event=cancel_event,
            execution_id=execution_id,
            user_message=message,
        )
    finally:
        state.cancel_events.pop(execution_id, None)


@router.get("/{name}/runs", response_model=list[ExecutionSummary])
async def agent_runs(name: str, request: Request, limit: int = 10):
    rt = request.app.state.runtime
    config = rt.registry.get(name)
    if not config:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    execs = await rt.db.get_executions(name, limit=limit)
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
