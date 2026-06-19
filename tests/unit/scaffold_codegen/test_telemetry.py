"""Telemetry scaffold emitter tests (Tier-1 PR2)."""

from __future__ import annotations

import pytest

from startd8.scaffold_codegen import parse_app_manifest, render_scaffold, scaffold_in_sync
from startd8.scaffold_codegen.telemetry_renderer import otel_runtime_dependencies, render_telemetry

pytestmark = pytest.mark.unit

TELEMETRY_MANIFEST = """
app:
  name: shop
  package: app
telemetry:
  enabled: true
  otlp_endpoint: http://127.0.0.1:4318
  patterns:
    - http
    - db
""".strip()


def test_telemetry_defaults_off():
    m = parse_app_manifest(None)
    assert not m.telemetry_enabled
    assert m.telemetry_patterns == ()


def test_telemetry_manifest_parses():
    m = parse_app_manifest(TELEMETRY_MANIFEST)
    assert m.telemetry_enabled
    assert m.telemetry_patterns == ("http", "db")


def test_invalid_pattern_fails():
    with pytest.raises(ValueError, match="telemetry.patterns"):
        parse_app_manifest("telemetry:\n  enabled: true\n  patterns: [nope]\n")


def test_render_telemetry_byte_stable():
    text = render_telemetry(TELEMETRY_MANIFEST)
    assert "configure_telemetry" in text
    assert "FastAPIInstrumentor" in text
    assert "SQLAlchemyInstrumentor" in text
    assert text == render_telemetry(TELEMETRY_MANIFEST)


def test_scaffold_includes_telemetry_when_enabled():
    artifacts = dict(render_scaffold(TELEMETRY_MANIFEST))
    assert "app/telemetry.py" in artifacts
    assert scaffold_in_sync(TELEMETRY_MANIFEST, artifacts["app/telemetry.py"])


def test_scaffold_omits_telemetry_when_disabled():
    artifacts = dict(render_scaffold("app:\n  name: x\n"))
    assert "app/telemetry.py" not in artifacts


def test_otel_deps_added_to_pyproject():
    deps = otel_runtime_dependencies(TELEMETRY_MANIFEST)
    assert "opentelemetry-sdk" in deps
    assert "opentelemetry-instrumentation-fastapi" in deps


def test_messaging_backend_defaults():
    m = parse_app_manifest(None)
    assert m.messaging_backend == "aiokafka"


def test_messaging_backend_parses():
    m = parse_app_manifest("messaging:\n  backend: kafka-python\n")
    assert m.messaging_backend == "kafka-python"


def test_invalid_messaging_backend_fails():
    with pytest.raises(ValueError, match="messaging.backend"):
        parse_app_manifest("messaging:\n  backend: rabbitmq\n")


_MESSAGING_KAFKA_PYTHON = """
app:
  name: shop
telemetry:
  enabled: true
  patterns:
    - messaging
messaging:
  backend: kafka-python
""".strip()

_MESSAGING_AIOKAFKA = """
app:
  name: shop
telemetry:
  enabled: true
  patterns:
    - messaging
messaging:
  backend: aiokafka
""".strip()


def test_messaging_dep_is_backend_driven():
    # kafka-python has an official OTel instrumentor → dep is added.
    kp_deps = otel_runtime_dependencies(_MESSAGING_KAFKA_PYTHON)
    assert "opentelemetry-instrumentation-kafka-python" in kp_deps
    # aiokafka has no auto-instrumentor → no instrumentor dep (manual spans instead).
    ak_deps = otel_runtime_dependencies(_MESSAGING_AIOKAFKA)
    assert "opentelemetry-instrumentation-kafka-python" not in ak_deps
    assert not any("kafka" in d for d in ak_deps)


def test_messaging_render_is_backend_driven():
    kp = render_telemetry(_MESSAGING_KAFKA_PYTHON)
    assert "KafkaInstrumentor().instrument()" in kp
    ak = render_telemetry(_MESSAGING_AIOKAFKA)
    assert "KafkaInstrumentor" not in ak
    assert "aiokafka has no OTel auto-instrumentor" in ak
