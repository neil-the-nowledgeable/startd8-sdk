"""checkoutservice dependency-stub harness (FR-CO-1..6, FR-CO-8).

The Track-2 behavioral harness scores ``checkoutservice.PlaceOrder`` — a 6-way gRPC orchestrator —
by standing up SDK-authored, fixed-ground-truth **dependency stubs** the generated checkout dials,
**never** other models' generated services (NR-CO-1 / NR-X2). Per the planning discoveries:

  - The six dependency servicers **already exist** in ``demo_pb2_grpc`` — we **subclass** them, no
    proto/codegen (FR-CO-1, D3).
  - The suite client runs *outside* the seatbelt sandbox while only the SUT is sandboxed
    (loopback-allowed / egress-denied), so the stubs can be **in-process Python gRPC servers** on
    loopback that the sandboxed Go checkout reaches over ``127.0.0.1`` (FR-CO-2, D2).
  - ``payment.Charge`` returns an opaque ``transaction_id`` and ``email.SendOrderConfirmation``
    returns ``Empty`` — neither step is response-observable, so each stub **must** record a call
    counter; counters are the *only* observable for the payment/email steps (FR-CO-8, D9).

One configurable :class:`CheckoutStubHarness` owns all six servicers + one :class:`GroundTruth`
fixture (FR-CO-4). ``start()`` binds six servers on free loopback ports and returns the
``{ENV_NAME: "127.0.0.1:<port>"}`` address map the execute branch injects as ``*_SERVICE_ADDR``;
``stop()`` tears all six down deterministically and exception-safely (FR-CO-3).
"""
from __future__ import annotations

import socket
import threading
from concurrent import futures
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import grpc

from . import demo_pb2, demo_pb2_grpc

# ---------------------------------------------------------------------------
# Online Boutique dependency-address env convention (FR-CO-10). The seed declares
# these NAMES; the execute branch fills the VALUES after binding stubs.
# ---------------------------------------------------------------------------
ENV_PRODUCT_CATALOG = "PRODUCT_CATALOG_SERVICE_ADDR"
ENV_CART = "CART_SERVICE_ADDR"
ENV_CURRENCY = "CURRENCY_SERVICE_ADDR"
ENV_SHIPPING = "SHIPPING_SERVICE_ADDR"
ENV_PAYMENT = "PAYMENT_SERVICE_ADDR"
ENV_EMAIL = "EMAIL_SERVICE_ADDR"

#: Stable ordering of the six dependency env-var names (the harness contract).
DEP_ENV_NAMES: List[str] = [
    ENV_PRODUCT_CATALOG, ENV_CART, ENV_CURRENCY, ENV_SHIPPING, ENV_PAYMENT, ENV_EMAIL,
]


