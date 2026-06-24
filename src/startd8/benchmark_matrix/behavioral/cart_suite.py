"""cartservice behavioral ground-truth suite (Track-2 expansion — first STATEFUL leaf).

CartService is a **leaf** service (no gRPC peers). Unlike the catalog/email leaves, its correctness
is not a function of a single request — it is **stateful**: the response to one RPC depends on the
RPCs that came before it. The reference oracle keeps cart state IN-MEMORY (a per-user store, no
external Redis); the suite asserts that behavior over a *sequence* of RPCs, which is the
discriminating signal (a stub that drops state, or always returns an empty cart, fails here while a
static structural check would pass).

RPCs (demo.proto, CartService)::

    AddItem(AddItemRequest{user_id, CartItem item{product_id, quantity}}) -> Empty
    GetCart(GetCartRequest{user_id})                                      -> Cart{user_id, items}
    EmptyCart(EmptyCartRequest{user_id})                                  -> Empty

SDK-authored, language-agnostic over the gRPC wire: it talks to a live CartService on
``127.0.0.1:<port>`` regardless of what language the server was generated in, and asserts five
equal-weight stateful cases (each on a FRESH user_id so the cases don't interfere):

  - ``add_then_get_reflects_item``   — AddItem(P,q) then GetCart → the cart contains P with qty q.
  - ``add_twice_accumulates``        — AddItem(P,2) then AddItem(P,3) → GetCart shows P with qty 5
    (upstream OB semantics: a repeat add of the same product accumulates the quantity).
  - ``empty_then_get_is_empty``      — AddItem then EmptyCart then GetCart → the cart is empty.
  - ``get_unknown_user_is_empty``    — GetCart for a never-touched user → an empty cart, NOT an error.
  - ``add_distinct_products``        — two different products for one user → GetCart shows both.

``coverage`` ∈ [0,1] = passing cases / total (equal weight per case); provenance carries the suite
version + per-case results. Reuses :class:`RpcResult` / :class:`SuiteResult` from ``charge_suite``.
"""
from __future__ import annotations

import uuid
from typing import Dict, List

import grpc

from . import demo_pb2, demo_pb2_grpc
from .charge_suite import RpcResult, SuiteResult

SUITE_VERSION = "cart-suite/1"


def _uid(label: str) -> str:
    """A fresh, unique user_id per case so the five stateful cases never share cart state."""
    return f"cart-suite-{label}-{uuid.uuid4().hex[:8]}"


def _add(stub, user_id: str, product_id: str, quantity: int, timeout: float = 5.0) -> None:
    stub.AddItem(
        demo_pb2.AddItemRequest(
            user_id=user_id,
            item=demo_pb2.CartItem(product_id=product_id, quantity=quantity),
        ),
        timeout=timeout,
    )


def _get(stub, user_id: str, timeout: float = 5.0):
    return stub.GetCart(demo_pb2.GetCartRequest(user_id=user_id), timeout=timeout)


def _qty_by_product(cart) -> Dict[str, int]:
    """Collapse a Cart's repeated items into {product_id: total_quantity} (sums duplicate lines so a
    server that appends a second line instead of accumulating one is still scored on the total)."""
    out: Dict[str, int] = {}
    for it in cart.items:
        out[it.product_id] = out.get(it.product_id, 0) + it.quantity
    return out


