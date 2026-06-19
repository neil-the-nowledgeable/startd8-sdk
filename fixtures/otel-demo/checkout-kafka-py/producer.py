#!/usr/bin/env python3
"""Kafka producer port of checkout order-event publish (Step 2).

Pattern fixture — Tier 1 NR-2 (no benchmark cell).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from confluent_kafka import Producer

_PROTO = Path(__file__).resolve().parents[1] / "_proto"
if str(_PROTO) not in sys.path:
    sys.path.insert(0, str(_PROTO))

import demo_pb2  # noqa: E402

TOPIC = "orders"


def _delivery(err, msg) -> None:
    if err:
        raise RuntimeError(err)


def publish_order(order: demo_pb2.OrderResult) -> None:
    servers = os.environ.get("KAFKA_ADDR", "localhost:9092")
    producer = Producer({"bootstrap.servers": servers})
    payload = order.SerializeToString()
    producer.produce(
        TOPIC,
        value=payload,
        callback=_delivery,
    )
    producer.flush()


def sample_order() -> demo_pb2.OrderResult:
    order = demo_pb2.OrderResult()
    order.order_id = "fixture-order-1"
    order.shipping_tracking_id = "TRACK-001"
    return order


if __name__ == "__main__":
    publish_order(sample_order())
