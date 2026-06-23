"""Pure-Python unit tests for the checkoutservice dependency-stub harness (FR-CO-1..6, FR-CO-8).

No Go, no sandbox — always run. Covers: harness start/stop/teardown, call-counter recording, that
the six stubs return demo.proto-shaped ground-truth responses, the deterministic expected-order
computation, and per-step attribution from call counts. The Go-gated live oracle is in
``test_checkout_e2e_go.py``.
"""
from __future__ import annotations

import grpc
import pytest

from startd8.benchmark_matrix.behavioral import demo_pb2, demo_pb2_grpc
from startd8.benchmark_matrix.behavioral.checkout_stubs import (
    DEP_ENV_NAMES,
    ENV_CART,
    ENV_CURRENCY,
    ENV_EMAIL,
    ENV_PAYMENT,
    ENV_PRODUCT_CATALOG,
    ENV_SHIPPING,
    CheckoutStubHarness,
    GroundTruth,
)
from startd8.benchmark_matrix.behavioral.checkout_suite import (
    SUITE_VERSION,
    score_placeorder,
)


# --------------------------------------------------------------------------- harness lifecycle
def test_start_returns_six_loopback_addrs():
    h = CheckoutStubHarness()
    try:
        addr_map = h.start()
        assert set(addr_map) == set(DEP_ENV_NAMES)
        assert len(addr_map) == 6
        for name, addr in addr_map.items():
            assert addr.startswith("127.0.0.1:")
            assert int(addr.rsplit(":", 1)[1]) > 0
        # all six ports distinct
        ports = {a.rsplit(":", 1)[1] for a in addr_map.values()}
        assert len(ports) == 6
    finally:
        h.stop()


def test_stop_is_exception_safe_and_idempotent():
    h = CheckoutStubHarness()
    h.start()
    h.stop()
    h.stop()  # second stop must not raise
    assert h.addr_map == {}


def test_double_start_raises():
    h = CheckoutStubHarness()
    h.start()
    try:
        with pytest.raises(RuntimeError):
            h.start()
    finally:
        h.stop()


def test_context_manager():
    with CheckoutStubHarness() as h:
        assert len(h.addr_map) == 6
    assert h.addr_map == {}


def test_no_orphaned_listener_across_cycles():
    # Re-binding after teardown must succeed (ports released) — proves no orphan/leak (FR-X3-ISO).
    h = CheckoutStubHarness()
    for _ in range(3):
        addrs = h.start()
        assert len(addrs) == 6
        h.stop()


# --------------------------------------------------------------------------- stub responses
def _channel(addr):
    ch = grpc.insecure_channel(addr)
    grpc.channel_ready_future(ch).result(timeout=5.0)
    return ch


def test_stubs_return_ground_truth_messages():
    gt = GroundTruth()
    h = CheckoutStubHarness(gt)
    addr = h.start()
    try:
        # ProductCatalog.GetProduct
        ch = _channel(addr[ENV_PRODUCT_CATALOG])
        prod = demo_pb2_grpc.ProductCatalogServiceStub(ch).GetProduct(
            demo_pb2.GetProductRequest(id="OLJCESPC7Z"))
        assert prod.id == "OLJCESPC7Z"
        assert prod.price_usd.currency_code == "USD"
        assert (prod.price_usd.units, prod.price_usd.nanos) == (19, 990_000_000)
        ch.close()

        # Cart.GetCart
        ch = _channel(addr[ENV_CART])
        cart = demo_pb2_grpc.CartServiceStub(ch).GetCart(
            demo_pb2.GetCartRequest(user_id=gt.user_id))
        got = {(it.product_id, it.quantity) for it in cart.items}
        assert got == {("OLJCESPC7Z", 1), ("66VCHSJNUP", 2)}
        ch.close()

        # Currency.Convert (identity rate)
        ch = _channel(addr[ENV_CURRENCY])
        conv = demo_pb2_grpc.CurrencyServiceStub(ch).Convert(
            demo_pb2.CurrencyConversionRequest(
                **{"from": demo_pb2.Money(currency_code="USD", units=10, nanos=0)}, to_code="USD"))
        assert (conv.units, conv.nanos, conv.currency_code) == (10, 0, "USD")
        ch.close()

        # Shipping.GetQuote + ShipOrder
        ch = _channel(addr[ENV_SHIPPING])
        sstub = demo_pb2_grpc.ShippingServiceStub(ch)
        quote = sstub.GetQuote(demo_pb2.GetQuoteRequest())
        assert (quote.cost_usd.units, quote.cost_usd.nanos) == (5, 0)
        ship = sstub.ShipOrder(demo_pb2.ShipOrderRequest())
        assert ship.tracking_id == gt.shipping_tracking_id
        ch.close()

        # Payment.Charge -> opaque txn
        ch = _channel(addr[ENV_PAYMENT])
        charge = demo_pb2_grpc.PaymentServiceStub(ch).Charge(demo_pb2.ChargeRequest())
        assert charge.transaction_id == gt.transaction_id
        ch.close()

        # Email.SendOrderConfirmation -> Empty
        ch = _channel(addr[ENV_EMAIL])
        empty = demo_pb2_grpc.EmailServiceStub(ch).SendOrderConfirmation(
            demo_pb2.SendOrderConfirmationRequest())
        assert isinstance(empty, demo_pb2.Empty)
        ch.close()
    finally:
        h.stop()


