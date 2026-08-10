import aiosqlite
from datetime import datetime, timedelta, timezone
from agent_md.execution import checkpoint_maint as cm


async def _make_checkpoint_db(path, thread_ids):
    async with aiosqlite.connect(str(path)) as conn:
        await conn.execute("CREATE TABLE checkpoints (thread_id TEXT, checkpoint_id TEXT)")
        await conn.execute("CREATE TABLE checkpoint_writes (thread_id TEXT)")
        await conn.execute("CREATE TABLE checkpoint_blobs (thread_id TEXT)")
        for t in thread_ids:
            await conn.execute("INSERT INTO checkpoints VALUES (?, ?)", (str(t), "c"))
        await conn.commit()


async def test_sweep_preserves_latest_and_waiting(db):
    old_iso = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()

    for _ in range(3):
        eid = await db.create_execution("a", "manual")
        await db.db.execute("UPDATE executions SET status='success', finished_at=? WHERE id=?", (old_iso, eid))
    w = await db.create_execution("b", "manual", status="waiting")
    await db.db.execute("UPDATE executions SET finished_at=? WHERE id=?", (old_iso, w))
    await db.db.commit()

    cp = cm.checkpoint_db_path(db.db_path)
    await _make_checkpoint_db(cp, [1, 2, 3, 4])

    removed = await cm.sweep_old_checkpoints(db, db.db_path, retention_days=30)
    assert removed == 2  # ids 1,2 removed; 3 (latest) and 4 (waiting) kept

    async with aiosqlite.connect(str(cp)) as conn:
        cur = await conn.execute("SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id")
        remaining = sorted(int(r[0]) for r in await cur.fetchall())
    assert remaining == [3, 4]


async def test_purge_force_wipes(db):
    e = await db.create_execution("a", "manual", status="waiting")
    cp = cm.checkpoint_db_path(db.db_path)
    await _make_checkpoint_db(cp, [e])
    removed = await cm.purge_checkpoints(db, db.db_path, force=True)
    assert removed == 1


async def test_sweep_preserves_non_latest_waiting(db):
    # Agent "a": an OLD waiting execution (id 1) then a NEWER finished one (id 2).
    # id 2 is the latest-per-agent (kept); id 1 is waiting but NOT latest — it must
    # still be preserved by the waiting rule alone.
    old_iso = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()

    e1 = await db.create_execution("a", "manual", status="waiting")
    await db.db.execute("UPDATE executions SET finished_at=? WHERE id=?", (old_iso, e1))
    e2 = await db.create_execution("a", "manual")
    await db.db.execute("UPDATE executions SET status='success', finished_at=? WHERE id=?", (old_iso, e2))
    await db.db.commit()

    cp = cm.checkpoint_db_path(db.db_path)
    await _make_checkpoint_db(cp, [e1, e2])

    removed = await cm.sweep_old_checkpoints(db, db.db_path, retention_days=30)
    assert removed == 0  # e2 kept (latest), e1 kept (waiting, even though not latest)

    async with aiosqlite.connect(str(cp)) as conn:
        cur = await conn.execute("SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id")
        remaining = sorted(int(r[0]) for r in await cur.fetchall())
    assert remaining == [e1, e2]


async def test_stats_maps_threads_to_agents(db):
    e1 = await db.create_execution("alpha", "manual")
    e2 = await db.create_execution("beta", "manual")
    cp = cm.checkpoint_db_path(db.db_path)
    await _make_checkpoint_db(cp, [e1, e2])
    s = await cm.checkpoint_stats(db, db.db_path)
    assert s["threads"] == 2
    assert s["per_agent"] == {"alpha": 1, "beta": 1}
