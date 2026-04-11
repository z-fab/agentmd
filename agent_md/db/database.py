from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite

from agent_md.db.models import ExecutionRecord, LogRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS executions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id      TEXT NOT NULL,
    status        TEXT NOT NULL,
    trigger       TEXT NOT NULL,
    started_at    TIMESTAMP NOT NULL,
    finished_at   TIMESTAMP,
    duration_ms   INTEGER,
    input_data    TEXT,
    output_data   TEXT,
    error         TEXT,
    input_tokens  INTEGER,
    output_tokens INTEGER,
    total_tokens  INTEGER,
    cost_usd      REAL,
    pid           INTEGER
);

CREATE TABLE IF NOT EXISTS execution_logs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id INTEGER NOT NULL,
    timestamp    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    event_type   TEXT NOT NULL,
    message      TEXT NOT NULL,
    metadata     TEXT
);

CREATE INDEX IF NOT EXISTS idx_executions_agent ON executions(agent_id);
CREATE INDEX IF NOT EXISTS idx_executions_status ON executions(status);
CREATE INDEX IF NOT EXISTS idx_logs_execution ON execution_logs(execution_id);
"""


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


class Database:
    """Async SQLite database manager."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def connect(self, readonly: bool = False) -> None:
        """Open the database connection and create tables."""
        if readonly:
            uri = f"file:{self.db_path}?mode=ro"
            self._db = await aiosqlite.connect(uri, uri=True)
            self._db.row_factory = aiosqlite.Row
        else:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db = await aiosqlite.connect(str(self.db_path))
            self._db.row_factory = aiosqlite.Row
            await self._db.execute("PRAGMA journal_mode=WAL")
            await self._db.executescript(SCHEMA)
            await self._db.commit()
        logger.info(f"Database connected: {self.db_path}")

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._db

    # --- Executions ---

    async def create_execution(self, agent_id: str, trigger: str, status: str = "running") -> int:
        """Create a new execution record. Returns the execution ID."""
        import os

        now = datetime.now(timezone.utc).isoformat()
        cursor = await self.db.execute(
            "INSERT INTO executions (agent_id, status, trigger, started_at, pid) VALUES (?, ?, ?, ?, ?)",
            (agent_id, status, trigger, now, os.getpid()),
        )
        await self.db.commit()
        return cursor.lastrowid

    async def update_execution(
        self,
        execution_id: int,
        status: str,
        duration_ms: Optional[int] = None,
        output_data: Optional[str] = None,
        error: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        total_tokens: Optional[int] = None,
        cost_usd: Optional[float] = None,
    ) -> None:
        """Update an execution with its final status."""
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            """
            UPDATE executions
            SET status = ?, finished_at = ?, duration_ms = ?,
                output_data = ?, error = ?,
                input_tokens = ?, output_tokens = ?, total_tokens = ?,
                cost_usd = ?
            WHERE id = ?
            """,
            (status, now, duration_ms, output_data, error, input_tokens, output_tokens, total_tokens, cost_usd, execution_id),
        )
        await self.db.commit()

    async def list_running_executions(self) -> list[ExecutionRecord]:
        """Get all executions with status 'running'."""
        cursor = await self.db.execute("SELECT * FROM executions WHERE status = 'running'")
        rows = await cursor.fetchall()
        return [ExecutionRecord(**dict(row)) for row in rows]

    async def get_executions(self, agent_id: str, limit: int = 10) -> list[ExecutionRecord]:
        """Get recent executions for an agent."""
        cursor = await self.db.execute(
            """
            SELECT * FROM executions
            WHERE agent_id = ?
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (agent_id, limit),
        )
        rows = await cursor.fetchall()
        return [ExecutionRecord(**dict(row)) for row in rows]

    async def get_last_execution(self, agent_id: str) -> Optional[ExecutionRecord]:
        """Get the most recent execution for an agent."""
        results = await self.get_executions(agent_id, limit=1)
        return results[0] if results else None

    async def get_execution(self, execution_id: int) -> Optional[ExecutionRecord]:
        """Get a single execution by ID."""
        cursor = await self.db.execute(
            "SELECT * FROM executions WHERE id = ?",
            (execution_id,),
        )
        row = await cursor.fetchone()
        return ExecutionRecord(**dict(row)) if row else None

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

    # --- Logs ---

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

    async def get_logs(self, execution_id: int, limit: int = 100) -> list[LogRecord]:
        """Get logs for an execution."""
        cursor = await self.db.execute(
            """
            SELECT * FROM execution_logs
            WHERE execution_id = ?
            ORDER BY timestamp ASC
            LIMIT ?
            """,
            (execution_id, limit),
        )
        rows = await cursor.fetchall()
        return [LogRecord(**dict(row)) for row in rows]
