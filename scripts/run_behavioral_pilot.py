#!/usr/bin/env python3
"""Scoped Track 2 behavioral pilot — paymentservice × flagships × N (M-T2.4).

SET UP, NOT STARTED. The default is a **dry-run**: it prints the plan + pre-run cost estimate and
spends nothing. Pass ``--run`` to actually generate code and behaviorally score it (real LLM spend).

The pilot answers OQ-T2-2: does executed ``Charge`` behavior discriminate the flagships, or does it
saturate too (→ escalate to a harder RPC before any full re-run)?

Prereq for ``--run``: vendor the Node gRPC runtime once (with network):
    src/startd8/benchmark_matrix/behavioral/node_runtime/vendor.sh

Usage:
    python3 scripts/run_behavioral_pilot.py                 # dry-run: plan + cost, no spend
    python3 scripts/run_behavioral_pilot.py --run           # execute the pilot (SPENDS)
    python3 scripts/run_behavioral_pilot.py --repetitions 5 --budget 25
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from startd8.benchmark_matrix import (  # noqa: E402
    BenchmarkRunSpec,
    aggregate_cells,
    build_matrix_markdown,
    estimate_run_cost,
    format_estimate,
    rank_models_by_quality,
    run_matrix,
)

SEEDS_DIR = REPO / "docs" / "design" / "model-benchmark" / "seeds"
NODE_RUNTIME = REPO / "src" / "startd8" / "benchmark_matrix" / "behavioral" / "node_runtime"
# Roster: the three available flagships. Fable 5 removed (access-gated 404) — OQ-T2-3.
DEFAULT_MODELS = ("anthropic:claude-opus-4-8", "openai:gpt-5.5", "gemini:gemini-2.5-pro")
PILOT_SERVICE = "paymentservice"


def build_spec(models, repetitions: int, budget: float, per_cell_cap: float | None) -> BenchmarkRunSpec:
    """The pilot spec: one service, the flagship roster, N reps. Behavioral scoring is enabled on
    the executor (not the spec) — the spec just fixes what is generated."""
    return BenchmarkRunSpec(
        name="behavioral-pilot-paymentservice",
        models=tuple(models),
        services=(PILOT_SERVICE,),
        repetitions=repetitions,
        budget_ceiling_usd=budget,
        per_cell_cap_usd=per_cell_cap,
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run", action="store_true",
                    help="Actually generate + behaviorally score (LLM SPEND). Default: dry-run only.")
    ap.add_argument("--model", action="append", dest="models", default=[],
                    help="Override roster (repeatable). Default: the 3 flagships.")
    ap.add_argument("--repetitions", type=int, default=3)
    ap.add_argument("--budget", type=float, default=10.0, help="Fail-closed batch budget ceiling (USD).")
    ap.add_argument("--per-cell-cap", type=float, default=None)
    ap.add_argument("--workdir-root", default=None)
    args = ap.parse_args(argv)

    models = list(dict.fromkeys(args.models)) or list(DEFAULT_MODELS)
    spec = build_spec(models, args.repetitions, args.budget, args.per_cell_cap)
    est = estimate_run_cost(spec)

    print("=== Behavioral pilot plan ===")
    print(f"service : {PILOT_SERVICE} (nodejs, single-file gRPC server)")
    print(f"models  : {', '.join(models)}")
    print(f"reps    : {spec.repetitions}   cells: {spec.total_cells}")
    print(format_estimate(spec, est))
    vendored = (NODE_RUNTIME / "node_modules").is_dir()
    print(f"node runtime vendored: {vendored}"
          + ("" if vendored else "  ← run node_runtime/vendor.sh before --run"))

    if not args.run:
        print("\nDRY-RUN — nothing generated, $0 spent. Re-run with --run to execute (SPENDS).")
        return 0

    if not vendored:
        print("\nERROR: Node runtime not vendored; run node_runtime/vendor.sh first.", file=sys.stderr)
        return 2

    from startd8.benchmark_matrix.runner import SubprocessCellExecutor

    executor = SubprocessCellExecutor(SEEDS_DIR, behavioral=True, workdir_root=args.workdir_root)
    result = run_matrix(spec, executor, languages={PILOT_SERVICE: "nodejs"})
    agg = aggregate_cells(result.cells)
    print("\n" + build_matrix_markdown(spec.name, spec.spec_hash(), agg))
    print("=== functional coverage per cell (OQ-T2-2: does behavior discriminate?) ===")
    for c in result.cells:
        fc = "N/A" if c.functional_coverage is None else f"{c.functional_coverage:.3f}"
        print(f"  {c.model:<32} rep{c.repetition}  functional={fc}  status={c.status}")
    print("\nRanking (quality):", rank_models_by_quality(agg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
