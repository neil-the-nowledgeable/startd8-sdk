#!/usr/bin/env python3
"""Kafka consumer port of accounting/Consumer.cs (Step 1).

Pattern fixture — not a benchmark matrix cell (Tier 1 NR-2).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from confluent_kafka import Consumer, KafkaError

# Shared protobuf stubs from upstream demo tag 2.2.0
_PROTO = Path(__file__).resolve().parents[1] / "_proto"
if str(_PROTO) not in sys.path:
    sys.path.insert(0, str(_PROTO))

import demo_pb2  # noqa: E402

from models import OrderEntity, OrderItemEntity, session_factory, ShippingEntity  # noqa: E402

TOPIC = "orders"


def _persist_order(order: demo_pb2.OrderResult, session_factory) -> None:
    if session_factory is None:
        return
    Session = session_factory()
    with Session() as db:
        db.add(OrderEntity(id=order.order_id))
        for item in order.items:
            db.add(
                OrderItemEntity(
                    order_id=order.order_id,
                    product_id=item.item.product_id,
                    quantity=item.item.quantity,
                    item_cost_currency_code=item.cost.currency_code,
                    item_cost_units=item.cost.units,
                    item_cost_nanos=item.cost.nanos,
                )
            )
        addr = order.shipping_address
        db.add(
            ShippingEntity(
                order_id=order.order_id,
                shipping_tracking_id=order.shipping_tracking_id,
                shipping_cost_currency_code=order.shipping_cost.currency_code,
                shipping_cost_units=order.shipping_cost.units,
                shipping_cost_nanos=order.shipping_cost.nanos,
                street_address=addr.street_address,
                city=addr.city,
                state=addr.state,
                country=addr.country,
                zip_code=addr.zip_code,
            )
        )
        db.commit()


def run_consumer() -> None:
    servers = os.environ.get("KAFKA_ADDR", "localhost:9092")
    consumer = Consumer(
        {
            "bootstrap.servers": servers,
            "group.id": "accounting-py",
            "auto.offset.reset": "earliest",
        }
    )
    consumer.subscribe([TOPIC])
    sf = session_factory()
    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                raise RuntimeError(msg.error())
            order = demo_pb2.OrderResult.FromString(msg.value())
            _persist_order(order, sf)
    finally:
        consumer.close()


if __name__ == "__main__":
    run_consumer()
