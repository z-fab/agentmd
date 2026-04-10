from typing import Optional


class ExecutionRecord:
    """Represents a row from the executions table."""

    def __init__(self, **kwargs):
        self.id: int = kwargs.get("id", 0)
        self.agent_id: str = kwargs.get("agent_id", "")
        self.status: str = kwargs.get("status", "")
        self.trigger: str = kwargs.get("trigger", "")
        self.started_at: str = kwargs.get("started_at", "")
        self.finished_at: Optional[str] = kwargs.get("finished_at")
        self.duration_ms: Optional[int] = kwargs.get("duration_ms")
        self.input_data: Optional[str] = kwargs.get("input_data")
        self.output_data: Optional[str] = kwargs.get("output_data")
        self.error: Optional[str] = kwargs.get("error")
        self.input_tokens: Optional[int] = kwargs.get("input_tokens")
        self.output_tokens: Optional[int] = kwargs.get("output_tokens")
        self.total_tokens: Optional[int] = kwargs.get("total_tokens")
        self.cost_usd: Optional[float] = kwargs.get("cost_usd")
        self.pid: Optional[int] = kwargs.get("pid")


class LogRecord:
    """Represents a row from the execution_logs table."""

    def __init__(self, **kwargs):
        self.id: int = kwargs.get("id", 0)
        self.execution_id: int = kwargs.get("execution_id", 0)
        self.timestamp: str = kwargs.get("timestamp", "")
        self.event_type: str = kwargs.get("event_type", "")
        self.message: str = kwargs.get("message", "")
        self.metadata: Optional[str] = kwargs.get("metadata")
