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
    run_matrix,
)

SEEDS_DIR = REPO / "docs" / "design" / "model-benchmark" / "seeds"
NODE_RUNTIME = REPO / "src" / "startd8" / "benchmark_matrix" / "behavioral" / "node_runtime"
# Roster: the three available flagships. Fable 5 removed (access-gated 404) — OQ-T2-3.
DEFAULT_MODELS = ("anthropic:claude-opus-4-8", "openai:gpt-5.5", "gemini:gemini-2.5-pro")
PILOT_SERVICE = "paymentservice"


def _service_language(service: str) -> str:
    """Per-service language from the seed (for the run_matrix languages map)."""
    import json
    seed = SEEDS_DIR / f"seed-{service}.json"
    if seed.is_file():
        return json.loads(seed.read_text()).get("service_metadata", {}).get("language", "unknown")
    return "unknown"


def build_spec(services, models, repetitions: int, budget: float, per_cell_cap: float | None) -> BenchmarkRunSpec:
    """The pilot spec: the chosen service(s), the flagship roster, N reps. Behavioral scoring is
    enabled on the executor (not the spec) — the spec just fixes what is generated."""
    services = tuple(services)
    name = "behavioral-pilot-" + "-".join(services)
    return BenchmarkRunSpec(
        name=name[:60],
        models=tuple(models),
        services=services,
        repetitions=repetitions,
        budget_ceiling_usd=budget,
        per_cell_cap_usd=per_cell_cap,
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--run", action="store_true",
                      help="Actually generate + behaviorally score (LLM SPEND).")
    mode.add_argument("--dry-run", action="store_true",
                      help="Print the plan + cost estimate and exit (default; spends nothing).")
    ap.add_argument("--model", action="append", dest="models", default=[],
                    help="Override roster (repeatable). Default: the 3 flagships.")
    ap.add_argument("--services", default=PILOT_SERVICE,
                    help="Comma-separated services (default: paymentservice). Pilot-each-once uses "
                         "--repetitions 1 across several services to confirm discrimination.")
    ap.add_argument("--repetitions", type=int, default=3)
    ap.add_argument("--budget", type=float, default=10.0, help="Fail-closed batch budget ceiling (USD).")
    ap.add_argument("--per-cell-cap", type=float, default=None)
    ap.add_argument("--workdir-root", default=None)
    args = ap.parse_args(argv)

    models = list(dict.fromkeys(args.models)) or list(DEFAULT_MODELS)
    services = [s.strip() for s in args.services.split(",") if s.strip()]
    languages = {s: _service_language(s) for s in services}
    spec = build_spec(services, models, args.repetitions, args.budget, args.per_cell_cap)
    est = estimate_run_cost(spec)

    print("=== Behavioral pilot plan ===")
    print(f"services: {', '.join(f'{s} ({languages[s]})' for s in services)}")
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

    import json
    from datetime import datetime

    from startd8.benchmark_matrix.runner import SubprocessCellExecutor

    # FR-T2-PERSIST: durable, inspectable batch root (NOT $TMPDIR, which the OS reaps). Per-cell
    # workdirs land here; cells.json + report.md are written here for re-scoring / audit.
    batch_root = (Path(args.workdir_root) if args.workdir_root
                  else REPO / "out" / "behavioral-pilot" / f"run-{datetime.now():%Y%m%dT%H%M%S}")
    batch_root.mkdir(parents=True, exist_ok=True)
    print(f"batch root (persistent): {batch_root}")

    executor = SubprocessCellExecutor(SEEDS_DIR, behavioral=True, workdir_root=str(batch_root))
    result = run_matrix(spec, executor, languages=languages)
    agg = aggregate_cells(result.cells)

    # Functional-coverage section (OQ-T2-2) — written into the report too, not just printed.
    lines = ["", "## Functional coverage per cell (OQ-T2-2: does behavior discriminate?)", ""]
    for c in result.cells:
        fc = "N/A" if c.functional_coverage is None else f"{c.functional_coverage:.3f}"
        why = ""
        if c.functional_coverage is None and c.behavioral:
            why = f"  ({c.behavioral.get('missing_module') or c.behavioral.get('attempted_proto_path') or c.behavioral.get('reason') or c.status})"
        lines.append(f"- `{c.model}` rep{c.repetition}: functional={fc} status={c.status}{why}")
    report = build_matrix_markdown(spec.name, spec.spec_hash(), agg) + "\n".join(lines) + "\n"

    (batch_root / "cells.json").write_text(
        json.dumps([c.to_dict() for c in result.cells], indent=2, default=str), encoding="utf-8")
    (batch_root / "report.md").write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"\nartifacts: {batch_root}/report.md  +  cells.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
