import json
import pytest
from agent_md.db.database import Database


@pytest.fixture
async def db(tmp_path):
    d = Database(tmp_path / "t.db")
    await d.connect()
    yield d
    await d.close()


async def test_pending_interrupt_roundtrip(db):
    ex = await db.create_execution(agent_id="a", trigger="manual")
    payload = {"request_id": "r1", "kind": "confirm", "message": "ok?"}
    await db.set_pending_interrupt(ex, "r1", payload)

    rec = await db.get_pending_interrupt(ex)
    assert rec is not None
    assert rec.request_id == "r1"
    assert json.loads(rec.payload_json)["kind"] == "confirm"

    listed = await db.list_pending_interrupts()
    assert [r.execution_id for r in listed] == [ex]

    await db.clear_pending_interrupt(ex)
    assert await db.get_pending_interrupt(ex) is None


async def test_set_pending_replaces(db):
    ex = await db.create_execution(agent_id="a", trigger="manual")
    await db.set_pending_interrupt(ex, "r1", {"request_id": "r1"})
    await db.set_pending_interrupt(ex, "r2", {"request_id": "r2"})
    rec = await db.get_pending_interrupt(ex)
    assert rec.request_id == "r2"


async def test_claim_execution_for_resume_is_atomic(db):
    ex = await db.create_execution("a", "manual", status="waiting")
    assert await db.claim_execution_for_resume(ex) is True   # first wins
    assert await db.claim_execution_for_resume(ex) is False  # second loses (already running)
    e = await db.get_execution(ex)
    assert e.status == "running"
