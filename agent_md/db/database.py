from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite

from agent_md.db.models import ExecutionRecord, LogRecord, PendingInterruptRecord

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
    pid           INTEGER,
    parent_execution_id INTEGER
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

CREATE TABLE IF NOT EXISTS pending_interrupts (
    execution_id INTEGER PRIMARY KEY,
    request_id   TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at   TIMESTAMP NOT NULL
);
"""

# Columns that may be missing on DBs created before they were added.
_EXECUTIONS_MIGRATIONS: list[tuple[str, str]] = [
    ("cost_usd", "REAL"),
    ("pid", "INTEGER"),
    ("parent_execution_id", "INTEGER"),
]

_TERMINAL_STATUSES = frozenset({"success", "error", "aborted", "cancelled", "orphaned", "timeout"})


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
            if not self.db_path.exists():
                # Fresh install: create schema so readonly CLI commands don't crash.
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                async with aiosqlite.connect(str(self.db_path)) as tmp:
                    await tmp.execute("PRAGMA journal_mode=WAL")
                    await tmp.execute("PRAGMA synchronous=NORMAL")
                    await tmp.executescript(SCHEMA)
                    await tmp.commit()
                    await self._migrate(tmp)
            uri = f"file:{self.db_path}?mode=ro"
            self._db = await aiosqlite.connect(uri, uri=True)
            self._db.row_factory = aiosqlite.Row
        else:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db = await aiosqlite.connect(str(self.db_path))
            self._db.row_factory = aiosqlite.Row
            await self._db.execute("PRAGMA journal_mode=WAL")
            await self._db.execute("PRAGMA synchronous=NORMAL")
            await self._db.executescript(SCHEMA)
            await self._db.commit()
            await self._migrate(self._db)
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

    async def _migrate(self, db: aiosqlite.Connection) -> None:
        """Run schema migrations for columns added after initial release."""
        cursor = await db.execute("PRAGMA table_info(executions)")
        columns = {row[1] for row in await cursor.fetchall()}
        for col_name, col_type in _EXECUTIONS_MIGRATIONS:
            if col_name not in columns:
                await db.execute(f"ALTER TABLE executions ADD COLUMN {col_name} {col_type}")
                logger.info(f"Migration: added {col_name} column to executions")
        await db.commit()

    # --- Executions ---

    async def create_execution(
        self, agent_id: str, trigger: str, status: str = "running", parent_execution_id: int | None = None
    ) -> int:
        """Create a new execution record. Returns the execution ID."""
        import os

        now = datetime.now(timezone.utc).isoformat()
        cursor = await self.db.execute(
            "INSERT INTO executions (agent_id, status, trigger, started_at, pid, parent_execution_id) VALUES (?, ?, ?, ?, ?, ?)",
            (agent_id, status, trigger, now, os.getpid(), parent_execution_id),
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
        """Update an execution — only fields explicitly passed are written.

        ``finished_at`` is set only for terminal statuses.
        """
        sets = ["status = ?"]
        params: list = [status]

        if status in _TERMINAL_STATUSES:
            sets.append("finished_at = ?")
            params.append(datetime.now(timezone.utc).isoformat())

        optional = {
            "duration_ms": duration_ms,
            "output_data": output_data,
            "error": error,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "cost_usd": cost_usd,
        }
        for col, value in optional.items():
            if value is not None:
                sets.append(f"{col} = ?")
                params.append(value)

        params.append(execution_id)
        await self.db.execute(
            f"UPDATE executions SET {', '.join(sets)} WHERE id = ?",
            params,
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

    async def count_executions_by_agent_id(self, agent_id: str) -> int:
        """Count executions keyed by ``agent_id``."""
        cursor = await self.db.execute(
            "SELECT COUNT(*) AS n FROM executions WHERE agent_id = ?",
            (agent_id,),
        )
        row = await cursor.fetchone()
        return int(row["n"] if row else 0)

    async def rekey_agent_id(self, old_agent_id: str, new_agent_id: str) -> int:
        """Rewrite ``executions.agent_id`` from *old* to *new*. Returns rows updated."""
        if old_agent_id == new_agent_id:
            return 0
        cursor = await self.db.execute(
            "UPDATE executions SET agent_id = ? WHERE agent_id = ?",
            (new_agent_id, old_agent_id),
        )
        await self.db.commit()
        return cursor.rowcount

    async def get_last_execution(self, agent_id: str) -> Optional[ExecutionRecord]:
        """Get the most recent execution for an agent."""
        results = await self.get_executions(agent_id, limit=1)
        return results[0] if results else None

    async def get_last_finished_execution(self, agent_id: str, exclude_id: int | None = None):
        """Most recent execution for an agent that is not running/waiting/pending."""
        cursor = await self.db.execute(
            """
            SELECT * FROM executions
            WHERE agent_id = ?
              AND status NOT IN ('running', 'waiting', 'pending')
              AND (? IS NULL OR id != ?)
            ORDER BY id DESC
            LIMIT 1
            """,
            (agent_id, exclude_id, exclude_id),
        )
        row = await cursor.fetchone()
        return ExecutionRecord(**dict(row)) if row else None

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

    async def get_logs(self, execution_id: int, limit: int = 10_000) -> list[LogRecord]:
        """Get logs for an execution, ordered by insertion id (stable)."""
        cursor = await self.db.execute(
            """
            SELECT * FROM execution_logs
            WHERE execution_id = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (execution_id, limit),
        )
        rows = await cursor.fetchall()
        return [LogRecord(**dict(row)) for row in rows]

    async def count_logs(self, execution_id: int, event_type: str | None = None) -> int:
        """Count log rows for an execution, optionally filtered by event_type."""
        if event_type is None:
            cursor = await self.db.execute(
                "SELECT COUNT(*) AS n FROM execution_logs WHERE execution_id = ?",
                (execution_id,),
            )
        else:
            cursor = await self.db.execute(
                "SELECT COUNT(*) AS n FROM execution_logs WHERE execution_id = ? AND event_type = ?",
                (execution_id, event_type),
            )
        row = await cursor.fetchone()
        return int(row["n"] if row else 0)

    # --- Pending interrupts (HILT) ---

    async def set_pending_interrupt(self, execution_id: int, request_id: str, payload: dict) -> None:
        """Insert or replace the pending interrupt for an execution."""
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            """
            INSERT INTO pending_interrupts (execution_id, request_id, payload_json, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(execution_id) DO UPDATE SET
                request_id = excluded.request_id,
                payload_json = excluded.payload_json,
                created_at = excluded.created_at
            """,
            (execution_id, request_id, json.dumps(payload), now),
        )
        await self.db.commit()

    async def get_pending_interrupt(self, execution_id: int) -> Optional[PendingInterruptRecord]:
        cursor = await self.db.execute(
            "SELECT * FROM pending_interrupts WHERE execution_id = ?",
            (execution_id,),
        )
        row = await cursor.fetchone()
        return PendingInterruptRecord(**dict(row)) if row else None

    async def list_pending_interrupts(self) -> list[PendingInterruptRecord]:
        cursor = await self.db.execute("SELECT * FROM pending_interrupts ORDER BY created_at ASC")
        rows = await cursor.fetchall()
        return [PendingInterruptRecord(**dict(row)) for row in rows]

    async def clear_pending_interrupt(self, execution_id: int) -> None:
        await self.db.execute("DELETE FROM pending_interrupts WHERE execution_id = ?", (execution_id,))
        await self.db.commit()

    async def claim_execution_for_resume(self, execution_id: int) -> bool:
        """Atomically transition waiting -> running. Returns True if this caller won the claim."""
        cursor = await self.db.execute(
            "UPDATE executions SET status = 'running' WHERE id = ? AND status = 'waiting'",
            (execution_id,),
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def has_waiting_execution(self, agent_id: str) -> bool:
        cursor = await self.db.execute(
            "SELECT 1 FROM executions WHERE agent_id = ? AND status = 'waiting' LIMIT 1",
            (agent_id,),
        )
        return await cursor.fetchone() is not None

    # --- Checkpoint maintenance helpers ---

    async def latest_execution_id_per_agent(self) -> list[int]:
        cursor = await self.db.execute("SELECT MAX(id) AS mx FROM executions GROUP BY agent_id")
        rows = await cursor.fetchall()
        return [row["mx"] for row in rows if row["mx"] is not None]

    async def waiting_execution_ids(self) -> list[int]:
        cursor = await self.db.execute("SELECT id FROM executions WHERE status = 'waiting'")
        rows = await cursor.fetchall()
        return [row["id"] for row in rows]

    async def finished_execution_ids_before(self, cutoff_iso: str) -> list[int]:
        cursor = await self.db.execute(
            """
            SELECT id FROM executions
            WHERE status NOT IN ('running', 'waiting', 'pending')
              AND (finished_at IS NOT NULL AND finished_at < ?)
            """,
            (cutoff_iso,),
        )
        rows = await cursor.fetchall()
        return [row["id"] for row in rows]

    async def all_execution_ids_for_agent(self, agent_id: str) -> list[int]:
        cursor = await self.db.execute("SELECT id FROM executions WHERE agent_id = ?", (agent_id,))
        rows = await cursor.fetchall()
        return [row["id"] for row in rows]
