"""Unit tests for R3-M3 layered scoring (fleet.score) — pure function over synthetic JourneyResults.

Pins the per-service ATTRIBUTION rules: a direct step's culprit is model-fault; an orchestrated
(checkout) step broken by a downstream dep attributes model-fault to the DEP and propagated (NOT
model-fault) to checkoutservice — a downstream break is never charged to the entry service.
"""
from __future__ import annotations

import pytest

from startd8.benchmark_matrix.fleet import journey as J
from startd8.benchmark_matrix.fleet import score as S
from startd8.benchmark_matrix.fleet.adapter_b import JourneyResult, StepResult

pytestmark = pytest.mark.unit


def _result(verdicts: dict[str, tuple[bool, str | None]]) -> JourneyResult:
    """Build a JourneyResult from {step_name: (passed, culprit)} over the canonical 5 steps."""
    r = JourneyResult()
    for step in J.JOURNEY:
        passed, culprit = verdicts[step.name]
        r.steps.append(StepResult(step.name, passed, "detail", step.weight, culprit if not passed else None))
    return r


_ALL_PASS = {s.name: (True, None) for s in J.JOURNEY}


def test_healthy_mesh_scorecard():
    sc = S.score_journey(_result(_ALL_PASS))
    assert sc.unweighted_coverage == 1.0 and sc.weighted_coverage == 1.0
    assert sc.journey_completed is True
    assert sc.confidence == "high"
    assert sc.faults == [] and sc.model_faulted_services == set()


def test_break_payment_attributes_to_payment_not_checkout():
    """Only checkout fails, culprit=payment (a downstream dep) → payment is model-fault, checkout is
    PROPAGATED (exonerated). The load-bearing 'downstream break never charged to the entry' rule."""
    v = dict(_ALL_PASS)
    v["checkout"] = (False, "paymentservice")
    sc = S.score_journey(_result(v))
    assert sc.model_faulted_services == {"paymentservice"}
    assert sc.propagated_services == {"checkoutservice"}
    assert "checkoutservice" not in sc.model_faulted_services  # NOT charged for the upstream break
    assert sc.journey_completed is False
    assert sc.confidence == "high"  # other steps passed -> a healthy baseline exists
    # weighted coverage drops only by checkout's weight (1 of 18)
    assert abs(sc.weighted_coverage - 17 / 18) < 1e-9


def test_break_catalog_attributes_to_catalog_checkout_propagated():
    """catalog breaks: its direct steps (browse, addToCart) fail model-fault:catalog; checkout also
    fails (culprit=catalog via getproduct) -> propagated:checkout<-catalog. catalog model-fault once."""
    v = dict(_ALL_PASS)
    v["browse"] = (False, "productcatalogservice")
    v["addToCart"] = (False, "productcatalogservice")
    v["checkout"] = (False, "productcatalogservice")
    sc = S.score_journey(_result(v))
    assert sc.model_faulted_services == {"productcatalogservice"}  # the real broken service, once
    assert sc.propagated_services == {"checkoutservice"}           # checkout exonerated
    assert sc.journey_completed is False


def test_checkout_own_logic_fault_is_model_fault_on_checkout():
    """A checkout failure whose culprit IS checkoutservice (its own logic, e.g. empty order_id) is
    model-fault on checkout — propagation only applies to downstream-dep culprits."""
    v = dict(_ALL_PASS)
    v["checkout"] = (False, "checkoutservice")
    sc = S.score_journey(_result(v))
    assert sc.model_faulted_services == {"checkoutservice"}
    assert sc.propagated_services == set()


def test_all_steps_failed_is_low_confidence():
    v = {s.name: (False, "currencyservice") for s in J.JOURNEY}
    sc = S.score_journey(_result(v))
    assert sc.confidence == "low"  # no healthy baseline -> attribution is low-confidence (FR-22)
    assert sc.journey_completed is False


def test_unidentified_culprit_is_harness_not_a_model():
    v = dict(_ALL_PASS)
    v["viewCart"] = (False, None)  # a failure with no identified culprit
    sc = S.score_journey(_result(v))
    assert sc.model_faulted_services == set()
    assert any(f.classification == S.HARNESS for f in sc.faults)
