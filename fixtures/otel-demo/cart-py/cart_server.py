#!/usr/bin/env python3
"""gRPC CartService port (Step 4)."""
from __future__ import annotations

import os
import sys
from concurrent import futures
from pathlib import Path

import grpc
from openfeature import api
from openfeature.contrib.provider.flagd import FlagdProvider

_PROTO = Path(__file__).resolve().parents[1] / "_proto"
if str(_PROTO) not in sys.path:
    sys.path.insert(0, str(_PROTO))

import demo_pb2  # noqa: E402
import demo_pb2_grpc  # noqa: E402

from valkey_store import ValkeyCartStore  # noqa: E402


class CartService(demo_pb2_grpc.CartServiceServicer):
    def __init__(self, store: ValkeyCartStore) -> None:
        self._store = store

    def AddItem(self, request, context):
        self._store.add_item(request.user_id, request.item.product_id, request.item.quantity)
        return demo_pb2.Empty()

    def GetCart(self, request, context):
        items = self._store.get_cart(request.user_id)
        resp = demo_pb2.Cart()
        for row in items:
            resp.items.add(product_id=row["product_id"], quantity=int(row["quantity"]))
        return resp

    def EmptyCart(self, request, context):
        self._store.empty_cart(request.user_id)
        return demo_pb2.Empty()


def serve() -> None:
    api.set_provider(FlagdProvider())
    port = os.environ.get("CART_PORT", "7070")
    store = ValkeyCartStore()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    demo_pb2_grpc.add_CartServiceServicer_to_server(CartService(store), server)
    server.add_insecure_port(f"0.0.0.0:{port}")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
