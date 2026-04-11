"""Pydantic models for API request/response bodies."""

from __future__ import annotations

from pydantic import BaseModel


# --- Requests ---


class RunRequest(BaseModel):
    args: list[str] = []
    context: str | None = None
    message: str | None = None


# --- Responses ---


class HealthResponse(BaseModel):
    status: str = "ok"


class InfoResponse(BaseModel):
    version: str
    pid: int
    uptime_seconds: float
    agents_loaded: int
    agents_enabled: int
    scheduler_status: str
    watcher_active: bool
    active_streams: int
    active_executions: int


class ShutdownResponse(BaseModel):
    message: str = "shutting down"


class AgentSummary(BaseModel):
    name: str
    description: str
    enabled: bool
    trigger_type: str
    model_provider: str | None = None
    model_name: str | None = None


class AgentDetail(AgentSummary):
    last_run: str | None = None
    next_run: str | None = None
    history: str
    settings: dict


class RunResponse(BaseModel):
    execution_id: int
    model: str | None = None


class ExecutionSummary(BaseModel):
    id: int
    agent_id: str
    status: str
    trigger: str
    started_at: str
    finished_at: str | None = None
    duration_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    error: str | None = None


class ExecutionDetail(ExecutionSummary):
    output_data: str | None = None


class LogEntry(BaseModel):
    id: int
    execution_id: int
    timestamp: str
    event_type: str
    message: str
    metadata: str | None = None


class SchedulerJob(BaseModel):
    agent_name: str
    trigger_type: str
    next_run: str | None = None


class SchedulerStatus(BaseModel):
    status: str
    jobs: list[SchedulerJob]


class ReloadResponse(BaseModel):
    agents_loaded: int


class CancelResponse(BaseModel):
    status: str
    execution_id: int


class ErrorResponse(BaseModel):
    detail: str
