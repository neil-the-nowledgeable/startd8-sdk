"""Orchestrate events overlay rendering from ``events.yaml`` + Prisma schema."""

from __future__ import annotations

from typing import List, Tuple

from .events_manifest import parse_events_manifest
from .kafka_renderers import render_consumer, render_producer


def render_events_artifacts(
    events_text: str,
    schema_text: str,
    *,
    events_source: str = "events.yaml",
    schema_source: str = "prisma/schema.prisma",
    messaging_backend: str = "aiokafka",
    package: str = "app",
) -> List[Tuple[str, str]]:
    """Return ``(relative_path, content)`` pairs for declared channels."""
    if messaging_backend not in ("aiokafka", "kafka-python"):
        raise ValueError(
            f"messaging.backend must be 'aiokafka' or 'kafka-python', got {messaging_backend!r}"
        )
    specs = parse_events_manifest(events_text)
    artifacts: List[Tuple[str, str]] = []
    for spec in specs:
        common = {
            "spec": spec,
            "schema_text": schema_text,
            "events_text": events_text,
            "events_source": events_source.replace("\\", "/"),
            "schema_source": schema_source.replace("\\", "/"),
            "messaging_backend": messaging_backend,
        }
        if spec.direction == "publish":
            rel = f"{package}/events/{spec.name}_producer.py"
            artifacts.append((rel, render_producer(**common)))
        else:
            rel = f"{package}/events/{spec.name}_consumer.py"
            artifacts.append((rel, render_consumer(**common)))
    return artifacts
