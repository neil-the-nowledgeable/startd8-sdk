"""OpenTelemetry span helpers for the agentic loop (FR-18).

Thin, dependency-tolerant wrappers over the standard ``trace.get_tracer`` pattern (the same one the
FastMCP server uses). Instrumentation is **unconditional**; export only happens when a real
``TracerProvider`` is configured (e.g. via :func:`startd8.otel.configure_tracing`). When OpenTelemetry
is not installed, or no provider is set, every call is a cheap no-op — so importing/using this never
forces the dependency and never errors in minimal environments.

Span tree emitted by ``AgenticSession``::

    agentic.session                     (provider, model, tool_format, tool_count → stop_reason,
      ├── agentic.turn                   turns, total_tokens, total_cost_usd)
      │     ├── agentic.compaction       (attempt → kept/summarized)         [only on overflow]
      │     └── agentic.tool_call        (tool, effect_class → ok, truncated)
      └── ...
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

try:  # OpenTelemetry is optional — the SDK guards availability the same way in otel.py
    from opentelemetry import trace as _trace

    _OTEL_AVAILABLE = True
except Exception:  # pragma: no cover - exercised only when opentelemetry is absent
    _OTEL_AVAILABLE = False

_TRACER_NAME = "startd8.agents.agentic"


class _NoopSpan:
    """Stands in for a span when OTel is unavailable; every method is a no-op."""

    def set_attribute(self, *args: Any, **kwargs: Any) -> None: ...
    def add_event(self, *args: Any, **kwargs: Any) -> None: ...
    def record_exception(self, *args: Any, **kwargs: Any) -> None: ...


def _set_attrs(span: Any, attrs: dict) -> None:
    for key, value in attrs.items():
        if value is not None:
            span.set_attribute(key, value)


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[Any]:
    """Start a span as the current span, set non-None *attributes*, and yield it.

    No-op (yields a :class:`_NoopSpan`) when OpenTelemetry is unavailable. The tracer is fetched per
    call so a provider configured after import is still honored (OTel proxy semantics)."""
    if not _OTEL_AVAILABLE:
        yield _NoopSpan()
        return
    tracer = _trace.get_tracer(_TRACER_NAME)
    with tracer.start_as_current_span(name) as active_span:
        _set_attrs(active_span, attributes)
        yield active_span


def set_attributes(span_obj: Any, **attributes: Any) -> None:
    """Set non-None attributes on an already-open span (used to stamp final session outcome)."""
    if span_obj is not None:
        _set_attrs(span_obj, attributes)
