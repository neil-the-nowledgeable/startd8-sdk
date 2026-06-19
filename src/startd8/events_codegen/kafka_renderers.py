"""Kafka producer/consumer skeleton renderers (Python only — Tier-1 PR4).

Backend-aware instrumentation (resolves the OTel messaging/aiokafka mismatch):
- ``kafka-python`` has an official OpenTelemetry auto-instrumentor (``KafkaInstrumentor``), so the
  generated code stays plain — spans + Kafka-header context propagation are added at runtime by the
  instrumentor wired in ``app/telemetry.py``.
- ``aiokafka`` has **no** auto-instrumentor, so the generated producer/consumer create spans
  **manually** and propagate W3C tracecontext through the CloudEvents envelope (the Distributed
  Tracing extension: ``traceparent``/``tracestate`` attributes). All OTel use is import-guarded, so
  an app without OpenTelemetry installed still runs (the spans become no-ops).
"""

from __future__ import annotations

import json
from typing import Any, Dict

from ..frontend_codegen.schema_renderer import schema_sha256
from ..schema_contract.prisma_json_schema import entity_read_schema
from .headers import header_events
from .models import EventChannelSpec

_PRODUCER_KIND = "python-events-producer"
_CONSUMER_KIND = "python-events-consumer"

# Manual-span helpers emitted only for the aiokafka path (kafka-python is auto-instrumented).
_PRODUCER_OTEL_HELPERS = (
    "def _otel_tracer():\n"
    '    """Return the OpenTelemetry trace module, or None when OTel is not installed."""\n'
    "    try:\n"
    "        from opentelemetry import trace\n"
    "    except ImportError:\n"
    "        return None\n"
    "    return trace\n\n\n"
    "def _inject_trace_context(event: MutableMapping[str, Any]) -> None:\n"
    '    """Inject W3C tracecontext into the CloudEvents envelope (Distributed Tracing ext)."""\n'
    "    try:\n"
    "        from opentelemetry.propagate import inject\n"
    "    except ImportError:\n"
    "        return\n"
    "    carrier: dict[str, str] = {}\n"
    "    inject(carrier)\n"
    '    for key in ("traceparent", "tracestate"):\n'
    "        if key in carrier:\n"
    "            event[key] = carrier[key]\n"
)

_CONSUMER_OTEL_HELPERS = (
    "def _otel_tracer():\n"
    '    """Return the OpenTelemetry trace module, or None when OTel is not installed."""\n'
    "    try:\n"
    "        from opentelemetry import trace\n"
    "    except ImportError:\n"
    "        return None\n"
    "    return trace\n\n\n"
    "def _extract_context(envelope: Mapping[str, Any]):\n"
    '    """Extract a parent context from the CloudEvents envelope tracecontext attributes."""\n'
    "    try:\n"
    "        from opentelemetry.propagate import extract\n"
    "    except ImportError:\n"
    "        return None\n"
    "    carrier = {\n"
    '        key: envelope[key]\n'
    '        for key in ("traceparent", "tracestate")\n'
    "        if isinstance(envelope.get(key), str)\n"
    "    }\n"
    "    return extract(carrier) if carrier else None\n"
)


def _payload_schema(schema_text: str, model_name: str) -> Dict[str, Any]:
    return entity_read_schema(schema_text, model_name)


def _schema_literal(schema: Dict[str, Any]) -> str:
    """Embed the schema as a ``json.loads(...)`` call.

    Parsing a JSON string at import (rather than inlining a Python dict literal) keeps the
    generated module valid even if the schema later contains JSON ``true``/``false``/``null``,
    which are not valid Python tokens. ``sort_keys`` keeps output byte-stable for drift checks.
    """
    json_text = json.dumps(schema, sort_keys=True)
    return f"json.loads({json.dumps(json_text)})"


def _cloudevent_type(channel: str) -> str:
    return f"com.app.{channel}"


def _cloudevent_source(channel: str) -> str:
    return f"/app/events/{channel}"


def _producer_publish_block(messaging_backend: str) -> str:
    if messaging_backend == "kafka-python":
        # Auto-instrumented by KafkaInstrumentor (wired in app/telemetry.py): no manual spans.
        return (
            'def publish(payload: Mapping[str, Any], *, bootstrap_servers: str = "localhost:9092") -> None:\n'
            "    from kafka import KafkaProducer\n"
            "    event = build_cloudevent(payload)\n"
            "    producer = KafkaProducer(bootstrap_servers=bootstrap_servers)\n"
            "    try:\n"
            "        producer.send(TOPIC, _encode_event(event)).get(timeout=10)\n"
            "    finally:\n"
            "        producer.close()\n"
        )
    # aiokafka: manual PRODUCER span + CloudEvents tracecontext injection (import-guarded).
    return (
        'async def publish(payload: Mapping[str, Any], *, bootstrap_servers: str = "localhost:9092") -> None:\n'
        "    from aiokafka import AIOKafkaProducer\n\n"
        "    producer = AIOKafkaProducer(bootstrap_servers=bootstrap_servers)\n"
        "    await producer.start()\n"
        "    try:\n"
        "        trace = _otel_tracer()\n"
        "        if trace is None:\n"
        "            await producer.send_and_wait(TOPIC, _encode_event(build_cloudevent(payload)))\n"
        "        else:\n"
        "            tracer = trace.get_tracer(__name__)\n"
        "            with tracer.start_as_current_span(\n"
        '                f"{TOPIC} publish",\n'
        "                kind=trace.SpanKind.PRODUCER,\n"
        "                attributes={\n"
        '                    "messaging.system": "kafka",\n'
        '                    "messaging.destination.name": TOPIC,\n'
        '                    "messaging.operation": "publish",\n'
        "                },\n"
        "            ):\n"
        "                event = build_cloudevent(payload)\n"
        "                _inject_trace_context(event)\n"
        "                await producer.send_and_wait(TOPIC, _encode_event(event))\n"
        "    finally:\n"
        "        await producer.stop()\n"
    )


