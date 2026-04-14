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


class TestSchedulerGlobalEvents:
    async def test_scheduler_paused_published(self):
        global_bus = GlobalEventBus()
        queue = global_bus.subscribe()

        await global_bus.publish(
            {
                "type": "scheduler_changed",
                "data": {"status": "paused"},
            }
        )

        event = queue.get_nowait()
        assert event["type"] == "scheduler_changed"
        assert event["data"]["status"] == "paused"
        global_bus.unsubscribe(queue)

    async def test_scheduler_resumed_published(self):
        global_bus = GlobalEventBus()
        queue = global_bus.subscribe()

        await global_bus.publish(
            {
                "type": "scheduler_changed",
                "data": {"status": "running"},
            }
        )

        event = queue.get_nowait()
        assert event["type"] == "scheduler_changed"
        assert event["data"]["status"] == "running"
        global_bus.unsubscribe(queue)


class TestAgentsChangedGlobalEvents:
    async def test_agent_loaded_published(self):
        global_bus = GlobalEventBus()
        queue = global_bus.subscribe()

        await global_bus.publish(
            {
                "type": "agents_changed",
                "data": {"event": "loaded", "agent_name": "new-agent"},
            }
        )

        event = queue.get_nowait()
        assert event["type"] == "agents_changed"
        assert event["data"]["event"] == "loaded"
        assert event["data"]["agent_name"] == "new-agent"
        global_bus.unsubscribe(queue)

    async def test_agent_updated_published(self):
        global_bus = GlobalEventBus()
        queue = global_bus.subscribe()

        await global_bus.publish(
            {
                "type": "agents_changed",
                "data": {"event": "updated", "agent_name": "my-agent"},
            }
        )

        event = queue.get_nowait()
        assert event["type"] == "agents_changed"
        assert event["data"]["event"] == "updated"
        global_bus.unsubscribe(queue)

    async def test_agent_removed_published(self):
        global_bus = GlobalEventBus()
        queue = global_bus.subscribe()

        await global_bus.publish(
            {
                "type": "agents_changed",
                "data": {"event": "removed", "agent_name": "old-agent"},
            }
        )

        event = queue.get_nowait()
        assert event["type"] == "agents_changed"
        assert event["data"]["event"] == "removed"
        global_bus.unsubscribe(queue)
