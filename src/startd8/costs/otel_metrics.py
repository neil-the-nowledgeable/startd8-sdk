"""
OTel metrics for cost tracking.

Exports cost and token usage metrics via OpenTelemetry when available.
All methods are no-ops if OTel is not installed.
"""

from typing import Any, Optional

try:
    from opentelemetry import metrics as _otel_metrics
    _OTEL_AVAILABLE = True
except ImportError:
    _otel_metrics = None  # type: ignore[assignment]
    _OTEL_AVAILABLE = False

# Observability manifest descriptor — consumed by generate_manifest(), zero runtime cost.
# Module-level taxonomy defaults (REQ-OBS-SHARED-001): cost telemetry is AI-agent
# observability, system-oriented.
_OTEL_DESCRIPTORS = {
    "category": "ai_agent_observability",
    "orientation": "system",
    "metrics": [
        {
            "name": "startd8.cost.total",
            "instrument": "counter",
            "unit": "USD",
            "description": "Total cost in USD across all API calls",
            "meter": "startd8.costs",
            "labels": ["model", "provider", "project"],
        },
        {
            "name": "startd8.cost.input_tokens",
            "instrument": "counter",
            "unit": "tokens",
            "description": "Total input tokens consumed",
            "meter": "startd8.costs",
            "labels": ["model", "provider", "project"],
        },
        {
            "name": "startd8.cost.output_tokens",
            "instrument": "counter",
            "unit": "tokens",
            "description": "Total output tokens consumed",
            "meter": "startd8.costs",
            "labels": ["model", "provider", "project"],
        },
        {
            "name": "startd8.cost.per_request",
            "instrument": "histogram",
            "unit": "USD",
            "description": "Cost per individual request in USD",
            "meter": "startd8.costs",
            "labels": ["model", "provider", "project"],
        },
    ],
}


class CostMetrics:
    """
    OTel cost metrics exporter.

    Creates and manages OTel instruments for cost tracking:
    - ``startd8.cost.total`` (Counter, unit=USD)
    - ``startd8.cost.input_tokens`` / ``output_tokens`` (Counter)
    - ``startd8.cost.per_request`` (Histogram)

    All methods are no-ops if OTel is not available.
    """

    def __init__(self) -> None:
        self._meter: Any = None
        self._cost_total: Any = None
        self._input_tokens: Any = None
        self._output_tokens: Any = None
        self._cost_per_request: Any = None
        self._initialized = False

    def _ensure_initialized(self) -> bool:
        """Lazy-init instruments on first use. Returns True if ready."""
        if self._initialized:
            return self._meter is not None
        self._initialized = True

        if not _OTEL_AVAILABLE:
            return False

        try:
            self._meter = _otel_metrics.get_meter("startd8.costs")
        except Exception:
            return False

        self._cost_total = self._meter.create_counter(
            name="startd8.cost.total",
            description="Total cost in USD across all API calls",
            unit="USD",
        )
        self._input_tokens = self._meter.create_counter(
            name="startd8.cost.input_tokens",
            description="Total input tokens consumed",
            unit="tokens",
        )
        self._output_tokens = self._meter.create_counter(
            name="startd8.cost.output_tokens",
            description="Total output tokens consumed",
            unit="tokens",
        )
        self._cost_per_request = self._meter.create_histogram(
            name="startd8.cost.per_request",
            description="Cost per individual request in USD",
            unit="USD",
        )
        return True

    def record(self, cost_record: Any) -> None:
        """
        Record cost metrics from a CostRecord.

        Args:
            cost_record: A ``CostRecord`` instance (from ``startd8.costs.models``).
        """
        if not self._ensure_initialized():
            return

        attrs = {
            "model": getattr(cost_record, "model", "unknown"),
            "provider": getattr(cost_record, "provider", "unknown"),
        }
        project = getattr(cost_record, "project", None)
        if project:
            attrs["project"] = project

        total_cost = getattr(cost_record, "total_cost", 0.0)
        input_tokens = getattr(cost_record, "input_tokens", 0)
        output_tokens = getattr(cost_record, "output_tokens", 0)

        self._cost_total.add(total_cost, attributes=attrs)
        self._input_tokens.add(input_tokens, attributes=attrs)
        self._output_tokens.add(output_tokens, attributes=attrs)
        self._cost_per_request.record(total_cost, attributes=attrs)
