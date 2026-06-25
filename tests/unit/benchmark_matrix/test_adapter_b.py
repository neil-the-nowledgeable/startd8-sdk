"""Unit tests for R3-M2 Adapter B (fleet.adapter_b) — NO live fleet, mock gRPC stubs.

Exercises the step logic + the per-service ATTRIBUTION property: on a healthy mesh all 5 steps pass
(coverage 1.0); break ONE service and only the steps that touch it fail. The live driver-container run
against the real M1 fleet is a separate gated path (validate_m2).
"""
from __future__ import annotations

import grpc
import pytest

from startd8.benchmark_matrix.behavioral import demo_pb2
from startd8.benchmark_matrix.fleet import adapter_b as A
from startd8.benchmark_matrix.fleet import journey as J

pytestmark = pytest.mark.unit

SKU = J.CANONICAL_SKU
_USD10 = demo_pb2.Money(currency_code="USD", units=10, nanos=0)


class _Down(grpc.RpcError):
    """A stand-in for an unreachable/broken service RPC."""
    def code(self):
        return grpc.StatusCode.UNAVAILABLE

    def details(self):
        return "service down"


class FakeCatalog:
    def ListProducts(self, req, timeout=None):
        return demo_pb2.ListProductsResponse(products=[demo_pb2.Product(id=SKU, price_usd=_USD10)])

    def GetProduct(self, req, timeout=None):
        return demo_pb2.Product(id=SKU, price_usd=_USD10)


class FakeCurrency:
    def GetSupportedCurrencies(self, req, timeout=None):
        return demo_pb2.GetSupportedCurrenciesResponse(currency_codes=["USD", "EUR", "GBP"])

    def Convert(self, req, timeout=None):
        # echo the requested target code with a plausible amount (identity-ish; rate-independent)
        return demo_pb2.Money(currency_code=req.to_code, units=10, nanos=0)


class FakeCart:
    def __init__(self):
        self.items = []

    def AddItem(self, req, timeout=None):
        self.items.append(req.item)
        return demo_pb2.Empty()

    def GetCart(self, req, timeout=None):
        return demo_pb2.Cart(user_id=req.user_id, items=self.items)


class FakeShipping:
    def GetQuote(self, req, timeout=None):
        return demo_pb2.GetQuoteResponse(cost_usd=demo_pb2.Money(currency_code="USD", units=9, nanos=990000000))


class FakeCheckout:
    def PlaceOrder(self, req, timeout=None):
        return demo_pb2.PlaceOrderResponse(order=demo_pb2.OrderResult(order_id="order-abc-123"))


def _healthy_stubs():
    return {
        "productcatalogservice": FakeCatalog(),
        "currencyservice": FakeCurrency(),
        "cartservice": FakeCart(),
        "shippingservice": FakeShipping(),
        "checkoutservice": FakeCheckout(),
    }


def test_healthy_mesh_full_coverage():
    res = A.run_journey_with_stubs(_healthy_stubs(), now_year=2026)
    assert res.failed_steps == []
    assert res.unweighted_coverage == 1.0
    assert res.weighted_coverage == 1.0
    assert [s.name for s in res.steps] == ["browse", "setCurrency", "addToCart", "viewCart", "checkout"]


def test_break_payment_only_checkout_fails():
    """The attribution property: payment is exercised ONLY by checkout, so breaking it must fail the
    checkout step and NOTHING else (browse/setCurrency/addToCart/viewCart don't touch payment)."""
    stubs = _healthy_stubs()

    class BrokenCheckout:  # checkout's PlaceOrder fans out to payment; a payment failure surfaces here
        def PlaceOrder(self, req, timeout=None):
            raise _Down()

    stubs["checkoutservice"] = BrokenCheckout()
    res = A.run_journey_with_stubs(stubs, now_year=2026)
    assert res.failed_steps == ["checkout"]
    # 4 of 5 steps pass; weighted coverage drops only by checkout's weight (1 of 18).
    assert res.unweighted_coverage == 0.8
    assert abs(res.weighted_coverage - (17 / 18)) < 1e-9


def test_checkout_error_attributes_to_named_dep():
    """The checkout orchestrator wraps its dep errors ("charge: ..."); Adapter B parses the prefix so
    a checkout failure names the responsible DEP (paymentservice) — the live attribution mechanism."""
    stubs = _healthy_stubs()

    class _ChargeDown(grpc.RpcError):
        def code(self):
            return grpc.StatusCode.UNKNOWN

        def details(self):
            return "charge: rpc error: code = Unavailable desc = connection refused"

    class BrokenCheckout:
        def PlaceOrder(self, req, timeout=None):
            raise _ChargeDown()

    stubs["checkoutservice"] = BrokenCheckout()
    res = A.run_journey_with_stubs(stubs, now_year=2026)
    checkout = next(s for s in res.steps if s.name == "checkout")
    assert checkout.culprit == "paymentservice"  # parsed from the wrapped "charge:" error


def test_break_cart_fails_only_cart_dependent_steps():
    """Breaking cart fails addToCart + viewCart (both touch cart); browse/setCurrency stay green.
    checkout also fans out to cart, so it fails too — i.e. failures localize to cart-touching steps."""
    stubs = _healthy_stubs()

    class BrokenCart:
        def AddItem(self, req, timeout=None):
            raise _Down()

        def GetCart(self, req, timeout=None):
            raise _Down()

    stubs["cartservice"] = BrokenCart()
    res = A.run_journey_with_stubs(stubs, now_year=2026)
    assert "browse" not in res.failed_steps and "setCurrency" not in res.failed_steps
    assert "addToCart" in res.failed_steps and "viewCart" in res.failed_steps


def test_default_addr_map_is_service_dns():
    m = A._default_addr_map()
    assert m["checkoutservice"] == "checkoutservice:5050"
    assert m["emailservice"] == "emailservice:5000" if "emailservice" in m else True
    # only services Adapter B drives have stubs; email/payment are leaf deps (no direct step stub)
    assert "productcatalogservice" in m and m["productcatalogservice"] == "productcatalogservice:3550"
