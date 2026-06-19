"""Unit tests — inter-context OTel helper and traced context clients (Role 3 OQ-5)."""

from __future__ import annotations

import types
from pathlib import Path

import pytest

from startd8.backend_codegen import owned_file_in_sync, render_backend
from startd8.backend_codegen.context_client_renderer import render_context_client
from startd8.backend_codegen.context_manifest import parse_contexts
from startd8.backend_codegen.context_otel_renderer import (
    CONTEXT_OTEL_PATH,
    render_context_otel,
)
from startd8.backend_codegen.openapi_client_renderer import render_http_client

pytestmark = pytest.mark.unit

SCHEMA = """\
model Note {
  id    String @id @default(cuid())
  title String
}
"""

CONTEXTS = """\
outbound:
  - id: catalog
    local: true
    routes: crud
"""


def test_render_context_otel_emits_trace_helper() -> None:
    text = render_context_otel("prisma/schema.prisma", SCHEMA)
    assert "python-context-otel" in text
    assert "trace_outbound_request" in text
    assert "context.outbound." in text
    assert "io.startd8.context.producer_id" in text


def test_context_client_uses_traced_request() -> None:
    (ctx,) = parse_contexts(CONTEXTS)
    text = render_context_client(SCHEMA, CONTEXTS, ctx)
    assert "from clients._context_otel import trace_outbound_request" in text
    assert 'self._producer_id = "catalog"' in text
    assert "def _request(self, method: str, path: str" in text
    assert "self._request(" in text
    assert "self._client.get(" not in text


def test_http_client_unchanged_without_tracing() -> None:
    text = render_http_client(SCHEMA)
    assert "self._client.get(" in text
    assert "_context_otel" not in text
    assert "_request(" not in text


def test_render_backend_includes_context_otel_helper() -> None:
    arts = dict(render_backend(SCHEMA, contexts_text=CONTEXTS))
    assert CONTEXT_OTEL_PATH in arts
    assert "trace_outbound_request" in arts[CONTEXT_OTEL_PATH]


def test_context_otel_drift_in_sync() -> None:
    text = render_context_otel("prisma/schema.prisma", SCHEMA)
    assert owned_file_in_sync(SCHEMA, text)


def test_trace_outbound_request_emits_span(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("opentelemetry")
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    arts = dict(render_backend(SCHEMA, contexts_text=CONTEXTS))
    otel_path = tmp_path / CONTEXT_OTEL_PATH
    otel_path.parent.mkdir(parents=True, exist_ok=True)
    otel_path.write_text(arts[CONTEXT_OTEL_PATH], encoding="utf-8")

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(
        "opentelemetry.trace.get_tracer",
        lambda *_a, **_k: provider.get_tracer("startd8.context_client"),
    )

    mod = types.ModuleType("clients._context_otel")
    exec(compile(otel_path.read_text(encoding="utf-8"), str(otel_path), "exec"), mod.__dict__)

    class _Resp:
        status_code = 200

    mod.trace_outbound_request("catalog", "GET", "/note/", lambda: _Resp())

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "context.outbound.catalog GET /note/"
    assert spans[0].attributes["io.startd8.context.producer_id"] == "catalog"
    assert spans[0].attributes["http.request.method"] == "GET"
