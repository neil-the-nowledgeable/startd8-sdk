"""
EventBus → OpenTelemetry bridge.

Subscribes to all EventBus events and:
1. Adds each event as a span event on the current active span (if any).
2. Increments an ``startd8.events.total`` counter with ``event_type`` attribute.

All operations are no-ops if OTel is not available or no active span exists.
"""

from typing import Any

try:
    from opentelemetry import trace as _otel_trace
    from opentelemetry import metrics as _otel_metrics
    _OTEL_AVAILABLE = True
except ImportError:
    _otel_trace = None  # type: ignore[assignment]
    _otel_metrics = None  # type: ignore[assignment]
    _OTEL_AVAILABLE = False

# Observability manifest descriptor — consumed by generate_manifest(), zero runtime cost.
# Pipeline-innate (REQ-OBS-SHARED-001): the SDK's own event-bus telemetry.
_OTEL_DESCRIPTORS = {
    "category": "pipeline_innate",
    "orientation": "system",
    "metrics": [
        {
            "name": "startd8.events.total",
            "instrument": "counter",
            "unit": "events",
            "description": "Total EventBus events emitted",
            "meter": "startd8.events",
            "labels": ["event_type"],
        },
    ],
}


class OTelEventBridge:
    """
    Bridge between the StartD8 EventBus and OpenTelemetry.

    Call ``OTelEventBridge.activate()`` once during OTel configuration
    to subscribe to all events. Duplicate activation is safe (idempotent).
    """

    _active: bool = False
    _counter: Any = None

    @classmethod
    def activate(cls) -> None:
        """Subscribe to all EventBus events and set up OTel counter."""
        if cls._active or not _OTEL_AVAILABLE:
            return

        try:
            from ..events import EventBus
        except ImportError:
            return

        # Create event counter
        try:
            meter = _otel_metrics.get_meter("startd8.events")
            cls._counter = meter.create_counter(
                name="startd8.events.total",
                description="Total EventBus events emitted",
                unit="events",
            )
        except Exception:
            pass

        EventBus.subscribe_all(cls._handle_event)
        cls._active = True

    @classmethod
    def deactivate(cls) -> None:
        """Unsubscribe from EventBus events."""
        if not cls._active:
            return
        try:
            from ..events import EventBus
            EventBus.unsubscribe_all(cls._handle_event)
        except ImportError:
            pass
        cls._active = False

    @classmethod
    def _handle_event(cls, event: Any) -> None:
        """Handle an EventBus event by bridging to OTel."""
        if not _OTEL_AVAILABLE:
            return

        event_type_name = event.type.name if hasattr(event.type, "name") else str(event.type)

        # Increment event counter
        if cls._counter is not None:
            try:
                cls._counter.add(1, attributes={"event_type": event_type_name})
            except Exception:
                pass

        # Add as span event on the current active span
        try:
            span = _otel_trace.get_current_span()
            if span and span.is_recording():
                # Build attributes from event data (flatten to string values)
                attrs = {"event.source": event.source}
                if event.correlation_id:
                    attrs["event.correlation_id"] = event.correlation_id
                for key, value in event.data.items():
                    if isinstance(value, (str, int, float, bool)):
                        attrs[f"event.data.{key}"] = value
                span.add_event(
                    f"startd8.{event_type_name.lower()}",
                    attributes=attrs,
                )
        except Exception:
            pass
