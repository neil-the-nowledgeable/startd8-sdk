"""OTel tracer helpers for context seed handlers."""

from __future__ import annotations

from startd8.contractors.artisan_contractor import _NoOpTracer

# Module-level tracer — reuses the HAS_OTEL/_NoOpTracer pattern from
# artisan_contractor.py for per-task span instrumentation.
try:
    from opentelemetry import trace as _trace

    _phase_tracer = _trace.get_tracer("startd8.artisan.phases")
    _HAS_OTEL = True
except ImportError:
    _phase_tracer = _NoOpTracer()
    _HAS_OTEL = False

__all__ = ["_HAS_OTEL", "_phase_tracer"]
