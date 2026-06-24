"""Pure-Python validation of the cartservice ground-truth suite (no subprocess, no .NET).

Stand up an in-process gRPC CartService (a stateful IN-MEMORY oracle) and prove ``run_cart_suite``
reaches coverage 1.00 against a *correct* servicer — so the suite's stateful expectations are
internally consistent — then prove it DISCRIMINATES per case against deliberately-broken servicers
(the same failure shapes the C# ``cart_broken`` fixture exercises live). Also covers the equal-weight
per-case coverage shape and suite registration on the leaf path.

CartService is STATEFUL: each case drives a SEQUENCE of RPCs (AddItem→GetCart, EmptyCart→GetCart) on
a fresh user_id; the cart returned by GetCart must reflect prior AddItem/EmptyCart calls.
"""
from __future__ import annotations

import socket
import threading
from concurrent import futures

import grpc
import pytest

from startd8.benchmark_matrix.behavioral import demo_pb2, demo_pb2_grpc, execute
from startd8.benchmark_matrix.behavioral.cart_suite import (
    CASE_NAMES,
    SUITE_VERSION,
    run_cart_suite,
)

pytestmark = pytest.mark.unit


class _ReferenceCart(demo_pb2_grpc.CartServiceServicer):
    """A correct, stateful in-memory CartService — the in-process oracle (no Redis).

    AddItem accumulates the quantity for a repeated product (upstream OB semantics); GetCart reflects
    the per-user store; EmptyCart clears it; GetCart for an unknown user returns an empty cart."""

    def __init__(self) -> None:
        self._store: dict = {}
        self._lock = threading.Lock()

    def AddItem(self, request, context):
        with self._lock:
            items = self._store.setdefault(request.user_id, {})
            items[request.item.product_id] = items.get(request.item.product_id, 0) + request.item.quantity
        return demo_pb2.Empty()

    def GetCart(self, request, context):
        cart = demo_pb2.Cart(user_id=request.user_id)
        with self._lock:
            for pid, qty in self._store.get(request.user_id, {}).items():
                cart.items.append(demo_pb2.CartItem(product_id=pid, quantity=qty))
        return cart

    def EmptyCart(self, request, context):
        with self._lock:
            self._store.pop(request.user_id, None)
        return demo_pb2.Empty()


class _BrokenAlwaysEmpty(_ReferenceCart):
    """GetCart always returns an empty cart (ignores AddItem) — the live ``cart_broken`` fixture.

    The four stateful cases fail; only the unknown-user case (which expects empty) coincidentally
    passes."""

    def GetCart(self, request, context):
        return demo_pb2.Cart(user_id=request.user_id)


class _BrokenNoAccumulate(_ReferenceCart):
    """A repeated AddItem OVERWRITES the quantity instead of accumulating (2 then 3 → 3, not 5).

    Only ``add_twice_accumulates`` fails."""

    def AddItem(self, request, context):
        with self._lock:
            items = self._store.setdefault(request.user_id, {})
            items[request.item.product_id] = request.item.quantity  # set, not +=
        return demo_pb2.Empty()


class _BrokenEmptyNoop(_ReferenceCart):
    """EmptyCart is a no-op (doesn't clear) — only ``empty_then_get_is_empty`` fails."""

    def EmptyCart(self, request, context):
        return demo_pb2.Empty()


class _BrokenUnknownErrors(_ReferenceCart):
    """GetCart for a user that was never touched raises NOT_FOUND instead of an empty cart.

    Only ``get_unknown_user_is_empty`` fails: the other cases first AddItem (or EmptyCart, which here
    leaves an empty entry rather than popping), so the user is known and GetCart returns normally."""

    def EmptyCart(self, request, context):
        # Leave an (empty) entry so a post-EmptyCart GetCart is still "known" (empty, not NOT_FOUND).
        with self._lock:
            self._store[request.user_id] = {}
        return demo_pb2.Empty()

    def GetCart(self, request, context):
        with self._lock:
            known = request.user_id in self._store
        if not known:
            context.abort(grpc.StatusCode.NOT_FOUND, "no cart")
        return super().GetCart(request, context)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _serve(servicer):
    port = _free_port()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    demo_pb2_grpc.add_CartServiceServicer_to_server(servicer, server)
    server.add_insecure_port(f"127.0.0.1:{port}")
    server.start()
    return server, port


# --------------------------------------------------------------------------- oracle self-consistency


def test_reference_cart_scores_full_coverage():
    server, port = _serve(_ReferenceCart())
    try:
        suite = run_cart_suite(port)
    finally:
        server.stop(grace=None)
    failing = [r.__dict__ for r in suite.results if not r.passed]
    assert suite.coverage == 1.0, f"coverage={suite.coverage}; failing={failing}"
    assert suite.suite_version == SUITE_VERSION
    # Five equal-weight stateful cases.
    assert len(suite.results) == 5
    assert [r.name for r in suite.results] == CASE_NAMES


# --------------------------------------------------------------------------- per-case discrimination


def test_broken_always_empty_fails_stateful_cases():
    """The ``cart_broken`` shape: GetCart never reflects state → every stateful case fails, only the
    unknown-user case (which expects empty) passes."""
    server, port = _serve(_BrokenAlwaysEmpty())
    try:
        suite = run_cart_suite(port)
    finally:
        server.stop(grace=None)
    failed = {r.name for r in suite.results if not r.passed}
    assert failed == {
        "add_then_get_reflects_item",
        "add_twice_accumulates",
        "add_distinct_products",
    }, [r.__dict__ for r in suite.results]
    # empty_then_get_is_empty and get_unknown_user_is_empty still pass (both expect an empty cart).
    assert suite.coverage == 2 / 5


def test_broken_no_accumulate_fails_only_accumulate_case():
    server, port = _serve(_BrokenNoAccumulate())
    try:
        suite = run_cart_suite(port)
    finally:
        server.stop(grace=None)
    failed = {r.name for r in suite.results if not r.passed}
    assert failed == {"add_twice_accumulates"}, [r.__dict__ for r in suite.results]
    assert suite.coverage == 4 / 5


def test_broken_empty_noop_fails_only_empty_case():
    server, port = _serve(_BrokenEmptyNoop())
    try:
        suite = run_cart_suite(port)
    finally:
        server.stop(grace=None)
    failed = {r.name for r in suite.results if not r.passed}
    assert failed == {"empty_then_get_is_empty"}, [r.__dict__ for r in suite.results]


def test_broken_unknown_errors_fails_only_unknown_case():
    server, port = _serve(_BrokenUnknownErrors())
    try:
        suite = run_cart_suite(port)
    finally:
        server.stop(grace=None)
    failed = {r.name for r in suite.results if not r.passed}
    assert failed == {"get_unknown_user_is_empty"}, [r.__dict__ for r in suite.results]


def test_connect_error_when_no_server():
    suite = run_cart_suite(_free_port(), connect_timeout=0.5)
    assert suite.connect_error
    assert suite.coverage == 0.0
    assert suite.results == []


# --------------------------------------------------------------------------- wiring


def test_cart_registered_in_suites_leaf_path():
    assert execute._SUITES.get("cartservice") is run_cart_suite
    # Leaf path: NOT the checkout dedicated branch, NOT a per-service proto override (shared demo.proto).
    assert "cartservice" not in execute._PROTO_BY_SERVICE
