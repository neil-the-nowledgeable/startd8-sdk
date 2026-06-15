"""currencyservice behavioral suite (P2) — INVARIANT-based, no pinned rates needed (FR-P2-2/5).

The proto pins no exchange rates, so we can't assert exact converted amounts. Instead we assert
behavioral invariants that hold rate-independently and separate a correct impl from a careless one:
  - Convert identity: USD→USD returns the same amount (rate-independent)
  - Convert rejects an unknown ISO-4217 to_code (validation)
  - Convert is deterministic (same input → same output)
  - GetSupportedCurrencies returns a non-empty list
``Money from`` is a Python keyword in the generated stub → set via setattr/getattr.
"""
from __future__ import annotations

import grpc

from . import demo_pb2, demo_pb2_grpc
from .charge_suite import RpcResult, SuiteResult

SUITE_VERSION = "currency-suite/1"


def _money(code: str, units: int, nanos: int = 0):
    return demo_pb2.Money(currency_code=code, units=units, nanos=nanos)


def _convert_req(from_money, to_code: str):
    req = demo_pb2.CurrencyConversionRequest(to_code=to_code)
    getattr(req, "from").CopyFrom(from_money)  # 'from' is a Python keyword
    return req


def run_currency_suite(port: int, *, host: str = "127.0.0.1", connect_timeout: float = 5.0) -> SuiteResult:
    suite = SuiteResult(suite_version=SUITE_VERSION)
    try:
        channel = grpc.insecure_channel(f"{host}:{port}")
        grpc.channel_ready_future(channel).result(timeout=connect_timeout)
    except Exception as e:  # noqa: BLE001
        suite.connect_error = f"{type(e).__name__}: {e}"
        return suite
    try:
        stub = demo_pb2_grpc.CurrencyServiceStub(channel)

        # 1) identity — USD→USD must return the same amount, regardless of rates.
        try:
            r = stub.Convert(_convert_req(_money("USD", 100, 0), "USD"), timeout=5.0)
            ok = (r.currency_code == "USD" and r.units == 100 and r.nanos == 0)
            suite.results.append(RpcResult("convert_identity", ok, f"{r.currency_code} {r.units}.{r.nanos}"))
        except grpc.RpcError as e:
            suite.results.append(RpcResult("convert_identity", False, f"error: {e.code()}"))

        # 2) unknown currency code must be rejected.
        try:
            stub.Convert(_convert_req(_money("USD", 100, 0), "ZZZ"), timeout=5.0)
            suite.results.append(RpcResult("convert_rejects_unknown_code", False, "accepted ZZZ"))
        except grpc.RpcError:
            suite.results.append(RpcResult("convert_rejects_unknown_code", True, "rejected"))

        # 3) determinism — same EUR→GBP conversion twice yields the same result.
        try:
            a = stub.Convert(_convert_req(_money("EUR", 50, 0), "GBP"), timeout=5.0)
            b = stub.Convert(_convert_req(_money("EUR", 50, 0), "GBP"), timeout=5.0)
            same = (a.currency_code == b.currency_code and a.units == b.units and a.nanos == b.nanos)
            suite.results.append(RpcResult("convert_deterministic", same, "stable" if same else "varied"))
        except grpc.RpcError as e:
            suite.results.append(RpcResult("convert_deterministic", False, f"error: {e.code()}"))

        # 4) GetSupportedCurrencies returns a non-empty list.
        try:
            resp = stub.GetSupportedCurrencies(demo_pb2.Empty(), timeout=5.0)
            n = len(resp.currency_codes)
            suite.results.append(RpcResult("supported_currencies_nonempty", n >= 1, f"{n} codes"))
        except grpc.RpcError as e:
            suite.results.append(RpcResult("supported_currencies_nonempty", False, f"error: {e.code()}"))
    finally:
        channel.close()
    return suite
