# GENERATED from prisma/schema.prisma — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: python-openapi-client
# Source of truth: the Prisma schema.
# schema-sha256: b914136a55bbc023ec648d2a29986a918c88b6e70d55d4300cd1a0e7725e70ba

from __future__ import annotations

import httpx

from app.tables import PlaceOrderSession, PlaceOrderSessionCreate, PlaceOrderSessionRead, PlaceOrderSessionUpdate


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
    def list_placeordersession(self) -> list[PlaceOrderSessionRead]:
        """``GET /placeordersession/`` — list all PlaceOrderSession rows."""
        resp = self._client.get("/placeordersession/")
        resp.raise_for_status()
        return [PlaceOrderSessionRead.model_validate(row) for row in resp.json()]


    def create_placeordersession(self, item: PlaceOrderSessionCreate) -> PlaceOrderSessionRead:
        """``POST /placeordersession/`` — create a PlaceOrderSession."""
        resp = self._client.post("/placeordersession/", json=item.model_dump())
        resp.raise_for_status()
        return PlaceOrderSessionRead.model_validate(resp.json())


    def get_placeordersession(self, item_id: str) -> PlaceOrderSessionRead:
        """``GET /placeordersession/{item_id}`` — fetch one PlaceOrderSession."""
        resp = self._client.get(f"/placeordersession/{item_id}")
        resp.raise_for_status()
        return PlaceOrderSessionRead.model_validate(resp.json())


    def update_placeordersession(self, item_id: str, item: PlaceOrderSessionUpdate) -> PlaceOrderSessionRead:
        """``PATCH /placeordersession/{item_id}`` — partial update."""
        resp = self._client.patch(f"/placeordersession/{item_id}", json=item.model_dump(exclude_unset=True))
        resp.raise_for_status()
        return PlaceOrderSessionRead.model_validate(resp.json())


    def delete_placeordersession(self, item_id: str) -> None:
        """``DELETE /placeordersession/{item_id}`` — remove a PlaceOrderSession."""
        resp = self._client.delete(f"/placeordersession/{item_id}")
        resp.raise_for_status()
