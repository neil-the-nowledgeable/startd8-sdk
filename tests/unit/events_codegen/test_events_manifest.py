"""events.yaml parser tests (Tier-1 PR4)."""

from __future__ import annotations

import pytest

from startd8.events_codegen import parse_events_manifest

pytestmark = pytest.mark.unit

VALID = """
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


def test_parse_events_manifest():
    specs = parse_events_manifest(VALID)
    assert len(specs) == 2
    pub = next(s for s in specs if s.name == "order_paid")
    assert pub.direction == "publish"
    assert pub.topic == "orders.paid"
    assert pub.payload == "Order"


def test_empty_channels_fails():
    with pytest.raises(ValueError, match="at least one channel"):
        parse_events_manifest("channels: {}\n")


def test_invalid_direction_fails():
    with pytest.raises(ValueError, match="direction must be publish or subscribe"):
        parse_events_manifest(
            "channels:\n  x:\n    direction: emit\n    topic: t\n    payload: Order\n"
        )
