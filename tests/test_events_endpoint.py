"""Tests for GET /events/stream SSE endpoint."""

import pytest

import agent_md.api.routes.events as events_module
from agent_md.api.routes.events import global_event_stream, router
from agent_md.execution.global_event_bus import GlobalEventBus
from fastapi import FastAPI


def _create_test_app(global_event_bus: GlobalEventBus) -> FastAPI:
    app = FastAPI()
    app.state.global_event_bus = global_event_bus
    app.include_router(router)
    return app


class _FakeRequest:
    """Minimal Request-like object for unit-testing the generator directly."""

    def __init__(self, app):
        self.app = app


class TestEventsEndpoint:
    def test_stream_returns_event_source(self):
        """SSE endpoint should return text/event-stream content type."""
        from fastapi.sse import EventSourceResponse

        stream_route = next(r for r in router.routes if r.path == "/events/stream")
        assert stream_route.response_class is EventSourceResponse

    async def test_stream_cleans_up_on_disconnect(self, monkeypatch):
        """Disconnecting should unsubscribe from the bus — verified via generator close."""
        monkeypatch.setattr(events_module, "_HEARTBEAT_TIMEOUT", 0.05)
        bus = GlobalEventBus()
        app = _create_test_app(bus)
        request = _FakeRequest(app)
        gen = global_event_stream(request)
        await gen.__anext__()  # generator is now running and subscribed
        assert bus.stream_count == 1
        await gen.aclose()  # simulate disconnect
        assert bus.stream_count == 0

    @pytest.mark.asyncio
    async def test_generator_yields_queued_event(self):
        """Generator immediately yields events that are already in the queue."""
        bus = GlobalEventBus()
        app = _create_test_app(bus)
        request = _FakeRequest(app)

        # Monkeypatch subscribe to pre-load one event
        original_subscribe = bus.subscribe
        pre_filled_q = None

        def capturing_subscribe():
            nonlocal pre_filled_q
            q = original_subscribe()
            q.put_nowait(
                {"type": "execution_started", "data": {"execution_id": 1, "agent_name": "test", "trigger": "manual"}}
            )
            pre_filled_q = q
            return q

        bus.subscribe = capturing_subscribe

        gen = global_event_stream(request)
        first = await gen.__anext__()

        assert first.event == "execution_started"
        assert first.data["execution_id"] == 1

        await gen.aclose()
        assert bus.stream_count == 0

    @pytest.mark.asyncio
    async def test_generator_sends_heartbeat_on_timeout(self, monkeypatch):
        """Generator emits a heartbeat SSE when idle for _HEARTBEAT_TIMEOUT."""
        monkeypatch.setattr(events_module, "_HEARTBEAT_TIMEOUT", 0.05)
        bus = GlobalEventBus()
        app = _create_test_app(bus)
        request = _FakeRequest(app)
        gen = global_event_stream(request)
        try:
            event = await gen.__anext__()
            assert event.event == "heartbeat"
            assert "timestamp" in event.data
        finally:
            await gen.aclose()

    @pytest.mark.asyncio
    async def test_generator_unsubscribes_on_close(self, monkeypatch):
        """Closing the generator calls unsubscribe via finally."""
        monkeypatch.setattr(events_module, "_HEARTBEAT_TIMEOUT", 0.05)
        bus = GlobalEventBus()
        app = _create_test_app(bus)
        request = _FakeRequest(app)
        gen = global_event_stream(request)
        await gen.__anext__()
        assert bus.stream_count == 1
        await gen.aclose()
        assert bus.stream_count == 0
