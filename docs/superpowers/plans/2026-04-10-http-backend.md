# HTTP Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the ephemeral-process daemon with a long-lived FastAPI backend over Unix socket, turning the CLI into a thin HTTP client.

**Architecture:** A single FastAPI process owns the database, scheduler, file watcher, MCP servers, and agent execution. The CLI talks to it via Unix domain socket (httpx). Commands that don't need execution (`list`, `logs`, `validate`) remain static and read the DB directly in read-only mode.

**Tech Stack:** FastAPI >= 0.135.0 (native SSE), uvicorn[standard], httpx (Unix socket transport), existing LangGraph + APScheduler stack.

**Spec:** `docs/superpowers/specs/2026-04-08-http-backend-design.md`

---

## File Structure

### New files

| File | Responsibility |
|---|---|
| `agent_md/core/event_bus.py` | In-memory pub/sub for execution events |
| `agent_md/core/lifecycle.py` | Idle timeout tracking + graceful shutdown |
| `agent_md/api/__init__.py` | Package init |
| `agent_md/api/app.py` | FastAPI app factory + lifespan |
| `agent_md/api/schemas.py` | Pydantic request/response models |
| `agent_md/api/dependencies.py` | FastAPI dependency injection helpers |
| `agent_md/api/auth.py` | API key middleware (TCP only) |
| `agent_md/api/routes/__init__.py` | Package init |
| `agent_md/api/routes/info.py` | `/health`, `/info`, `/shutdown` |
| `agent_md/api/routes/agents.py` | `/agents` CRUD + run |
| `agent_md/api/routes/executions.py` | `/executions` + SSE stream + cancel |
| `agent_md/api/routes/scheduler.py` | `/scheduler` status + pause/resume |
| `agent_md/cli/client.py` | httpx client wrapper (Unix socket + TCP) |
| `agent_md/cli/spawn.py` | Auto-spawn backend process |
| `tests/test_event_bus.py` | EventBus unit tests |
| `tests/api/__init__.py` | Package init |
| `tests/api/test_info.py` | Info route tests |
| `tests/api/test_agents.py` | Agent route tests |
| `tests/api/test_executions.py` | Execution route tests |
| `tests/api/test_scheduler.py` | Scheduler route tests |
| `tests/api/test_auth.py` | Auth middleware tests |
| `tests/test_lifecycle.py` | Lifecycle manager tests |
| `tests/test_runner_events.py` | Runner event publishing tests |
| `tests/test_cli_client.py` | CLI client tests |
| `tests/api/test_chat.py` | Chat endpoint tests |
| `docs/api.md` | REST API reference |
| `docs/migration-0.8.md` | Breaking changes guide |

### Modified files

| File | Changes |
|---|---|
| `pyproject.toml` | Add fastapi, uvicorn, httpx; bump to 0.8.0 |
| `agent_md/core/runner.py` | Accept event_bus + cancel_event, publish events |
| `agent_md/core/scheduler.py` | Add pause/resume/get_jobs, accept event_bus |
| `agent_md/db/database.py` | Add `get_execution()`, `list_executions()`, `add_log()` returns id, WAL mode |
| `agent_md/cli/commands.py` | `run`/`chat`/`start`/`stop`/`status` become thin clients |
| `agent_md/main.py` | Add `--internal-backend` flag |
| `agent_md/core/bootstrap.py` | Accept event_bus param, pass to runner |

### Removed files

| File | Reason |
|---|---|
| `agent_md/cli/daemon.py` | Replaced by backend + spawn |

---

## Task 1: Dependencies and EventBus

**Files:**
- Modify: `pyproject.toml`
- Create: `agent_md/core/event_bus.py`
- Create: `tests/test_event_bus.py`

- [ ] **Step 1: Add dependencies to pyproject.toml**

```toml
dependencies = [
    "aiosqlite>=0.22.1",
    "apscheduler>=3.11.2",
    "fastapi>=0.135.0",
    "httpx>=0.28.0",
    "langchain-google-genai>=4.2.1",
    "langchain-mcp-adapters>=0.1.0",
    "langgraph>=1.1.0",
    "pydantic-settings>=2.13.1",
    "python-dotenv>=1.2.2",
    "pyyaml>=6.0.3",
    "rich>=14.3.3",
    "typer>=0.24.1",
    "questionary>=2.1.0",
    "uvicorn[standard]>=0.34.0",
    "watchdog>=6.0.0",
    "langgraph-checkpoint-sqlite>=2.0.0",
]
```

- [ ] **Step 2: Install dependencies**

Run: `uv sync`
Expected: All dependencies install successfully.

- [ ] **Step 3: Write EventBus tests**

```python
# tests/test_event_bus.py
"""Tests for the in-memory event bus."""

import asyncio
import pytest
from agent_md.core.event_bus import EventBus


@pytest.fixture
def bus():
    return EventBus()


@pytest.mark.asyncio
async def test_subscribe_and_publish(bus):
    queue = bus.subscribe(1)
    await bus.publish(1, {"type": "message", "data": "hello", "seq": 1})
    event = queue.get_nowait()
    assert event == {"type": "message", "data": "hello", "seq": 1}


@pytest.mark.asyncio
async def test_multi_subscriber(bus):
    q1 = bus.subscribe(1)
    q2 = bus.subscribe(1)
    await bus.publish(1, {"type": "message", "data": "hello", "seq": 1})
    assert q1.get_nowait() == {"type": "message", "data": "hello", "seq": 1}
    assert q2.get_nowait() == {"type": "message", "data": "hello", "seq": 1}


@pytest.mark.asyncio
async def test_unsubscribe(bus):
    q = bus.subscribe(1)
    bus.unsubscribe(1, q)
    await bus.publish(1, {"type": "message", "data": "hello", "seq": 1})
    assert q.empty()


@pytest.mark.asyncio
async def test_publish_wrong_execution_id(bus):
    bus.subscribe(1)
    await bus.publish(999, {"type": "message", "data": "hello", "seq": 1})
    # No error, just no delivery


@pytest.mark.asyncio
async def test_queue_full_does_not_block(bus):
    q = bus.subscribe(1)
    # Fill the queue to capacity
    for i in range(1000):
        await bus.publish(1, {"type": "message", "data": f"msg-{i}", "seq": i})
    assert q.full()
    # Next publish should not block or raise
    await bus.publish(1, {"type": "message", "data": "overflow", "seq": 1001})
    assert q.qsize() == 1000  # No change, overflow was dropped


@pytest.mark.asyncio
async def test_stream_count(bus):
    assert bus.stream_count == 0
    q1 = bus.subscribe(1)
    assert bus.stream_count == 1
    q2 = bus.subscribe(2)
    assert bus.stream_count == 2
    bus.unsubscribe(1, q1)
    assert bus.stream_count == 1
    bus.unsubscribe(2, q2)
    assert bus.stream_count == 0


@pytest.mark.asyncio
async def test_unsubscribe_cleans_empty_list(bus):
    q = bus.subscribe(1)
    bus.unsubscribe(1, q)
    assert 1 not in bus._subscribers
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `python -m pytest tests/test_event_bus.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent_md.core.event_bus'`

- [ ] **Step 5: Implement EventBus**

```python
# agent_md/core/event_bus.py
"""In-memory pub/sub for execution events.

The runner publishes events (message, tool_call, tool_result, meta, complete)
as each message is processed. SSE stream endpoints subscribe to receive
live events. Events are dicts with at least ``type``, ``data``, and ``seq`` keys.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict


class EventBus:
    """Lightweight pub/sub keyed by execution_id."""

    def __init__(self) -> None:
        self._subscribers: dict[int, list[asyncio.Queue]] = defaultdict(list)
        self._active_streams: int = 0

    async def publish(self, execution_id: int, event: dict) -> None:
        """Send *event* to all subscribers of *execution_id*."""
        for queue in self._subscribers.get(execution_id, []):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass  # slow client — drop event, client will catch up via replay

    def subscribe(self, execution_id: int) -> asyncio.Queue:
        """Create a new subscriber queue for *execution_id*."""
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers[execution_id].append(q)
        self._active_streams += 1
        return q

    def unsubscribe(self, execution_id: int, q: asyncio.Queue) -> None:
        """Remove a subscriber queue."""
        subs = self._subscribers.get(execution_id, [])
        if q in subs:
            subs.remove(q)
            self._active_streams -= 1
        if not subs:
            self._subscribers.pop(execution_id, None)

    @property
    def stream_count(self) -> int:
        """Number of active SSE streams (for lifecycle tracking)."""
        return self._active_streams
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_event_bus.py -v`
Expected: All 7 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml agent_md/core/event_bus.py tests/test_event_bus.py
git commit -m "feat: add EventBus and backend dependencies (fastapi, uvicorn, httpx)"
```

---

## Task 2: Database enhancements

**Files:**
- Modify: `agent_md/db/database.py`
- Modify: `agent_md/db/models.py`

The API needs new query methods that the current DB doesn't have: get a single execution by ID, list executions with filters across all agents, and `add_log` needs to return the inserted row ID for SSE sequencing.

- [ ] **Step 1: Write tests for new DB methods**

```python
# tests/test_db_api.py
"""Tests for database methods needed by the HTTP API."""

import pytest
from pathlib import Path
from agent_md.db.database import Database


@pytest.fixture
async def db(tmp_path):
    d = Database(tmp_path / "test.db")
    await d.connect()
    yield d
    await d.close()


@pytest.mark.asyncio
async def test_get_execution_by_id(db):
    eid = await db.create_execution("agent-1", "manual")
    result = await db.get_execution(eid)
    assert result is not None
    assert result.id == eid
    assert result.agent_id == "agent-1"


@pytest.mark.asyncio
async def test_get_execution_not_found(db):
    result = await db.get_execution(9999)
    assert result is None


@pytest.mark.asyncio
async def test_list_executions_all(db):
    await db.create_execution("agent-1", "manual")
    await db.create_execution("agent-2", "schedule")
    results = await db.list_executions()
    assert len(results) == 2


@pytest.mark.asyncio
async def test_list_executions_filter_agent(db):
    await db.create_execution("agent-1", "manual")
    await db.create_execution("agent-2", "schedule")
    results = await db.list_executions(agent_id="agent-1")
    assert len(results) == 1
    assert results[0].agent_id == "agent-1"


@pytest.mark.asyncio
async def test_list_executions_filter_status(db):
    eid = await db.create_execution("agent-1", "manual")
    await db.update_execution(eid, status="success")
    await db.create_execution("agent-1", "manual")  # still running
    results = await db.list_executions(status="running")
    assert len(results) == 1


