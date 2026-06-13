"""Summer 2026 model-benchmark matrix (service x model x repetition).

This subpackage holds the benchmark's execution-model primitives:

- ``run_spec`` — the immutable :class:`BenchmarkRunSpec`, the single source of truth
  for a benchmark run (FR-36): roster, services, repetitions, budget, flag states,
  seed hashes. Everything downstream reads the spec, not scattered CLI flags.
- ``budget`` — pre-run cost estimation + budget guardrails (FR-33 / M2.5):
  fail-closed budget ceiling, per-cell cap, cumulative abort, dry-run sizing.

The matrix runner itself (generalizing ``model_comparison.py``) lands in M3 and
consumes these primitives.
"""
from .run_spec import BenchmarkRunSpec, MatrixCell
from .budget import (
    BenchmarkCostEstimate,
    BudgetError,
    BudgetGuard,
    estimate_run_cost,
    format_estimate,
)

__all__ = [
    "BenchmarkRunSpec",
    "MatrixCell",
    "BenchmarkCostEstimate",
    "BudgetError",
    "BudgetGuard",
    "estimate_run_cost",
    "format_estimate",
]
