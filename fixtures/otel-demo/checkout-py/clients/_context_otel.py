# GENERATED from prisma/schema.prisma — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: python-context-otel
# Source of truth: the Prisma schema.
# schema-sha256: b914136a55bbc023ec648d2a29986a918c88b6e70d55d4300cd1a0e7725e70ba

"""OTel hooks for inter-context outbound HTTP (Role 3 OQ-5).

Wraps each generated context-client request in a CLIENT span when OpenTelemetry is installed.
No-op when ``opentelemetry`` is absent — safe in tests and minimal installs.
"""

from __future__ import annotations

from typing import Callable, TypeVar

T = TypeVar("T")

# StartD8 inter-context semantic convention (OQ-5).
PRODUCER_ID_ATTR = "io.startd8.context.producer_id"
OUTBOUND_ATTR = "io.startd8.context.outbound"


def span_name(producer_id: str, method: str, path: str) -> str:
    """Canonical span name: ``context.outbound.<producer> <METHOD> <path>``."""
    return f"context.outbound.{producer_id} {method.upper()} {path}"


def trace_outbound_request(
    producer_id: str,
    method: str,
    path: str,
    fn: Callable[[], T],
) -> T:
    """Run *fn* inside an optional OTel CLIENT span; always returns *fn*'s result."""
    try:
        from opentelemetry import trace
        from opentelemetry.trace import SpanKind, StatusCode
    except ImportError:
        return fn()

    tracer = trace.get_tracer("startd8.context_client")
    with tracer.start_as_current_span(
        span_name(producer_id, method, path),
        kind=SpanKind.CLIENT,
        attributes={
            "http.request.method": method.upper(),
            "url.path": path,
            PRODUCER_ID_ATTR: producer_id,
            OUTBOUND_ATTR: True,
        },
    ) as span:
        try:
            result = fn()
            status = getattr(result, "status_code", None)
            if status is not None:
                code = int(status)
                span.set_attribute("http.response.status_code", code)
                if code >= 400:
                    span.set_status(StatusCode.ERROR, f"HTTP {code}")
                    return result
            span.set_status(StatusCode.OK)
            return result
        except Exception as exc:
            span.set_status(StatusCode.ERROR, str(exc))
            span.record_exception(exc)
            raise
