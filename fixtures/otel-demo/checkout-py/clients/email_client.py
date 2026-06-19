# GENERATED from prisma/schema.prisma (+ contexts.yaml) — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: python-context-client
# startd8-entity: email
# Source of truth: the Prisma schema, contexts manifest, and producer contract snapshot.
# schema-sha256: b914136a55bbc023ec648d2a29986a918c88b6e70d55d4300cd1a0e7725e70ba
# contexts-sha256: 074ccef8b51da9de39da42467d525aa1967723ddaaa0844f34156d15d1826547
# contract-sha256: 299289569c938de0f8096dc6e5460a18dda169ec9d1872d4683d7eb76628ac24

from __future__ import annotations

import httpx

from clients._context_otel import trace_outbound_request



class EmailClient:
    """Typed HTTP client for outbound context 'email' (../openapi/email.json)."""
    # Default base URL (override in __init__): http://email:8080

    def __init__(self, base_url: str, *, client: httpx.Client | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            self._client = httpx.Client(base_url=self._base_url)
            self._owns_client = True
        self._producer_id = "email"

    def _auth_headers(self) -> dict[str, str]:
        return {}
    def _request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        headers = dict(kwargs.pop('headers', None) or {})
        headers.update(self._auth_headers())
        if headers:
            kwargs['headers'] = headers
        def _do() -> httpx.Response:
            return getattr(self._client, method.lower())(path, **kwargs)
        return trace_outbound_request(self._producer_id, method, path, _do)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "EmailClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
    def list_orderconfirmation(self) -> dict[str, object]:
        """``GET /orderconfirmation/`` — pinned contract operation."""
        resp = self._request('GET', "/orderconfirmation/")
        resp.raise_for_status()
        return resp.json()


    def create_orderconfirmation(self, body: dict[str, object]) -> dict[str, object]:
        """``POST /orderconfirmation/`` — pinned contract operation."""
        resp = self._request('POST', "/orderconfirmation/", json=body)
        resp.raise_for_status()
        return resp.json()


    def get_orderconfirmation(self, item_id: str) -> dict[str, object]:
        """``GET /orderconfirmation/{item_id}`` — pinned contract operation."""
        resp = self._request('GET', f"/orderconfirmation/{item_id}")
        resp.raise_for_status()
        return resp.json()


    def update_orderconfirmation(self, item_id: str, body: dict[str, object]) -> dict[str, object]:
        """``PATCH /orderconfirmation/{item_id}`` — pinned contract operation."""
        resp = self._request('PATCH', f"/orderconfirmation/{item_id}", json=body)
        resp.raise_for_status()
        return resp.json()


    def post_send_order_confirmation(self, body: dict[str, object]) -> None:
        """``POST /send_order_confirmation`` — pinned contract operation."""
        resp = self._request('POST', "/send_order_confirmation", json=body)
        resp.raise_for_status()
