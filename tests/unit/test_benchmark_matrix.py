"""M3-prereqs — BenchmarkRunSpec (FR-36) + budget guardrails (FR-33 / M2.5)."""
from __future__ import annotations

import pytest

from startd8.benchmark_matrix import (
    BenchmarkRunSpec,
    BudgetError,
    BudgetGuard,
    estimate_run_cost,
)


def _spec(**over) -> BenchmarkRunSpec:
    kw = dict(
        name="t",
        models=("anthropic:claude-fable-5", "openai:gpt-5.5"),
        services=("cartservice", "emailservice", "adservice"),
        repetitions=5,
        budget_ceiling_usd=50.0,
    )
    kw.update(over)
    return BenchmarkRunSpec(**kw)


# --- FR-36 BenchmarkRunSpec --------------------------------------------------

def test_spec_is_frozen():
    spec = _spec()
    with pytest.raises(Exception):
        spec.repetitions = 9  # type: ignore[misc]


def test_total_cells_and_iteration():
    spec = _spec()
    assert spec.total_cells == 3 * 2 * 5
    cells = list(spec.cells())
    assert len(cells) == spec.total_cells
    assert len(set(cells)) == spec.total_cells  # all distinct
    assert cells[0].service == "cartservice" and cells[0].repetition == 0


def test_validation_rejects_empty_and_dupes_and_bad_reps():
    with pytest.raises(Exception):
        _spec(models=())
    with pytest.raises(Exception):
        _spec(services=("cartservice", "cartservice"))
    with pytest.raises(Exception):
        _spec(repetitions=0)
    with pytest.raises(Exception):
        _spec(budget_ceiling_usd=-1.0)


def test_spec_hash_is_deterministic_and_sensitive():
    a = _spec()
    b = _spec()
    assert a.spec_hash() == b.spec_hash()  # identity-stable
    assert a.spec_hash() != _spec(repetitions=6).spec_hash()
    assert a.spec_hash() != _spec(models=("openai:gpt-5.5",)).spec_hash()
    # token-sizing fields are NOT identity — they don't change WHAT is run
    assert a.spec_hash() == _spec(est_output_tokens_per_cell=99999).spec_hash()


def test_json_round_trip():
    spec = _spec(seed_hashes={"cartservice": "abc"}, proto_sha256="deadbeef")
    import json
    restored = BenchmarkRunSpec.from_dict(json.loads(spec.to_json()))
    assert restored.spec_hash() == spec.spec_hash()
    assert restored.models == spec.models


# --- FR-33 / M2.5 budget -----------------------------------------------------

def test_estimate_sums_cells_times_pricing():
    spec = _spec()
    est = estimate_run_cost(spec)
    assert est.total_cells == spec.total_cells
    assert est.cells_per_model == 3 * 5
    # total == sum of per-model totals
    assert est.total_usd == pytest.approx(sum(est.per_model_usd.values()))
    assert not est.has_missing_pricing  # fable + gpt-5.5 both priced


def test_estimate_flags_missing_pricing():
    spec = _spec(models=("anthropic:claude-fable-5", "openai:nonexistent-model-zzz"))
    est = estimate_run_cost(spec)
    assert "openai:nonexistent-model-zzz" in est.missing_pricing


def test_preflight_fail_closed_without_ceiling():
    spec = _spec(budget_ceiling_usd=None)
    est = estimate_run_cost(spec)
    with pytest.raises(BudgetError, match="fail-closed"):
        BudgetGuard(spec).preflight(est)


def test_preflight_blocks_missing_pricing():
    spec = _spec(models=("anthropic:claude-fable-5", "openai:nope-zzz"))
    est = estimate_run_cost(spec)
    with pytest.raises(BudgetError, match="missing pricing"):
        BudgetGuard(spec).preflight(est)


def test_preflight_blocks_when_estimate_exceeds_ceiling():
    spec = _spec(budget_ceiling_usd=0.01)  # tiny ceiling
    est = estimate_run_cost(spec)
    with pytest.raises(BudgetError, match="exceeds ceiling"):
        BudgetGuard(spec).preflight(est)


def test_preflight_ok_under_ceiling():
    spec = _spec(budget_ceiling_usd=10_000.0)
    BudgetGuard(spec).preflight(estimate_run_cost(spec))  # no raise


def test_cumulative_abort_and_per_cell_cap():
    spec = _spec(budget_ceiling_usd=1.0, per_cell_cap_usd=0.5)
    guard = BudgetGuard(spec)
    v1 = guard.record("cell-1", 0.4)
    assert v1["over_per_cell_cap"] is False
    assert guard.would_exceed(0.4) is False
    v2 = guard.record("cell-2", 0.7)         # over the 0.5 per-cell cap
    assert v2["over_per_cell_cap"] is True
    assert guard.spent_usd == pytest.approx(1.1)
    assert guard.would_exceed() is True       # 1.1 > 1.0 ceiling
    assert len(guard.over_cap_cells) == 1
