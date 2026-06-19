"""Kafka producer/consumer renderer tests (Tier-1 PR4)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import ModuleType

import py_compile
import pytest

from startd8.events_codegen import is_owned_events_file, render_events_artifacts
from startd8.openapi_contract import synthesize_body

pytestmark = pytest.mark.unit

ORDER_SCHEMA = """
model Order {
  id String @id
  total Float
  paid Boolean @default(false)
}
""".strip()

EVENTS_MANIFEST = """
channels:
  order_paid:
    direction: publish
    topic: orders.paid
    payload: Order
  order_notify:
    direction: subscribe
    topic: orders.paid
    payload: Order
""".strip()


def _load_generated_module(source: str) -> ModuleType:
    mod = ModuleType("generated_events")
    exec(compile(source, "<generated>", "exec"), mod.__dict__)  # noqa: S102
    return mod


@pytest.fixture()
def artifacts() -> dict[str, str]:
    return dict(
        render_events_artifacts(
            EVENTS_MANIFEST,
            ORDER_SCHEMA,
            messaging_backend="aiokafka",
            package="app",
        )
    )


def test_render_producer_and_consumer(artifacts: dict[str, str]):
    producer = artifacts["app/events/order_paid_producer.py"]
    consumer = artifacts["app/events/order_notify_consumer.py"]
    assert "python-events-producer" in producer
    assert "python-events-consumer" in consumer
    assert "CLOUDEVENTS_TYPE = \"com.app.order_paid\"" in producer
    assert "TOPIC = \"orders.paid\"" in producer
    assert "AIOKafkaProducer" in producer
    assert "AIOKafkaConsumer" in consumer
    assert is_owned_events_file(producer)
    assert is_owned_events_file(consumer)


def test_aiokafka_emits_manual_spans_and_tracecontext(artifacts: dict[str, str]):
    """aiokafka has no auto-instrumentor → producer/consumer create spans + propagate context."""
    producer = artifacts["app/events/order_paid_producer.py"]
    consumer = artifacts["app/events/order_notify_consumer.py"]
    # Producer: PRODUCER span + tracecontext injected into the CloudEvents envelope.
    assert "start_as_current_span" in producer
    assert "SpanKind.PRODUCER" in producer
    assert "_inject_trace_context" in producer
    assert "traceparent" in producer
    # Consumer: CONSUMER span parented on the extracted envelope context.
    assert "SpanKind.CONSUMER" in consumer
    assert "_extract_context" in consumer
    # Import-guarded so a no-OTel app still runs.
    assert "except ImportError" in producer


def test_kafka_python_backend_relies_on_auto_instrumentation():
    artifacts = dict(
        render_events_artifacts(
            EVENTS_MANIFEST,
            ORDER_SCHEMA,
            messaging_backend="kafka-python",
            package="shop",
        )
    )
    producer = artifacts["shop/events/order_paid_producer.py"]
    consumer = artifacts["shop/events/order_notify_consumer.py"]
    assert "KafkaProducer" in producer
    assert "KafkaConsumer" in consumer
    # kafka-python is auto-instrumented by KafkaInstrumentor: no manual spans in the generated code.
    assert "start_as_current_span" not in producer
    assert "_inject_trace_context" not in producer
    assert "_extract_context" not in consumer


def test_producer_compiles(artifacts: dict[str, str]):
    text = artifacts["app/events/order_paid_producer.py"]
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8") as f:
        f.write(text)
        path = f.name
    py_compile.compile(path, doraise=True)


def test_fr_f6_payload_matches_json_schema(artifacts: dict[str, str]):
    """FR-F6: synthesized payload serializes and validates against embedded schema."""
    jsonschema = pytest.importorskip("jsonschema")

    producer_src = artifacts["app/events/order_paid_producer.py"]
    mod = _load_generated_module(producer_src)
    schema = mod.PAYLOAD_SCHEMA

    payload = synthesize_body(schema, schema)
    jsonschema.validate(payload, schema)

    raw = mod.serialize_payload(payload)
    roundtrip = json.loads(raw.decode("utf-8"))
    jsonschema.validate(roundtrip, schema)

    event = mod.build_cloudevent(payload, event_id="evt-1")
    assert event["specversion"] == "1.0"
    assert event["type"] == "com.app.order_paid"
    assert event["source"] == "/app/events/order_paid"
    assert event["id"] == "evt-1"
    assert event["data"] == payload