def test_call_counters_record_each_dial():
    gt = GroundTruth()
    h = CheckoutStubHarness(gt)
    addr = h.start()
    try:
        assert all(c == 0 for c in h.call_counts.values())
        ch = _channel(addr[ENV_PAYMENT])
        demo_pb2_grpc.PaymentServiceStub(ch).Charge(demo_pb2.ChargeRequest())
        demo_pb2_grpc.PaymentServiceStub(ch).Charge(demo_pb2.ChargeRequest())
        ch.close()
        assert h.call_counts[ENV_PAYMENT] == 2
        assert h.call_counts[ENV_EMAIL] == 0
        # request capture (CQ-2 deferred-content, but retained)
        assert len(h.requests_for(ENV_PAYMENT)) == 2
    finally:
        h.stop()


def test_reset_counts():
    h = CheckoutStubHarness()
    addr = h.start()
    try:
        ch = _channel(addr[ENV_PAYMENT])
        demo_pb2_grpc.PaymentServiceStub(ch).Charge(demo_pb2.ChargeRequest())
        ch.close()
        assert h.call_counts[ENV_PAYMENT] == 1
        h.reset_counts()
        assert all(c == 0 for c in h.call_counts.values())
    finally:
        h.stop()


# --------------------------------------------------------------------------- ground-truth oracle math
def test_expected_order_identity_currency():
    gt = GroundTruth()  # USD identity
    order = gt.expected_order()
    # 2 line items
    assert len(order.items) == 2
    by_id = {it.item.product_id: it for it in order.items}
    # Sunglasses x1 = $19.99
    assert (by_id["OLJCESPC7Z"].cost.units, by_id["OLJCESPC7Z"].cost.nanos) == (19, 990_000_000)
    # Tank Top x2 = $37.98
    assert (by_id["66VCHSJNUP"].cost.units, by_id["66VCHSJNUP"].cost.nanos) == (37, 980_000_000)
    assert order.shipping_tracking_id == gt.shipping_tracking_id
    assert (order.shipping_cost.units, order.shipping_cost.nanos) == (5, 0)
    # total = 19.99 + 37.98 + 5.00 = 62.97
    total = gt.expected_total()
    assert (total.units, total.nanos, total.currency_code) == (62, 970_000_000, "USD")


def test_expected_order_nonidentity_currency():
    gt = GroundTruth(user_currency="EUR", currency_rate=0.5)
    order = gt.expected_order()
    by_id = {it.item.product_id: it for it in order.items}
    # 19.99 * 0.5 = 9.995  (round-half-to-even on nanos)
    assert by_id["OLJCESPC7Z"].cost.currency_code == "EUR"
    assert by_id["OLJCESPC7Z"].cost.units == 9
    # 5.00 * 0.5 = 2.50 shipping
    assert (order.shipping_cost.units, order.shipping_cost.nanos) == (2, 500_000_000)


# --------------------------------------------------------------------------- per-step attribution
def _all_dialed():
    return {n: 1 for n in DEP_ENV_NAMES}


def test_score_full_coverage_when_correct():
    gt = GroundTruth()
    suite = score_placeorder(gt.expected_order(), ground_truth=gt, stub_calls=_all_dialed())
    assert suite.suite_version == SUITE_VERSION
    assert len(suite.results) == 6
    assert suite.coverage == 1.0, [r.__dict__ for r in suite.results if not r.passed]


def test_score_payment_uncalled_fails_only_payment():
    gt = GroundTruth()
    calls = _all_dialed()
    calls[ENV_PAYMENT] = 0  # checkout skipped payment
    suite = score_placeorder(gt.expected_order(), ground_truth=gt, stub_calls=calls)
    failed = {r.name for r in suite.results if not r.passed}
    assert failed == {"payment_charged"}
    assert suite.coverage == pytest.approx(5 / 6)


def test_score_email_uncalled_fails_only_email():
    gt = GroundTruth()
    calls = _all_dialed()
    calls[ENV_EMAIL] = 0
    suite = score_placeorder(gt.expected_order(), ground_truth=gt, stub_calls=calls)
    failed = {r.name for r in suite.results if not r.passed}
    assert failed == {"email_confirmed"}


def test_score_no_order_fails_response_steps_but_counters_independent():
    gt = GroundTruth()
    # Order errored (None) but counters show all deps were dialed: response-observable steps fail,
    # email (counter-only) still passes; payment fails because no order was produced.
    suite = score_placeorder(None, ground_truth=gt, stub_calls=_all_dialed())
    passed = {r.name for r in suite.results if r.passed}
    assert passed == {"email_confirmed"}


def test_score_wrong_total_fails_pricing_steps():
    gt = GroundTruth()
    bad = gt.expected_order()
    bad.items[0].cost.units = 999  # corrupt a price
    suite = score_placeorder(bad, ground_truth=gt, stub_calls=_all_dialed())
    failed = {r.name for r in suite.results if not r.passed}
    # catalog_priced + currency_converted both ride price correctness; cart still matches ids/qty.
    assert "catalog_priced" in failed
    assert "currency_converted" in failed
    assert "cart_honored" not in failed
