# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""OTel helpers for WLQ enqueue/drain (FR-17). Graceful no-op without OTel."""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from typing import Any, Dict, Iterator, Optional

try:
    from opentelemetry import trace as _otel_trace

    _tracer = _otel_trace.get_tracer("startd8.workflows.loop_queue")
except ImportError:  # pragma: no cover
    _otel_trace = None  # type: ignore[assignment]
    _tracer = None


@contextmanager
def wlq_span(
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
) -> Iterator[Any]:
    """Yield a WLQ span or ``None`` when OTel is unavailable."""
    if not _tracer:
        with nullcontext(None) as span:
            yield span
        return

    attrs = {k: v for k, v in (attributes or {}).items() if v is not None}
    with _tracer.start_as_current_span(name, attributes=attrs) as span:
        yield span


def set_span_status(span: Any, *, ok: bool, description: str = "") -> None:
    if span is None or _otel_trace is None:
        return
    if ok:
        span.set_status(_otel_trace.StatusCode.OK)
    else:
        span.set_status(_otel_trace.StatusCode.ERROR, description or "error")
