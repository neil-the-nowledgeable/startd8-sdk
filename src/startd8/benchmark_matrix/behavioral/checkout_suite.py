"""checkoutservice.PlaceOrder per-step behavioral suite (FR-CO-7, FR-CO-8).

Unlike the leaf suites (Charge/Convert/GetQuote), checkout is a **6-way orchestrator**: it only
behaves correctly when all six dependencies answer. This suite drives **one** happy-path
``PlaceOrder`` against a live CheckoutService and scores **per-step partial coverage** — skipping a
dependency fails only that step (FR-CO-7), it is not all-or-nothing.

Two classes of observable, both required:

  - **response-observable** steps (catalog priced / cart honored / currency converted / shipping
    applied / order produced) ride the returned ``PlaceOrderResponse`` against the
    :class:`GroundTruth` oracle;
  - **call-counter-only** steps — ``payment.Charge``'s ``transaction_id`` is opaque and
    ``email.SendOrderConfirmation`` returns ``Empty``, so steps 5/6 are attributed **solely** from
    the stub call-counters the harness records (FR-CO-8, the HARD requirement).

``coverage ∈ [0,1]`` = passing steps / 6, folded through the existing ``compute_composite`` path
(FR-CO-15). The same ``RpcResult``/``SuiteResult`` shape as ``charge_suite`` is reused (FR-CO-7).
"""
from __future__ import annotations

from typing import Dict, Optional

import grpc

from . import demo_pb2, demo_pb2_grpc
from .charge_suite import RpcResult, SuiteResult  # reuse the shipped result shape (FR-CO-7/15)
from .checkout_stubs import (
    ENV_CART,
    ENV_CURRENCY,
    ENV_EMAIL,
    ENV_PAYMENT,
    ENV_PRODUCT_CATALOG,
    ENV_SHIPPING,
    GroundTruth,
)

SUITE_VERSION = "checkout-suite/1"

# Default test card (Luhn-valid Visa, future expiry) + a fixed shipping address.
_PAN = "4111111111111111"


def _request(gt: GroundTruth) -> "demo_pb2.PlaceOrderRequest":
    return demo_pb2.PlaceOrderRequest(
        user_id=gt.user_id,
        user_currency=gt.user_currency,
        address=demo_pb2.Address(street_address="1600 Amphitheatre Pkwy", city="Mountain View",
                                 state="CA", country="USA", zip_code=94043),
        email=gt.email,
        credit_card=demo_pb2.CreditCardInfo(
            credit_card_number=_PAN, credit_card_cvv=123,
            credit_card_expiration_year=2030, credit_card_expiration_month=12),
    )


def _money_eq(a: "demo_pb2.Money", b: "demo_pb2.Money") -> bool:
    return (a.currency_code == b.currency_code and a.units == b.units and a.nanos == b.nanos)


