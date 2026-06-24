"""recommendationservice.ListRecommendations behavioral suite (Track-2 expansion — 1-dep).

RecommendationService is a 1-dependency mini-orchestrator: ``ListRecommendations`` dials
``ProductCatalog.ListProducts`` to learn the catalog, then returns a few recommended product ids
drawn from that catalog **excluding** the input ``product_ids``. Correctness is therefore observable
on two axes, both required:

  - **response-observable** — the returned ids come from the catalog and exclude the inputs;
  - **call-counter** — the productcatalog stub was actually DIALED. A naive service that returns
    hardcoded ids without calling the catalog must NOT get full credit, exactly as checkout attributes
    its payment/email steps solely from the dependency call-counters.

Three equal-weight cases (FR — equal weight per case):

  1. ``rec_excludes_input``  — ListRecommendations(user, [some product_ids]) returns ids that come
     FROM the catalog AND EXCLUDE the input product_ids, AND the catalog stub was dialed.
  2. ``rec_empty_input``     — ListRecommendations(user, []) returns ids from the catalog (a non-empty
     recommendation with no inputs to exclude), AND the catalog stub was dialed.
  3. ``rec_subset_of_catalog`` — across both calls every recommended id is a subset of the stub's
     catalog (no invented ids), AND the catalog stub was dialed.

``coverage`` ∈ [0,1] = passing cases / total. Reuses :class:`RpcResult` / :class:`SuiteResult`.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import grpc

from . import demo_pb2, demo_pb2_grpc
from .charge_suite import RpcResult, SuiteResult
from .recommendation_stubs import ENV_PRODUCT_CATALOG, GroundTruth, recommendation_ground_truth

SUITE_VERSION = "recommendation-suite/1"

# Fixed inputs the suite sends (subset of the ground-truth catalog so exclusion is meaningful).
INPUT_PRODUCT_IDS: List[str] = ["OLJCESPC7Z", "66VCHSJNUP"]
TEST_USER_ID = "ground-truth-user"


def score_recommendations(
    rec_with_input: Optional[Sequence[str]],
    rec_empty_input: Optional[Sequence[str]],
    *,
    catalog_ids: Sequence[str],
    input_product_ids: Sequence[str],
    stub_calls: Dict[str, int],
) -> SuiteResult:
    """Score the three cases from the two responses + the catalog stub call-counts (pure function).

    ``rec_with_input`` is the recommended ids for ListRecommendations(user, input_product_ids);
    ``rec_empty_input`` is the recommended ids for ListRecommendations(user, []). Either is ``None``
    when that RPC errored. ``stub_calls`` is the harness ``call_counts`` map — the catalog-dialed
    observable. Fully unit-testable without a live server or the SUT.
    """
    suite = SuiteResult(suite_version=SUITE_VERSION)
    calls = stub_calls or {}
    catalog = set(catalog_ids)
    inputs = set(input_product_ids)

    catalog_dialed = calls.get(ENV_PRODUCT_CATALOG, 0) > 0

    with_ids = list(rec_with_input) if rec_with_input is not None else None
    empty_ids = list(rec_empty_input) if rec_empty_input is not None else None

    # Case 1 — recommendations from the catalog that EXCLUDE the inputs AND the catalog was dialed.
    # Must be non-empty, every id in the catalog, and no id among the inputs.
    excludes_ok = (
        with_ids is not None
        and len(with_ids) > 0
        and all(pid in catalog for pid in with_ids)
        and all(pid not in inputs for pid in with_ids)
    )
    suite.results.append(RpcResult(
        "rec_excludes_input", bool(catalog_dialed and excludes_ok),
        f"catalog_dialed={catalog_dialed} from_catalog+excludes_input={excludes_ok} got={with_ids}"))

    # Case 2 — empty input returns recommendations from the catalog AND the catalog was dialed.
    empty_ok = (
        empty_ids is not None
        and len(empty_ids) > 0
        and all(pid in catalog for pid in empty_ids)
    )
    suite.results.append(RpcResult(
        "rec_empty_input", bool(catalog_dialed and empty_ok),
        f"catalog_dialed={catalog_dialed} non_empty_from_catalog={empty_ok} got={empty_ids}"))

    # Case 3 — across BOTH calls every recommended id is a subset of the stub's catalog (no invented
    # ids) AND the catalog was dialed. A service that fabricates ids fails here even if it excludes inputs.
    seen: List[str] = []
    for ids in (with_ids, empty_ids):
        if ids:
            seen.extend(ids)
    subset_ok = bool(seen) and all(pid in catalog for pid in seen)
    suite.results.append(RpcResult(
        "rec_subset_of_catalog", bool(catalog_dialed and subset_ok),
        f"catalog_dialed={catalog_dialed} all_ids_in_catalog={subset_ok}"))

    return suite


def run_recommendation_suite(
    port: int,
    *,
    stub_calls: Dict[str, int],
    ground_truth: Optional[GroundTruth] = None,
    catalog_ids: Optional[Sequence[str]] = None,
    host: str = "127.0.0.1",
    connect_timeout: float = 5.0,
    rpc_timeout: float = 20.0,
) -> SuiteResult:
    """Connect a RecommendationServiceStub to a live SUT, run two ListRecommendations, score 3 cases.

    ``stub_calls`` (the harness ``call_counts``, possibly a callable for a live snapshot) and the
    catalog universe (``catalog_ids`` or derived from ``ground_truth``) are partial-bound by the
    execute branch AFTER the productcatalog stub is bound. A connect failure is an env outcome →
    empty results (degrade upstream), mirroring the other suites. Call-counts are read AFTER the RPCs
    return, so they reflect whether the SUT actually dialed the catalog during these recommendations.
    """
    gt = ground_truth or recommendation_ground_truth()
    universe = list(catalog_ids) if catalog_ids is not None else list(gt.catalog.keys())
    try:
        channel = grpc.insecure_channel(f"{host}:{port}")
        grpc.channel_ready_future(channel).result(timeout=connect_timeout)
    except Exception as e:  # noqa: BLE001 — failure to connect is an env outcome (degrade upstream)
        suite = SuiteResult(suite_version=SUITE_VERSION)
        suite.connect_error = f"{type(e).__name__}: {e}"
        return suite
    try:
        stub = demo_pb2_grpc.RecommendationServiceStub(channel)

        def _list(product_ids: Sequence[str]) -> Optional[List[str]]:
            try:
                resp = stub.ListRecommendations(
                    demo_pb2.ListRecommendationsRequest(
                        user_id=TEST_USER_ID, product_ids=list(product_ids)),
                    timeout=rpc_timeout)
                return list(resp.product_ids)
            except grpc.RpcError:
                return None  # RPC error → response-observable cases fail; counter cases still scored

        rec_with_input = _list(INPUT_PRODUCT_IDS)
        rec_empty_input = _list([])
        # Read counters AFTER the RPCs (callable returns a live snapshot).
        calls = stub_calls() if callable(stub_calls) else dict(stub_calls)
        return score_recommendations(
            rec_with_input, rec_empty_input,
            catalog_ids=universe, input_product_ids=INPUT_PRODUCT_IDS, stub_calls=calls)
    finally:
        channel.close()
