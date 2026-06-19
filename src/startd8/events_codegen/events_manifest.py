"""Parse ``events.yaml`` — opt-in AsyncAPI-shaped event overlay."""

from __future__ import annotations

from typing import List, Tuple

import yaml

from .models import EventChannelSpec

_VALID_DIRECTIONS = frozenset({"publish", "subscribe"})


def parse_events_manifest(text: str) -> Tuple[EventChannelSpec, ...]:
    data = yaml.safe_load(text or "") or {}
    if not isinstance(data, dict):
        raise ValueError("events.yaml must be a mapping")
    unknown = set(data) - {"channels"}
    if unknown:
        raise ValueError(f"events.yaml has unknown top-level keys {sorted(unknown)}")
    channels = data.get("channels") or {}
    if not isinstance(channels, dict) or not channels:
        raise ValueError("events.yaml must declare at least one channel under `channels`")
    specs: List[EventChannelSpec] = []
    for name, item in channels.items():
        if not isinstance(name, str) or not name:
            raise ValueError("events.yaml channel names must be non-empty strings")
        if not isinstance(item, dict):
            raise ValueError(f"events.yaml channels.{name} must be a mapping")
        unknown_item = set(item) - {"direction", "topic", "payload"}
        if unknown_item:
            raise ValueError(f"events.yaml channels.{name} unknown keys {sorted(unknown_item)}")
        direction = str(item.get("direction", "")).lower()
        topic = item.get("topic")
        payload = item.get("payload")
        if direction not in _VALID_DIRECTIONS:
            raise ValueError(
                f"events.yaml channels.{name}.direction must be publish or subscribe, got {direction!r}"
            )
        if not isinstance(topic, str) or not topic.strip():
            raise ValueError(f"events.yaml channels.{name}.topic is required")
        if not isinstance(payload, str) or not payload.strip():
            raise ValueError(f"events.yaml channels.{name}.payload is required")
        specs.append(
            EventChannelSpec(
                name=name,
                direction=direction,
                topic=topic.strip(),
                payload=payload.strip(),
            )
        )
    return tuple(specs)
