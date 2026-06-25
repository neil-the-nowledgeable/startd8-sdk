"""Round-3 Adapter B (M2) — the direct-gRPC journey driver (always-on diagnostic backbone).

Replays the transport-agnostic journey (``fleet.journey.JOURNEY``) as its gRPC *fan-out* against a
live fleet: each logical step issues the real RPCs (catalog.ListProducts/GetProduct, currency.Convert,
cart.AddItem/GetCart, shipping.GetQuote, checkout.PlaceOrder) and scores its transport-independent
expected outcome. Per-step pass/fail → per-step coverage (weighted by the §1 locust mix + unweighted),
and — because each step touches a known service set (``JourneyStep.services``) — a failed step is
attributable to the responsible service (M3): break payment and ONLY the checkout step fails.

Reuses the SDK proto stubs + the checkout PlaceOrder path; outcomes are INVARIANT-based (order id
non-empty, cart contains the SKU, quote non-negative, price localized) — the same rate/price-independent
discipline as the per-service behavioral suites, so no exact-amount oracle calibration is needed for
the reference mesh. (Promoting ``checkout_stubs.GroundTruth`` to an exact fleet oracle over the seeded
catalog/cart fixtures is a later refinement.)

Run inside a driver container ON the fleet network (dialing peers by service-DNS); the addr map keys
are service names → ``host:port`` (service-DNS ``name:dial_port`` in-fleet, ``127.0.0.1:port`` in tests).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

import grpc

from ..behavioral import demo_pb2, demo_pb2_grpc
from . import journey as J

# service name -> (stub class, the gRPC stub attribute used). Built lazily from a channel map.
_STUBS = {
    "productcatalogservice": demo_pb2_grpc.ProductCatalogServiceStub,
    "currencyservice": demo_pb2_grpc.CurrencyServiceStub,
    "cartservice": demo_pb2_grpc.CartServiceStub,
    "shippingservice": demo_pb2_grpc.ShippingServiceStub,
    "checkoutservice": demo_pb2_grpc.CheckoutServiceStub,
}


@dataclass
class StepResult:
    name: str
    passed: bool
    detail: str
    weight: int


@dataclass
class JourneyResult:
    steps: list[StepResult] = field(default_factory=list)

    @property
    def unweighted_coverage(self) -> float:
        return sum(s.passed for s in self.steps) / len(self.steps) if self.steps else 0.0

    @property
    def weighted_coverage(self) -> float:
        total = sum(s.weight for s in self.steps)
        return sum(s.weight for s in self.steps if s.passed) / total if total else 0.0

    @property
    def failed_steps(self) -> list[str]:
        return [s.name for s in self.steps if not s.passed]

    def to_dict(self) -> dict:
        return {
            "steps": [{"name": s.name, "passed": s.passed, "detail": s.detail, "weight": s.weight}
                      for s in self.steps],
            "unweighted_coverage": self.unweighted_coverage,
            "weighted_coverage": self.weighted_coverage,
            "failed_steps": self.failed_steps,
        }


def _convert_req(from_money, to_code: str):
    req = demo_pb2.CurrencyConversionRequest(to_code=to_code)
    getattr(req, "from").CopyFrom(from_money)  # 'from' is a Python keyword
    return req


# --- the five steps. Each takes the stub map + the shared journey state, returns (passed, detail). ---

def _step_browse(stubs, state) -> tuple[bool, str]:
    """products returned + a product's price renders in the active currency."""
    products = stubs["productcatalogservice"].ListProducts(demo_pb2.Empty(), timeout=5.0).products
    if not products:
        return False, "ListProducts returned no products"
    prod = stubs["productcatalogservice"].GetProduct(
        demo_pb2.GetProductRequest(id=J.CANONICAL_SKU), timeout=5.0)
    if prod.id != J.CANONICAL_SKU:
        return False, f"GetProduct({J.CANONICAL_SKU}) returned id={prod.id!r}"
    localized = stubs["currencyservice"].Convert(
        _convert_req(prod.price_usd, state["currency"]), timeout=5.0)
    if localized.currency_code != state["currency"]:
        return False, f"price not localized to {state['currency']} (got {localized.currency_code})"
    return True, f"{len(products)} products; {J.CANONICAL_SKU} priced in {localized.currency_code}"


def _step_set_currency(stubs, state) -> tuple[bool, str]:
    """the code is supported and subsequent prices reflect the new currency."""
    supported = set(stubs["currencyservice"].GetSupportedCurrencies(
        demo_pb2.Empty(), timeout=5.0).currency_codes)
    target = next((c for c in J.CURRENCY_WHITELIST if c in supported and c != state["currency"]), None)
    if target is None:
        return False, f"no whitelisted target currency in supported set {sorted(supported)}"
    probe = stubs["currencyservice"].Convert(
        _convert_req(demo_pb2.Money(currency_code="USD", units=100, nanos=0), target), timeout=5.0)
    if probe.currency_code != target:
        return False, f"Convert to {target} returned {probe.currency_code}"
    state["currency"] = target  # subsequent steps localize to the new currency
    return True, f"active currency -> {target} ({len(supported)} supported)"