@pytest.mark.asyncio
async def test_list_executions_pagination(db):
    for i in range(5):
        await db.create_execution(f"agent-{i}", "manual")
    results = await db.list_executions(limit=2, offset=1)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_add_log_returns_id(db):
    eid = await db.create_execution("agent-1", "manual")
    log_id = await db.add_log(eid, "ai", "hello world")
    assert isinstance(log_id, int)
    assert log_id > 0
    log_id_2 = await db.add_log(eid, "tool_call", "some call")
    assert log_id_2 > log_id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_db_api.py -v`
Expected: FAIL — `AttributeError: 'Database' object has no attribute 'get_execution'`

- [ ] **Step 3: Add get_execution method to Database**

Add to `agent_md/db/database.py` after the `get_last_execution` method (line 162):

```python
    async def get_execution(self, execution_id: int) -> Optional[ExecutionRecord]:
        """Get a single execution by ID."""
        cursor = await self.db.execute(
            "SELECT * FROM executions WHERE id = ?",
            (execution_id,),
        )
        row = await cursor.fetchone()
        return ExecutionRecord(**dict(row)) if row else None
```

- [ ] **Step 4: Add list_executions method to Database**

Add after `get_execution`:

```python
    async def list_executions(
        self,
        agent_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ExecutionRecord]:
        """List executions with optional filters."""
        conditions = []
        params: list = []
        if agent_id:
            conditions.append("agent_id = ?")
            params.append(agent_id)
        if status:
            conditions.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.extend([limit, offset])
        cursor = await self.db.execute(
            f"SELECT * FROM executions {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params,
        )
        rows = await cursor.fetchall()
        return [ExecutionRecord(**dict(row)) for row in rows]
```

- [ ] **Step 5: Make add_log return the inserted row ID**

In `agent_md/db/database.py`, change `add_log` (line 166) to return `int`:

```python
    async def add_log(
        self,
        execution_id: int,
        event_type: str,
        message: str,
        metadata: Optional[dict] = None,
    ) -> int:
        """Add a log entry for an execution. Returns the log entry ID."""
        meta_json = json.dumps(metadata) if metadata else None
        cursor = await self.db.execute(
            """
            INSERT INTO execution_logs (execution_id, event_type, message, metadata)
            VALUES (?, ?, ?, ?)
            """,
            (execution_id, event_type, message, meta_json),
        )
        await self.db.commit()
        return cursor.lastrowid
```

- [ ] **Step 6: Make ExecutionLogger._persist return the log ID**

In `agent_md/core/execution_logger.py`, change `_persist` and `log_message` to return the log entry ID. This is needed so the runner can use the DB log ID as the sequence number for SSE dedup.

Change `_persist` (line 133):

```python
    async def _persist(self, event_type: str, message: str) -> int:
        """Write a log entry to the database. Returns the log entry ID."""
        return await self.db.add_log(
            execution_id=self.execution_id,
            event_type=event_type,
            message=message,
        )
```

Change `log_message` (line 57) to return the last log ID. At the end of each branch, capture and return the ID. The simplest approach: make `log_message` return the ID of the last persisted log entry:

```python
    async def log_message(self, msg) -> int:
        """Classify a single LangChain message and persist it.

        Returns the log entry ID of the last persisted entry.
        """
        msg_type = getattr(msg, "type", "unknown")
        log_id = 0

        if msg_type == "ai" and hasattr(msg, "tool_calls") and msg.tool_calls:
            reasoning = _extract_text(getattr(msg, "content", ""))
            if reasoning:
                logger.info(f"[{self.agent_name}] 🤖 {reasoning[:200]}")
                self._emit("ai", {"content": reasoning[:200], "agent_name": self.agent_name})
                log_id = await self._persist("ai", reasoning[:500])

            for tc in msg.tool_calls:
                tool_name = tc.get("name", "unknown")
                tool_args = str(tc.get("args", {}))[:300]
                logger.info(f"[{self.agent_name}] 🔧 {tool_name}({tool_args[:80]})")
                self._emit(
                    "tool_call", {"tool_name": tool_name, "tool_args": tool_args[:80], "agent_name": self.agent_name}
                )
                log_id = await self._persist("tool_call", f"{tool_name} — args: {tool_args}")

        elif msg_type == "tool":
            tool_name = getattr(msg, "name", "unknown")
            tool_content = _extract_text(getattr(msg, "content", ""))[:500]
            logger.info(f"[{self.agent_name}] 📎 {tool_name} → {tool_content[:100]}")
            self._emit(
                "tool_response", {"tool_name": tool_name, "content": tool_content[:100], "agent_name": self.agent_name}
            )
            log_id = await self._persist("tool_response", f"{tool_name} — {tool_content}")

        elif msg_type == "ai":
            content = _extract_text(getattr(msg, "content", ""))[:500]
            logger.info(f"[{self.agent_name}] 🤖 {content[:200]}")
            self._emit("ai", {"content": content[:200], "agent_name": self.agent_name})
            log_id = await self._persist("ai", content)

        else:
            content = _extract_text(getattr(msg, "content", ""))[:500]
            log_id = await self._persist(msg_type, content)

        return log_id
```

- [ ] **Step 7: Enable WAL mode on connect**

In `agent_md/db/database.py`, add WAL mode after the connection (inside `connect()`, after `self._conn.row_factory = aiosqlite.Row`):

```python
        await self._conn.execute("PRAGMA journal_mode=WAL")
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/test_db_api.py -v`
Expected: All 7 tests PASS.

- [ ] **Step 8: Run existing tests to verify no regressions**

Run: `python -m pytest tests/ -v`
Expected: All existing tests PASS.

- [ ] **Step 9: Commit**

```bash
git add agent_md/db/database.py tests/test_db_api.py
git commit -m "feat: add DB methods for API (get_execution, list_executions, WAL mode)"
```

---

## Task 3: Runner event publishing and cancellation

**Files:**
- Modify: `agent_md/core/runner.py`
- Create: `tests/test_runner_events.py`

The runner needs two new capabilities: (1) publish events to an EventBus so SSE clients can follow live execution, and (2) check an `asyncio.Event` for cancellation requests between messages.

- [ ] **Step 1: Write tests for event publishing**

```python
# tests/test_runner_events.py
"""Tests for runner event publishing and cancellation."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from agent_md.core.event_bus import EventBus
from agent_md.core.runner import _classify_event_type


@pytest.mark.asyncio
async def test_classify_event_type_ai_with_tools():
    msg = MagicMock()
    msg.type = "ai"
    msg.tool_calls = [{"name": "file_read"}]
    assert _classify_event_type(msg) == "tool_call"


@pytest.mark.asyncio
async def test_classify_event_type_ai_no_tools():
    msg = MagicMock()
    msg.type = "ai"
    msg.tool_calls = []
    msg.additional_kwargs = {}
    assert _classify_event_type(msg) == "message"


@pytest.mark.asyncio
async def test_classify_event_type_tool():
    msg = MagicMock()
    msg.type = "tool"
    msg.additional_kwargs = {}
    assert _classify_event_type(msg) == "tool_result"


@pytest.mark.asyncio
async def test_classify_event_type_meta():
    msg = MagicMock()
    msg.type = "human"
    msg.additional_kwargs = {"meta_type": "skill-context"}
    assert _classify_event_type(msg) == "meta"


@pytest.mark.asyncio
async def test_classify_event_type_human():
    msg = MagicMock()
    msg.type = "human"
    msg.additional_kwargs = {}
    assert _classify_event_type(msg) == "message"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_runner_events.py -v`
Expected: FAIL — `ImportError: cannot import name '_classify_event_type'`

- [ ] **Step 3: Add _classify_event_type helper to runner.py**

Add after the `_is_final_ai_message` function (around line 62) in `agent_md/core/runner.py`:

```python
def _classify_event_type(msg) -> str:
    """Map a LangChain message to an SSE event type.

    Returns one of: message, tool_call, tool_result, meta.
    """
    meta_type = getattr(msg, "additional_kwargs", {}).get("meta_type")
    if meta_type:
        return "meta"
    msg_type = getattr(msg, "type", "unknown")
    if msg_type == "ai" and hasattr(msg, "tool_calls") and msg.tool_calls:
        return "tool_call"
    if msg_type == "tool":
        return "tool_result"
    return "message"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_runner_events.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Add event_bus and cancel_event parameters to run()**

In `agent_md/core/runner.py`, modify the `run()` method signature (line 198) to add two new parameters:

```python
    async def run(
        self,
        config: AgentConfig,
        trigger_type: str = "manual",
        trigger_context: str | None = None,
        on_event=None,
        on_start=None,
        on_complete=None,
        arguments: str = "",
        event_bus=None,
        cancel_event: asyncio.Event | None = None,
        execution_id: int | None = None,
    ) -> dict:
```

- [ ] **Step 6: Add optional execution_id parameter to run()**

The API route needs to create the execution record *before* calling `run()` (to return the `execution_id` in the HTTP response). Add an optional `execution_id` parameter so the runner can reuse a pre-created record instead of creating a duplicate:

In the `run()` method, after the parameter list, modify the execution creation block (around line 231):

```python
        # Use pre-created execution_id or create a new one
        if execution_id is None:
            execution_id = await self.db.create_execution(
                agent_id=config.name, trigger=trigger_type, status="running"
            )
```

Add `execution_id: int | None = None` to the `run()` signature.

- [ ] **Step 7: Publish events to event_bus inside _stream()**

Inside the nested `_stream()` async generator in `run()`, change the `await ex_logger.log_message(msg)` line to capture the returned log ID, then publish to the event bus using that ID as the sequence number. This ensures the SSE `seq` matches the DB `log.id`, enabling correct dedup between replay and live events:

```python
                log_id = await ex_logger.log_message(msg)

                # Publish to event bus for SSE clients
                if event_bus is not None:
                    event_type = _classify_event_type(msg)
                    content = _extract_text(getattr(msg, "content", ""))[:500]
                    await event_bus.publish(execution_id, {
                        "type": event_type,
                        "seq": log_id,
                        "data": {
                            "event_type": event_type,
                            "content": content,
                            "agent_name": config.name,
                        },
                    })
```

Add the import at the top of the file:
```python
from agent_md.core.execution_logger import _extract_text
```

(Remove the lazy import of `_extract_text` used in the output extraction section around line 331.)

- [ ] **Step 7: Add cancellation check inside _stream()**

Inside the `_stream()` generator, after the event bus publishing block, add cancellation check:

```python
                # Check for cancellation
                if cancel_event is not None and cancel_event.is_set():
                    raise LimitExceeded("cancelled", "Execution cancelled by user")
```

- [ ] **Step 8: Publish complete event on all exit paths**

In each of the four exit paths (success, timeout, LimitExceeded, Exception), after calling `_finish_execution()`, publish a `complete` event:

```python
            if event_bus is not None:
                await event_bus.publish(execution_id, {
                    "type": "complete",
                    "seq": seq_counter,
                    "data": {
                        "status": result["status"],
                        "duration_ms": result.get("duration_ms"),
                        "total_tokens": result.get("total_tokens"),
                        "cost_usd": result.get("cost_usd"),
                    },
                })
```

- [ ] **Step 9: Run all tests to verify no regressions**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 10: Commit**

```bash
git add agent_md/core/runner.py tests/test_runner_events.py
git commit -m "feat: runner publishes events to EventBus and supports cancellation"
```

---

## Task 4: API Schemas

**Files:**
- Create: `agent_md/api/__init__.py`
- Create: `agent_md/api/schemas.py`

- [ ] **Step 1: Create api package**

```python
# agent_md/api/__init__.py
```

(Empty file — package init.)

- [ ] **Step 2: Write API schemas**

```python
# agent_md/api/schemas.py
"""Pydantic models for API request/response bodies."""

from __future__ import annotations

from pydantic import BaseModel


# --- Requests ---

class RunRequest(BaseModel):
    args: list[str] = []
    context: str | None = None


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


class SchedulerStatus(BaseModel):
    status: str  # "running" or "paused"
    jobs: list[SchedulerJob]


class SchedulerJob(BaseModel):
    agent_name: str
    trigger_type: str
    next_run: str | None = None


class ReloadResponse(BaseModel):
    agents_loaded: int


class CancelResponse(BaseModel):
    status: str
    execution_id: int


class ChatCreateResponse(BaseModel):
    execution_id: int
    model: str


class ChatMessageRequest(BaseModel):
    content: str


class ChatMessageResponse(BaseModel):
    status: str = "ok"


class ErrorResponse(BaseModel):
    detail: str
```

- [ ] **Step 3: Fix forward reference — move SchedulerJob before SchedulerStatus**

In the file above, `SchedulerStatus` references `SchedulerJob` which is defined after it. Move `SchedulerJob` class definition before `SchedulerStatus`.

- [ ] **Step 4: Commit**

```bash
git add agent_md/api/__init__.py agent_md/api/schemas.py
git commit -m "feat: add API Pydantic schemas for all endpoints"
```

---

## Task 5: FastAPI app factory, dependencies, and info routes

**Files:**
- Create: `agent_md/api/dependencies.py`
- Create: `agent_md/api/app.py`
- Create: `agent_md/api/routes/__init__.py`
- Create: `agent_md/api/routes/info.py`
- Create: `tests/api/__init__.py`
- Create: `tests/api/test_info.py`

- [ ] **Step 1: Write tests for info routes**

```python
# tests/api/__init__.py
```

```python
# tests/api/test_info.py
"""Tests for /health, /info, /shutdown routes."""

import pytest
from httpx import ASGITransport, AsyncClient
from agent_md.api.app import create_app


@pytest.fixture
async def app(tmp_path):
    application = create_app(workspace=tmp_path)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_info(client):
    resp = await client.get("/info")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    assert "pid" in data
    assert "uptime_seconds" in data
    assert "agents_loaded" in data


@pytest.mark.asyncio
async def test_shutdown(client):
    resp = await client.post("/shutdown")
    assert resp.status_code == 200
    assert resp.json()["message"] == "shutting down"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_info.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create dependencies module**

```python
# agent_md/api/dependencies.py
"""FastAPI dependency injection helpers.

