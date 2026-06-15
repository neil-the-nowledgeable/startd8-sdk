"""adservice behavioral suite (P2) — INVARIANT-based (FR-P2-2/5).

GetAds has the weakest ground truth of the P2 set (any ad is plausibly "correct"), so this asserts
only the floor invariants a usable impl must meet — and is flagged as a likely-saturating /
non-discriminating candidate (FR-P2-4 pilot-each-once decides whether it's worth keeping):
  - returns at least one ad for context keywords
  - each ad has non-empty text and redirect_url
"""
from __future__ import annotations

import grpc

from . import demo_pb2, demo_pb2_grpc
from .charge_suite import RpcResult, SuiteResult

SUITE_VERSION = "ad-suite/1"


def run_ad_suite(port: int, *, host: str = "127.0.0.1", connect_timeout: float = 5.0) -> SuiteResult:
    suite = SuiteResult(suite_version=SUITE_VERSION)
    try:
        channel = grpc.insecure_channel(f"{host}:{port}")
        grpc.channel_ready_future(channel).result(timeout=connect_timeout)
    except Exception as e:  # noqa: BLE001
        suite.connect_error = f"{type(e).__name__}: {e}"
        return suite
    try:
        stub = demo_pb2_grpc.AdServiceStub(channel)
        try:
            resp = stub.GetAds(demo_pb2.AdRequest(context_keys=["clothing"]), timeout=5.0)
            ads = list(resp.ads)
            suite.results.append(RpcResult("ads_returned", len(ads) >= 1, f"{len(ads)} ads"))
            well_formed = bool(ads) and all((a.text or "").strip() and (a.redirect_url or "").strip() for a in ads)
            suite.results.append(RpcResult("ads_well_formed", well_formed,
                                           "text+url present" if well_formed else "empty text/url"))
        except grpc.RpcError as e:
            suite.results.append(RpcResult("ads_returned", False, f"error: {e.code()}"))
            suite.results.append(RpcResult("ads_well_formed", False, f"error: {e.code()}"))
    finally:
        channel.close()
    return suite
