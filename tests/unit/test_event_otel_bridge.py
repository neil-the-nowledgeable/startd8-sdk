"""
Tests for EventBus → OTel bridge (Phase 2C).

Covers:
- Events → span events when active span exists
- Counter incremented on each event
- No-op without OTel / without active span
- Idempotent activation/deactivation
"""

from unittest.mock import patch, MagicMock
import pytest


class TestOTelEventBridge:
    """Tests for OTelEventBridge class."""

    def setup_method(self):
        """Reset bridge state before each test."""
        from startd8.events.otel_bridge import OTelEventBridge
        OTelEventBridge._active = False
        OTelEventBridge._counter = None

    def teardown_method(self):
        """Deactivate bridge and clean up EventBus handlers."""
        from startd8.events.otel_bridge import OTelEventBridge
        OTelEventBridge.deactivate()
        from startd8.events import EventBus
        EventBus.clear()

    def test_activate_subscribes_to_all_events(self):
        """activate() subscribes _handle_event to EventBus."""
        from startd8.events.otel_bridge import OTelEventBridge

        with patch("startd8.events.otel_bridge._OTEL_AVAILABLE", True), \
             patch("startd8.events.otel_bridge._otel_metrics") as mock_metrics:
            mock_metrics.get_meter.return_value = MagicMock()
            OTelEventBridge.activate()
            assert OTelEventBridge._active is True

    def test_activate_idempotent(self):
        """Calling activate() twice only subscribes once."""
        from startd8.events.otel_bridge import OTelEventBridge

        with patch("startd8.events.otel_bridge._OTEL_AVAILABLE", True), \
             patch("startd8.events.otel_bridge._otel_metrics") as mock_metrics:
            mock_meter = MagicMock()
            mock_metrics.get_meter.return_value = mock_meter
            OTelEventBridge.activate()
            OTelEventBridge.activate()
            # get_meter should only be called once
            assert mock_metrics.get_meter.call_count == 1

    def test_no_op_without_otel(self):
        """activate() is a no-op when OTel is unavailable."""
        from startd8.events.otel_bridge import OTelEventBridge

        with patch("startd8.events.otel_bridge._OTEL_AVAILABLE", False):
            OTelEventBridge.activate()
            assert OTelEventBridge._active is False

    def test_handle_event_increments_counter(self):
        """_handle_event increments the events counter."""
        from startd8.events.otel_bridge import OTelEventBridge
        from startd8.events import Event, EventType

        mock_counter = MagicMock()
        OTelEventBridge._counter = mock_counter

        event = Event(
            type=EventType.AGENT_CALL_COMPLETE,
            source="test",
            data={"agent_name": "claude", "response_time_ms": 100},
        )

        with patch("startd8.events.otel_bridge._OTEL_AVAILABLE", True), \
             patch("startd8.events.otel_bridge._otel_trace") as mock_trace:
            # No active span
            mock_span = MagicMock()
            mock_span.is_recording.return_value = False
            mock_trace.get_current_span.return_value = mock_span

            OTelEventBridge._handle_event(event)

            mock_counter.add.assert_called_once_with(
                1, attributes={"event_type": "AGENT_CALL_COMPLETE"}
            )

    def test_handle_event_adds_span_event(self):
        """_handle_event adds event to active span when recording."""
        from startd8.events.otel_bridge import OTelEventBridge
        from startd8.events import Event, EventType

        mock_counter = MagicMock()
        OTelEventBridge._counter = mock_counter

        event = Event(
            type=EventType.PIPELINE_START,
            source="Pipeline",
            data={"pipeline_id": "pipe-123", "pipeline_name": "test"},
            correlation_id="corr-456",
        )

        with patch("startd8.events.otel_bridge._OTEL_AVAILABLE", True), \
             patch("startd8.events.otel_bridge._otel_trace") as mock_trace:
            mock_span = MagicMock()
            mock_span.is_recording.return_value = True
            mock_trace.get_current_span.return_value = mock_span

            OTelEventBridge._handle_event(event)

            # Verify span.add_event was called
            mock_span.add_event.assert_called_once()
            call_args = mock_span.add_event.call_args
            assert call_args[0][0] == "startd8.pipeline_start"
            attrs = call_args[1]["attributes"]
            assert attrs["event.source"] == "Pipeline"
            assert attrs["event.correlation_id"] == "corr-456"
            assert attrs["event.data.pipeline_id"] == "pipe-123"

    def test_deactivate_unsubscribes(self):
        """deactivate() removes the handler from EventBus."""
        from startd8.events.otel_bridge import OTelEventBridge

        with patch("startd8.events.otel_bridge._OTEL_AVAILABLE", True), \
             patch("startd8.events.otel_bridge._otel_metrics") as mock_metrics:
            mock_metrics.get_meter.return_value = MagicMock()
            OTelEventBridge.activate()
            assert OTelEventBridge._active is True

            OTelEventBridge.deactivate()
            assert OTelEventBridge._active is False
