"""productcatalogservice behavioral ground-truth suite (Track-2 expansion — first stateful-LOCAL leaf).

ProductCatalogService is a **leaf** service: it has no gRPC peers, it reads a local ``products.json``
catalog file (the cell's only state). The harness OWNS that file (``CATALOG_PRODUCTS`` →
``products_json()``) and provisions it into the launched server's workdir, so the correct responses
are known BEFORE any model is judged — the oracle-first contract the checkout suite established.

SDK-authored, language-agnostic over the gRPC wire: it talks to a live ProductCatalogService on
``127.0.0.1:<port>`` regardless of what language the server was generated in, and asserts the three
RPCs' *behavior* against the seeded catalog (the discriminating signal; static coverage saturates):

  - ``ListProducts``  → returns exactly the N seeded products (by id).
  - ``GetProduct(known id)``   → returns the matching product (id + name + price).
  - ``GetProduct(absent id)``  → the RPC is rejected (NOT_FOUND), not an empty/zero Product.
  - ``SearchProducts(query that matches)``  → returns the expected product(s).
  - ``SearchProducts(query that matches nothing)`` → an empty result set (no error).

``coverage`` ∈ [0,1] = passing RPCs / total (equal weight per RPC); provenance carries the suite
version + per-RPC results. Reuses :class:`RpcResult` / :class:`SuiteResult` from ``charge_suite``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List

import grpc

from . import demo_pb2, demo_pb2_grpc
from .charge_suite import RpcResult, SuiteResult

SUITE_VERSION = "catalog-suite/1"

# On-disk name + relative location the launched server's cwd is expected to read (OB convention:
# products.json next to the binary / in the service working dir). Provisioned by execute.py.
PRODUCTS_FILENAME = "products.json"


@dataclass(frozen=True)
class _Product:
    id: str
    name: str
    description: str
    categories: List[str]
    price_units: int
    price_nanos: int = 0
    currency: str = "USD"

    def as_json(self) -> Dict:
        """The upstream-OB products.json product shape (price_usd as a Money sub-object)."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "picture": f"/static/img/products/{self.id}.jpg",
            "priceUsd": {
                "currencyCode": self.currency,
                "units": self.price_units,
                "nanos": self.price_nanos,
            },
            "categories": list(self.categories),
        }


# ---- Ground truth: a small, fixed 3-product catalog with deterministic ids/names/prices ---------
# Ids mirror the upstream hipstershop style (10-char alnum) so a model copying the canonical
# products.json would coincidentally match — but the harness OWNS this file, so the response is
# fixed regardless of what the model would have shipped.
CATALOG_PRODUCTS: List[_Product] = [
    _Product("OLJCESPC7Z", "Sunglasses",
             "Add a modern touch to your outfits with these sleek aviator sunglasses.",
             ["accessories"], 19, 990_000_000),
    _Product("66VCHSJNUP", "Tank Top",
             "Perfectly cropped cotton tank, with a scooped neckline.",
             ["clothing", "tops"], 18, 990_000_000),
    _Product("1YMWWN1N4O", "Watch",
             "This gold-tone stainless steel watch will work with most of your outfits.",
             ["accessories"], 109, 990_000_000),
]

_BY_ID: Dict[str, _Product] = {p.id: p for p in CATALOG_PRODUCTS}

# A known-present id, a guaranteed-absent id, a query that matches exactly one product by name,
# and a query that matches nothing — all derived from CATALOG_PRODUCTS so they can't drift.
KNOWN_ID = "OLJCESPC7Z"          # Sunglasses
ABSENT_ID = "NO_SUCH_PRODUCT_X"  # not in the catalog → GetProduct must NOT_FOUND
MATCH_QUERY = "Watch"            # matches exactly the Watch product (by name)
EXPECTED_MATCH_IDS = {"1YMWWN1N4O"}
NO_MATCH_QUERY = "zzz_nonexistent_query_zzz"  # matches nothing → empty results, no error


def products_json() -> str:
    """The canonical ground-truth ``products.json`` body (upstream-OB ``{"products": [...]}`` shape).

    The harness writes this into the launched server's workdir so ListProducts/GetProduct/Search
    have fixed, known-correct responses. Generated once here; never derived from model output."""
    return json.dumps({"products": [p.as_json() for p in CATALOG_PRODUCTS]}, indent=2)


