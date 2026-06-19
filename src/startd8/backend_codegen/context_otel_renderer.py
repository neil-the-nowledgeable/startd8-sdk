"""OTel helper for inter-context outbound HTTP (OpenAPI Role 3 — OQ-5).

Emits ``clients/_context_otel.py`` — a self-contained, optional-OTel trace wrapper used by
generated ``clients/{id}_client.py`` artifacts. No ``startd8`` runtime dependency in deployed apps.
"""

from __future__ import annotations

from ..frontend_codegen.schema_renderer import schema_sha256
from ._headers import header_standard as _header

CONTEXT_OTEL_PATH = "clients/_context_otel.py"
_KIND = "python-context-otel"

# Owned once per project when contexts.yaml is present; content is convention-stable.
_BODY = '''\
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
                span.set_attribute("http.response.status_code", int(status))
            span.set_status(StatusCode.OK)
            return result
        except Exception as exc:
            span.set_status(StatusCode.ERROR, str(exc))
            span.record_exception(exc)
            raise
'''


def render_context_otel(source_file: str = "prisma/schema.prisma", schema_text: str = "") -> str:
    """Render ``clients/_context_otel.py``."""
    sha = schema_sha256(schema_text) if schema_text else schema_sha256("")
    return _header(source_file, sha, _KIND) + "\n\n" + _BODY
