"""OTel app bootstrap emitter (Tier-1 PR2 — manifest-declared patterns only)."""

from __future__ import annotations

from typing import List

from .manifest import AppManifest, parse_app_manifest

_VALID_PATTERNS = frozenset({"http", "grpc", "db", "messaging"})

_OTEL_RUNTIME: tuple[str, ...] = (
    "opentelemetry-api",
    "opentelemetry-sdk",
    "opentelemetry-exporter-otlp-proto-http",
)
_PATTERN_DEPS: dict[str, tuple[str, ...]] = {
    "http": ("opentelemetry-instrumentation-fastapi",),
    "grpc": ("opentelemetry-instrumentation-grpc",),
    "db": ("opentelemetry-instrumentation-sqlalchemy",),
    "messaging": ("opentelemetry-instrumentation-kafka-python",),
}


def otel_runtime_dependencies(manifest_text: str) -> tuple[str, ...]:
    """Extra runtime deps to add when ``telemetry.enabled`` (for pyproject rendering)."""
    m = parse_app_manifest(manifest_text)
    if not m.telemetry_enabled:
        return ()
    deps: List[str] = list(_OTEL_RUNTIME)
    for pattern in m.telemetry_patterns:
        deps.extend(_PATTERN_DEPS.get(pattern, ()))
    return tuple(dict.fromkeys(deps))


def render_telemetry(manifest_text: str) -> str:
    """``app/telemetry.py`` — OTLP bootstrap + declared pattern hooks."""
    from ..frontend_codegen.schema_renderer import schema_sha256

    m = parse_app_manifest(manifest_text)
    if not m.telemetry_enabled:
        raise ValueError("render_telemetry requires telemetry.enabled in app.yaml")
    sha = schema_sha256(manifest_text)
    service = m.telemetry_service_name or m.name
    endpoint = m.telemetry_otlp_endpoint
    patterns = m.telemetry_patterns

    lines: List[str] = [
        "# GENERATED from app.yaml — do not edit by hand; regenerate via `startd8 generate scaffold`.",
        "# startd8-artifact: scaffold-telemetry",
        "# Source of truth: the app manifest.",
        f"# manifest-sha256: {sha}",
        "",
        "from __future__ import annotations",
        "",
        "import os",
        "from typing import Any",
        "",
        "_CONFIGURED = False",
        "",
        "",
        "def configure_telemetry(app: Any = None) -> None:",
        '    """Initialize OTLP export and manifest-declared instrumentations (idempotent)."""',
        "    global _CONFIGURED",
        "    if _CONFIGURED:",
        "        return",
        "    from opentelemetry import trace",
        "    from opentelemetry.sdk.resources import Resource",
        "    from opentelemetry.sdk.trace import TracerProvider",
        "    from opentelemetry.sdk.trace.export import BatchSpanProcessor",
        "    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter",
        "",
        f"    service_name = os.environ.get('OTEL_SERVICE_NAME', {service!r})",
        f"    endpoint = os.environ.get('OTEL_EXPORTER_OTLP_ENDPOINT', {endpoint!r})",
        "    resource = Resource.create({",
        '        "service.name": service_name,',
        '        "deployment.environment": os.environ.get("ENV", "development"),',
        "    })",
        "    provider = TracerProvider(resource=resource)",
        "    provider.add_span_processor(",
        "        BatchSpanProcessor(OTLPSpanExporter(endpoint=f'{endpoint.rstrip(\"/\")}/v1/traces'))",
        "    )",
        "    trace.set_tracer_provider(provider)",
    ]

    if "http" in patterns:
        lines += [
            "",
            "    if app is not None:",
            "        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor",
            "        FastAPIInstrumentor.instrument_app(app)",
        ]

    if "db" in patterns:
        lines += [
            "",
            "    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor",
            "    SQLAlchemyInstrumentor().instrument(enable_commenter=True)",
        ]

    if "grpc" in patterns:
        lines += [
            "",
            "    from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer",
            "    GrpcInstrumentorServer().instrument()",
        ]

    if "messaging" in patterns:
        lines += [
            "",
            "    # Messaging hooks: instrument producers/consumers in app/events/ when present.",
        ]

    lines += [
        "",
        "    _CONFIGURED = True",
        "",
    ]
    return "\n".join(lines)
