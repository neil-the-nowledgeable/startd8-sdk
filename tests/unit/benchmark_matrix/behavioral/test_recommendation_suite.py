"""Pure-Python unit tests for the recommendationservice behavioral suite (no live launch).

Covers the oracle (exclude-input + from-catalog + subset), the catalog-dialed call-count gate, and
the 1-dep stub harness — all without launching a server or the SUT.
"""
from __future__ import annotations

import pytest

from startd8.benchmark_matrix.behavioral.recommendation_stubs import (
    ENV_PRODUCT_CATALOG,
    RecommendationDepHarness,
    recommendation_ground_truth,
)
from startd8.benchmark_matrix.behavioral.recommendation_suite import (
    INPUT_PRODUCT_IDS,
    score_recommendations,
)

_GT = recommendation_ground_truth()
_CATALOG = list(_GT.catalog.keys())
_DIALED = {ENV_PRODUCT_CATALOG: 2}
_NOT_DIALED = {ENV_PRODUCT_CATALOG: 0}

# Correct recommendations: catalog ids that exclude the inputs.
_GOOD = [pid for pid in _CATALOG if pid not in set(INPUT_PRODUCT_IDS)][:3]


def _names_failed(suite):
    return {r.name for r in suite.results if not r.passed}


def test_oracle_full_coverage_when_correct_and_dialed():
    suite = score_recommendations(
        _GOOD, _GOOD, catalog_ids=_CATALOG, input_product_ids=INPUT_PRODUCT_IDS, stub_calls=_DIALED)
    assert suite.coverage == 1.0, [r.__dict__ for r in suite.results]
    assert len(suite.results) == 3


def test_not_dialed_zeroes_every_case_even_with_correct_ids():
    # Correct ids but the catalog was never dialed → all three cases gated to fail.
    suite = score_recommendations(
        _GOOD, _GOOD, catalog_ids=_CATALOG, input_product_ids=INPUT_PRODUCT_IDS, stub_calls=_NOT_DIALED)
    assert suite.coverage == 0.0, [r.__dict__ for r in suite.results]
    assert _names_failed(suite) == {"rec_excludes_input", "rec_empty_input", "rec_subset_of_catalog"}


def test_echoing_input_fails_exclude_case_only():
    # Returns the INPUT ids for the with-input call (violates exclude); empty-input call is fine.
    suite = score_recommendations(
        list(INPUT_PRODUCT_IDS), _GOOD,
        catalog_ids=_CATALOG, input_product_ids=INPUT_PRODUCT_IDS, stub_calls=_DIALED)
    # rec_excludes_input fails (echoed inputs); rec_empty_input passes; subset still holds (inputs are
    # in the catalog) so rec_subset_of_catalog passes.
    assert _names_failed(suite) == {"rec_excludes_input"}, [r.__dict__ for r in suite.results]
    assert suite.coverage == pytest.approx(2 / 3)


def test_invented_ids_fail_subset_and_exclude():
    invented = ["NOT-IN-CATALOG-1", "NOT-IN-CATALOG-2"]
    suite = score_recommendations(
        invented, invented, catalog_ids=_CATALOG, input_product_ids=INPUT_PRODUCT_IDS, stub_calls=_DIALED)
    failed = _names_failed(suite)
    # Invented ids are not from the catalog → every from-catalog case fails.
    assert "rec_subset_of_catalog" in failed
    assert "rec_excludes_input" in failed
    assert "rec_empty_input" in failed


def test_empty_recommendation_fails_non_empty_cases():
    suite = score_recommendations(
        [], [], catalog_ids=_CATALOG, input_product_ids=INPUT_PRODUCT_IDS, stub_calls=_DIALED)
    # Empty lists are non-discriminating: every case requires a non-empty, from-catalog result.
    assert suite.coverage == 0.0


def test_rpc_error_responses_none_fail_response_cases():
    suite = score_recommendations(
        None, None, catalog_ids=_CATALOG, input_product_ids=INPUT_PRODUCT_IDS, stub_calls=_DIALED)
    assert suite.coverage == 0.0


def test_ground_truth_catalog_has_room_to_exclude_inputs():
    # The oracle universe must have candidates left after excluding the inputs (else case 1 is vacuous).
    remaining = [pid for pid in _CATALOG if pid not in set(INPUT_PRODUCT_IDS)]
    assert len(remaining) >= 2
    assert set(INPUT_PRODUCT_IDS).issubset(set(_CATALOG))


def test_harness_addr_map_and_counts_shape():
    h = RecommendationDepHarness()
    # Before start: empty addr map, zero counts.
    assert h.addr_map == {}
    assert h.call_counts == {ENV_PRODUCT_CATALOG: 0}
    assert ENV_PRODUCT_CATALOG == "PRODUCT_CATALOG_SERVICE_ADDR"
    assert h.catalog_ids == _CATALOG


def test_harness_start_binds_loopback_and_dials_increment_counts():
    import grpc

    from startd8.benchmark_matrix.behavioral import demo_pb2, demo_pb2_grpc

    h = RecommendationDepHarness()
    addr_map = h.start()
    try:
        assert set(addr_map) == {ENV_PRODUCT_CATALOG}
        assert addr_map[ENV_PRODUCT_CATALOG].startswith("127.0.0.1:")
        ch = grpc.insecure_channel(addr_map[ENV_PRODUCT_CATALOG])
        grpc.channel_ready_future(ch).result(timeout=5.0)
        stub = demo_pb2_grpc.ProductCatalogServiceStub(ch)
        resp = stub.ListProducts(demo_pb2.Empty(), timeout=5.0)
        ch.close()
        # The stub serves the fixed ground-truth catalog.
        assert {p.id for p in resp.products} == set(_CATALOG)
        # The dial was counted (the observable that proves the dep was reached).
        assert h.call_counts[ENV_PRODUCT_CATALOG] == 1
    finally:
        h.stop()
    # Idempotent, exception-safe teardown.
    h.stop()