def _free_port() -> int:
    """Bind ``127.0.0.1:0`` to get a free ephemeral port (mirrors execute._free_port)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


# ---------------------------------------------------------------------------
# Ground-truth fixture (FR-CO-5/6) — the suite's oracle.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CatalogProduct:
    id: str
    name: str
    price_units: int
    price_nanos: int = 0


@dataclass(frozen=True)
class GroundTruth:
    """Fixed ground-truth for the single happy-path PlaceOrder (FR-CO-5).

    The expected :class:`demo_pb2.PlaceOrderResponse` is **deterministically computable** from these
    fields (FR-CO-6): order items = cart items priced from the catalog and currency-converted; total
    = Σ(price × qty) converted + shipping; tracking + cost from the shipping stub.
    """

    user_id: str = "ground-truth-user"
    user_currency: str = "USD"
    email: str = "buyer@example.com"
    # Catalog: id -> product (USD prices).
    catalog: Dict[str, CatalogProduct] = field(default_factory=lambda: {
        "OLJCESPC7Z": CatalogProduct("OLJCESPC7Z", "Sunglasses", 19, 990_000_000),  # $19.99
        "66VCHSJNUP": CatalogProduct("66VCHSJNUP", "Tank Top", 18, 990_000_000),     # $18.99
    })
    # Cart for ``user_id``: product_id -> quantity (deterministic order preserved).
    cart_items: Dict[str, int] = field(default_factory=lambda: {
        "OLJCESPC7Z": 1,
        "66VCHSJNUP": 2,
    })
    # Currency conversion: fixed multiplier applied to USD amounts for ``user_currency``.
    # 1.0 = identity (USD). Non-USD test currencies can override.
    currency_rate: float = 1.0
    # Shipping stub fixed outputs.
    shipping_cost_units: int = 5
    shipping_cost_nanos: int = 0
    shipping_tracking_id: str = "GROUND-TRUTH-TRACK-0001"
    # Payment stub fixed opaque transaction id.
    transaction_id: str = "ground-truth-txn-0001"
    # Order id the reference checkout assigns (any non-empty id passes step 5; pinned for determinism).
    order_id: str = "ground-truth-order-0001"

    # -- derived helpers ----------------------------------------------------
    def _convert_money(self, units: int, nanos: int) -> "demo_pb2.Money":
        """Apply ``currency_rate`` to a USD (units, nanos) amount, return Money in ``user_currency``."""
        total_nanos = (units * 1_000_000_000 + nanos) * self.currency_rate
        total_nanos = int(round(total_nanos))
        out_units = total_nanos // 1_000_000_000
        out_nanos = total_nanos - out_units * 1_000_000_000
        return demo_pb2.Money(currency_code=self.user_currency, units=out_units, nanos=int(out_nanos))

    def expected_order(self) -> "demo_pb2.OrderResult":
        """The correct PlaceOrderResponse.order computed from the fixture (the oracle, FR-CO-6)."""
        items: List[demo_pb2.OrderItem] = []
        for pid, qty in self.cart_items.items():
            prod = self.catalog[pid]
            cost = self._convert_money(prod.price_units * qty, prod.price_nanos * qty)
            items.append(demo_pb2.OrderItem(
                item=demo_pb2.CartItem(product_id=pid, quantity=qty), cost=cost))
        shipping_cost = self._convert_money(self.shipping_cost_units, self.shipping_cost_nanos)
        return demo_pb2.OrderResult(
            order_id=self.order_id,
            shipping_tracking_id=self.shipping_tracking_id,
            shipping_cost=shipping_cost,
            items=items,
        )

    def expected_total(self) -> "demo_pb2.Money":
        """Σ(item costs) + shipping, in ``user_currency`` (for assertion, FR-CO-6)."""
        order = self.expected_order()
        total = 0
        for it in order.items:
            total += it.cost.units * 1_000_000_000 + it.cost.nanos
        total += order.shipping_cost.units * 1_000_000_000 + order.shipping_cost.nanos
        units = total // 1_000_000_000
        nanos = total - units * 1_000_000_000
        return demo_pb2.Money(currency_code=self.user_currency, units=units, nanos=int(nanos))


# ---------------------------------------------------------------------------
# The six servicer subclasses (FR-CO-1) — each records a call counter (FR-CO-8).
# ---------------------------------------------------------------------------
class _CallCounter:
    """Thread-safe per-servicer call counter + last-request capture (FR-CO-8, CQ-2 deferred-content)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.count = 0
        self.requests: List[object] = []

    def record(self, request: object) -> None:
        with self._lock:
            self.count += 1
            self.requests.append(request)


class _ProductCatalogStub(demo_pb2_grpc.ProductCatalogServiceServicer):
    def __init__(self, gt: GroundTruth, calls: _CallCounter):
        self._gt, self._calls = gt, calls

    def GetProduct(self, request, context):
        self._calls.record(request)
        prod = self._gt.catalog.get(request.id)
        if prod is None:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details(f"unknown product {request.id!r}")
            return demo_pb2.Product()
        return demo_pb2.Product(
            id=prod.id, name=prod.name,
            price_usd=demo_pb2.Money(currency_code="USD", units=prod.price_units, nanos=prod.price_nanos),
        )

    def ListProducts(self, request, context):
        self._calls.record(request)
        return demo_pb2.ListProductsResponse(products=[
            demo_pb2.Product(id=p.id, name=p.name,
                             price_usd=demo_pb2.Money(currency_code="USD",
                                                      units=p.price_units, nanos=p.price_nanos))
            for p in self._gt.catalog.values()
        ])