All runtime state is stored on ``app.state`` and accessed via these
dependency functions, keeping route handlers decoupled from globals.
"""

from __future__ import annotations

from fastapi import Request

from agent_md.core.event_bus import EventBus
from agent_md.db.database import Database


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_event_bus(request: Request) -> EventBus:
    return request.app.state.event_bus


def get_runtime(request: Request):
    return request.app.state.runtime
```

- [ ] **Step 4: Create info routes**

```python
# agent_md/api/routes/__init__.py
```

```python
# agent_md/api/routes/info.py
"""Health, info, and shutdown endpoints."""

from __future__ import annotations

import asyncio
import os
import time

from fastapi import APIRouter, Request

from agent_md.api.schemas import HealthResponse, InfoResponse, ShutdownResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse()


@router.get("/info", response_model=InfoResponse)
async def info(request: Request):
    state = request.app.state
    rt = state.runtime

    scheduler_status = "off"
    if rt.scheduler:
        scheduler_status = "paused" if getattr(rt.scheduler, "_paused", False) else "running"

    running = await rt.db.list_running_executions()

    return InfoResponse(
        version=state.version,
        pid=os.getpid(),
        uptime_seconds=time.monotonic() - state.start_time,
        agents_loaded=len(rt.registry),
        agents_enabled=len(rt.registry.enabled()),
        scheduler_status=scheduler_status,
        watcher_active=rt.scheduler is not None,
        active_streams=state.event_bus.stream_count,
        active_executions=len(running),
    )


@router.post("/shutdown", response_model=ShutdownResponse)
async def shutdown(request: Request):
    state = request.app.state
    # Schedule shutdown after response is sent
    asyncio.get_event_loop().call_later(0.5, _trigger_shutdown, state)
    return ShutdownResponse()


def _trigger_shutdown(state):
    """Signal the lifecycle manager or server to stop."""
    if hasattr(state, "shutdown_event"):
        state.shutdown_event.set()
```

- [ ] **Step 5: Create FastAPI app factory**

```python
# agent_md/api/app.py
"""FastAPI application factory.

Creates the app with lifespan management — bootstraps the runtime on
startup and tears it down on shutdown.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from agent_md.core.bootstrap import bootstrap
from agent_md.core.event_bus import EventBus


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Startup: bootstrap runtime. Shutdown: close everything."""
    state = app.state

    # Bootstrap the full runtime
    rt = await bootstrap(
        workspace=state.workspace,
        start_scheduler=state.start_scheduler,
        on_event=state.on_event,
        on_start=state.on_start,
        on_complete=state.on_complete,
    )
    state.runtime = rt
    state.db = rt.db
    state.start_time = time.monotonic()
    state.shutdown_event = asyncio.Event()
    state.cancel_events: dict[int, asyncio.Event] = {}

    # Start lifecycle manager (idle timeout)
    from agent_md.core.lifecycle import LifecycleManager

    lifecycle = LifecycleManager(
        shutdown_event=state.shutdown_event,
        idle_timeout=300.0,
    )
    lifecycle.keep_alive = getattr(state, "keep_alive", False)
    lifecycle.has_scheduled_agents = lambda: bool(
        rt.scheduler and rt.scheduler.get_jobs()
    )
    lifecycle.has_running_executions = lambda: bool(
        state.cancel_events  # active executions have cancel events
    )
    lifecycle.has_active_streams = lambda: state.event_bus.stream_count > 0
    state.lifecycle = lifecycle

    lifecycle_task = asyncio.create_task(lifecycle.run())

    yield

    # Shutdown
    lifecycle_task.cancel()
    try:
        await lifecycle_task
    except asyncio.CancelledError:
        pass

    # Shutdown
    await rt.aclose()


def create_app(
    workspace: Path | None = None,
    start_scheduler: bool = False,
    on_event=None,
    on_start=None,
    on_complete=None,
) -> FastAPI:
    """Build and return the FastAPI application."""
    from agent_md.api.routes import info, agents, executions, scheduler

    app = FastAPI(
        title="AgentMD",
        description="Agent.md HTTP Backend",
        lifespan=_lifespan,
    )

    # Pre-lifespan state (available during lifespan startup)
    app.state.workspace = workspace
    app.state.start_scheduler = start_scheduler
    app.state.on_event = on_event
    app.state.on_start = on_start
    app.state.on_complete = on_complete
    app.state.event_bus = EventBus()

    # Version from package metadata
    try:
        from importlib.metadata import version
        app.state.version = version("agentmd")
    except Exception:
        app.state.version = "dev"

    # Register routers
    app.include_router(info.router)
    app.include_router(agents.router)
    app.include_router(executions.router)
    app.include_router(scheduler.router)

    return app
```

- [ ] **Step 6: Create stub route files so imports work**

The app factory imports all route modules. Create stubs for the ones not yet implemented:

```python
# agent_md/api/routes/agents.py
from fastapi import APIRouter
router = APIRouter(prefix="/agents", tags=["agents"])
```

```python
# agent_md/api/routes/executions.py
from fastapi import APIRouter
router = APIRouter(prefix="/executions", tags=["executions"])
```

```python
# agent_md/api/routes/scheduler.py
from fastapi import APIRouter
router = APIRouter(prefix="/scheduler", tags=["scheduler"])
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_info.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 8: Commit**

```bash
git add agent_md/api/ tests/api/
git commit -m "feat: FastAPI app factory with health/info/shutdown routes"
```

---

## Task 6: Agent routes

**Files:**
- Modify: `agent_md/api/routes/agents.py`
- Modify: `agent_md/core/scheduler.py`
- Create: `tests/api/test_agents.py`

- [ ] **Step 1: Add get_next_run to scheduler**

In `agent_md/core/scheduler.py`, add a method to `AgentScheduler` to get the next run time for an agent:

```python
    def get_next_run(self, agent_name: str) -> str | None:
        """Return ISO timestamp of next scheduled run for *agent_name*, or None."""
        job = self._scheduler.get_job(agent_name)
        if job and job.next_run_time:
            return job.next_run_time.isoformat()
        return None

    def get_jobs(self) -> list[dict]:
        """Return list of scheduled jobs with next_run times."""
        jobs = []
        for job in self._scheduler.get_jobs():
            jobs.append({
                "agent_name": job.id,
                "trigger_type": "schedule",
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            })
        return jobs
```

- [ ] **Step 2: Add pause/resume to scheduler**

In `agent_md/core/scheduler.py`, add pause/resume methods:

```python
    def pause(self) -> None:
        """Pause the scheduler (does not cancel running jobs)."""
        self._scheduler.pause()
        self._paused = True

    def resume(self) -> None:
        """Resume the scheduler."""
        self._scheduler.resume()
        self._paused = False
```

Add `self._paused = False` to `__init__`.

- [ ] **Step 3: Write tests for agent routes**

```python
# tests/api/test_agents.py
"""Tests for /agents endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient
from agent_md.api.app import create_app


@pytest.fixture
async def app_with_agents(tmp_path):
    # Create a minimal agent file
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "test-agent.md").write_text(
        "---\n"
        "model:\n"
        "  provider: google\n"
        "  name: gemini-2.5-flash\n"
        "---\n"
        "You are a test agent.\n"
    )
    application = create_app(workspace=tmp_path)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app_with_agents):
    transport = ASGITransport(app=app_with_agents)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_list_agents(client):
    resp = await client.get("/agents")
    assert resp.status_code == 200
    agents = resp.json()
    assert len(agents) >= 1
    assert any(a["name"] == "test-agent" for a in agents)


@pytest.mark.asyncio
async def test_get_agent_detail(client):
    resp = await client.get("/agents/test-agent")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "test-agent"
    assert data["model_provider"] == "google"