def score_placeorder(
    order: Optional["demo_pb2.OrderResult"],
    *,
    ground_truth: GroundTruth,
    stub_calls: Dict[str, int],
) -> SuiteResult:
    """Score the six orchestration steps from the response ``order`` + ``stub_calls`` (FR-CO-7/8).

    ``order`` is ``PlaceOrderResponse.order`` (None if PlaceOrder errored). ``stub_calls`` is the
    harness's ``call_counts`` map (``{ENV_NAME: count}``) — the **only** observable for payment/email.
    This is a pure function so it is fully unit-testable without a live server or Go.
    """
    suite = SuiteResult(suite_version=SUITE_VERSION)
    gt = ground_truth
    expected = gt.expected_order()
    calls = stub_calls or {}

    has_order = order is not None
    items = list(order.items) if has_order else []

    # Step 1 — catalog priced: order items carry catalog-sourced (converted) prices AND the catalog
    # stub was dialed.
    catalog_dialed = calls.get(ENV_PRODUCT_CATALOG, 0) > 0
    prices_ok = has_order and len(items) == len(expected.items) and all(
        _money_eq(a.cost, b.cost) for a, b in zip(items, expected.items))
    suite.results.append(RpcResult(
        "catalog_priced", bool(catalog_dialed and prices_ok),
        f"catalog_dialed={catalog_dialed} prices_match={prices_ok}"))

    # Step 2 — cart honored: order items match the fixed cart's product ids × quantities AND cart dialed.
    cart_dialed = calls.get(ENV_CART, 0) > 0
    got_items = {(it.item.product_id, it.item.quantity) for it in items}
    want_items = {(it.item.product_id, it.item.quantity) for it in expected.items}
    cart_ok = has_order and got_items == want_items
    suite.results.append(RpcResult(
        "cart_honored", bool(cart_dialed and cart_ok),
        f"cart_dialed={cart_dialed} items_match={cart_ok}"))

    # Step 3 — currency converted: item costs are in user_currency per the fixed rate AND currency dialed.
    currency_dialed = calls.get(ENV_CURRENCY, 0) > 0
    currency_ok = has_order and bool(items) and all(
        it.cost.currency_code == gt.user_currency for it in items) and prices_ok
    suite.results.append(RpcResult(
        "currency_converted", bool(currency_dialed and currency_ok),
        f"currency_dialed={currency_dialed} amounts_in_{gt.user_currency}={currency_ok}"))

    # Step 4 — shipping applied: non-empty tracking_id + shipping_cost set AND shipping dialed.
    shipping_dialed = calls.get(ENV_SHIPPING, 0) > 0
    shipping_ok = has_order and bool(order.shipping_tracking_id) and (
        _money_eq(order.shipping_cost, expected.shipping_cost))
    suite.results.append(RpcResult(
        "shipping_applied", bool(shipping_dialed and shipping_ok),
        f"shipping_dialed={shipping_dialed} tracking+cost_ok={shipping_ok}"))

    # Step 5 — payment charged: an order was produced (non-empty order_id) AND the payment stub was
    # actually dialed. transaction_id is opaque → counter is the ONLY observable (FR-CO-8).
    payment_dialed = calls.get(ENV_PAYMENT, 0) > 0
    order_produced = has_order and bool(order.order_id)
    suite.results.append(RpcResult(
        "payment_charged", bool(payment_dialed and order_produced),
        f"payment_dialed={payment_dialed} order_produced={order_produced}"))

    # Step 6 — email confirmed: email stub dialed. SendOrderConfirmation returns Empty → counter is
    # the ONLY observable (FR-CO-8).
    email_dialed = calls.get(ENV_EMAIL, 0) > 0
    suite.results.append(RpcResult(
        "email_confirmed", bool(email_dialed), f"email_dialed={email_dialed}"))

    return suite


def run_checkout_suite(
    port: int,
    *,
    stub_calls: Dict[str, int],
    ground_truth: GroundTruth,
    host: str = "127.0.0.1",
    connect_timeout: float = 5.0,
    rpc_timeout: float = 20.0,
) -> SuiteResult:
    """Connect a CheckoutServiceStub to a live SUT, send one PlaceOrder, score the six steps.

    ``stub_calls`` and ``ground_truth`` are partial-bound by the execute branch *after* the stubs are
    bound and the SUT has dialed them. A connect failure is an env outcome → empty results (degrade
    upstream), mirroring ``charge_suite``. The call-counter snapshot is read **after** PlaceOrder
    returns, so it reflects the dependencies the SUT actually dialed during this order.
    """
    gt = ground_truth
    try:
        channel = grpc.insecure_channel(f"{host}:{port}")
        grpc.channel_ready_future(channel).result(timeout=connect_timeout)
    except Exception as e:  # noqa: BLE001 — failure to connect is an env outcome (degrade upstream)
        suite = SuiteResult(suite_version=SUITE_VERSION)
        suite.connect_error = f"{type(e).__name__}: {e}"
        return suite
    try:
        stub = demo_pb2_grpc.CheckoutServiceStub(channel)
        order: Optional[demo_pb2.OrderResult] = None
        try:
            resp = stub.PlaceOrder(_request(gt), timeout=rpc_timeout)
            order = resp.order if resp.HasField("order") else demo_pb2.OrderResult()
        except grpc.RpcError:
            order = None  # PlaceOrder failed → response-observable steps fail; counter steps still scored
        # Read counters AFTER the order has been placed (callable returns a live snapshot).
        calls = stub_calls() if callable(stub_calls) else dict(stub_calls)
        return score_placeorder(order, ground_truth=gt, stub_calls=calls)
    finally:
        channel.close()
