"""Valkey/Redis cart store — port of ValkeyCartStore.cs (Step 4)."""
from __future__ import annotations

import json
import os
from typing import Any

import redis


class ValkeyCartStore:
    def __init__(self, address: str | None = None) -> None:
        addr = address or os.environ.get("VALKEY_ADDR", "localhost:6379")
        self._client = redis.Redis.from_url(f"redis://{addr}", decode_responses=True)

    def get_cart(self, user_id: str) -> list[dict[str, Any]]:
        raw = self._client.get(self._key(user_id))
        if not raw:
            return []
        return json.loads(raw)

    def add_item(self, user_id: str, product_id: str, quantity: int) -> list[dict[str, Any]]:
        items = self.get_cart(user_id)
        for item in items:
            if item.get("product_id") == product_id:
                item["quantity"] = int(item.get("quantity", 0)) + quantity
                break
        else:
            items.append({"product_id": product_id, "quantity": quantity})
        self._client.set(self._key(user_id), json.dumps(items))
        return items

    def empty_cart(self, user_id: str) -> None:
        self._client.delete(self._key(user_id))

    @staticmethod
    def _key(user_id: str) -> str:
        return f"cart:{user_id}"
