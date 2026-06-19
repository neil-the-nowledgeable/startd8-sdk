# GENERATED from prisma/schema.prisma — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: python-openapi-client
# Source of truth: the Prisma schema.
# schema-sha256: 0b898e5f7f7f45151610a0e3830b0b5c32150ec8cc732b449b0d0ea40e8ce102

from __future__ import annotations

import httpx

from app.tables import OrderConfirmation, OrderConfirmationCreate, OrderConfirmationRead, OrderConfirmationUpdate


class ApiClient:
    """Minimal typed HTTP client for schema-derived CRUD routes."""

    def __init__(self, base_url: str, *, client: httpx.Client | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            self._client = httpx.Client(base_url=self._base_url)
            self._owns_client = True

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "ApiClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
    def list_orderconfirmation(self) -> list[OrderConfirmationRead]:
        """``GET /orderconfirmation/`` — list all OrderConfirmation rows."""
        resp = self._client.get("/orderconfirmation/")
        resp.raise_for_status()
        return [OrderConfirmationRead.model_validate(row) for row in resp.json()]


    def create_orderconfirmation(self, item: OrderConfirmationCreate) -> OrderConfirmationRead:
        """``POST /orderconfirmation/`` — create a OrderConfirmation."""
        resp = self._client.post("/orderconfirmation/", json=item.model_dump())
        resp.raise_for_status()
        return OrderConfirmationRead.model_validate(resp.json())


    def get_orderconfirmation(self, item_id: str) -> OrderConfirmationRead:
        """``GET /orderconfirmation/{item_id}`` — fetch one OrderConfirmation."""
        resp = self._client.get(f"/orderconfirmation/{item_id}")
        resp.raise_for_status()
        return OrderConfirmationRead.model_validate(resp.json())


    def update_orderconfirmation(self, item_id: str, item: OrderConfirmationUpdate) -> OrderConfirmationRead:
        """``PATCH /orderconfirmation/{item_id}`` — partial update."""
        resp = self._client.patch(f"/orderconfirmation/{item_id}", json=item.model_dump(exclude_unset=True))
        resp.raise_for_status()
        return OrderConfirmationRead.model_validate(resp.json())


    def delete_orderconfirmation(self, item_id: str) -> None:
        """``DELETE /orderconfirmation/{item_id}`` — remove a OrderConfirmation."""
        resp = self._client.delete(f"/orderconfirmation/{item_id}")
        resp.raise_for_status()