def _consumer_consume_block(messaging_backend: str) -> str:
    if messaging_backend == "kafka-python":
        # Auto-instrumented by KafkaInstrumentor (wired in app/telemetry.py): no manual spans.
        return (
            'def consume_once(*, bootstrap_servers: str = "localhost:9092", group_id: str = "app") -> dict[str, Any] | None:\n'
            "    from kafka import KafkaConsumer\n"
            "    consumer = KafkaConsumer(\n"
            "        TOPIC,\n"
            "        bootstrap_servers=bootstrap_servers,\n"
            "        group_id=group_id,\n"
            '        auto_offset_reset="earliest",\n'
            "        consumer_timeout_ms=1000,\n"
            "    )\n"
            "    try:\n"
            "        for message in consumer:\n"
            "            return parse_message(message.value)\n"
            "    finally:\n"
            "        consumer.close()\n"
            "    return None\n"
        )
    # aiokafka: manual CONSUMER span parented on the envelope's extracted tracecontext.
    return (
        'async def consume_once(*, bootstrap_servers: str = "localhost:9092", group_id: str = "app") -> dict[str, Any] | None:\n'
        "    from aiokafka import AIOKafkaConsumer\n\n"
        "    consumer = AIOKafkaConsumer(\n"
        "        TOPIC,\n"
        "        bootstrap_servers=bootstrap_servers,\n"
        "        group_id=group_id,\n"
        '        auto_offset_reset="earliest",\n'
        "    )\n"
        "    await consumer.start()\n"
        "    try:\n"
        "        message = await consumer.getone()\n"
        '        envelope = json.loads(message.value.decode("utf-8"))\n'
        "        trace = _otel_tracer()\n"
        "        if trace is None:\n"
        "            return _event_data(envelope)\n"
        "        tracer = trace.get_tracer(__name__)\n"
        "        with tracer.start_as_current_span(\n"
        '            f"{TOPIC} process",\n'
        "            context=_extract_context(envelope),\n"
        "            kind=trace.SpanKind.CONSUMER,\n"
        "            attributes={\n"
        '                "messaging.system": "kafka",\n'
        '                "messaging.destination.name": TOPIC,\n'
        '                "messaging.operation": "process",\n'
        "            },\n"
        "        ):\n"
        "            return _event_data(envelope)\n"
        "    finally:\n"
        "        await consumer.stop()\n"
        "    return None\n"
    )


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
    is_aiokafka = messaging_backend != "kafka-python"
    typing_import = (
        "from typing import Any, Mapping, MutableMapping\n\n"
        if is_aiokafka
        else "from typing import Any, Mapping\n\n"
    )
    otel_helpers = _PRODUCER_OTEL_HELPERS + "\n\n" if is_aiokafka else ""

    body = (
        f'"""Generated Kafka producer for channel ``{spec.name}`` (CloudEvents envelope)."""\n'
        "from __future__ import annotations\n\n"
        "import json\n"
        "import uuid\n"
        + typing_import
        + f'CLOUDEVENTS_SPECVERSION = "1.0"\n'
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
        "def _encode_event(event: Mapping[str, Any]) -> bytes:\n"
        '    """Serialize the full CloudEvents envelope (JSON, stable key order)."""\n'
        '    return json.dumps(dict(event), separators=(",", ":"), sort_keys=True).encode("utf-8")\n\n\n'
        + otel_helpers
        + _producer_publish_block(messaging_backend)
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
    is_aiokafka = messaging_backend != "kafka-python"
    otel_helpers = _CONSUMER_OTEL_HELPERS + "\n\n" if is_aiokafka else ""

    body = (
        f'"""Generated Kafka consumer for channel ``{spec.name}``."""\n'
        "from __future__ import annotations\n\n"
        "import json\n"
        "from typing import Any, Mapping\n\n"
        f'TOPIC = "{spec.topic}"\n\n'
        f"PAYLOAD_SCHEMA: dict[str, Any] = {schema_lit}\n\n\n"
        "def _event_data(envelope: Mapping[str, Any]) -> dict[str, Any]:\n"
        '    data = envelope.get("data")\n'
        "    if not isinstance(data, dict):\n"
        '        raise ValueError("event data must be a JSON object")\n'
        "    return data\n\n\n"
        "def parse_message(raw: bytes) -> dict[str, Any]:\n"
        '    """Parse a CloudEvents JSON envelope and return the ``data`` object."""\n'
        '    return _event_data(json.loads(raw.decode("utf-8")))\n\n\n'
        + otel_helpers
        + _consumer_consume_block(messaging_backend)
    )
    return header + "\n\n" + body
