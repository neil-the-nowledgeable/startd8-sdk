"""Kafka producer/consumer skeleton renderers (Python only — Tier-1 PR4)."""

from __future__ import annotations

import json
from typing import Any, Dict

from ..frontend_codegen.schema_renderer import schema_sha256
from ..schema_contract.prisma_json_schema import entity_read_schema
from .headers import header_events
from .models import EventChannelSpec

_PRODUCER_KIND = "python-events-producer"
_CONSUMER_KIND = "python-events-consumer"


def _payload_schema(schema_text: str, model_name: str) -> Dict[str, Any]:
    return entity_read_schema(schema_text, model_name)


def _schema_literal(schema: Dict[str, Any]) -> str:
    return json.dumps(schema, indent=4, sort_keys=True)


def _cloudevent_type(channel: str) -> str:
    return f"com.app.{channel}"


def _cloudevent_source(channel: str) -> str:
    return f"/app/events/{channel}"


def render_producer(
    *,
    spec: EventChannelSpec,
    schema_text: str,
    events_text: str,
    events_source: str,
    schema_source: str,
    messaging_backend: str = "aiokafka",
) -> str:
    payload_schema = _payload_schema(schema_text, spec.payload)
    header = header_events(
        events_source,
        schema_sha256(events_text),
        schema_source,
        schema_sha256(schema_text),
        _PRODUCER_KIND,
        spec.name,
    )
    schema_lit = _schema_literal(payload_schema)
    if messaging_backend == "kafka-python":
        publish_block = (
            "def publish(payload: Mapping[str, Any], *, bootstrap_servers: str = \"localhost:9092\") -> None:\n"
            "    from kafka import KafkaProducer\n"
            "    event = build_cloudevent(payload)\n"
            "    body = json.dumps(event, separators=(\",\", \":\"), sort_keys=True).encode(\"utf-8\")\n"
            "    producer = KafkaProducer(bootstrap_servers=bootstrap_servers)\n"
            "    try:\n"
            "        producer.send(TOPIC, body).get(timeout=10)\n"
            "    finally:\n"
            "        producer.close()\n"
        )
    else:
        publish_block = (
            "async def publish(payload: Mapping[str, Any], *, bootstrap_servers: str = \"localhost:9092\") -> None:\n"
            "    from aiokafka import AIOKafkaProducer\n"
            "    event = build_cloudevent(payload)\n"
            "    body = json.dumps(event, separators=(\",\", \":\"), sort_keys=True).encode(\"utf-8\")\n"
            "    producer = AIOKafkaProducer(bootstrap_servers=bootstrap_servers)\n"
            "    await producer.start()\n"
            "    try:\n"
            "        await producer.send_and_wait(TOPIC, body)\n"
            "    finally:\n"
            "        await producer.stop()\n"
        )

    body = (
        f'"""Generated Kafka producer for channel ``{spec.name}`` (CloudEvents envelope)."""\n'
        "from __future__ import annotations\n\n"
        "import json\n"
        "import uuid\n"
        "from typing import Any, Mapping\n\n"
        f'CLOUDEVENTS_SPECVERSION = "1.0"\n'
        f'CLOUDEVENTS_TYPE = "{_cloudevent_type(spec.name)}"\n'
        f'CLOUDEVENTS_SOURCE = "{_cloudevent_source(spec.name)}"\n'
        f'TOPIC = "{spec.topic}"\n\n'
        f"PAYLOAD_SCHEMA: dict[str, Any] = {schema_lit}\n\n\n"
        "def build_cloudevent(payload: Mapping[str, Any], *, event_id: str | None = None) -> dict[str, Any]:\n"
        "    return {\n"
        '        "specversion": CLOUDEVENTS_SPECVERSION,\n'
        '        "type": CLOUDEVENTS_TYPE,\n'
        '        "source": CLOUDEVENTS_SOURCE,\n'
        '        "id": event_id or str(uuid.uuid4()),\n'
        '        "datacontenttype": "application/json",\n'
        '        "data": dict(payload),\n'
        "    }\n\n\n"
        "def serialize_payload(payload: Mapping[str, Any]) -> bytes:\n"
        '    """Serialize the domain payload bytes (JSON, stable key order)."""\n'
        '    return json.dumps(dict(payload), separators=(",", ":"), sort_keys=True).encode("utf-8")\n\n\n'
        + publish_block
    )
    return header + "\n\n" + body


def render_consumer(
    *,
    spec: EventChannelSpec,
    schema_text: str,
    events_text: str,
    events_source: str,
    schema_source: str,
    messaging_backend: str = "aiokafka",
) -> str:
    payload_schema = _payload_schema(schema_text, spec.payload)
    header = header_events(
        events_source,
        schema_sha256(events_text),
        schema_source,
        schema_sha256(schema_text),
        _CONSUMER_KIND,
        spec.name,
    )
    schema_lit = _schema_literal(payload_schema)
    if messaging_backend == "kafka-python":
        consume_block = (
            "def consume_once(*, bootstrap_servers: str = \"localhost:9092\", group_id: str = \"app\") -> dict[str, Any] | None:\n"
            "    from kafka import KafkaConsumer\n"
            "    consumer = KafkaConsumer(\n"
            "        TOPIC,\n"
            "        bootstrap_servers=bootstrap_servers,\n"
            "        group_id=group_id,\n"
            "        auto_offset_reset=\"earliest\",\n"
            "        consumer_timeout_ms=1000,\n"
            "    )\n"
            "    try:\n"
            "        for message in consumer:\n"
            "            return parse_message(message.value)\n"
            "    finally:\n"
            "        consumer.close()\n"
            "    return None\n"
        )
    else:
        consume_block = (
            "async def consume_once(*, bootstrap_servers: str = \"localhost:9092\", group_id: str = \"app\") -> dict[str, Any] | None:\n"
            "    from aiokafka import AIOKafkaConsumer\n"
            "    consumer = AIOKafkaConsumer(\n"
            "        TOPIC,\n"
            "        bootstrap_servers=bootstrap_servers,\n"
            "        group_id=group_id,\n"
            "        auto_offset_reset=\"earliest\",\n"
            "    )\n"
            "    await consumer.start()\n"
            "    try:\n"
            "        message = await consumer.getone()\n"
            "        return parse_message(message.value)\n"
            "    finally:\n"
            "        await consumer.stop()\n"
            "    return None\n"
        )

    body = (
        f'"""Generated Kafka consumer for channel ``{spec.name}``."""\n'
        "from __future__ import annotations\n\n"
        "import json\n"
        "from typing import Any\n\n"
        f'TOPIC = "{spec.topic}"\n\n'
        f"PAYLOAD_SCHEMA: dict[str, Any] = {schema_lit}\n\n\n"
        "def parse_message(raw: bytes) -> dict[str, Any]:\n"
        '    """Parse a CloudEvents JSON envelope and return the ``data`` object."""\n'
        "    envelope = json.loads(raw.decode(\"utf-8\"))\n"
        '    data = envelope.get("data")\n'
        "    if not isinstance(data, dict):\n"
        '        raise ValueError("event data must be a JSON object")\n'
        "    return data\n\n\n"
        + consume_block
    )
    return header + "\n\n" + body
