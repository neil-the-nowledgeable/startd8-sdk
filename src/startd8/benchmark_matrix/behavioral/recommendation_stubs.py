"""recommendationservice dependency-stub harness (Track-2 expansion — 1-dep mini-orchestrator).

RecommendationService is NOT a leaf: its single RPC dials exactly ONE gRPC peer, productcatalog::

    ListRecommendations(ListRecommendationsRequest{user_id, repeated product_ids})
        -> ListRecommendationsResponse{repeated product_ids}

Real semantics (upstream Online Boutique): it calls ``ProductCatalog.ListProducts`` to learn the
full catalog, then returns a few recommended product ids drawn from that catalog **excluding** the
input ``product_ids``. So it is structurally checkout-shaped (bring up dependency stub(s) → inject
``*_SERVICE_ADDR`` → launch SUT → snapshot call-counts → score → teardown) but with ONE dependency
instead of six.

Rather than duplicate the ProductCatalog stub, this harness **reuses checkout_stubs'**
:class:`_ProductCatalogStub` + :class:`_CallCounter` (the same fixed-ground-truth servicer the
checkout harness dials), generalized to a single-dependency harness. :class:`GroundTruth` carries the
fixed catalog the stub serves over ``ListProducts`` (the recommendation oracle's universe), so the
correct recommendations are deterministically computable before any model is judged.
"""
from __future__ import annotations

import socket
from concurrent import futures
from dataclasses import dataclass
from typing import Dict, List, Optional

import grpc

from . import demo_pb2_grpc
from .checkout_stubs import (
    ENV_PRODUCT_CATALOG,
    CatalogProduct,
    GroundTruth,
    _CallCounter,
    _ProductCatalogStub,
)

__all__ = [
    "ENV_PRODUCT_CATALOG",
    "CatalogProduct",
    "GroundTruth",
    "RecommendationDepHarness",
    "recommendation_ground_truth",
]


def recommendation_ground_truth() -> GroundTruth:
    """The fixed catalog the productcatalog stub serves for recommendation (the oracle's universe).

    A handful of distinct product ids so ``ListProducts`` returns a deterministic catalog and a
    recommendation that excludes its inputs still has candidates left. Reuses checkout's
    :class:`GroundTruth` (the ProductCatalog stub reads ``.catalog`` for ``ListProducts``); the
    cart/currency/shipping/payment fields are inert here (recommendation only dials productcatalog).
    """
    return GroundTruth(catalog={
        "OLJCESPC7Z": CatalogProduct("OLJCESPC7Z", "Sunglasses", 19, 990_000_000),
        "66VCHSJNUP": CatalogProduct("66VCHSJNUP", "Tank Top", 18, 990_000_000),
        "1YMWWN1N4O": CatalogProduct("1YMWWN1N4O", "Watch", 109, 990_000_000),
        "L9ECAV7KIM": CatalogProduct("L9ECAV7KIM", "Loafers", 89, 990_000_000),
        "2ZYFJ3GM2N": CatalogProduct("2ZYFJ3GM2N", "Hairdryer", 24, 990_000_000),
    })


def _free_port() -> int:
    """Bind ``127.0.0.1:0`` for a free ephemeral port (mirrors checkout_stubs._free_port)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


@dataclass
class RecommendationDepHarness:
    """One in-process loopback gRPC ProductCatalog stub for recommendationservice (1-dep harness).

    Mirrors :class:`CheckoutStubHarness`'s contract (``start()`` -> ``{ENV_NAME: addr}`` map,
    ``stop()`` exception-safe teardown, ``call_counts``) but binds only the single productcatalog
    dependency recommendation dials. The stub is checkout's :class:`_ProductCatalogStub` over a fixed
    :class:`GroundTruth` catalog, so ``ListProducts`` answers deterministically::

        harness = RecommendationDepHarness()                 # default fixed catalog
        addr_map = harness.start()                            # {"PRODUCT_CATALOG_SERVICE_ADDR": "127.0.0.1:<port>"}
        try:
            extra_env = {**extra_env, **addr_map}             # inject BEFORE the SUT launches
            ...                                                # run the SUT + suite
            harness.call_counts                                # {"PRODUCT_CATALOG_SERVICE_ADDR": <n>}
        finally:
            harness.stop()                                     # deterministic, exception-safe teardown
    """

    ground_truth: GroundTruth = None  # type: ignore[assignment]
    max_workers: int = 8
    grace: float = 1.0

    def __post_init__(self) -> None:
        if self.ground_truth is None:
            self.ground_truth = recommendation_ground_truth()
        self._counter = _CallCounter()
        self._servicer = _ProductCatalogStub(self.ground_truth, self._counter)
        self._server: Optional[grpc.Server] = None
        self._addr: str = ""
        self._started = False

    # -- lifecycle ----------------------------------------------------------
    def start(self) -> Dict[str, str]:
        """Bind the productcatalog stub on a free loopback port; return ``{ENV_NAME: addr}``.

        Idempotent-safe: raises if called twice without an intervening ``stop()``."""
        if self._started:
            raise RuntimeError("RecommendationDepHarness.start() called twice without stop()")
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=self.max_workers))
        demo_pb2_grpc.add_ProductCatalogServiceServicer_to_server(self._servicer, server)
        port = server.add_insecure_port("127.0.0.1:0")
        if port == 0:  # pragma: no cover — bind failure
            try:
                server.stop(0)
            except Exception:  # noqa: BLE001
                pass
            raise RuntimeError("failed to bind loopback port for PRODUCT_CATALOG_SERVICE_ADDR")
        server.start()
        self._server = server
        self._addr = f"127.0.0.1:{port}"
        self._started = True
        return self.addr_map

    def stop(self) -> None:
        """Deterministically stop the stub server, exception-safe — no orphaned listener."""
        srv = self._server
        if srv is not None:
            try:
                srv.stop(self.grace).wait(timeout=self.grace + 1.0)
            except Exception:  # noqa: BLE001 — teardown must never raise / leak the listener
                pass
            finally:
                self._server = None
                self._addr = ""
        self._started = False

    # -- inspection ---------------------------------------------------------
    @property
    def addr_map(self) -> Dict[str, str]:
        """``{PRODUCT_CATALOG_SERVICE_ADDR: "127.0.0.1:<port>"}`` (empty until ``start()``)."""
        return {ENV_PRODUCT_CATALOG: self._addr} if self._addr else {}

    @property
    def call_counts(self) -> Dict[str, int]:
        """``{PRODUCT_CATALOG_SERVICE_ADDR: <times ListProducts/GetProduct was invoked>}`` — the
        observable that proves recommendation actually DIALED the catalog (vs returning hardcoded ids)."""
        return {ENV_PRODUCT_CATALOG: self._counter.count}

    @property
    def catalog_ids(self) -> List[str]:
        """The fixed catalog product ids the stub serves (the oracle's candidate universe)."""
        return list(self.ground_truth.catalog.keys())

    def requests_seen(self) -> List[object]:
        """The captured request messages the productcatalog stub saw (for assertions/provenance)."""
        return list(self._counter.requests)

    def reset_counts(self) -> None:
        """Zero the call counter (for reuse across reps in one process)."""
        with self._counter._lock:
            self._counter.count = 0
            self._counter.requests.clear()

    # -- context manager ----------------------------------------------------
    def __enter__(self) -> "RecommendationDepHarness":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()