@pytest.mark.asyncio
async def test_get_agent_not_found(client):
    resp = await client.get("/agents/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_agent_runs_empty(client):
    resp = await client.get("/agents/test-agent/runs")
    assert resp.status_code == 200
    assert resp.json() == []
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_agents.py -v`
Expected: FAIL — routes not implemented

- [ ] **Step 5: Implement agent routes**

```python
# agent_md/api/routes/agents.py
"""Agent management endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request

from agent_md.api.schemas import (
    AgentDetail,
    AgentSummary,
    CancelResponse,
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


@router.post("/{name}/run", response_model=RunResponse)
async def run_agent(name: str, request: Request, body: RunRequest | None = None):
    rt = request.app.state.runtime
    state = request.app.state
    config = rt.registry.get(name)
    if not config:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")

    body = body or RunRequest()
    arguments = " ".join(body.args) if body.args else ""

    cancel_event = asyncio.Event()
    # Create execution eagerly so we can return the ID
    execution_id = await rt.db.create_execution(
        agent_id=config.name, trigger="manual", status="running"
    )
    state.cancel_events[execution_id] = cancel_event

    # Fire and forget — the execution runs in the background
    asyncio.create_task(
        _run_in_background(rt, config, execution_id, state, arguments, cancel_event)
    )

    return RunResponse(execution_id=execution_id)


async def _run_in_background(rt, config, execution_id, state, arguments, cancel_event):
    """Run agent execution as a background task."""
    try:
        await rt.runner.run(
            config,
            trigger_type="manual",
            arguments=arguments,
            event_bus=state.event_bus,
            cancel_event=cancel_event,
            execution_id=execution_id,
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
            id=e.id, agent_id=e.agent_id, status=e.status, trigger=e.trigger,
            started_at=e.started_at, finished_at=e.finished_at,
            duration_ms=e.duration_ms, input_tokens=e.input_tokens,
            output_tokens=e.output_tokens, total_tokens=e.total_tokens,
            cost_usd=e.cost_usd, error=e.error,
        )
        for e in execs
    ]


@router.post("/reload", response_model=ReloadResponse)
async def reload_agents(request: Request):
    rt = request.app.state.runtime
    from agent_md.core.parser import parse_agent_file

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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_agents.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add agent_md/api/routes/agents.py agent_md/core/scheduler.py tests/api/test_agents.py
git commit -m "feat: agent routes (/agents, /agents/{name}, /run, /runs, /reload)"
```

---

## Task 7: Execution routes and SSE stream

**Files:**
- Modify: `agent_md/api/routes/executions.py`
- Create: `tests/api/test_executions.py`

- [ ] **Step 1: Write tests for execution routes**

```python
# tests/api/test_executions.py
"""Tests for /executions endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient
from agent_md.api.app import create_app


@pytest.fixture
async def app(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    application = create_app(workspace=tmp_path)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_list_executions_empty(client):
    resp = await client.get("/executions")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_get_execution_not_found(client):
    resp = await client.get("/executions/9999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cancel_execution_not_found(client):
    resp = await client.delete("/executions/9999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_and_get_execution(app, client):
    # Create an execution directly in the DB
    rt = app.state.runtime
    eid = await rt.db.create_execution("test-agent", "manual")
    await rt.db.update_execution(eid, status="success", duration_ms=100)

    # List
    resp = await client.get("/executions")
    assert resp.status_code == 200
    execs = resp.json()
    assert len(execs) == 1
    assert execs[0]["id"] == eid

    # Detail
    resp = await client.get(f"/executions/{eid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == eid
    assert resp.json()["status"] == "success"


@pytest.mark.asyncio
async def test_get_execution_messages(app, client):
    rt = app.state.runtime
    eid = await rt.db.create_execution("test-agent", "manual")
    await rt.db.add_log(eid, "system", "System prompt")
    await rt.db.add_log(eid, "ai", "Hello")

    resp = await client.get(f"/executions/{eid}/messages")
    assert resp.status_code == 200
    msgs = resp.json()
    assert len(msgs) == 2
    assert msgs[0]["event_type"] == "system"
    assert msgs[1]["event_type"] == "ai"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_executions.py -v`
Expected: FAIL — routes not implemented

- [ ] **Step 3: Implement execution routes**

```python
# agent_md/api/routes/executions.py
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
    execs = await db.list_executions(
        agent_id=agent, status=status, limit=limit, offset=offset
    )
    return [
        ExecutionSummary(
            id=e.id, agent_id=e.agent_id, status=e.status, trigger=e.trigger,
            started_at=e.started_at, finished_at=e.finished_at,
            duration_ms=e.duration_ms, input_tokens=e.input_tokens,
            output_tokens=e.output_tokens, total_tokens=e.total_tokens,
            cost_usd=e.cost_usd, error=e.error,
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
        id=e.id, agent_id=e.agent_id, status=e.status, trigger=e.trigger,
        started_at=e.started_at, finished_at=e.finished_at,
        duration_ms=e.duration_ms, input_tokens=e.input_tokens,
        output_tokens=e.output_tokens, total_tokens=e.total_tokens,
        cost_usd=e.cost_usd, error=e.error, output_data=e.output_data,
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
            id=l.id, execution_id=l.execution_id, timestamp=l.timestamp,
            event_type=l.event_type, message=l.message, metadata=l.metadata,
        )
        for l in logs
    ]


@router.get("/{exec_id}/stream", response_class=EventSourceResponse)
async def stream_execution(exec_id: int, request: Request) -> AsyncIterable[ServerSentEvent]:
    db = request.app.state.db
    event_bus = request.app.state.event_bus

    e = await db.get_execution(exec_id)
    if not e:
        raise HTTPException(status_code=404, detail="Execution not found")

    async def event_generator() -> AsyncIterable[ServerSentEvent]:
        # 1. Subscribe BEFORE replay to avoid missing live events
        queue = event_bus.subscribe(exec_id)
        try:
            # 2. Replay historical logs from DB
            seen_seq = -1
            logs = await db.get_logs(exec_id, limit=10000)
            for log in logs:
                seen_seq = log.id
                yield ServerSentEvent(
                    data=json.dumps({
                        "event_type": log.event_type,
                        "message": log.message,
                        "timestamp": log.timestamp,
                    }),
                    event=log.event_type,
                    id=str(seen_seq),
                )

            # 3. Check if already finished
            execution = await db.get_execution(exec_id)
            if execution and execution.status not in ("running", "pending"):
                yield ServerSentEvent(
                    data=json.dumps({"status": execution.status}),
                    event="complete",
                )
                return

            # 4. Drain live events (dedup against replay)
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    # Keep-alive — check if execution still exists
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_executions.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add agent_md/api/routes/executions.py tests/api/test_executions.py
git commit -m "feat: execution routes with SSE streaming and cancellation"
```

---

## Task 8: Scheduler routes

**Files:**
- Modify: `agent_md/api/routes/scheduler.py`
- Create: `tests/api/test_scheduler.py`

- [ ] **Step 1: Write tests for scheduler routes**

```python
# tests/api/test_scheduler.py
"""Tests for /scheduler endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient
from agent_md.api.app import create_app


@pytest.fixture
async def app(tmp_path):
    application = create_app(workspace=tmp_path, start_scheduler=False)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_scheduler_status_no_scheduler(client):
    resp = await client.get("/scheduler")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "off"
    assert data["jobs"] == []


@pytest.mark.asyncio
async def test_scheduler_pause_no_scheduler(client):
    resp = await client.post("/scheduler/pause")
    assert resp.status_code == 409
```

- [ ] **Step 2: Implement scheduler routes**

```python
# agent_md/api/routes/scheduler.py
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
    jobs = [
        SchedulerJob(**j)
        for j in rt.scheduler.get_jobs()
    ]
    return SchedulerStatus(status=status, jobs=jobs)


@router.post("/pause")
async def pause_scheduler(request: Request):
    rt = request.app.state.runtime
    if not rt.scheduler:
        raise HTTPException(status_code=409, detail="No scheduler active")
    rt.scheduler.pause()
    return {"status": "paused"}


@router.post("/resume")
async def resume_scheduler(request: Request):
    rt = request.app.state.runtime
    if not rt.scheduler:
        raise HTTPException(status_code=409, detail="No scheduler active")
    rt.scheduler.resume()
    return {"status": "running"}
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_scheduler.py -v`
Expected: All 2 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add agent_md/api/routes/scheduler.py tests/api/test_scheduler.py
git commit -m "feat: scheduler routes (status, pause, resume)"
```

---

## Task 9: API key auth middleware

**Files:**
- Create: `agent_md/api/auth.py`
- Create: `tests/api/test_auth.py`

- [ ] **Step 1: Write tests for auth middleware**

```python
# tests/api/test_auth.py
"""Tests for API key authentication middleware."""

import pytest
from httpx import ASGITransport, AsyncClient
from agent_md.api.app import create_app
from agent_md.api.auth import ApiKeyMiddleware


@pytest.fixture
async def secured_app(tmp_path):
    application = create_app(workspace=tmp_path)
    application.add_middleware(ApiKeyMiddleware, api_key="test-secret-key")
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(secured_app):
    transport = ASGITransport(app=secured_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health_no_auth_required(client):
    resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_info_requires_auth(client):
    resp = await client.get("/info")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_info_with_valid_key(client):
    resp = await client.get("/info", headers={"X-API-Key": "test-secret-key"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_info_with_wrong_key(client):
    resp = await client.get("/info", headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 401
```

- [ ] **Step 2: Implement auth middleware**

```python
# agent_md/api/auth.py
"""API key middleware for TCP transport.

Only applied when the backend is started with --port. Unix socket
connections are implicitly trusted (file permissions are the gate).
"""

from __future__ import annotations

import json

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


_PUBLIC_PATHS = {"/health"}


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Require X-API-Key header on all routes except /health."""

    def __init__(self, app, api_key: str) -> None:
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        provided = request.headers.get("X-API-Key")
        if not provided or provided != self.api_key:
            return Response(
                content=json.dumps({"detail": "Invalid or missing API key"}),
                status_code=401,
                media_type="application/json",
            )

        return await call_next(request)
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_auth.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add agent_md/api/auth.py tests/api/test_auth.py
git commit -m "feat: API key middleware for TCP transport"
```

---

## Task 10: CLI client

**Files:**
- Create: `agent_md/cli/client.py`
- Create: `tests/test_cli_client.py`

The CLI client wraps httpx for communication with the backend over Unix socket (default) or TCP.

- [ ] **Step 1: Write tests for CLI client**

```python
# tests/test_cli_client.py
"""Tests for the CLI HTTP client."""

import pytest
from agent_md.cli.client import BackendClient, get_socket_path


def test_get_socket_path():
    path = get_socket_path()
    assert path.name == "agentmd.sock"
    assert "agentmd" in str(path)


def test_client_default_socket():
    client = BackendClient()
    assert client.base_url.startswith("http+unix://")


def test_client_tcp():
    client = BackendClient(host="127.0.0.1", port=4100, api_key="secret")
    assert client.base_url == "http://127.0.0.1:4100"
    assert client._api_key == "secret"
```

- [ ] **Step 2: Implement CLI client**

```python
# agent_md/cli/client.py
"""HTTP client for communicating with the agentmd backend.

Supports Unix domain socket (default) and TCP connections.
"""

from __future__ import annotations

import os
import urllib.parse
from pathlib import Path

import httpx


def get_state_dir() -> Path:
    """Return the XDG state directory for agentmd."""
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "state"
    return base / "agentmd"


def get_socket_path() -> Path:
    """Return the path to the Unix domain socket."""
    return get_state_dir() / "agentmd.sock"


def get_log_path() -> Path:
    """Return the path to the backend log file."""
    return get_state_dir() / "backend.log"


class BackendClient:
    """Thin HTTP client for the agentmd backend."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        api_key: str | None = None,
        socket_path: Path | None = None,
    ) -> None:
        self._api_key = api_key

        if host and port:
            # TCP mode
            self.base_url = f"http://{host}:{port}"
            self._transport = None
        else:
            # Unix socket mode
            sock = socket_path or get_socket_path()
            encoded = urllib.parse.quote(str(sock), safe="")
            self.base_url = f"http+unix://{encoded}"
            self._transport = httpx.HTTPTransport(uds=str(sock))

    def _client(self, **kwargs) -> httpx.Client:
        headers = kwargs.pop("headers", {})
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        transport = self._transport
        return httpx.Client(
            base_url=self.base_url,
            transport=transport,
            headers=headers,
            timeout=10.0,
            **kwargs,
        )

    def _async_client(self, **kwargs) -> httpx.AsyncClient:
        headers = kwargs.pop("headers", {})
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        transport = httpx.AsyncHTTPTransport(uds=str(get_socket_path())) if self._transport else None
        return httpx.AsyncClient(
            base_url=self.base_url,
            transport=transport,
            headers=headers,
            timeout=10.0,
            **kwargs,
        )

    def health_check(self) -> bool:
        """Return True if the backend is alive."""
        try:
            with self._client() as c:
                resp = c.get("/health")
                return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, OSError):
            return False

    def get(self, path: str, **kwargs) -> httpx.Response:
        with self._client() as c:
            return c.get(path, **kwargs)

    def post(self, path: str, **kwargs) -> httpx.Response:
        with self._client() as c:
            return c.post(path, **kwargs)

    def delete(self, path: str, **kwargs) -> httpx.Response:
        with self._client() as c:
            return c.delete(path, **kwargs)

    def stream_sse(self, path: str):
        """Open an SSE stream. Returns an httpx response to iterate over.

        Usage:
            with client.stream_sse("/executions/1/stream") as lines:
                for line in lines:
                    ...
        """
        client = self._client(timeout=httpx.Timeout(None))
        return client.stream("GET", path)
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `python -m pytest tests/test_cli_client.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add agent_md/cli/client.py tests/test_cli_client.py
git commit -m "feat: CLI HTTP client for Unix socket and TCP communication"
```

---

## Task 11: CLI auto-spawn

**Files:**
- Create: `agent_md/cli/spawn.py`

- [ ] **Step 1: Implement auto-spawn module**

```python
# agent_md/cli/spawn.py
"""Auto-spawn the backend process when needed.

The CLI detects whether the backend is alive via a health check on the
Unix socket. If it's not running, it spawns a new backend process with
stdout/stderr redirected to the log file, then polls until the socket
appears.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from agent_md.cli.client import BackendClient, get_log_path, get_socket_path, get_state_dir


def ensure_backend(client: BackendClient | None = None, workspace: Path | None = None) -> BackendClient:
    """Ensure the backend is running, spawning it if necessary.

    Returns a BackendClient connected to the running backend.
    """
    if os.environ.get("AGENTMD_NO_AUTOSPAWN") == "1":
        raise RuntimeError(
            "Backend is not running and AGENTMD_NO_AUTOSPAWN=1 is set. "
            "Start it manually with 'agentmd start'."
        )

    client = client or BackendClient()
    if client.health_check():
        return client

    # Spawn backend
    _spawn_backend(workspace)

    # Wait for socket to appear
    socket_path = get_socket_path()
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if socket_path.exists() and client.health_check():
            return client
        time.sleep(0.2)

    raise RuntimeError(
        f"Backend failed to start within 10s. Check logs at {get_log_path()}"
    )


def _spawn_backend(workspace: Path | None = None) -> int:
    """Spawn the backend as a detached process. Returns PID."""
    state_dir = get_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)

    log_path = get_log_path()

    cmd = [sys.executable, "-m", "agent_md.main", "start", "--internal-backend"]
    if workspace:
        cmd.extend(["--workspace", str(workspace)])

    log_file = open(log_path, "a")

    kwargs = {
        "stdout": log_file,
        "stderr": log_file,
        "stdin": subprocess.DEVNULL,
    }

    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        kwargs["start_new_session"] = True

    proc = subprocess.Popen(cmd, **kwargs)

    # Write PID for reference
    pid_path = state_dir / "backend.pid"
    pid_path.write_text(str(proc.pid))

    return proc.pid
```

- [ ] **Step 2: Commit**

```bash
git add agent_md/cli/spawn.py
git commit -m "feat: CLI auto-spawn for backend process"
```

---

## Task 12: Backend entry point

**Files:**
- Modify: `agent_md/main.py`
- Modify: `agent_md/cli/commands.py`

The `agentmd start` command becomes the backend launcher (foreground by default, `-d` for daemon). A hidden `--internal-backend` flag is used by the auto-spawn mechanism.

- [ ] **Step 1: Rewrite main.py with internal-backend support**

```python
# agent_md/main.py
from agent_md.cli import app

if __name__ == "__main__":
    app()
```

No changes to `main.py` — the `--internal-backend` flag is handled by the `start` command itself.

- [ ] **Step 2: Rewrite the start command**

In `agent_md/cli/commands.py`, replace the existing `start` command (around line 366) with:

```python
@app.command()
def start(
    workspace: Annotated[Optional[str], typer.Option("--workspace", "-w")] = None,
    daemon: Annotated[bool, typer.Option("--daemon", "-d")] = False,
    keep_alive: Annotated[bool, typer.Option("--keep-alive")] = False,
    port: Annotated[Optional[int], typer.Option("--port")] = None,
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    api_key: Annotated[Optional[str], typer.Option("--api-key")] = None,
    internal_backend: Annotated[bool, typer.Option("--internal-backend", hidden=True)] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q")] = False,
):
    """Start the AgentMD backend."""
    import asyncio
    from pathlib import Path
    from rich.console import Console

    console = Console()
    ws = Path(workspace) if workspace else None

    if daemon and not internal_backend:
        # Spawn in background via the spawn module
        from agent_md.cli.spawn import _spawn_backend
        from agent_md.cli.client import BackendClient, get_log_path

        client = BackendClient()
        if client.health_check():
            console.print("[yellow]Backend is already running.[/yellow]")
            return

        pid = _spawn_backend(ws)
        console.print(f"[green]Backend started[/green] (PID {pid})")
        console.print(f"  Logs: {get_log_path()}")
        return

    # Foreground or --internal-backend mode
    if not quiet and not internal_backend:
        console.print("[bold]AgentMD Backend[/bold]")

    asyncio.run(_run_backend(ws, keep_alive, port, host, api_key, quiet or internal_backend))
```

- [ ] **Step 3: Implement _run_backend async function**

Add to `agent_md/cli/commands.py`:

```python
async def _run_backend(
    workspace: Path | None,
    keep_alive: bool,
    port: int | None,
    host: str,
    api_key: str | None,
    quiet: bool,
):
    """Run the FastAPI backend with uvicorn."""
    import uvicorn
    from agent_md.api.app import create_app
    from agent_md.cli.client import get_socket_path, get_state_dir

    app = create_app(workspace=workspace, start_scheduler=True)
    app.state.keep_alive = keep_alive

    socket_path = get_socket_path()
    state_dir = get_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)

    # Clean up stale socket
    if socket_path.exists():
        socket_path.unlink()

    if api_key and port:
        from agent_md.api.auth import ApiKeyMiddleware
        app.add_middleware(ApiKeyMiddleware, api_key=api_key)

    config = uvicorn.Config(
        app,
        uds=str(socket_path),
        log_level="warning" if quiet else "info",
    )
    server = uvicorn.Server(config)

    # Set socket permissions after it's created
    async def _set_socket_perms():
        while not socket_path.exists():
            await asyncio.sleep(0.1)
        socket_path.chmod(0o600)

    # Watch for shutdown signal from lifecycle or /shutdown endpoint
    async def _watch_shutdown():
        # Wait for app to start and state to be initialized
        while not hasattr(app.state, "shutdown_event"):
            await asyncio.sleep(0.1)
        await app.state.shutdown_event.wait()
        server.should_exit = True

    asyncio.create_task(_set_socket_perms())
    asyncio.create_task(_watch_shutdown())

    if port:
        # Run both UDS and TCP — two uvicorn servers sharing the app
        tcp_config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="warning" if quiet else "info",
        )
        tcp_server = uvicorn.Server(tcp_config)

        async def _watch_shutdown_tcp():
            while not hasattr(app.state, "shutdown_event"):
                await asyncio.sleep(0.1)
            await app.state.shutdown_event.wait()
            tcp_server.should_exit = True

        asyncio.create_task(_watch_shutdown_tcp())
        await asyncio.gather(server.serve(), tcp_server.serve())
    else:
        await server.serve()
```

- [ ] **Step 4: Rewrite the stop command**

Replace the existing `stop` command:

```python
@app.command()
def stop(
    workspace: Annotated[Optional[str], typer.Option("--workspace", "-w")] = None,
):
    """Stop the AgentMD backend."""
    from rich.console import Console
    from agent_md.cli.client import BackendClient

    console = Console()
    client = BackendClient()

    if not client.health_check():
        console.print("[yellow]Backend is not running.[/yellow]")
        return

    try:
        resp = client.post("/shutdown")
        if resp.status_code == 200:
            console.print("[green]Backend is shutting down.[/green]")
        else:
            console.print(f"[red]Shutdown failed: {resp.text}[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
```

- [ ] **Step 5: Rewrite the status command**

Replace the existing `status` command:

```python
@app.command()
def status(
    workspace: Annotated[Optional[str], typer.Option("--workspace", "-w")] = None,
):
    """Check the AgentMD backend status."""
    from rich.console import Console
    from rich.table import Table
    from agent_md.cli.client import BackendClient, get_log_path

    console = Console()
    client = BackendClient()

    if not client.health_check():
        console.print("[dim]Backend is not running.[/dim]")
        console.print("  Start with: [bold]agentmd start[/bold]")
        return

    try:
        resp = client.get("/info")
        info = resp.json()

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style="dim")
        table.add_column()

        table.add_row("Status", "[green]running[/green]")
        table.add_row("PID", str(info["pid"]))

        # Format uptime
        secs = int(info["uptime_seconds"])
        hours, remainder = divmod(secs, 3600)
        minutes, secs = divmod(remainder, 60)
        uptime = f"{hours}h {minutes}m {secs}s" if hours else f"{minutes}m {secs}s"
        table.add_row("Uptime", uptime)

        table.add_row("Version", info["version"])
        table.add_row("Agents", f"{info['agents_enabled']} enabled / {info['agents_loaded']} loaded")
        table.add_row("Scheduler", info["scheduler_status"])
        table.add_row("Active executions", str(info["active_executions"]))
        table.add_row("SSE streams", str(info["active_streams"]))
        table.add_row("Log file", str(get_log_path()))

        console.print(table)
    except Exception as e:
        console.print(f"[red]Error getting status: {e}[/red]")
```

- [ ] **Step 6: Run existing tests to check for regressions**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add agent_md/main.py agent_md/cli/commands.py
git commit -m "feat: backend entry point with start/stop/status commands"
```

---

## Task 13: CLI run and chat as thin clients

**Files:**
- Modify: `agent_md/cli/commands.py`

- [ ] **Step 1: Rewrite the run command**

Replace the existing `run` command with a thin client that auto-spawns the backend, triggers execution via POST, then streams SSE events to the console:

```python
@app.command(context_settings={"allow_extra_args": True, "allow_interspersed_args": False})
def run(
    ctx: typer.Context,
    agent: Annotated[Optional[str], typer.Argument()] = None,
    workspace: Annotated[Optional[str], typer.Option("--workspace", "-w")] = None,
    quiet: Annotated[bool, typer.Option("--quiet", "-q")] = False,
):
    """Execute a single agent."""
    import json
    from pathlib import Path
    from rich.console import Console
    from agent_md.cli.client import BackendClient
    from agent_md.cli.spawn import ensure_backend

    console = Console()

    if not agent:
        # Interactive picker — use existing static listing
        ws = Path(workspace) if workspace else None
        agent = _pick_or_resolve_agent(ws)
        if not agent:
            return

    # Ensure backend is running
    try:
        client = ensure_backend(workspace=Path(workspace) if workspace else None)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    # Extra args from -- separator
    arguments = ctx.args

    # Trigger execution
    body = {"args": arguments} if arguments else {}
    resp = client.post(f"/agents/{agent}/run", json=body)
    if resp.status_code == 404:
        console.print(f"[red]Agent '{agent}' not found.[/red]")
        raise typer.Exit(1)
    if resp.status_code != 200:
        console.print(f"[red]Error: {resp.text}[/red]")
        raise typer.Exit(1)

    execution_id = resp.json()["execution_id"]
    if not quiet:
        console.print(f"[dim]Execution {execution_id} started[/dim]")

    # Stream SSE events
    try:
        _stream_execution(client, execution_id, console, quiet)
    except KeyboardInterrupt:
        # Cancel on Ctrl+C
        console.print("\n[yellow]Cancelling...[/yellow]")
        client.delete(f"/executions/{execution_id}")


def _stream_execution(client, execution_id: int, console, quiet: bool):
    """Stream SSE events from an execution and print them."""
    import json
    import httpx

    with client.stream_sse(f"/executions/{execution_id}/stream") as response:
        event_type = None
        data_buffer = ""

        for line in response.iter_lines():
            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                data_buffer = line[5:].strip()
            elif line == "" and data_buffer:
                # Empty line = end of event
                try:
                    data = json.loads(data_buffer)
                except json.JSONDecodeError:
                    data = {"raw": data_buffer}

                if event_type == "complete":
                    if not quiet:
                        status = data.get("status", "unknown")
                        tokens = data.get("total_tokens")
                        cost = data.get("cost_usd")
                        parts = [f"[bold]{status}[/bold]"]
                        if tokens:
                            parts.append(f"{tokens} tokens")
                        if cost:
                            parts.append(f"${cost:.4f}")
                        console.print(f"\n[dim]{'  |  '.join(parts)}[/dim]")
                    break
                elif not quiet:
                    _print_event(console, event_type, data)

                data_buffer = ""
                event_type = None


def _print_event(console, event_type: str, data: dict):
    """Format and print a single SSE event to the console."""
    content = data.get("content", data.get("message", ""))
    if event_type == "tool_call":
        tool = data.get("tool_name", "")
        console.print(f"  [cyan]⚡ {tool}[/cyan]")
    elif event_type == "tool_result" or event_type == "tool_response":
        tool = data.get("tool_name", "")
        result = content[:100]
        console.print(f"  [dim]↳ {tool}: {result}[/dim]")
    elif event_type == "ai":
        if content:
            console.print(f"  [white]{content[:300]}[/white]")
    elif event_type == "final_answer":
        console.print(f"\n{content}")
    elif event_type == "meta":
        pass  # Silently ignore meta messages in CLI
```

- [ ] **Step 2: Rewrite the chat command as thin client**

Replace the existing `chat` command. The flow is: create a chat session via POST, open the SSE stream in a background thread, then loop reading user input and sending messages via POST. The checkpointer already handles conversation state persistence — the backend just needs to keep the compiled graph warm per session.

```python
@app.command()
def chat(
    agent: Annotated[Optional[str], typer.Argument()] = None,
    workspace: Annotated[Optional[str], typer.Option("--workspace", "-w")] = None,
):
    """Start an interactive chat session with an agent."""
    import json
    import threading
    from pathlib import Path
    from rich.console import Console
    from agent_md.cli.client import BackendClient
    from agent_md.cli.spawn import ensure_backend

    console = Console()

    if not agent:
        ws = Path(workspace) if workspace else None
        agent = _pick_or_resolve_agent(ws)
        if not agent:
            return

    try:
        client = ensure_backend(workspace=Path(workspace) if workspace else None)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    # Create chat session
    resp = client.post(f"/agents/{agent}/chat")
    if resp.status_code == 404:
        console.print(f"[red]Agent '{agent}' not found.[/red]")
        raise typer.Exit(1)
    if resp.status_code != 200:
        console.print(f"[red]Error: {resp.text}[/red]")
        raise typer.Exit(1)

    data = resp.json()
    execution_id = data["execution_id"]
    model_info = data.get("model", "")
    console.print(f"[bold]Chat with {agent}[/bold] [dim]({model_info})[/dim]")
    console.print("[dim]Type /exit to end the session[/dim]\n")

    # Background SSE stream to print agent responses
    stop_event = threading.Event()

    def _stream_background():
        """Read SSE events and print them."""
        try:
            with client.stream_sse(f"/executions/{execution_id}/stream") as response:
                event_type = None
                data_buffer = ""
                for line in response.iter_lines():
                    if stop_event.is_set():
                        break
                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                    elif line.startswith("data:"):
                        data_buffer = line[5:].strip()
                    elif line == "" and data_buffer:
                        try:
                            evt_data = json.loads(data_buffer)
                        except json.JSONDecodeError:
                            evt_data = {"raw": data_buffer}
                        if event_type == "complete":
                            break
                        elif event_type == "turn_complete":
                            pass  # Signal that agent is done, prompt for input
                        elif event_type not in ("system", "human", "meta"):
                            _print_event(console, event_type, evt_data)
                        data_buffer = ""
                        event_type = None
        except Exception:
            pass

    stream_thread = threading.Thread(target=_stream_background, daemon=True)
    stream_thread.start()

    # Chat loop
    try:
        while True:
            try:
                user_input = console.input("[bold green]> [/bold green]")
            except EOFError:
                break

            if user_input.strip().lower() in ("/exit", "/quit"):
                break
            if not user_input.strip():
                continue

            # Send message
            resp = client.post(
                f"/executions/{execution_id}/message",
                json={"content": user_input},
            )
            if resp.status_code != 200:
                console.print(f"[red]Error: {resp.text}[/red]")
                break
    except KeyboardInterrupt:
        pass
    finally:
        console.print("\n[dim]Ending chat session...[/dim]")
        stop_event.set()
        client.delete(f"/executions/{execution_id}")

        # Print summary
        resp = client.get(f"/executions/{execution_id}")
        if resp.status_code == 200:
            detail = resp.json()
            tokens = detail.get("total_tokens")
            cost = detail.get("cost_usd")
            parts = []
            if tokens:
                parts.append(f"{tokens} tokens")
            if cost:
                parts.append(f"${cost:.4f}")
            if parts:
                console.print(f"[dim]{'  |  '.join(parts)}[/dim]")
```

- [ ] **Step 3: Run tests to check for regressions**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add agent_md/cli/commands.py
git commit -m "feat: CLI run command as thin client with SSE streaming"
```

---

## Task 14: Lifecycle manager

**Files:**
- Create: `agent_md/core/lifecycle.py`
- Create: `tests/test_lifecycle.py`

- [ ] **Step 1: Write lifecycle tests**

```python
# tests/test_lifecycle.py
"""Tests for the lifecycle manager (idle timeout)."""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock
from agent_md.core.lifecycle import LifecycleManager


@pytest.fixture
def lifecycle():
    shutdown_event = asyncio.Event()
    return LifecycleManager(
        shutdown_event=shutdown_event,
        idle_timeout=1,  # 1 second for tests
        check_interval=0.2,
    )


@pytest.mark.asyncio
async def test_idle_triggers_shutdown(lifecycle):
    # No scheduler, no executions, no streams
    lifecycle.has_scheduled_agents = lambda: False
    lifecycle.has_running_executions = lambda: False
    lifecycle.has_active_streams = lambda: False

    task = asyncio.create_task(lifecycle.run())
    await asyncio.sleep(1.5)
    assert lifecycle.shutdown_event.is_set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_keep_alive_prevents_shutdown(lifecycle):
    lifecycle.keep_alive = True
    lifecycle.has_scheduled_agents = lambda: False
    lifecycle.has_running_executions = lambda: False
    lifecycle.has_active_streams = lambda: False

    task = asyncio.create_task(lifecycle.run())
    await asyncio.sleep(1.5)
    assert not lifecycle.shutdown_event.is_set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_scheduler_prevents_shutdown(lifecycle):
    lifecycle.has_scheduled_agents = lambda: True
    lifecycle.has_running_executions = lambda: False
    lifecycle.has_active_streams = lambda: False

    task = asyncio.create_task(lifecycle.run())
    await asyncio.sleep(1.5)
    assert not lifecycle.shutdown_event.is_set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_active_streams_prevent_shutdown(lifecycle):
    lifecycle.has_scheduled_agents = lambda: False
    lifecycle.has_running_executions = lambda: False
    lifecycle.has_active_streams = lambda: True

    task = asyncio.create_task(lifecycle.run())
    await asyncio.sleep(1.5)
    assert not lifecycle.shutdown_event.is_set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_lifecycle.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement lifecycle manager**

```python
# agent_md/core/lifecycle.py
"""Lifecycle manager — idle timeout and graceful shutdown.

Periodically checks whether the backend has any active work. If all
conditions are idle for longer than ``idle_timeout``, triggers a
graceful shutdown via the shared ``shutdown_event``.
"""

from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class LifecycleManager:
    """Monitors backend activity and triggers shutdown when idle."""

    def __init__(
        self,
        shutdown_event: asyncio.Event,
        idle_timeout: float = 300.0,
        check_interval: float = 30.0,
    ) -> None:
        self.shutdown_event = shutdown_event
        self.idle_timeout = idle_timeout
        self.check_interval = check_interval
        self.keep_alive = False
        self._idle_since: float | None = None

        # These are set by the app after construction
        self.has_scheduled_agents: callable = lambda: False
        self.has_running_executions: callable = lambda: False
        self.has_active_streams: callable = lambda: False

    def _is_idle(self) -> bool:
        """Check if all idle conditions are met."""
        if self.has_scheduled_agents():
            return False
        if self.has_running_executions():
            return False
        if self.has_active_streams():
            return False
        return True

    async def run(self) -> None:
        """Run the lifecycle check loop until shutdown is triggered."""
        while not self.shutdown_event.is_set():
            if self.keep_alive:
                await asyncio.sleep(self.check_interval)
                continue

            if self._is_idle():
                if self._idle_since is None:
                    self._idle_since = time.monotonic()
                    logger.info("Backend is idle, starting timeout countdown")

                elapsed = time.monotonic() - self._idle_since
                if elapsed >= self.idle_timeout:
                    logger.info(
                        f"Idle for {elapsed:.0f}s (timeout={self.idle_timeout}s), "
                        "triggering shutdown"
                    )
                    self.shutdown_event.set()
                    return
            else:
                if self._idle_since is not None:
                    logger.info("Backend is active again, resetting idle timer")
                self._idle_since = None

            await asyncio.sleep(self.check_interval)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_lifecycle.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add agent_md/core/lifecycle.py tests/test_lifecycle.py
git commit -m "feat: lifecycle manager with idle timeout and keep-alive"
```

---

## Task 15: DB read-only for CLI static commands and daemon removal

**Files:**
- Modify: `agent_md/core/services.py`
- Modify: `agent_md/db/database.py`
- Remove: `agent_md/cli/daemon.py`
- Modify: `agent_md/cli/commands.py`

CLI static commands (`list`, `logs`, `validate`) should open the DB in read-only mode so they don't interfere with the backend writer.

- [ ] **Step 1: Add read-only connection support to Database**

In `agent_md/db/database.py`, modify `connect()` to accept a `readonly` parameter:

```python
    async def connect(self, readonly: bool = False) -> None:
        """Connect to the database."""
        if readonly:
            uri = f"file:{self.db_path}?mode=ro"
            self._conn = await aiosqlite.connect(uri, uri=True)
        else:
            self._conn = await aiosqlite.connect(self.db_path)
            await self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.row_factory = aiosqlite.Row
        if not readonly:
            await self._conn.executescript(SCHEMA)
            for migration in MIGRATIONS:
                try:
                    await self._conn.execute(migration)
                    await self._conn.commit()
                except Exception:
                    pass
```

- [ ] **Step 2: Update services.py _runtime to use read-only when not writing**

Add a `readonly` parameter to `_runtime`:

```python
@asynccontextmanager
async def _runtime(workspace: Path | None = None, readonly: bool = False, **kwargs):
    """Async context manager that bootstraps and auto-closes a Runtime."""
    rt = await bootstrap(workspace, readonly=readonly, **kwargs)
    try:
        yield rt
    finally:
        await rt.aclose()
```

- [ ] **Step 3: Pass readonly to bootstrap**

In `agent_md/core/bootstrap.py`, add `readonly: bool = False` parameter to `bootstrap()` and pass it to `db.connect()`:

```python
async def bootstrap(
    workspace: Path | None = None,
    agents_dir: Path | None = None,
    db_path: Path | None = None,
    mcp_config: Path | None = None,
    start_scheduler: bool = False,
    readonly: bool = False,
    on_event=None,
    on_complete=None,
    on_start=None,
) -> Runtime:
```

Change line 143-144 from:
```python
    db = Database(resolved_db_path)
    await db.connect()
```
to:
```python
    db = Database(resolved_db_path)
    await db.connect(readonly=readonly)
```

Skip orphan sweep when readonly:
```python
    if not readonly:
        orphan_count = await sweep_orphans(db)
```

- [ ] **Step 4: Update static service functions to use readonly**

In `agent_md/core/services.py`, update the read-only service functions:

```python
async def list_agents(workspace: Path | None = None) -> list[AgentConfig]:
    async with _runtime(workspace, readonly=True) as rt:
        return rt.registry.all()

async def get_agent_logs(agent_name: str, n: int, workspace: Path | None = None) -> list:
    async with _runtime(workspace, readonly=True) as rt:
        return await rt.db.get_executions(agent_name, limit=n)

async def get_execution_messages(execution_id: int, workspace: Path | None = None) -> list:
    async with _runtime(workspace, readonly=True) as rt:
        return await rt.db.get_logs(execution_id)

async def get_last_execution(agent_name: str, workspace: Path | None = None) -> object | None:
    async with _runtime(workspace, readonly=True) as rt:
        return await rt.db.get_last_execution(agent_name)
```

- [ ] **Step 5: Remove daemon.py**

```bash
git rm agent_md/cli/daemon.py
```

- [ ] **Step 6: Remove daemon imports from commands.py**

In `agent_md/cli/commands.py`, remove all imports from `agent_md.cli.daemon` (`is_running`, `start_daemon`, `stop_daemon`, `get_daemon_uptime`, `get_daemon_start_time`, `get_log_file`).

Also remove the `_follow_logs` helper that reads the daemon log file (it will be reimplemented to read from `get_log_path()` if needed).

- [ ] **Step 7: Run all tests to verify no regressions**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 8: Commit**

```bash
git add agent_md/db/database.py agent_md/core/services.py agent_md/core/bootstrap.py agent_md/cli/commands.py
git commit -m "feat: DB read-only mode for CLI, remove old daemon"
```

---

## Task 16: Documentation and release prep

**Files:**
- Create: `docs/api.md`
- Create: `docs/migration-0.8.md`
- Modify: `docs/architecture.md` (if exists)
- Modify: `CHANGELOG.md`
- Modify: `README.md`
- Modify: `pyproject.toml` (version bump)
- Modify: `mkdocs.yml`

- [ ] **Step 1: Create API reference doc**

```markdown
# REST API Reference

AgentMD exposes an HTTP API over a Unix domain socket. The CLI uses this
API internally — you can also use it directly for integrations.

## Connection

**Unix socket (default):**
```bash
curl --unix-socket ~/.local/state/agentmd/agentmd.sock http://localhost/health
```

**TCP (opt-in):** Start with `agentmd start --port 4100 --api-key YOUR_KEY`, then:
```bash
curl -H "X-API-Key: YOUR_KEY" http://127.0.0.1:4100/health
```

## Endpoints

### Health & Info

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | No | Liveness check |
| GET | `/info` | Yes | Backend status (version, pid, uptime, agents, scheduler) |
| POST | `/shutdown` | Yes | Graceful shutdown |

### Agents

| Method | Path | Description |
|--------|------|-------------|
| GET | `/agents` | List all agents |
| GET | `/agents/{name}` | Agent detail (config + last_run + next_run) |
| POST | `/agents/{name}/run` | Start execution, returns `{execution_id}` |
| GET | `/agents/{name}/runs` | Execution history for agent |
| POST | `/agents/{name}/chat` | Create chat session, returns `{execution_id, model}` |
| POST | `/agents/reload` | Re-parse agent files from disk |

**Run request body:**
```json
{"args": ["arg1", "arg2"], "context": "optional context"}
```

### Executions

| Method | Path | Description |
|--------|------|-------------|
| GET | `/executions` | List executions (filters: `status`, `agent`, `limit`, `offset`) |
| GET | `/executions/{id}` | Execution detail |
| GET | `/executions/{id}/messages` | Full message log |
| GET | `/executions/{id}/stream` | SSE stream (catchup + live) — also used for chat |
| POST | `/executions/{id}/message` | Send message in a chat session |
| DELETE | `/executions/{id}` | Cancel running execution or end chat session |

**SSE event types:** `message`, `meta`, `tool_call`, `tool_result`, `ai`, `final_answer`, `turn_complete`, `complete`

### Scheduler

| Method | Path | Description |
|--------|------|-------------|
| GET | `/scheduler` | Status + jobs with next_run |
| POST | `/scheduler/pause` | Pause scheduler |
| POST | `/scheduler/resume` | Resume scheduler |

## OpenAPI

Interactive docs available at `/docs` (Swagger) and `/redoc` when the backend is running.
```

- [ ] **Step 2: Create migration guide**

```markdown
# Migration Guide: v0.7.x → v0.8.0

## Breaking Changes

### Backend replaces daemon

The `agentmd start` command now runs a FastAPI HTTP backend instead of
the old foreground daemon. The CLI communicates with it via Unix socket.

**What changed:**
- `agentmd start` runs the backend in **foreground** (was background)
- Use `agentmd start -d` for background (daemon) mode
- `agentmd run` auto-starts the backend if needed
- `agentmd stop` sends a shutdown request via HTTP (was SIGTERM)
- `agentmd status` queries the backend API (was PID file check)

**What didn't change:**
- Agent `.md` files — same format, same location
- Custom tools — same `@tool` interface
- CLI commands — same names and arguments
- `agentmd list`, `logs`, `validate` — still work without backend

### New dependencies

`fastapi`, `uvicorn`, and `httpx` are now core dependencies.

### Database

The backend is the sole writer. CLI read-only commands (`list`, `logs`,
`validate`) open the DB in read-only mode with WAL, so they work even
while the backend is running.

### PID files

Old PID files at `workspace/data/agentmd.pid` are ignored. The new
backend stores its PID at `~/.local/state/agentmd/backend.pid`.

### Environment variable

Set `AGENTMD_NO_AUTOSPAWN=1` to prevent auto-starting the backend in
CI/container environments.
```

- [ ] **Step 3: Update CHANGELOG.md**

Add v0.8.0 entry at the top:

```markdown
## [0.8.0] — 2026-04-XX

### Breaking Changes
- **Backend replaces daemon** — `agentmd start` now runs a FastAPI HTTP backend over Unix socket
- Old daemon (`daemon.py`) removed entirely
- `agentmd start` default changed to foreground (use `-d` for background)

### Added
- HTTP API with 17 endpoints (agents, executions, chat, scheduler, health)
- SSE streaming for real-time execution events (`/executions/{id}/stream`)
- Execution cancellation via `DELETE /executions/{id}`
- EventBus for in-memory pub/sub of execution events
- CLI auto-spawn — `agentmd run` starts the backend automatically if needed
- Lifecycle manager with idle timeout (5min default, `--keep-alive` to disable)
- API key authentication for TCP transport (`--port` + `--api-key`)
- DB WAL mode for concurrent read access
- `POST /agents/reload` to re-parse agent files
- Scheduler pause/resume via API
- `GET /agents/{name}` includes `next_run` for scheduled agents
- Interactive chat over HTTP (`POST /agents/{name}/chat` + `POST /executions/{id}/message`)
- Chat sessions use existing SSE stream and LangGraph checkpointer

### Changed
- CLI `run` command now streams via SSE instead of direct execution
- DB opened in read-only mode for static CLI commands (`list`, `logs`, `validate`)
- Backend is the sole DB writer (eliminates SQLite lock contention)

### Fixed
- Ghost processes no longer possible (backend owns all executions)
- Cold start eliminated for subsequent runs (backend keeps state warm)
```

- [ ] **Step 4: Update README.md**

Add backend section to README, update the architecture description to mention the HTTP backend.

- [ ] **Step 5: Bump version to 0.8.0**

In `pyproject.toml`:
```toml
version = "0.8.0"
```

- [ ] **Step 6: Update mkdocs.yml**

Add new pages to navigation:
```yaml
- REST API: api.md
- Migration v0.8: migration-0.8.md
```

- [ ] **Step 7: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 8: Run linter**

Run: `ruff check . && ruff format --check .`
Expected: No issues.

- [ ] **Step 9: Commit**

```bash
git add docs/api.md docs/migration-0.8.md CHANGELOG.md README.md pyproject.toml mkdocs.yml
git commit -m "docs: API reference, migration guide, changelog for v0.8.0"
```

---

## Task 17: Chat over HTTP

**Files:**
- Modify: `agent_md/api/routes/agents.py` (add `POST /agents/{name}/chat`)
- Modify: `agent_md/api/routes/executions.py` (add `POST /executions/{id}/message`)
- Modify: `agent_md/core/runner.py` (add `chat_turn` event bus support)
- Create: `tests/api/test_chat.py`

The chat session leverages the existing LangGraph checkpointer for state persistence. The backend keeps compiled graphs warm in `app.state.chat_sessions`. Each chat turn publishes events to the EventBus, so the existing SSE stream (`GET /executions/{id}/stream`) delivers responses in real-time. No new SSE infrastructure needed.

**Session state stored in `app.state.chat_sessions`:**
```python
@dataclass
class ChatSessionState:
    config: AgentConfig
    graph: Any  # compiled LangGraph
    messages: list  # accumulated messages
    ex_logger: ExecutionLogger
    timeout: float
    graph_config: dict | None
```

- [ ] **Step 1: Write tests for chat endpoints**

```python
# tests/api/test_chat.py
"""Tests for chat session endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient
from agent_md.api.app import create_app


@pytest.fixture
async def app(tmp_path):
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "chat-agent.md").write_text(
        "---\n"
        "model:\n"
        "  provider: google\n"
        "  name: gemini-2.5-flash\n"
        "history: low\n"
        "---\n"
        "You are a helpful assistant.\n"
    )
    application = create_app(workspace=tmp_path)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_create_chat_session(client):
    resp = await client.post("/agents/chat-agent/chat")
    assert resp.status_code == 200
    data = resp.json()
    assert "execution_id" in data
    assert "model" in data


@pytest.mark.asyncio
async def test_create_chat_not_found(client):
    resp = await client.post("/agents/nonexistent/chat")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_send_message_no_session(client):
    resp = await client.post("/executions/9999/message", json={"content": "hello"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_chat_creates_execution(app, client):
    resp = await client.post("/agents/chat-agent/chat")
    execution_id = resp.json()["execution_id"]
    # Verify execution exists in DB
    rt = app.state.runtime
    execution = await rt.db.get_execution(execution_id)
    assert execution is not None
    assert execution.trigger == "chat"
    assert execution.status == "running"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_chat.py -v`
Expected: FAIL — endpoints not implemented

- [ ] **Step 3: Add chat_sessions state to app lifespan**

In `agent_md/api/app.py`, inside the `_lifespan` function, after `state.cancel_events`, add:

```python
    state.chat_sessions: dict[int, object] = {}
```

- [ ] **Step 4: Add POST /agents/{name}/chat endpoint**

In `agent_md/api/routes/agents.py`, add the chat creation endpoint:

```python
from agent_md.api.schemas import ChatCreateResponse


@router.post("/{name}/chat", response_model=ChatCreateResponse)
async def create_chat(name: str, request: Request):
    """Create a new interactive chat session for an agent.

    Returns an execution_id. Open GET /executions/{id}/stream to receive
    events, then send messages via POST /executions/{id}/message.
    """
    rt = request.app.state.runtime
    state = request.app.state
    config = rt.registry.get(name)
    if not config:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")

    from agent_md.core.execution_logger import ExecutionLogger
    from agent_md.graph.builder import build_system_message

    # Create execution record
    execution_id = await rt.db.create_execution(
        agent_id=config.name, trigger="chat", status="running"
    )

    # Build graph and seed conversation
    graph = await rt.runner.prepare_agent(config)
    system_msg = build_system_message(config.system_prompt, config, rt.path_context)
    ex_logger = ExecutionLogger(rt.db, execution_id, config.name)
    await ex_logger.log_message(system_msg)

    graph_config = (
        {"configurable": {"thread_id": config.name}}
        if config.history != "off"
        else None
    )

    cancel_event = asyncio.Event()
    state.cancel_events[execution_id] = cancel_event

    # Store session state
    state.chat_sessions[execution_id] = {
        "config": config,
        "graph": graph,
        "messages": [system_msg],
        "ex_logger": ex_logger,
        "timeout": config.settings.timeout,
        "graph_config": graph_config,
    }

    model_info = f"{config.model.provider}/{config.model.name}" if config.model else ""
    return ChatCreateResponse(execution_id=execution_id, model=model_info)
```

- [ ] **Step 5: Add POST /executions/{id}/message endpoint**

In `agent_md/api/routes/executions.py`, add the message endpoint:

```python
from agent_md.api.schemas import ChatMessageRequest, ChatMessageResponse


@router.post("/{exec_id}/message", response_model=ChatMessageResponse)
async def send_message(exec_id: int, body: ChatMessageRequest, request: Request):
    """Send a user message in a chat session and trigger one agent turn.

    The agent's response is delivered via the SSE stream
    (GET /executions/{id}/stream). This endpoint returns immediately
    after the turn completes.
    """
    state = request.app.state
    session = state.chat_sessions.get(exec_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    from langchain_core.messages import HumanMessage
    from agent_md.core.execution_logger import _extract_text
    from agent_md.core.runner import _classify_event_type, _is_final_ai_message

    # Add user message
    human_msg = HumanMessage(content=body.content)
    session["messages"].append(human_msg)
    log_id = await session["ex_logger"].log_message(human_msg)

    # Publish user message to event bus
    event_bus = state.event_bus
    await event_bus.publish(exec_id, {
        "type": "message",
        "seq": log_id,
        "data": {
            "event_type": "human",
            "content": body.content[:500],
            "agent_name": session["config"].name,
        },
    })

    # Run one chat turn
    rt = state.runtime
    new_msgs, in_tok, out_tok = await rt.runner.chat_turn(
        session["graph"],
        session["messages"],
        session["ex_logger"],
        session["timeout"],
        graph_config=session["graph_config"],
    )

    session["messages"].extend(new_msgs)

    # Publish each new message to event bus
    for msg in new_msgs:
        event_type = _classify_event_type(msg)
        content = _extract_text(getattr(msg, "content", ""))[:500]
        log_id = await session["ex_logger"].log_message(msg)
        await event_bus.publish(exec_id, {
            "type": event_type,
            "seq": log_id,
            "data": {
                "event_type": event_type,
                "content": content,
                "agent_name": session["config"].name,
            },
        })

    # Signal turn complete
    await event_bus.publish(exec_id, {
        "type": "turn_complete",
        "seq": log_id + 1,
        "data": {
            "input_tokens": in_tok,
            "output_tokens": out_tok,
        },
    })

    return ChatMessageResponse()
```

- [ ] **Step 6: Clean up chat session on DELETE /executions/{id}**

In `agent_md/api/routes/executions.py`, update the `cancel_execution` handler to also clean up chat sessions:

Add after `cancel_event.set()`:

```python
    # Clean up chat session if this was a chat execution
    session = state.chat_sessions.pop(exec_id, None)
    if session:
        # Finalize the chat execution
        from agent_md.core.runner import AgentRunner
        duration_ms = 0  # TODO: track actual duration from session start
        await state.db.update_execution(
            exec_id, status="success",
            output_data="Chat session ended",
        )
        # Publish complete event
        await state.event_bus.publish(exec_id, {
            "type": "complete",
            "seq": 0,
            "data": {"status": "success"},
        })
        return CancelResponse(status="ended", execution_id=exec_id)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_chat.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 8: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 9: Commit**

```bash
git add agent_md/api/routes/agents.py agent_md/api/routes/executions.py agent_md/api/schemas.py agent_md/api/app.py tests/api/test_chat.py
git commit -m "feat: chat over HTTP with session management and SSE streaming"
```

---

## Summary

| Task | Description | Key files |
|------|-------------|-----------|
| 1 | Dependencies + EventBus | `pyproject.toml`, `event_bus.py` |
| 2 | Database enhancements | `database.py` |
| 3 | Runner event publishing + cancellation | `runner.py` |
| 4 | API schemas | `api/schemas.py` |
| 5 | FastAPI app + info routes | `api/app.py`, `api/routes/info.py` |
| 6 | Agent routes | `api/routes/agents.py` |
| 7 | Execution routes + SSE stream | `api/routes/executions.py` |
| 8 | Scheduler routes | `api/routes/scheduler.py` |
| 9 | API key auth | `api/auth.py` |
| 10 | CLI client | `cli/client.py` |
| 11 | CLI auto-spawn | `cli/spawn.py` |
| 12 | Backend entry point | `cli/commands.py`, `main.py` |
| 13 | CLI run/chat thin clients | `cli/commands.py` |
| 14 | Lifecycle manager | `lifecycle.py` |
| 15 | DB read-only + daemon removal | `database.py`, `services.py`, `daemon.py` |
| 16 | Documentation + release prep | `docs/`, `CHANGELOG.md`, `README.md` |
| 17 | Chat over HTTP | `api/routes/agents.py`, `api/routes/executions.py` |
