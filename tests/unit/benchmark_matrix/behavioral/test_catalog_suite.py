"""Pure-Python validation of the productcatalogservice ground-truth suite (no Go).

Mirrors ``test_pricing_suite.py``: stand up an in-process gRPC ProductCatalogService backed by the
harness-owned ground-truth catalog and prove ``run_catalog_suite`` reaches coverage 1.00 against a
*correct* servicer (so the suite's expected values are internally consistent), then prove it
DISCRIMINATES against deliberately-broken servicers per RPC. Also covers ground-truth products.json
construction, the equal-weight per-RPC coverage shape, suite registration, and state provisioning.

The benchmarked model writes its own Go server; these tests only prove the oracle is self-consistent
and the suite/registration/provisioning wiring is correct.
"""
from __future__ import annotations

import json
import socket
from concurrent import futures

import grpc
import pytest

from startd8.benchmark_matrix.behavioral import demo_pb2, demo_pb2_grpc, execute
from startd8.benchmark_matrix.behavioral.catalog_suite import (
    ABSENT_ID,
    CATALOG_PRODUCTS,
    EXPECTED_MATCH_IDS,
    KNOWN_ID,
    MATCH_QUERY,
    NO_MATCH_QUERY,
    PRODUCTS_FILENAME,
    SUITE_VERSION,
    products_json,
    run_catalog_suite,
)

pytestmark = pytest.mark.unit

_BY_ID = {p.id: p for p in CATALOG_PRODUCTS}


def _products() -> list:
    return [
        demo_pb2.Product(
            id=p.id, name=p.name, description=p.description,
            price_usd=demo_pb2.Money(currency_code=p.currency, units=p.price_units, nanos=p.price_nanos),
            categories=list(p.categories),
        )
        for p in CATALOG_PRODUCTS
    ]


class _ReferenceCatalog(demo_pb2_grpc.ProductCatalogServiceServicer):
    """A correct ProductCatalogService — the in-process oracle the suite is validated against."""

    def ListProducts(self, request, context):
        return demo_pb2.ListProductsResponse(products=_products())

    def GetProduct(self, request, context):
        for p in _products():
            if p.id == request.id:
                return p
        context.abort(grpc.StatusCode.NOT_FOUND, f"no product {request.id}")

    def SearchProducts(self, request, context):
        q = request.query.strip().lower()
        results = [p for p in _products()
                   if q and (q in p.name.lower() or q in p.description.lower())]
        return demo_pb2.SearchProductsResponse(results=results)


class _BrokenAbsent(_ReferenceCatalog):
    """Ignores NOT_FOUND: returns a zero Product for an absent id (the Go broken-variant analogue)."""

    def GetProduct(self, request, context):
        for p in _products():
            if p.id == request.id:
                return p
        return demo_pb2.Product()


class _BrokenList(_ReferenceCatalog):
    """Drops one product from ListProducts (incomplete catalog)."""

    def ListProducts(self, request, context):
        return demo_pb2.ListProductsResponse(products=_products()[1:])


class _BrokenSearch(_ReferenceCatalog):
    """Returns everything for every query → the no-match case must fail."""

    def SearchProducts(self, request, context):
        return demo_pb2.SearchProductsResponse(results=_products())


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _serve(servicer):
    port = _free_port()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    demo_pb2_grpc.add_ProductCatalogServiceServicer_to_server(servicer, server)
    server.add_insecure_port(f"127.0.0.1:{port}")
    server.start()
    return server, port


@pytest.fixture()
def reference_port():
    server, port = _serve(_ReferenceCatalog())
    try:
        yield port
    finally:
        server.stop(grace=None)


# --------------------------------------------------------------------------- oracle self-consistency


def test_reference_catalog_scores_full_coverage(reference_port):
    suite = run_catalog_suite(reference_port)
    failing = [r.__dict__ for r in suite.results if not r.passed]
    assert suite.coverage == 1.0, f"coverage={suite.coverage}; failing={failing}"
    assert suite.suite_version == SUITE_VERSION
    # Five equal-weight per-RPC cases.
    assert len(suite.results) == 5
    assert {r.name for r in suite.results} == {
        "list_products_all_seeded",
        "get_product_known_id",
        "get_product_absent_not_found",
        "search_products_match",
        "search_products_no_match_empty",
    }


# --------------------------------------------------------------------------- per-RPC discrimination


def test_broken_absent_fails_only_not_found_case():
    server, port = _serve(_BrokenAbsent())
    try:
        suite = run_catalog_suite(port)
    finally:
        server.stop(grace=None)
    failed = {r.name for r in suite.results if not r.passed}
    assert failed == {"get_product_absent_not_found"}, [r.__dict__ for r in suite.results]
    assert suite.coverage == 4 / 5


def test_broken_list_fails_only_list_case():
    server, port = _serve(_BrokenList())
    try:
        suite = run_catalog_suite(port)
    finally:
        server.stop(grace=None)
    failed = {r.name for r in suite.results if not r.passed}
    assert failed == {"list_products_all_seeded"}, [r.__dict__ for r in suite.results]


def test_broken_search_fails_only_no_match_case():
    server, port = _serve(_BrokenSearch())
    try:
        suite = run_catalog_suite(port)
    finally:
        server.stop(grace=None)
    failed = {r.name for r in suite.results if not r.passed}
    # Match query still finds the expected id (superset); the no-match query wrongly returns results.
    assert failed == {"search_products_no_match_empty"}, [r.__dict__ for r in suite.results]


def test_connect_error_when_no_server():
    suite = run_catalog_suite(_free_port(), connect_timeout=0.5)
    assert suite.connect_error
    assert suite.coverage == 0.0
    assert suite.results == []


# --------------------------------------------------------------------------- ground truth + wiring


def test_products_json_is_self_consistent_ground_truth():
    doc = json.loads(products_json())
    assert set(doc) == {"products"}
    ids = [p["id"] for p in doc["products"]]
    assert ids == [p.id for p in CATALOG_PRODUCTS]
    assert KNOWN_ID in ids and ABSENT_ID not in ids
    # The match query resolves to exactly the expected id(s) over the ground-truth catalog.
    matched = {p["id"] for p in doc["products"]
               if MATCH_QUERY.lower() in p["name"].lower()
               or MATCH_QUERY.lower() in p["description"].lower()}
    assert EXPECTED_MATCH_IDS.issubset(matched)
    # The no-match query matches nothing.
    assert not any(NO_MATCH_QUERY.lower() in p["name"].lower()
                   or NO_MATCH_QUERY.lower() in p["description"].lower()
                   for p in doc["products"])


def test_catalog_registered_in_suites_leaf_path():
    assert execute._SUITES.get("productcatalogservice") is run_catalog_suite
    # Leaf path: NOT the checkout dedicated branch, NOT a per-service proto override (shared demo.proto).
    assert "productcatalogservice" not in execute._PROTO_BY_SERVICE


def test_provision_catalog_state_writes_products_json(tmp_path):
    target_files = ["src/productcatalogservice/server.go"]
    written = execute.provision_catalog_state(tmp_path, target_files)
    # Written into the service dir (server cwd) AND the workdir root (fallback).
    svc_file = tmp_path / "src" / "productcatalogservice" / PRODUCTS_FILENAME
    root_file = tmp_path / PRODUCTS_FILENAME
    assert svc_file.is_file() and root_file.is_file()
    assert svc_file.read_text() == products_json()
    assert f"src/productcatalogservice/{PRODUCTS_FILENAME}" in written
