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
    """Public agent listing.

    ``id`` is the filename stem (canonical key). ``display_name`` is the
    presentation label from frontmatter ``name:`` (defaults to id).

    ``name`` is retained as an alias of ``display_name`` so existing CLI
    clients keep working until ticket 03 migrates them; it is not a route key.
    """

    id: str
    display_name: str
    name: str  # alias of display_name (schema compat for CLI until ticket 03)
    description: str
    icon: str | None = None
    enabled: bool
    trigger_type: str
    model_provider: str | None = None
    model_name: str | None = None


class AgentDetail(AgentSummary):
    last_run: str | None = None
    next_run: str | None = None
    history: str
    settings: dict
    paths: dict[str, str] = {}
    custom_tools: list[str] = []
    mcp: list[str] = []
    skills: list[str] = []
    trigger_every: str | None = None
    trigger_cron: str | None = None
    trigger_paths: list[str] = []
    source_path: str | None = None


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
    parent_execution_id: int | None = None


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
    """Scheduled job identity.

    ``agent_id`` is canonical. ``agent_name`` mirrors ``agent_id`` for schema
    compatibility with existing clients until ticket 03.
    """

    agent_id: str
    display_name: str
    agent_name: str  # alias of agent_id (schema compat until ticket 03)
    trigger_type: str
    next_run: str | None = None


class SchedulerStatus(BaseModel):
    status: str
    jobs: list[SchedulerJob]


class ReloadResponse(BaseModel):
    agents_loaded: int
    agents_removed: int = 0
    errors: list[str] = []


class CancelResponse(BaseModel):
    status: str
    execution_id: int


class ErrorResponse(BaseModel):
    detail: str


class RespondRequest(BaseModel):
    request_id: str
    response: dict


class RespondResponse(BaseModel):
    status: str
    execution_id: int


class PendingResponse(BaseModel):
    execution_id: int
    request_id: str
    kind: str
    message: str
    tool_name: str | None = None
    tool_args: dict | None = None
    options: list[str] | None = None
    multi: bool = False
    created_at: str
