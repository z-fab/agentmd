from agent_md.execution.global_event_bus import GlobalEventBus


class TestExecutionGlobalEvents:
    async def test_execution_started_published(self):
        """Runner should publish execution_started to global bus."""
        global_bus = GlobalEventBus()
        queue = global_bus.subscribe()

        await global_bus.publish(
            {
                "type": "execution_started",
                "data": {"execution_id": 42, "agent_name": "test-agent", "trigger": "manual"},
            }
        )

        event = queue.get_nowait()
        assert event["type"] == "execution_started"
        assert event["data"]["execution_id"] == 42
        assert event["data"]["agent_name"] == "test-agent"
        assert event["data"]["trigger"] == "manual"
        global_bus.unsubscribe(queue)

    async def test_execution_completed_published(self):
        """Runner should publish execution_completed to global bus."""
        global_bus = GlobalEventBus()
        queue = global_bus.subscribe()

        await global_bus.publish(
            {
                "type": "execution_completed",
                "data": {
                    "execution_id": 42,
                    "agent_name": "test-agent",
                    "status": "success",
                    "duration_ms": 3400,
                },
            }
        )

        event = queue.get_nowait()
        assert event["type"] == "execution_completed"
        assert event["data"]["status"] == "success"
        assert event["data"]["duration_ms"] == 3400
        global_bus.unsubscribe(queue)
