"""Task A (FR-CO-15): a checkoutservice cell must flow through the runner→aggregate scoring path
identically to any leaf service — its per-step PlaceOrder coverage lands on CellResult.functional_coverage,
its provenance carries the checkout keys, and aggregate_cells folds it into functional_median.

The runner dispatches checkout via the ``run_behavioral_cell`` guard (service=="checkoutservice")
BEFORE ``_SUITES``, so checkout is never special-cased OUT of scoring even though it is absent from
``_SUITES``. These tests pin that: the guard dispatch is the only divergence, and everything
downstream (CellResult shape, aggregate) is service-agnostic.
"""
from __future__ import annotations

import pytest

from startd8.benchmark_matrix.aggregate import aggregate_cells
from startd8.benchmark_matrix.behavioral import execute as exec_mod
from startd8.benchmark_matrix.behavioral.execute import BehavioralResult, run_behavioral_cell
from startd8.benchmark_matrix.runner import STATUS_OK, CellResult

pytestmark = pytest.mark.unit


def test_run_behavioral_cell_dispatches_checkout_through_guard(monkeypatch, tmp_path):
    """checkoutservice routes to ``_run_checkout_cell`` (the guard), NOT through ``_SUITES`` — and
    checkout is intentionally absent from ``_SUITES`` (so a regression that drops the guard would
    fall through to ``has_suite=False`` and silently stop scoring checkout)."""
    assert "checkoutservice" not in exec_mod._SUITES  # guard, not a leaf suite

    seen = {}

    def _fake_checkout(seed, workdir, target_files, *, cfg=None, port=None, tier="baseline"):
        seen["called"] = True
        seen["tier"] = tier
        return BehavioralResult(
            has_suite=True,
            functional=4 / 6,  # 4 of the 6 PlaceOrder steps passed
            degraded=False,
            provenance={
                "suite": {"coverage": 4 / 6, "results": [
                    {"name": "catalog_priced", "passed": True, "detail": ""},
                    {"name": "email_confirmed", "passed": False, "detail": ""},
                ]},
                "checkout_call_counts": {"PRODUCT_CATALOG_SERVICE_ADDR": 1, "EMAIL_SERVICE_ADDR": 0},
                "suite_kind": "checkout-orchestrator",
            },
        )

    monkeypatch.setattr(exec_mod, "_run_checkout_cell", _fake_checkout)

    res = run_behavioral_cell({}, tmp_path, "checkoutservice", [], tier="hardened")
    assert seen.get("called") is True
    assert seen.get("tier") == "hardened"  # tier threads through the guard
    assert res.has_suite is True
    assert res.functional == pytest.approx(4 / 6)
    assert res.provenance["suite_kind"] == "checkout-orchestrator"
    assert res.provenance["checkout_call_counts"]["PRODUCT_CATALOG_SERVICE_ADDR"] == 1


def _checkout_cellresult(model, fc, *, rep=1):
    """A CellResult exactly as the runner builds one from a checkout BehavioralResult."""
    return CellResult(
        cell_id=f"{model}-checkout-r{rep}",
        service="checkoutservice",
        model=model,
        language="go",
        repetition=rep,
        status=STATUS_OK,
        quality=0.9,
        cost_usd=0.5,
        functional_coverage=fc,
        behavioral={
            "checkout_call_counts": {"PRODUCT_CATALOG_SERVICE_ADDR": 1},
            "suite_kind": "checkout-orchestrator",
        },
    )


def _leaf_cellresult(model, fc):
    return CellResult(
        cell_id=f"{model}-payment-r1",
        service="paymentservice",
        model=model,
        language="python",
        repetition=1,
        status=STATUS_OK,
        quality=0.9,
        cost_usd=0.5,
        functional_coverage=fc,
    )


def test_aggregate_folds_checkout_functional_coverage_like_any_service():
    """``aggregate_cells`` reads ``CellResult.functional_coverage`` service-agnostically, so a
    checkout cell folds into ``functional_median``/``functional_iqr`` exactly like a leaf cell —
    no ``_SUITES`` membership gate anywhere in the aggregate path."""
    model = "anthropic:claude-opus-4-8"
    cells = [
        _checkout_cellresult(model, 0.5, rep=1),
        _checkout_cellresult(model, 1.0, rep=2),
        _leaf_cellresult(model, 1.0),
    ]
    agg = aggregate_cells(cells)
    # all three functional scores fold into the per-model median (0.5, 1.0, 1.0 -> 1.0)
    by_model = agg["by_model"][model]
    assert by_model["n_functional"] == 3
    assert by_model["functional_median"] == pytest.approx(1.0)
    # the checkout-only service view also carries its coverage
    co = agg["by_service"]["checkoutservice"]
    assert co["n_functional"] == 2
    assert co["functional_median"] == pytest.approx(0.75)


def test_checkout_only_run_still_scores_functional_median():
    """A run that exercised ONLY checkout still produces a functional aggregate (regression guard:
    nothing requires a leaf service to be present for checkout to be scored)."""
    model = "gemini:gemini-2.5-pro"
    agg = aggregate_cells([_checkout_cellresult(model, 5 / 6)])
    assert agg["by_model"][model]["functional_median"] == pytest.approx(5 / 6)
