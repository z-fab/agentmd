"""Checkpoint database maintenance — HILT-aware retention (issue #12)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

# LangGraph's AsyncSqliteSaver tables that key on thread_id.
_CHECKPOINT_TABLES = ("checkpoints", "checkpoint_writes", "checkpoint_blobs")


def checkpoint_db_path(db_path: str | Path) -> Path:
    return Path(str(db_path).replace(".db", "_checkpoints.db"))


async def _delete_threads(cp_path: Path, thread_ids: list[str]) -> int:
    if not thread_ids or not cp_path.exists():
        return 0
    async with aiosqlite.connect(str(cp_path)) as conn:
        cur = await conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing = {r[0] for r in await cur.fetchall()}
        for tid in thread_ids:
            for table in _CHECKPOINT_TABLES:
                if table in existing:
                    await conn.execute(f"DELETE FROM {table} WHERE thread_id = ?", (tid,))  # noqa: S608
        await conn.commit()
    return len(thread_ids)


async def sweep_old_checkpoints(db, db_path: str | Path, retention_days: int) -> int:
    """Delete checkpoint threads for finished executions older than retention_days.

    Preserves the latest execution per agent (history seeding) and all waiting
    executions (resume). Returns the number of threads removed. retention_days<=0
    disables the sweep.
    """
    if not retention_days or retention_days <= 0:
        return 0
    cp_path = checkpoint_db_path(db_path)
    if not cp_path.exists():
        return 0

    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    keep = set(await db.latest_execution_id_per_agent()) | set(await db.waiting_execution_ids())
    eligible = [eid for eid in await db.finished_execution_ids_before(cutoff) if eid not in keep]
    removed = await _delete_threads(cp_path, [str(eid) for eid in eligible])
    if removed:
        logger.info(f"Checkpoint sweep: removed {removed} old thread(s)")
    return removed


async def checkpoint_stats(db, db_path: str | Path) -> dict:
    """Return {agent_id: thread_count} and total file size in bytes."""
    cp_path = checkpoint_db_path(db_path)
    stats = {"path": str(cp_path), "size_bytes": cp_path.stat().st_size if cp_path.exists() else 0, "threads": 0, "per_agent": {}}
    if not cp_path.exists():
        return stats
    async with aiosqlite.connect(str(cp_path)) as conn:
        cur = await conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing = {r[0] for r in await cur.fetchall()}
        if "checkpoints" not in existing:
            return stats
        cur = await conn.execute("SELECT DISTINCT thread_id FROM checkpoints")
        thread_ids = [r[0] for r in await cur.fetchall()]
    stats["threads"] = len(thread_ids)
    for tid in thread_ids:
        try:
            rec = await db.get_execution(int(tid))
        except (ValueError, TypeError):
            rec = None
        agent = rec.agent_id if rec else "(unknown)"
        stats["per_agent"][agent] = stats["per_agent"].get(agent, 0) + 1
    return stats


async def purge_checkpoints(db, db_path: str | Path, agent: str | None = None, force: bool = False) -> int:
    """Manual purge. Without force, preserves the keep-set. With force, wipes targeted threads."""
    cp_path = checkpoint_db_path(db_path)
    if not cp_path.exists():
        return 0
    keep = set() if force else set(await db.latest_execution_id_per_agent()) | set(await db.waiting_execution_ids())

    if agent:
        targets = [eid for eid in await db.all_execution_ids_for_agent(agent) if eid not in keep]
    else:
        async with aiosqlite.connect(str(cp_path)) as conn:
            cur = await conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing = {r[0] for r in await cur.fetchall()}
            if "checkpoints" not in existing:
                return 0
            cur = await conn.execute("SELECT DISTINCT thread_id FROM checkpoints")
            all_threads = [r[0] for r in await cur.fetchall()]
        targets = [int(t) for t in all_threads if t.isdigit() and int(t) not in keep]

    return await _delete_threads(cp_path, [str(t) for t in targets])
