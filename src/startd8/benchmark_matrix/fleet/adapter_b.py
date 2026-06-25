"""Round-3 Adapter B (M2) — the direct-gRPC journey driver (always-on diagnostic backbone).

Replays the transport-agnostic journey (``fleet.journey.JOURNEY``) as its gRPC *fan-out* against a
live fleet: each logical step issues the real RPCs (catalog.ListProducts/GetProduct, currency.Convert,
cart.AddItem/GetCart, shipping.GetQuote, checkout.PlaceOrder) and scores its transport-independent
expected outcome. Per-step pass/fail → per-step coverage (weighted by the §1 locust mix + unweighted),
and — because each failed step identifies the **culprit service** (the one whose RPC raised / whose
response violated the invariant) — the M3 scorer attributes the fault per-service (M3): break payment
and ONLY the checkout step fails, attributed to payment (propagated, not charged to checkout).

The journey's DIRECT steps (browse/setCurrency/addToCart/viewCart) call services directly, so a failed
direct step's culprit IS the broken service. The checkout step calls the checkout ORCHESTRATOR, which
fans out to 6 deps; its wrapped error names the failing RPC, so a checkout failure is attributed to the
responsible dep (propagated) — or to checkout itself (model-fault) when its own logic fails.

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

_STUBS = {
    "productcatalogservice": demo_pb2_grpc.ProductCatalogServiceStub,
    "currencyservice": demo_pb2_grpc.CurrencyServiceStub,
    "cartservice": demo_pb2_grpc.CartServiceStub,
    "shippingservice": demo_pb2_grpc.ShippingServiceStub,
    "checkoutservice": demo_pb2_grpc.CheckoutServiceStub,
}

# Maps the checkout orchestrator's wrapped-error prefixes (reference_checkout PlaceOrder:
# `fmt.Errorf("charge: %w", err)` etc.) to the responsible dependency service — so a checkout failure
# is attributed to the dep that actually broke, not to checkoutservice.
_CHECKOUT_ERR_TO_SERVICE = {
    "getcart": "cartservice",
    "getproduct": "productcatalogservice",
    "convert": "currencyservice",
    "getquote": "shippingservice",
    "shiporder": "shippingservice",
    "charge": "paymentservice",
    "email": "emailservice",
}


class _ServiceFailure(Exception):
    """An RPC to ``service`` failed — carries the culprit for attribution."""
    def __init__(self, service: str, detail: str):
        super().__init__(detail)
        self.service = service
        self.detail = detail


def _rpc(service: str, fn):
    """Invoke a gRPC call, tagging an RpcError with the responsible ``service`` (for attribution)."""
    try:
        return fn()
    except grpc.RpcError as e:
        raise _ServiceFailure(service, f"{service}: {e.code()} {e.details()}") from e


@dataclass
class StepResult:
    name: str
    passed: bool
    detail: str
    weight: int
    culprit: Optional[str] = None  # the service responsible when the step failed (else None)


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
            "steps": [{"name": s.name, "passed": s.passed, "detail": s.detail,
                       "weight": s.weight, "culprit": s.culprit} for s in self.steps],
            "unweighted_coverage": self.unweighted_coverage,
            "weighted_coverage": self.weighted_coverage,
            "failed_steps": self.failed_steps,
        }


def _convert_req(from_money, to_code: str):
    req = demo_pb2.CurrencyConversionRequest(to_code=to_code)
    getattr(req, "from").CopyFrom(from_money)  # 'from' is a Python keyword
    return req


# --- the five steps. Each returns (passed, detail, culprit_service_or_None). ---

def _step_browse(stubs, state):
    products = _rpc("productcatalogservice",
                    lambda: stubs["productcatalogservice"].ListProducts(demo_pb2.Empty(), timeout=5.0)).products
    if not products:
        return False, "ListProducts returned no products", "productcatalogservice"
    prod = _rpc("productcatalogservice",
                lambda: stubs["productcatalogservice"].GetProduct(
                    demo_pb2.GetProductRequest(id=J.CANONICAL_SKU), timeout=5.0))
    if prod.id != J.CANONICAL_SKU:
        return False, f"GetProduct({J.CANONICAL_SKU}) returned id={prod.id!r}", "productcatalogservice"
    localized = _rpc("currencyservice",
                     lambda: stubs["currencyservice"].Convert(_convert_req(prod.price_usd, state["currency"]), timeout=5.0))
    if localized.currency_code != state["currency"]:
        return False, f"price not localized to {state['currency']} (got {localized.currency_code})", "currencyservice"
    return True, f"{len(products)} products; {J.CANONICAL_SKU} priced in {localized.currency_code}", None


def _step_set_currency(stubs, state):
    supported = set(_rpc("currencyservice",
                         lambda: stubs["currencyservice"].GetSupportedCurrencies(demo_pb2.Empty(), timeout=5.0)).currency_codes)
    target = next((c for c in J.CURRENCY_WHITELIST if c in supported and c != state["currency"]), None)
    if target is None:
        return False, f"no whitelisted target currency in supported set {sorted(supported)}", "currencyservice"
    probe = _rpc("currencyservice",
                 lambda: stubs["currencyservice"].Convert(
                     _convert_req(demo_pb2.Money(currency_code="USD", units=100, nanos=0), target), timeout=5.0))
    if probe.currency_code != target:
        return False, f"Convert to {target} returned {probe.currency_code}", "currencyservice"
    state["currency"] = target
    return True, f"active currency -> {target} ({len(supported)} supported)", None


def _step_add_to_cart(stubs, state):
    _rpc("productcatalogservice",
         lambda: stubs["productcatalogservice"].GetProduct(demo_pb2.GetProductRequest(id=J.CANONICAL_SKU), timeout=5.0))
    _rpc("cartservice", lambda: stubs["cartservice"].AddItem(demo_pb2.AddItemRequest(
        user_id=state["user_id"],
        item=demo_pb2.CartItem(product_id=J.CANONICAL_SKU, quantity=state["quantity"]),
    ), timeout=5.0))
    return True, f"AddItem {J.CANONICAL_SKU} x{state['quantity']}", None


def _step_view_cart(stubs, state):
    cart = _rpc("cartservice",
                lambda: stubs["cartservice"].GetCart(demo_pb2.GetCartRequest(user_id=state["user_id"]), timeout=5.0))
    if not any(it.product_id == J.CANONICAL_SKU for it in cart.items):
        return False, f"cart does not contain {J.CANONICAL_SKU} (items={len(cart.items)})", "cartservice"
    p = state["payload"]
    quote = _rpc("shippingservice", lambda: stubs["shippingservice"].GetQuote(demo_pb2.GetQuoteRequest(
        address=demo_pb2.Address(street_address=p.street_address, city=p.city, state=p.state,
                                 country=p.country, zip_code=p.zip_code),
        items=[demo_pb2.CartItem(product_id=J.CANONICAL_SKU, quantity=state["quantity"])],
    ), timeout=5.0)).cost_usd
    if not ((quote.units > 0) or (quote.units == 0 and quote.nanos >= 0)):
        return False, f"negative shipping quote {quote.units}.{quote.nanos}", "shippingservice"
    return True, f"cart has {J.CANONICAL_SKU}; shipping {quote.units}.{quote.nanos} {quote.currency_code}", None


def _checkout_culprit(detail: str) -> str:
    """Map a wrapped checkout error to the responsible dep (default: checkout's own logic)."""
    low = detail.lower()
    for prefix, svc in _CHECKOUT_ERR_TO_SERVICE.items():
        if prefix in low:
            return svc
    return "checkoutservice"


def _step_checkout(stubs, state):
    p = state["payload"]
    try:
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
    except grpc.RpcError as e:
        detail = f"{e.code()} {e.details()}"
        return False, f"PlaceOrder failed: {detail}", _checkout_culprit(detail)
    if not resp.order.order_id:
        return False, "PlaceOrder returned an empty order_id", "checkoutservice"
    return True, f"order_id={resp.order.order_id}", None


_STEP_FNS = {
    "browse": _step_browse, "setCurrency": _step_set_currency, "addToCart": _step_add_to_cart,
    "viewCart": _step_view_cart, "checkout": _step_checkout,
}


def run_journey_with_stubs(stubs: dict, *, now_year: Optional[int] = None) -> JourneyResult:
    """Drive the canonical journey against an already-built ``stubs`` map ({service: gRPC stub}). Each
    step is scored independently — a step that fails records its culprit service, leaving the others'
    verdicts intact (the per-service attribution property M3 relies on). Injectable so the step logic
    is unit-testable against fakes with no live fleet."""
    payload = J.canonical_checkout_payload(now_year=now_year)
    state = {"currency": payload.user_currency, "user_id": payload.user_id,
             "quantity": payload.quantity, "payload": payload}
    result = JourneyResult()
    for step in J.JOURNEY:
        fn = _STEP_FNS[step.name]
        try:
            passed, detail, culprit = fn(stubs, state)
        except _ServiceFailure as f:
            passed, detail, culprit = False, f.detail, f.service
        except Exception as e:  # noqa: BLE001 — a step never crashes the whole journey
            passed, detail, culprit = False, f"{type(e).__name__}: {e}", None
        result.steps.append(StepResult(step.name, passed, detail, step.weight, culprit))
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
    return {s.name: f"{s.name}:{s.dial_port}" for s in contestant_services() if s.name in _STUBS}


if __name__ == "__main__":  # entrypoint for the in-fleet driver container
    res = run_journey(_default_addr_map())
    print(json.dumps(res.to_dict()), flush=True)
    raise SystemExit(0 if not res.failed_steps else 1)