def _step_add_to_cart(stubs, state) -> tuple[bool, str]:
    """the item is present in the cart (verified by viewCart)."""
    stubs["productcatalogservice"].GetProduct(
        demo_pb2.GetProductRequest(id=J.CANONICAL_SKU), timeout=5.0)
    stubs["cartservice"].AddItem(demo_pb2.AddItemRequest(
        user_id=state["user_id"],
        item=demo_pb2.CartItem(product_id=J.CANONICAL_SKU, quantity=state["quantity"]),
    ), timeout=5.0)
    return True, f"AddItem {J.CANONICAL_SKU} x{state['quantity']}"


def _step_view_cart(stubs, state) -> tuple[bool, str]:
    """the cart shows the added item and a shipping quote + total compute."""
    cart = stubs["cartservice"].GetCart(
        demo_pb2.GetCartRequest(user_id=state["user_id"]), timeout=5.0)
    in_cart = any(it.product_id == J.CANONICAL_SKU for it in cart.items)
    if not in_cart:
        return False, f"cart does not contain {J.CANONICAL_SKU} (items={len(cart.items)})"
    quote = stubs["shippingservice"].GetQuote(demo_pb2.GetQuoteRequest(
        address=demo_pb2.Address(street_address=state["payload"].street_address,
                                 city=state["payload"].city, state=state["payload"].state,
                                 country=state["payload"].country, zip_code=state["payload"].zip_code),
        items=[demo_pb2.CartItem(product_id=J.CANONICAL_SKU, quantity=state["quantity"])],
    ), timeout=5.0).cost_usd
    nonneg = (quote.units > 0) or (quote.units == 0 and quote.nanos >= 0)
    if not nonneg:
        return False, f"negative shipping quote {quote.units}.{quote.nanos}"
    return True, f"cart has {J.CANONICAL_SKU}; shipping {quote.units}.{quote.nanos} {quote.currency_code}"


def _step_checkout(stubs, state) -> tuple[bool, str]:
    """an order id is returned and the 6-dep PlaceOrder orchestration succeeds."""
    p = state["payload"]
    resp = stubs["checkoutservice"].PlaceOrder(demo_pb2.PlaceOrderRequest(
        user_id=state["user_id"], user_currency=state["currency"],
        address=demo_pb2.Address(street_address=p.street_address, city=p.city, state=p.state,
                                 country=p.country, zip_code=p.zip_code),
        email=p.email,
        credit_card=demo_pb2.CreditCardInfo(
            credit_card_number=p.credit_card_number, credit_card_cvv=p.credit_card_cvv,
            credit_card_expiration_year=p.credit_card_expiration_year,
            credit_card_expiration_month=p.credit_card_expiration_month),
    ), timeout=15.0)
    if not resp.order.order_id:
        return False, "PlaceOrder returned an empty order_id"
    return True, f"order_id={resp.order.order_id}"


_STEP_FNS = {
    "browse": _step_browse, "setCurrency": _step_set_currency, "addToCart": _step_add_to_cart,
    "viewCart": _step_view_cart, "checkout": _step_checkout,
}


def run_journey_with_stubs(stubs: dict, *, now_year: Optional[int] = None) -> JourneyResult:
    """Drive the canonical journey against an already-built ``stubs`` map ({service: gRPC stub}). Each
    step is scored independently — a step that raises (a broken/unreachable dep) fails THAT step only,
    leaving the others' verdicts intact (the per-service attribution property M3 relies on). Injectable
    so the step logic is unit-testable against fakes with no live fleet."""
    payload = J.canonical_checkout_payload(now_year=now_year)
    state = {"currency": payload.user_currency, "user_id": payload.user_id,
             "quantity": payload.quantity, "payload": payload}
    result = JourneyResult()
    for step in J.JOURNEY:
        fn = _STEP_FNS[step.name]
        try:
            passed, detail = fn(stubs, state)
        except grpc.RpcError as e:
            passed, detail = False, f"RpcError {e.code()}: {e.details()}"
        except Exception as e:  # noqa: BLE001 — a step never crashes the whole journey
            passed, detail = False, f"{type(e).__name__}: {e}"
        result.steps.append(StepResult(step.name, passed, detail, step.weight))
    return result


def run_journey(addr_map: dict[str, str], *, now_year: Optional[int] = None) -> JourneyResult:
    """Drive the canonical journey against the fleet reachable at ``addr_map`` ({service: "host:port"};
    service-DNS in-fleet). Builds channels/stubs, then delegates to ``run_journey_with_stubs``."""
    channels = {name: grpc.insecure_channel(addr) for name, addr in addr_map.items()}
    stubs = {name: _STUBS[name](channels[name]) for name in addr_map if name in _STUBS}
    try:
        return run_journey_with_stubs(stubs, now_year=now_year)
    finally:
        for ch in channels.values():
            ch.close()


def _default_addr_map() -> dict[str, str]:
    """Service-DNS addresses for an in-fleet driver container (name:dial_port from the inventory)."""
    from .services import contestant_services
    return {s.name: f"{s.name}:{s.dial_port}" for s in contestant_services()
            if s.name in _STUBS}


if __name__ == "__main__":  # entrypoint for the in-fleet driver container
    res = run_journey(_default_addr_map())
    print(json.dumps(res.to_dict()), flush=True)
    raise SystemExit(0 if not res.failed_steps else 1)
