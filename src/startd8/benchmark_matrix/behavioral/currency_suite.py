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


def _total_nanos(m) -> int:
    """A Money's value expressed in nanos (units*1e9 + nanos) for tolerance comparisons."""
    return m.units * 1_000_000_000 + m.nanos


def run_currency_suite(port: int, *, host: str = "127.0.0.1", connect_timeout: float = 5.0,
                       tier: str = "baseline") -> SuiteResult:
    """CurrencyService behavioral suite. ``tier="hardened"`` runs a **superset** (FR-26): the four
    baseline invariants PLUS Money-contract + mathematical invariants that a careless impl (truncating
    sub-units, dumping a remainder into ``nanos`` un-normalized, ignoring the units/nanos sign rule, or
    converting non-linearly) fails — all rate-independent so the suite needs no pinned ECB rates."""
    hardened = tier == "hardened"
    suite = SuiteResult(suite_version=SUITE_VERSION + ("+hardened/1" if hardened else ""))
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

        # ---- Hardened superset (FR-7/FR-26/FR-27): rate-independent correctness invariants ----
        if hardened:
            # H1) zero maps to zero in any currency (no spurious fee/offset/rounding).
            try:
                r = stub.Convert(_convert_req(_money("USD", 0, 0), "EUR"), timeout=5.0)
                ok = (r.units == 0 and r.nanos == 0)
                suite.results.append(RpcResult("h_zero_maps_to_zero", ok, f"{r.units}.{r.nanos}"))
            except grpc.RpcError as e:
                suite.results.append(RpcResult("h_zero_maps_to_zero", False, f"error: {e.code()}"))

            # H2/H3) Money contract on a fractional-prone conversion (proto: nanos ∈
            # [-999_999_999, 999_999_999], and nanos sign must match units sign).
            try:
                r = stub.Convert(_convert_req(_money("USD", 100, 0), "EUR"), timeout=5.0)
                in_range = -999_999_999 <= r.nanos <= 999_999_999
                suite.results.append(RpcResult("h_nanos_in_range", in_range, f"nanos={r.nanos}"))
                sign_ok = not ((r.units > 0 and r.nanos < 0) or (r.units < 0 and r.nanos > 0))
                suite.results.append(RpcResult("h_nanos_sign_matches_units", sign_ok,
                                               f"{r.units}.{r.nanos}"))
            except grpc.RpcError as e:
                suite.results.append(RpcResult("h_nanos_in_range", False, f"error: {e.code()}"))
                suite.results.append(RpcResult("h_nanos_sign_matches_units", False, f"error: {e.code()}"))

            # H4) round-trip ≈ identity: USD→EUR→USD recovers the original within 1 unit (rate-
            # independent reciprocity; a truncating/lossy impl drifts past the tolerance).
            try:
                eur = stub.Convert(_convert_req(_money("USD", 100, 0), "EUR"), timeout=5.0)
                back = stub.Convert(_convert_req(_money("EUR", eur.units, eur.nanos), "USD"), timeout=5.0)
                drift = abs(_total_nanos(back) - 100 * 1_000_000_000)
                ok = drift <= 1_000_000_000  # within 1.00 USD
                suite.results.append(RpcResult("h_round_trip_identity", ok,
                                               f"back={back.units}.{back.nanos} drift_nanos={drift}"))
            except grpc.RpcError as e:
                suite.results.append(RpcResult("h_round_trip_identity", False, f"error: {e.code()}"))
    finally:
        channel.close()
    return suite
