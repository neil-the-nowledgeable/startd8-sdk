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
from .runner import (
    CellResult,
    MatrixRunResult,
    SubprocessCellExecutor,
    cell_id,
    is_infra_error,
    reclassify_infra_failures,
    resolve_generated_file,
    run_matrix,
    sandbox_dir_name,
)
from .aggregate import (
    aggregate_cells,
    build_leverage_delta_markdown,
    build_matrix_markdown,
    build_role_grid_markdown,
    leverage_delta,
    rank_models_by_consistency,
    rank_models_by_quality,
)
from .rescore import CellRescore, RescoreReport, rescore_run
from .method import MethodSignature, method_signature
from .combined import (
    CellProvenance,
    MergeResult,
    RunInfo,
    merge_runs,
)
from .combined_align import (
    AlignedInput,
    AlignmentAction,
    AlignmentResult,
    align_runs,
)
from .combined_scorecard import (
    build_combined_manifest,
    build_combined_scorecard,
    build_combined_scorecard_html,
    write_combined_manifest,
    write_combined_scorecard,
    write_combined_scorecard_html,
)

__all__ = [
    "MethodSignature",
    "method_signature",
    "merge_runs",
    "MergeResult",
    "CellProvenance",
    "RunInfo",
    "align_runs",
    "AlignmentResult",
    "AlignmentAction",
    "AlignedInput",
    "build_combined_scorecard",
    "build_combined_scorecard_html",
    "build_combined_manifest",
    "write_combined_scorecard",
    "write_combined_scorecard_html",
    "write_combined_manifest",
    "BenchmarkRunSpec",
    "MatrixCell",
    "BenchmarkCostEstimate",
    "BudgetError",
    "BudgetGuard",
    "estimate_run_cost",
    "format_estimate",
    "CellResult",
    "MatrixRunResult",
    "SubprocessCellExecutor",
    "cell_id",
    "is_infra_error",
    "reclassify_infra_failures",
    "resolve_generated_file",
    "run_matrix",
    "sandbox_dir_name",
    "aggregate_cells",
    "build_leverage_delta_markdown",
    "build_matrix_markdown",
    "build_role_grid_markdown",
    "leverage_delta",
    "rank_models_by_consistency",
    "rank_models_by_quality",
    "CellRescore",
    "RescoreReport",
    "rescore_run",
]
