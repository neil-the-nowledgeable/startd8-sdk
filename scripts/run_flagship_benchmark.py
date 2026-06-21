#!/usr/bin/env python3
"""Full Summer-2026 benchmark across the 3 flagship models — OB baseline + the pricing hardened seed.

Wraps the M3 matrix machinery (BenchmarkRunSpec + run_matrix + SubprocessCellExecutor) for the
specific run the team sized: the 3 confirmed-callable flagships (Opus 4.8, gpt-5.5, Gemini 2.5 Pro —
NOT Fable 5, which is access-gated) × the 9 Online Boutique services + the Liferay-derived
``pricingservice`` hardened seed × N=5, with Track 2 behavioral scoring ON (so every suite-backed
service — payment/currency/shipping/ad/pricing — gets a functional term).

DRY-RUN BY DEFAULT — prints the plan + cost estimate and spends NOTHING. Pass ``--run`` (and a
``--budget``, fail-closed) to actually generate code and call real LLM APIs.

Keys come from Doppler — run it under ``doppler run`` so the provider keys are injected:

    # size only, $0 (no keys needed):
    python3 scripts/run_flagship_benchmark.py

    # execute the full run (SPENDS ~$27; budget 40 gives margin for retries/variance):
    doppler run -p startd8 -c dev -- python3 scripts/run_flagship_benchmark.py --run --budget 40

    # cheaper smoke first (1 rep, pricing seed only):
    doppler run -p startd8 -c dev -- python3 scripts/run_flagship_benchmark.py --run --budget 5 \
        --services pricingservice --reps 1

Behavioral prereq for ``--run``: vendor the Node gRPC runtime once (with network) —
    src/startd8/benchmark_matrix/behavioral/node_runtime/vendor.sh
Without it, the nodejs cells degrade honestly (structural-only), they do not score 0.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from startd8.benchmark_matrix import (  # noqa: E402
    BenchmarkRunSpec,
    BudgetError,
    SubprocessCellExecutor,
    aggregate_cells,
    build_matrix_markdown,
    estimate_run_cost,
    format_estimate,
    run_matrix,
)
from startd8.benchmark_matrix.budget import BudgetGuard  # noqa: E402
from startd8.benchmark_matrix.operator_output import OperatorOutput  # noqa: E402

SEEDS_DIR = REPO / "docs" / "design" / "model-benchmark" / "seeds"
OB_INDEX = SEEDS_DIR / "seeds-index.json"
HARDENED_INDEX = SEEDS_DIR / "hardened-index.json"
NODE_RUNTIME = REPO / "src" / "startd8" / "benchmark_matrix" / "behavioral" / "node_runtime"

# The 3 confirmed-callable flagships. Fable 5 is deliberately excluded (access-gated); add it here
# once access is confirmed (it ~doubles cost — $10/$50 per Mtok).
DEFAULT_FLAGSHIPS = [
    "anthropic:claude-opus-4-8",
    "openai:gpt-5.5",
    "gemini:gemini-2.5-pro",
]


def _sdk_version():
    try:
        from importlib.metadata import version
        return version("startd8")
    except Exception:
        return None


def _load_seeds():
    """Merge the OB baseline index (9 services, shared demo.proto) with the hardened index
    (pricingservice, own proto). Returns (services, languages, seed_hashes)."""
    services, languages, seed_hashes = [], {}, {}
    ob = json.loads(OB_INDEX.read_text())
    for s in ob["services"]:
        services.append(s["service"])
        languages[s["service"]] = s["language"]
        seed_hashes[s["service"]] = s["seed_sha256"]
    if HARDENED_INDEX.exists():
        for s in json.loads(HARDENED_INDEX.read_text()).get("seeds", []):
            services.append(s["service"])
            languages[s["service"]] = s["language"]
            seed_hashes[s["service"]] = s["seed_sha256"]
    return services, languages, seed_hashes


def _build_spec(args, services, seed_hashes):
    return BenchmarkRunSpec(
        name=args.name,
        models=tuple(args.models),
        services=tuple(services),
        repetitions=args.reps,
        budget_ceiling_usd=args.budget,
        per_cell_cap_usd=args.per_cell_cap,
        seed_hashes={s: seed_hashes[s] for s in services if s in seed_hashes},
        proto_sha256=json.loads(OB_INDEX.read_text()).get("proto_sha256"),  # OB shared proto; pricing carries its own in-seed
        sdk_version=_sdk_version(),
        # Token estimate tuned to Round-1 actuals (docs/.../results/ROUND1_PARTIAL_2026-06-12.md):
        # the 8k/6k defaults under-estimate ~3x; 20k/9k reproduces the measured ~$27 for this matrix.
        est_input_tokens_per_cell=args.est_input_tokens,
        est_output_tokens_per_cell=args.est_output_tokens,
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", default="summer-2026-flagship")
    ap.add_argument("--run", action="store_true", help="Actually generate + score (LLM SPEND). Default: dry-run.")
    ap.add_argument("--budget", type=float, default=None, help="Fail-closed budget ceiling USD (required with --run).")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--models", nargs="*", default=list(DEFAULT_FLAGSHIPS), help="Override the flagship roster.")
    ap.add_argument("--services", nargs="*", default=None, help="Subset of services (default: all OB + pricing).")
    ap.add_argument("--no-behavioral", action="store_true", help="Disable Track 2 behavioral scoring.")
    ap.add_argument("--per-cell-cap", type=float, default=None)
    ap.add_argument("--est-input-tokens", type=int, default=20000)
    ap.add_argument("--est-output-tokens", type=int, default=9000)
    ap.add_argument("--timeout", type=float, default=1800.0, help="Per-cell timeout seconds.")
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--quiet", action="store_true", help="Suppress progress lines while retaining final errors.")
    ap.add_argument("--verbose", action="store_true", help="Relay redacted nested workflow output.")
    ap.add_argument("--json-events", nargs="?", const="auto", default=None,
                    help="Write operator events to a file, or '-' for JSONL on stdout.")
    ap.add_argument("--allow-large", action="store_true", help="Permit > 200 cells.")
    args = ap.parse_args(argv)

    all_services, languages, seed_hashes = _load_seeds()
    services = all_services if not args.services else [s for s in all_services if s in set(args.services)]
    if not services:
        print("no matching services", file=sys.stderr)
        return 2

    spec = _build_spec(args, services, seed_hashes)
    estimate = estimate_run_cost(spec)
    behavioral = not args.no_behavioral
    vendored = (NODE_RUNTIME / "node_modules").is_dir()

    print(f"name      : {spec.name}")
    print(f"models    : {', '.join(args.models)}")
    print(f"services  : {len(services)} ({', '.join(services)})")
    print(f"reps      : {spec.repetitions}    cells: {spec.total_cells}")
    print(f"behavioral: {'ON' if behavioral else 'off'}"
          + ("" if not behavioral or vendored else "   ← node runtime NOT vendored; nodejs cells will degrade"))
    print(f"\n{format_estimate(spec, estimate)}")
    if estimate.missing_pricing:
        print(f"⚠ no pricing for: {', '.join(estimate.missing_pricing)} (run will fail-closed on these)")

    CELL_GUARD = 200
    over_guard = spec.total_cells > CELL_GUARD and not args.allow_large

    if not args.run:
        if over_guard:
            print(f"\n⚠ {spec.total_cells} cells exceeds the {CELL_GUARD}-cell guard — a real run needs --allow-large.")
        print("\nDRY-RUN — nothing generated, $0 spent.")
        print("Re-run under Doppler to execute (SPENDS):")
        print("  doppler run -p startd8 -c dev -- python3 scripts/run_flagship_benchmark.py --run --budget 40")
        return 0

    if args.budget is None:
        print("\n--run requires --budget (fail-closed, FR-33).", file=sys.stderr)
        return 2
    if over_guard:
        print(f"\nrefusing {spec.total_cells} cells (> {CELL_GUARD}); pass --allow-large.", file=sys.stderr)
        return 2
    try:
        BudgetGuard(spec).preflight(estimate)
    except BudgetError as exc:
        print(f"\npreflight BLOCKED — {exc}", file=sys.stderr)
        return 2

    out_dir = args.out_dir or (REPO / ".startd8" / "benchmark-runs" / spec.spec_hash()[:12])
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "run-spec.json").write_text(spec.to_json(), encoding="utf-8")
    print(f"\nrunning {spec.total_cells} cells → {out_dir}\n")
    event_path = None if not args.json_events else (
        out_dir / "operator-events.jsonl" if args.json_events == "auto" else args.json_events
    )
    output = OperatorOutput(spec.spec_hash()[:12], out_dir, quiet=args.quiet, json_events=event_path,
                            text_stream=sys.stderr if args.json_events == "-" else sys.stdout)
    output.emit("run_started", "preflight", "benchmark execution started", data={
        "total_cells": spec.total_cells, "budget_ceiling_usd": spec.budget_ceiling_usd,
        "behavioral": behavioral, "output_dir": str(out_dir),
    })

    def _operator_event(message, stage, cell):
        if stage == "workflow_output" and not args.verbose:
            return
        output.emit("workflow_output" if stage == "workflow_output" else "stage_changed", stage,
                    message, cell=cell)

    executor = SubprocessCellExecutor(
        SEEDS_DIR, per_run_timeout_s=args.timeout, workdir_root=out_dir / "sandboxes",
        behavioral=behavioral, operator_callback=_operator_event,
    )

    observed = []

    def _progress(cr):
        observed.append(cr)
        fc = "" if cr.functional_coverage is None else f" fn={cr.functional_coverage:.2f}"
        message = (f"[{cr.status:<13}] {cr.service:<20} {cr.model:<30} r{cr.repetition} "
                   f"q={cr.quality if cr.quality is not None else 'NA'}{fc} ${cr.cost_usd or 0:.4f}")
        output.emit("cell_completed", "completed", message, cell=cr, data={
            "quality": cr.quality, "functional_coverage": cr.functional_coverage,
            "cost_usd": cr.cost_usd, "error": cr.error, "behavioral": cr.behavioral,
        })
        try:
            output.checkpoint(observed, aggregate_cells(observed), spec.total_cells)
        except OSError as exc:
            output.emit("operator_warning", "checkpoint", f"checkpoint failed: {exc}", cell=cr)

    res = run_matrix(spec, executor, languages=languages, on_cell=_progress, preflight=False)
    agg = aggregate_cells(res.cells)
    (out_dir / "cells.json").write_text(json.dumps([c.to_dict() for c in res.cells], indent=2), encoding="utf-8")
    (out_dir / "aggregate.json").write_text(json.dumps(agg, indent=2), encoding="utf-8")
    (out_dir / "leaderboard.md").write_text(build_matrix_markdown(spec.name, spec.spec_hash(), agg), encoding="utf-8")
    output.checkpoint(res.cells, agg, spec.total_cells)
    output.emit("run_completed", "completed", "benchmark execution completed", data={
        "completed_cells": len(res.cells), "total_cost_usd": res.total_cost_usd,
        "artifacts": ["run-spec.json", "cells.json", "aggregate.json", "leaderboard.md"],
    })
    print(f"\ndone → {out_dir}/leaderboard.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
