import pytest
from agent_md.execution.global_event_bus import GlobalEventBus


class TestGlobalEventBus:
    @pytest.fixture
    def bus(self):
        return GlobalEventBus()

    async def test_publish_no_subscribers(self, bus):
        """Publishing with no subscribers should not raise."""
        await bus.publish({"type": "heartbeat", "data": {}})

    async def test_publish_one_subscriber(self, bus):
        queue = bus.subscribe()
        await bus.publish({"type": "execution_started", "data": {"execution_id": 1}})
        event = queue.get_nowait()
        assert event["type"] == "execution_started"
        assert event["data"]["execution_id"] == 1
        bus.unsubscribe(queue)

    async def test_publish_multiple_subscribers(self, bus):
        q1 = bus.subscribe()
        q2 = bus.subscribe()
        await bus.publish({"type": "heartbeat", "data": {}})
        assert q1.get_nowait()["type"] == "heartbeat"
        assert q2.get_nowait()["type"] == "heartbeat"
        bus.unsubscribe(q1)
        bus.unsubscribe(q2)

    async def test_unsubscribe_stops_receiving(self, bus):
        queue = bus.subscribe()
        bus.unsubscribe(queue)
        await bus.publish({"type": "heartbeat", "data": {}})
        assert queue.empty()

    async def test_full_queue_drops_event(self, bus):
        queue = bus.subscribe()
        # Fill the queue
        for i in range(1000):
            await bus.publish({"type": "fill", "data": {"i": i}})
        # Next publish should not block or raise
        await bus.publish({"type": "overflow", "data": {}})
        assert queue.qsize() == 1000  # still at max, overflow dropped

    async def test_stream_count(self, bus):
        assert bus.stream_count == 0
        q1 = bus.subscribe()
        assert bus.stream_count == 1
        q2 = bus.subscribe()
        assert bus.stream_count == 2
        bus.unsubscribe(q1)
        assert bus.stream_count == 1
        bus.unsubscribe(q2)
        assert bus.stream_count == 0

    async def test_unsubscribe_idempotent(self, bus):
        queue = bus.subscribe()
        bus.unsubscribe(queue)
        bus.unsubscribe(queue)  # second call should not raise or decrement below 0
        assert bus.stream_count == 0