def run_cart_suite(port: int, *, host: str = "127.0.0.1",
                   connect_timeout: float = 5.0) -> SuiteResult:
    """Connect to a live CartService and run the stateful ground-truth checks (the client window).
    Same SuiteResult/coverage shape as the charge/catalog/email leaf suites — invoked by
    ``run_service_sandboxed`` as ``client(port)`` on the plain leaf path.

    Each case drives a SEQUENCE of RPCs (the statefulness is the point) against a fresh user_id, then
    asserts the observable cart. Any ``RpcError`` on a path that should succeed is a MISS for that
    case (recorded with the gRPC code), never an exception out of the suite."""
    suite = SuiteResult(suite_version=SUITE_VERSION)
    try:
        channel = grpc.insecure_channel(f"{host}:{port}")
        grpc.channel_ready_future(channel).result(timeout=connect_timeout)
    except Exception as e:  # noqa: BLE001 — failure to connect is an env outcome (degrade upstream)
        suite.connect_error = f"{type(e).__name__}: {e}"
        return suite
    try:
        stub = demo_pb2_grpc.CartServiceStub(channel)

        # 1) AddItem then GetCart reflects the added item (with the correct quantity).
        try:
            u = _uid("addget")
            _add(stub, u, "PROD-A", 2)
            got = _qty_by_product(_get(stub, u))
            ok = got == {"PROD-A": 2}
            suite.results.append(RpcResult(
                "add_then_get_reflects_item", ok, f"cart={got} want {{'PROD-A': 2}}"))
        except grpc.RpcError as e:
            suite.results.append(RpcResult("add_then_get_reflects_item", False, f"error: {e.code()}"))

        # 2) Two adds of the SAME product accumulate the quantity (upstream OB semantics: 2+3 -> 5).
        try:
            u = _uid("accum")
            _add(stub, u, "PROD-B", 2)
            _add(stub, u, "PROD-B", 3)
            got = _qty_by_product(_get(stub, u))
            ok = got == {"PROD-B": 5}
            suite.results.append(RpcResult(
                "add_twice_accumulates", ok, f"cart={got} want {{'PROD-B': 5}}"))
        except grpc.RpcError as e:
            suite.results.append(RpcResult("add_twice_accumulates", False, f"error: {e.code()}"))

        # 3) EmptyCart clears the user's cart → a subsequent GetCart is empty.
        try:
            u = _uid("empty")
            _add(stub, u, "PROD-C", 4)
            stub.EmptyCart(demo_pb2.EmptyCartRequest(user_id=u), timeout=5.0)
            got = _qty_by_product(_get(stub, u))
            ok = got == {}
            suite.results.append(RpcResult(
                "empty_then_get_is_empty", ok, f"cart after EmptyCart = {got} (want empty)"))
        except grpc.RpcError as e:
            suite.results.append(RpcResult("empty_then_get_is_empty", False, f"error: {e.code()}"))

        # 4) GetCart for a never-touched user → an EMPTY cart, not an error (no AddItem first).
        try:
            u = _uid("unknown")
            cart = _get(stub, u)
            got = _qty_by_product(cart)
            ok = got == {}
            suite.results.append(RpcResult(
                "get_unknown_user_is_empty", ok,
                f"unknown-user cart = {got} (want empty, no error)"))
        except grpc.RpcError as e:
            # A NOT_FOUND / error for an unknown user is a MISS — OB returns an empty cart.
            suite.results.append(RpcResult(
                "get_unknown_user_is_empty", False, f"errored instead of empty cart: {e.code()}"))

        # 5) Distinct products for one user both appear in the cart (state holds >1 line).
        try:
            u = _uid("distinct")
            _add(stub, u, "PROD-D", 1)
            _add(stub, u, "PROD-E", 7)
            got = _qty_by_product(_get(stub, u))
            ok = got == {"PROD-D": 1, "PROD-E": 7}
            suite.results.append(RpcResult(
                "add_distinct_products", ok,
                f"cart={got} want {{'PROD-D': 1, 'PROD-E': 7}}"))
        except grpc.RpcError as e:
            suite.results.append(RpcResult("add_distinct_products", False, f"error: {e.code()}"))
    finally:
        channel.close()
    return suite


# Case names in run order, for unit-test attribution and provenance documentation.
CASE_NAMES: List[str] = [
    "add_then_get_reflects_item",
    "add_twice_accumulates",
    "empty_then_get_is_empty",
    "get_unknown_user_is_empty",
    "add_distinct_products",
]