class _CartStub(demo_pb2_grpc.CartServiceServicer):
    def __init__(self, gt: GroundTruth, calls: _CallCounter):
        self._gt, self._calls = gt, calls

    def GetCart(self, request, context):
        self._calls.record(request)
        return demo_pb2.Cart(
            user_id=request.user_id,
            items=[demo_pb2.CartItem(product_id=pid, quantity=qty)
                   for pid, qty in self._gt.cart_items.items()],
        )

    def EmptyCart(self, request, context):
        self._calls.record(request)
        return demo_pb2.Empty()


class _CurrencyStub(demo_pb2_grpc.CurrencyServiceServicer):
    def __init__(self, gt: GroundTruth, calls: _CallCounter):
        self._gt, self._calls = gt, calls

    def Convert(self, request, context):
        self._calls.record(request)
        # Apply the fixed rate to the incoming amount, restamp to the requested currency.
        # 'from' is a Python keyword → the protobuf field is reached via getattr.
        src = getattr(request, "from")
        src_nanos = src.units * 1_000_000_000 + src.nanos
        out = int(round(src_nanos * self._gt.currency_rate))
        units = out // 1_000_000_000
        nanos = out - units * 1_000_000_000
        return demo_pb2.Money(currency_code=request.to_code, units=units, nanos=int(nanos))

    def GetSupportedCurrencies(self, request, context):
        self._calls.record(request)
        return demo_pb2.GetSupportedCurrenciesResponse(
            currency_codes=["USD", self._gt.user_currency])


class _ShippingStub(demo_pb2_grpc.ShippingServiceServicer):
    def __init__(self, gt: GroundTruth, calls: _CallCounter):
        self._gt, self._calls = gt, calls

    def GetQuote(self, request, context):
        self._calls.record(request)
        return demo_pb2.GetQuoteResponse(cost_usd=demo_pb2.Money(
            currency_code="USD", units=self._gt.shipping_cost_units, nanos=self._gt.shipping_cost_nanos))

    def ShipOrder(self, request, context):
        self._calls.record(request)
        return demo_pb2.ShipOrderResponse(tracking_id=self._gt.shipping_tracking_id)


class _PaymentStub(demo_pb2_grpc.PaymentServiceServicer):
    def __init__(self, gt: GroundTruth, calls: _CallCounter):
        self._gt, self._calls = gt, calls

    def Charge(self, request, context):
        self._calls.record(request)
        return demo_pb2.ChargeResponse(transaction_id=self._gt.transaction_id)


class _EmailStub(demo_pb2_grpc.EmailServiceServicer):
    def __init__(self, gt: GroundTruth, calls: _CallCounter):
        self._gt, self._calls = gt, calls

    def SendOrderConfirmation(self, request, context):
        self._calls.record(request)
        return demo_pb2.Empty()


# ---------------------------------------------------------------------------
# The harness (FR-CO-2/3/4).
# ---------------------------------------------------------------------------
@dataclass
class _StubEntry:
    env_name: str
    servicer: object
    register: object  # add_*ServiceServicer_to_server
    counter: _CallCounter
    server: Optional[grpc.Server] = None
    addr: str = ""


