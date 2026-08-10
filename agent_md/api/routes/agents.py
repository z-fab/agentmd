"""Agent management endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request

from agent_md.config.icons import resolve_agent_icon
from agent_md.workspace.scheduler import check_admission
from agent_md.api.schemas import (
    AgentDetail,
    AgentSummary,
    ExecutionSummary,
    LastResult,
    ReloadResponse,
    RunRequest,
    RunResponse,
)

router = APIRouter(prefix="/agents", tags=["agents"])


def _summary_fields(config) -> dict:
    """Shared id / display_name / name fields for agent API responses."""
    return {
        "id": config.id,
        "display_name": config.name,
        "name": config.name,  # schema compat alias of display_name (ticket 03)
        "description": config.description,
        "icon": resolve_agent_icon(config.id, config.icon),
        "enabled": config.enabled,
        "trigger_type": config.trigger.type,
        "model_provider": config.model.provider if config.model else None,
        "model_name": config.model.name if config.model else None,
    }


@router.get("", response_model=list[AgentSummary])
async def list_agents(request: Request):
    rt = request.app.state.runtime
    configs = rt.registry.all()
    last_by_id = await rt.db.get_last_executions([c.id for c in configs])

    summaries: list[AgentSummary] = []
    for config in configs:
        last_exec = last_by_id.get(config.id)
        next_run = None
        if rt.scheduler and config.trigger.type == "schedule":
            next_run = rt.scheduler.get_next_run(config.id)
        summaries.append(
            AgentSummary(
                **_summary_fields(config),
                next_run=next_run,
                last_result=(
                    LastResult(status=last_exec.status, started_at=last_exec.started_at) if last_exec else None
                ),
            )
        )
    return summaries


@router.get("/{agent_id}", response_model=AgentDetail)
async def get_agent(agent_id: str, request: Request):
    rt = request.app.state.runtime
    config = rt.registry.get(agent_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    last_exec = await rt.db.get_last_execution(config.id)
    next_run = None
    if rt.scheduler and config.trigger.type == "schedule":
        next_run = rt.scheduler.get_next_run(config.id)

    resolved_paths = {alias: str(rt.path_context.resolve_alias(alias, config)) for alias in config.paths}

    return AgentDetail(
        **_summary_fields(config),
        last_run=last_exec.started_at if last_exec else None,
        next_run=next_run,
        last_result=(LastResult(status=last_exec.status, started_at=last_exec.started_at) if last_exec else None),
        history=config.history,
        settings=config.settings.model_dump(),
        paths=resolved_paths,
        custom_tools=config.custom_tools,
        mcp=config.mcp,
        skills=config.skills,
        trigger_every=config.trigger.every,
        trigger_cron=config.trigger.cron,
        trigger_paths=config.trigger.paths,
        source_path=config.file_path or None,
    )


@router.post("/reload", response_model=ReloadResponse)
async def reload_agents(request: Request):
    rt = request.app.state.runtime
    from agent_md.workspace.parser import is_agent_file, parse_agent_file

    agents_dir = rt.path_context.agents_dir
    loaded_ids: set[str] = set()
    errors: list[str] = []
    count = 0

    for f in sorted(agents_dir.glob("*.md")):
        if not is_agent_file(f):
            continue
        try:
            config = parse_agent_file(f)
            rt.registry.register(config)
            loaded_ids.add(config.id)
            count += 1
            if rt.scheduler is not None:
                rt.scheduler.unschedule_agent(config.id)
                rt.scheduler.schedule_agent(config)
                if config.trigger.type == "watch" and config.enabled:
                    rt.scheduler._add_watch_handler(config)
        except Exception as e:
            errors.append(f"{f.name}: {e}")

    removed = 0
    for existing in list(rt.registry.all()):
        if existing.id not in loaded_ids:
            if rt.scheduler is not None:
                rt.scheduler.unschedule_agent(existing.id)
            rt.registry.remove(existing.id)
            removed += 1

    return ReloadResponse(agents_loaded=count, agents_removed=removed, errors=errors)


@router.post("/{agent_id}/run", response_model=RunResponse)
async def run_agent(agent_id: str, request: Request, body: RunRequest | None = None):
    """Start an agent execution."""
    rt = request.app.state.runtime
    state = request.app.state
    config = rt.registry.get(agent_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    body = body or RunRequest()
    arguments = body.args or []
    session_id = body.session_id
    # A run that carries a conversation is a chat turn; without one it is a plain
    # manual run. Recording the real trigger is what makes the two distinguishable.
    trigger = "chat" if session_id else "manual"

    # Same admission decision the trigger path makes, rendered as HTTP: a caller
    # who asked for a run gets told why it was refused, where a timer tick is
    # only logged. Scoped to the conversation this run joins — a chat parked on a
    # HILT holds itself, not every other session of the same agent.
    reason = await check_admission(config, rt.db, trigger_type=trigger, session_id=session_id)
    if reason:
        raise HTTPException(status_code=409, detail=f"Agent '{agent_id}': {reason}")

    cancel_event = asyncio.Event()
    execution_id = await rt.db.create_execution(
        agent_id=config.id, trigger=trigger, status="running", session_id=session_id
    )
    state.cancel_events[execution_id] = cancel_event

    model_info = f"{config.model.provider}/{config.model.name}" if config.model else None

    from agent_md.util.tasks import spawn_background

    spawn_background(
        _run_in_background(
            rt,
            config,
            execution_id,
            state,
            arguments,
            body.message,
            cancel_event,
            trigger_type=trigger,
            trigger_context=body.context,
            session_id=session_id,
        )
    )
    return RunResponse(execution_id=execution_id, model=model_info)


async def _run_in_background(
    rt,
    config,
    execution_id,
    state,
    arguments,
    message,
    cancel_event,
    *,
    trigger_type: str = "manual",
    trigger_context: str | None = None,
    session_id: str | None = None,
):
    """Run agent execution as a background task."""
    try:
        await rt.runner.run(
            config,
            trigger_type=trigger_type,
            trigger_context=trigger_context,
            arguments=arguments,
            event_bus=state.event_bus,
            global_event_bus=state.global_event_bus,
            cancel_event=cancel_event,
            execution_id=execution_id,
            user_message=message,
            session_id=session_id,
        )
    finally:
        state.cancel_events.pop(execution_id, None)


@router.get("/{agent_id}/runs", response_model=list[ExecutionSummary])
async def agent_runs(agent_id: str, request: Request, limit: int = 10):
    rt = request.app.state.runtime
    config = rt.registry.get(agent_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    execs = await rt.db.get_executions(config.id, limit=limit)
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
