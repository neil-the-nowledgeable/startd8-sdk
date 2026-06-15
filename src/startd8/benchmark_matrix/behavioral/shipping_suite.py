"""shippingservice behavioral suite (P2) — INVARIANT-based (FR-P2-2/5).

The proto pins no quote formula, so we assert invariants a correct GetQuote must satisfy:
  - non-negative cost
  - a valid (3-letter ISO-4217) currency code
  - determinism (same cart → same quote)
"""
from __future__ import annotations

import grpc

from . import demo_pb2, demo_pb2_grpc
from .charge_suite import RpcResult, SuiteResult

SUITE_VERSION = "shipping-suite/1"


def _quote_req():
    return demo_pb2.GetQuoteRequest(
        address=demo_pb2.Address(street_address="1600 Amphitheatre Pkwy", city="Mountain View",
                                 state="CA", country="USA", zip_code=94043),
        items=[demo_pb2.CartItem(product_id="OLJCESPC7Z", quantity=2)],
    )


def run_shipping_suite(port: int, *, host: str = "127.0.0.1", connect_timeout: float = 5.0) -> SuiteResult:
    suite = SuiteResult(suite_version=SUITE_VERSION)
    try:
        channel = grpc.insecure_channel(f"{host}:{port}")
        grpc.channel_ready_future(channel).result(timeout=connect_timeout)
    except Exception as e:  # noqa: BLE001
        suite.connect_error = f"{type(e).__name__}: {e}"
        return suite
    try:
        stub = demo_pb2_grpc.ShippingServiceStub(channel)
        try:
            r = stub.GetQuote(_quote_req(), timeout=5.0).cost_usd
            # 1) non-negative cost (units and nanos same sign per Money spec; check the combined amount).
            nonneg = (r.units > 0) or (r.units == 0 and r.nanos >= 0)
            suite.results.append(RpcResult("quote_non_negative", nonneg, f"{r.units}.{r.nanos}"))
            # 2) valid 3-letter currency code.
            code_ok = isinstance(r.currency_code, str) and len(r.currency_code) == 3 and r.currency_code.isalpha()
            suite.results.append(RpcResult("quote_valid_currency_code", code_ok, r.currency_code))
        except grpc.RpcError as e:
            suite.results.append(RpcResult("quote_non_negative", False, f"error: {e.code()}"))
            suite.results.append(RpcResult("quote_valid_currency_code", False, f"error: {e.code()}"))

        # 3) determinism — same cart twice → same quote.
        try:
            a = stub.GetQuote(_quote_req(), timeout=5.0).cost_usd
            b = stub.GetQuote(_quote_req(), timeout=5.0).cost_usd
            same = (a.currency_code == b.currency_code and a.units == b.units and a.nanos == b.nanos)
            suite.results.append(RpcResult("quote_deterministic", same, "stable" if same else "varied"))
        except grpc.RpcError as e:
            suite.results.append(RpcResult("quote_deterministic", False, f"error: {e.code()}"))
    finally:
        channel.close()
    return suite