class CheckoutStubHarness:
    """Six in-process loopback gRPC dependency stubs for checkoutservice (FR-CO-1..4, FR-CO-8).

    Usage (the execute branch will consume this contract verbatim)::

        harness = CheckoutStubHarness()              # optional: CheckoutStubHarness(GroundTruth(...))
        addr_map = harness.start()                   # {"PRODUCT_CATALOG_SERVICE_ADDR": "127.0.0.1:54321", ...}
        try:
            extra_env = {**extra_env, **addr_map}    # inject before the SUT launches
            ...                                       # run the SUT + suite
            harness.call_counts                       # {"PRODUCT_CATALOG_SERVICE_ADDR": 2, ...}
        finally:
            harness.stop()                            # deterministic, exception-safe teardown of all six

    Also usable as a context manager: ``with CheckoutStubHarness() as h: addr_map = h.addr_map``.
    """

    def __init__(self, ground_truth: Optional[GroundTruth] = None, *, max_workers: int = 8,
                 grace: float = 1.0) -> None:
        self.ground_truth = ground_truth or GroundTruth()
        self._grace = grace
        self._max_workers = max_workers
        gt = self.ground_truth
        self._entries: List[_StubEntry] = [
            _StubEntry(ENV_PRODUCT_CATALOG, _ProductCatalogStub(gt, _CallCounter()),
                       demo_pb2_grpc.add_ProductCatalogServiceServicer_to_server, None),
            _StubEntry(ENV_CART, _CartStub(gt, _CallCounter()),
                       demo_pb2_grpc.add_CartServiceServicer_to_server, None),
            _StubEntry(ENV_CURRENCY, _CurrencyStub(gt, _CallCounter()),
                       demo_pb2_grpc.add_CurrencyServiceServicer_to_server, None),
            _StubEntry(ENV_SHIPPING, _ShippingStub(gt, _CallCounter()),
                       demo_pb2_grpc.add_ShippingServiceServicer_to_server, None),
            _StubEntry(ENV_PAYMENT, _PaymentStub(gt, _CallCounter()),
                       demo_pb2_grpc.add_PaymentServiceServicer_to_server, None),
            _StubEntry(ENV_EMAIL, _EmailStub(gt, _CallCounter()),
                       demo_pb2_grpc.add_EmailServiceServicer_to_server, None),
        ]
        # Backfill the counter ref onto each entry (the servicer was constructed with it).
        for e in self._entries:
            e.counter = e.servicer._calls  # type: ignore[attr-defined]
        self._started = False

    # -- lifecycle ----------------------------------------------------------
    def start(self) -> Dict[str, str]:
        """Bind all six servers on free loopback ports; return the ``{ENV_NAME: addr}`` map.

        Idempotent-safe: raises if called twice without an intervening ``stop()``."""
        if self._started:
            raise RuntimeError("CheckoutStubHarness.start() called twice without stop()")
        for e in self._entries:
            server = grpc.server(futures.ThreadPoolExecutor(max_workers=self._max_workers))
            e.register(e.servicer, server)
            port = server.add_insecure_port("127.0.0.1:0")
            if port == 0:  # pragma: no cover — bind failure
                self.stop()
                raise RuntimeError(f"failed to bind loopback port for {e.env_name}")
            server.start()
            e.server = server
            e.addr = f"127.0.0.1:{port}"
        self._started = True
        return self.addr_map

    def stop(self) -> None:
        """Deterministically stop all six servers, exception-safe (FR-CO-3) — no orphaned listeners."""
        for e in self._entries:
            srv = e.server
            if srv is None:
                continue
            try:
                srv.stop(self._grace).wait(timeout=self._grace + 1.0)
            except Exception:  # noqa: BLE001 — teardown must never raise / leak the next listener
                pass
            finally:
                e.server = None
                e.addr = ""
        self._started = False

    # -- inspection ---------------------------------------------------------
    @property
    def addr_map(self) -> Dict[str, str]:
        """``{ENV_NAME: "127.0.0.1:<port>"}`` for all six stubs (empty until ``start()``)."""
        return {e.env_name: e.addr for e in self._entries if e.addr}

    @property
    def call_counts(self) -> Dict[str, int]:
        """``{ENV_NAME: <times the stub's RPCs were invoked>}`` (FR-CO-8 — the per-step observable)."""
        return {e.env_name: e.counter.count for e in self._entries}

    def requests_for(self, env_name: str) -> List[object]:
        """The captured request messages a given stub saw (CQ-2 content assertions: deferred but kept)."""
        for e in self._entries:
            if e.env_name == env_name:
                return list(e.counter.requests)
        raise KeyError(env_name)

    def reset_counts(self) -> None:
        """Zero all call counters (for reuse across reps in one process)."""
        for e in self._entries:
            with e.counter._lock:  # keep reset consistent with the locked record() path
                e.counter.count = 0
                e.counter.requests.clear()

    # -- context manager ----------------------------------------------------
    def __enter__(self) -> "CheckoutStubHarness":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()
