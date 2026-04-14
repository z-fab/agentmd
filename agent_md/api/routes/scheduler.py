"""Scheduler status and control endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from agent_md.api.schemas import SchedulerJob, SchedulerStatus

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.get("", response_model=SchedulerStatus)
async def scheduler_status(request: Request):
    rt = request.app.state.runtime
    if not rt.scheduler:
        return SchedulerStatus(status="off", jobs=[])

    status = "paused" if getattr(rt.scheduler, "_paused", False) else "running"
    jobs = [SchedulerJob(**j) for j in rt.scheduler.get_jobs()]
    return SchedulerStatus(status=status, jobs=jobs)


@router.post("/pause")
async def pause_scheduler(request: Request):
    rt = request.app.state.runtime
    if not rt.scheduler:
        raise HTTPException(status_code=409, detail="No scheduler active")
    rt.scheduler.pause()
    global_bus = request.app.state.global_event_bus
    await global_bus.publish({"type": "scheduler_changed", "data": {"status": "paused"}})
    return {"status": "paused"}


@router.post("/resume")
async def resume_scheduler(request: Request):
    rt = request.app.state.runtime
    if not rt.scheduler:
        raise HTTPException(status_code=409, detail="No scheduler active")
    rt.scheduler.resume()
    global_bus = request.app.state.global_event_bus
    await global_bus.publish({"type": "scheduler_changed", "data": {"status": "running"}})
    return {"status": "running"}
