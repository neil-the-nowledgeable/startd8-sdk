"""M3 increment-1 — matrix runner orchestration + budget enforcement + FR-17 aggregation.

Uses a fake executor so no LLM/subprocess runs: exercises run_matrix's budget cumulative-abort,
integrity handling, and the distribution-appropriate aggregation.
"""
from __future__ import annotations

import pytest

from startd8.benchmark_matrix import (
    BenchmarkRunSpec,
    BudgetError,
    CellResult,
    aggregate_cells,
    build_matrix_markdown,
    cell_id,
    rank_models_by_quality,
    run_matrix,
)
from startd8.benchmark_matrix.runner import (
    STATUS_BUDGET_SKIP,
    STATUS_INTEGRITY_FAIL,
    STATUS_OK,
)

LANGS = {"cartservice": "csharp", "emailservice": "python", "adservice": "java"}


def _spec(**over) -> BenchmarkRunSpec:
    kw = dict(
        name="t",
        models=("anthropic:claude-fable-5", "openai:gpt-5.5"),
        services=("cartservice", "emailservice", "adservice"),
        repetitions=2,
        budget_ceiling_usd=1000.0,
    )
    kw.update(over)
    return BenchmarkRunSpec(**kw)


def _fake_executor(quality=0.8, cost=0.10, status=STATUS_OK):
    def ex(cell, spec, language):
        return CellResult(
            cell_id=cell_id(spec.spec_hash(), cell),
            service=cell.service, model=cell.model, language=language,
            repetition=cell.repetition, status=status, quality=quality,
            cost_usd=cost, latency_s=2.0, input_tokens=8000, output_tokens=6000,
        )
    return ex


def test_run_matrix_covers_every_cell():
    spec = _spec()
    res = run_matrix(spec, _fake_executor(), languages=LANGS)
    assert len(res.cells) == spec.total_cells == 3 * 2 * 2
    assert all(c.status == STATUS_OK for c in res.cells)
    assert res.total_cost_usd == pytest.approx(0.10 * spec.total_cells)
    assert res.budget_exhausted is False


def test_preflight_fail_closed_no_ceiling():
    spec = _spec(budget_ceiling_usd=None)
    with pytest.raises(BudgetError, match="fail-closed"):
        run_matrix(spec, _fake_executor(), languages=LANGS)


def test_cumulative_abort_marks_remaining_budget_skip():
    # ceiling 0.25, each cell costs 0.10 -> after 3 cells (0.30 > 0.25) the rest are skipped.
    spec = _spec(budget_ceiling_usd=0.25)
    res = run_matrix(spec, _fake_executor(cost=0.10), languages=LANGS, preflight=False)
    ran = [c for c in res.cells if c.status != STATUS_BUDGET_SKIP]
    skipped = [c for c in res.cells if c.status == STATUS_BUDGET_SKIP]
    assert res.budget_exhausted is True
    assert len(skipped) > 0
    assert len(ran) + len(skipped) == spec.total_cells
    assert res.total_cost_usd <= 0.30 + 1e-9  # stopped shortly after crossing the ceiling


def test_tokens_per_sec_derived():
    c = CellResult(cell_id="x", service="s", model="m", language="go", repetition=0,
                   status=STATUS_OK, output_tokens=6000, latency_s=3.0)
    assert c.tokens_per_sec == pytest.approx(2000.0)


# --- FR-17 aggregation -------------------------------------------------------

def test_aggregate_median_iqr_passrate_and_catastrophic():
    # one (service,model) group: qualities [0.9, 0.0(failed)] -> median over scored only
    cells = [
        CellResult("a", "cartservice", "m1", "csharp", 0, STATUS_OK, quality=0.9, cost_usd=0.1, latency_s=2, output_tokens=6000),
        CellResult("b", "cartservice", "m1", "csharp", 1, STATUS_INTEGRITY_FAIL, quality=None, cost_usd=0.1),
    ]
    agg = aggregate_cells(cells)
    g = agg["by_service_model"]["cartservice|m1"]
    assert g["n"] == 2 and g["n_scored"] == 1
    assert g["quality_median"] == 0.9            # integrity-fail excluded from quality
    assert g["catastrophic_count"] == 1          # integrity-fail counts catastrophic
    assert g["pass_rate"] == pytest.approx(0.5)  # 1 pass of 2 that ran


def test_iqr_and_ranking():
    cells = [
        CellResult(f"m1-{i}", "s", "m1", "go", i, STATUS_OK, quality=q, cost_usd=0.2)
        for i, q in enumerate([0.6, 0.8, 1.0])
    ] + [
        CellResult(f"m2-{i}", "s", "m2", "go", i, STATUS_OK, quality=q, cost_usd=0.05)
        for i, q in enumerate([0.3, 0.4, 0.5])
    ]
    agg = aggregate_cells(cells)
    assert agg["by_model"]["m1"]["quality_iqr"] is not None
    ranking = rank_models_by_quality(agg)
    assert ranking[0][0] == "m1"  # higher median quality wins despite higher cost
    md = build_matrix_markdown("t", "deadbeefcafe", agg)
    assert "Leaderboard" in md and "m1" in md


def test_budget_skip_excluded_from_passrate_denominator():
    cells = [
        CellResult("a", "s", "m", "go", 0, STATUS_OK, quality=0.9),
        CellResult("b", "s", "m", "go", 1, STATUS_BUDGET_SKIP),
    ]
    g = aggregate_cells(cells)["by_service_model"]["s|m"]
    assert g["n_ran"] == 1
    assert g["pass_rate"] == pytest.approx(1.0)  # skip not counted against pass-rate


# --- infra-fail vs model-fail (FR-18 refinement from flagships-round1) -------

def test_is_infra_error_detection():
    from startd8.benchmark_matrix import is_infra_error
    assert is_infra_error("Error code: 401 - invalid x-api-key")
    assert is_infra_error("404 not_found_error: Claude Fable 5 is not available")
    assert is_infra_error("RateLimit: 429 overloaded")
    assert not is_infra_error("SyntaxError: invalid syntax in generated code")
    assert not is_infra_error(None)


def test_infra_fail_excluded_from_model_score():
    from startd8.benchmark_matrix.runner import STATUS_INFRA_FAIL
    # A model whose 9 cells all infra-failed (dead key) must NOT be scored 0/catastrophic.
    cells = [
        CellResult(f"x{i}", "svc", "anthropic:claude-fable-5", "python", i,
                   STATUS_INFRA_FAIL, error="401 invalid x-api-key")
        for i in range(9)
    ]
    g = aggregate_cells(cells)["by_model"]["anthropic:claude-fable-5"]
    assert g["infra_fail_count"] == 9
    assert g["n_ran"] == 0                  # nothing fairly ran
    assert g["catastrophic_count"] == 0     # NOT the model's fault
    assert g["pass_rate"] is None           # no denominator -> undefined, not 0.0


def test_reclassify_infra_failures_upgrades_failed_cells():
    from startd8.benchmark_matrix import reclassify_infra_failures
    from startd8.benchmark_matrix.runner import STATUS_FAILED, STATUS_INFRA_FAIL
    cells = [
        CellResult("a", "s", "m", "go", 0, STATUS_FAILED, error="Error code: 401 - invalid x-api-key"),
        CellResult("b", "s", "m", "go", 1, STATUS_FAILED, error="generated code has a real bug"),
    ]
    n = reclassify_infra_failures(cells)
    assert n == 1
    assert cells[0].status == STATUS_INFRA_FAIL
    assert cells[1].status == STATUS_FAILED  # genuine model failure stays
