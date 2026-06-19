"""Kafka producer/consumer renderer tests (Tier-1 PR4)."""

from __future__ import annotations

import json
import re
import tempfile
from ast import literal_eval
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


def _payload_schema_from_source(source: str) -> dict:
    match = re.search(r"PAYLOAD_SCHEMA: dict\[str, Any\] = (\{.*?\n\})\n\n", source, re.DOTALL)
    assert match, "PAYLOAD_SCHEMA not found in generated source"
    return literal_eval(match.group(1))


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


def test_kafka_python_backend():
    artifacts = dict(
        render_events_artifacts(
            EVENTS_MANIFEST,
            ORDER_SCHEMA,
            messaging_backend="kafka-python",
            package="shop",
        )
    )
    assert "KafkaProducer" in artifacts["shop/events/order_paid_producer.py"]
    assert "KafkaConsumer" in artifacts["shop/events/order_notify_consumer.py"]


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
    schema = _payload_schema_from_source(producer_src)
    mod = _load_generated_module(producer_src)

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