def run_catalog_suite(port: int, *, host: str = "127.0.0.1",
                      connect_timeout: float = 5.0) -> SuiteResult:
    """Connect to a live ProductCatalogService and run the catalog ground-truth checks (the client
    window). Same SuiteResult/coverage shape as the charge/shipping leaf suites — invoked by
    ``run_service_sandboxed`` as ``client(port)``."""
    suite = SuiteResult(suite_version=SUITE_VERSION)
    try:
        channel = grpc.insecure_channel(f"{host}:{port}")
        grpc.channel_ready_future(channel).result(timeout=connect_timeout)
    except Exception as e:  # noqa: BLE001 — failure to connect is an env outcome (degrade upstream)
        suite.connect_error = f"{type(e).__name__}: {e}"
        return suite
    try:
        stub = demo_pb2_grpc.ProductCatalogServiceStub(channel)

        # 1) ListProducts → exactly the N seeded products, identified by id.
        try:
            resp = stub.ListProducts(demo_pb2.Empty(), timeout=5.0)
            got_ids = {p.id for p in resp.products}
            ok = got_ids == set(_BY_ID)
            suite.results.append(RpcResult(
                "list_products_all_seeded", ok,
                f"got {sorted(got_ids)} want {sorted(_BY_ID)}"))
        except grpc.RpcError as e:
            suite.results.append(RpcResult("list_products_all_seeded", False, f"error: {e.code()}"))

        # 2) GetProduct(known id) → the matching product (id + name + price match the seed).
        try:
            p = stub.GetProduct(demo_pb2.GetProductRequest(id=KNOWN_ID), timeout=5.0)
            want = _BY_ID[KNOWN_ID]
            ok = (p.id == want.id and p.name == want.name
                  and p.price_usd.units == want.price_units
                  and p.price_usd.nanos == want.price_nanos)
            suite.results.append(RpcResult(
                "get_product_known_id", ok,
                f"id={p.id!r} name={p.name!r} price={p.price_usd.units}.{p.price_usd.nanos}"))
        except grpc.RpcError as e:
            suite.results.append(RpcResult("get_product_known_id", False, f"error: {e.code()}"))

        # 3) GetProduct(absent id) → must be REJECTED (NOT_FOUND), not a silent empty Product.
        try:
            p = stub.GetProduct(demo_pb2.GetProductRequest(id=ABSENT_ID), timeout=5.0)
            # Some naive impls return a zero-value Product instead of erroring — that is a MISS.
            suite.results.append(RpcResult(
                "get_product_absent_not_found", False,
                f"returned a product for an absent id (id={p.id!r})"))
        except grpc.RpcError as e:
            ok = e.code() == grpc.StatusCode.NOT_FOUND
            suite.results.append(RpcResult(
                "get_product_absent_not_found", ok,
                "NOT_FOUND" if ok else f"rejected but wrong code: {e.code()}"))

        # 4) SearchProducts(matching query) → the expected product(s).
        try:
            r = stub.SearchProducts(demo_pb2.SearchProductsRequest(query=MATCH_QUERY), timeout=5.0)
            got = {p.id for p in r.results}
            ok = EXPECTED_MATCH_IDS.issubset(got)
            suite.results.append(RpcResult(
                "search_products_match", ok,
                f"query={MATCH_QUERY!r} got {sorted(got)} want⊇{sorted(EXPECTED_MATCH_IDS)}"))
        except grpc.RpcError as e:
            suite.results.append(RpcResult("search_products_match", False, f"error: {e.code()}"))

        # 5) SearchProducts(no-match query) → empty results, NOT an error.
        try:
            r = stub.SearchProducts(demo_pb2.SearchProductsRequest(query=NO_MATCH_QUERY), timeout=5.0)
            ok = len(r.results) == 0
            suite.results.append(RpcResult(
                "search_products_no_match_empty", ok,
                f"query={NO_MATCH_QUERY!r} returned {len(r.results)} results"))
        except grpc.RpcError as e:
            suite.results.append(RpcResult(
                "search_products_no_match_empty", False, f"unexpected error: {e.code()}"))
    finally:
        channel.close()
    return suite
