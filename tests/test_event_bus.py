"""Tests for the in-memory event bus."""

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
    for i in range(1000):
        await bus.publish(1, {"type": "message", "data": f"msg-{i}", "seq": i})
    assert q.full()
    await bus.publish(1, {"type": "message", "data": "overflow", "seq": 1001})
    assert q.qsize() == 1000


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
