#!/usr/bin/env python3
"""Run the Online Boutique model benchmark — service x model x repetition matrix (M3).

Assembles a BenchmarkRunSpec from the M2 seeds + roster, enforces budget guardrails
(FR-33, fail-closed), runs each cell via run_prime_workflow.py --benchmark-mode, and
writes per-cell results + an aggregated leaderboard (FR-15/FR-17).

  python3 scripts/run_ob_benchmark.py --dry-run                  # size only, no spend
  python3 scripts/run_ob_benchmark.py --budget 50               # full roster, N=5
  python3 scripts/run_ob_benchmark.py --budget 20 --flagships-only --reps 3

WARNING: without --dry-run this spends real money and calls real LLM APIs. Requires a
--budget (fail-closed). Start small (--flagships-only --reps 1 --budget 5).
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
    build_leverage_delta_markdown,
    build_matrix_markdown,
    estimate_run_cost,
    format_estimate,
    leverage_delta,
    run_matrix,
)
from startd8.benchmark_matrix.budget import BudgetGuard  # noqa: E402
from startd8.benchmark_matrix.runner import STATUS_INTEGRITY_FAIL  # noqa: E402

SEEDS_DIR = REPO / "docs" / "design" / "model-benchmark" / "seeds"
SEEDS_INDEX = SEEDS_DIR / "seeds-index.json"

ROSTER_FULL = [
    "anthropic:claude-opus-4-8", "anthropic:claude-fable-5",
    "anthropic:claude-sonnet-4-6", "anthropic:claude-haiku-4-5-20251001",
    "openai:gpt-5.5", "openai:gpt-5.4-mini", "openai:gpt-5.4-nano",
    "gemini:gemini-2.5-pro", "gemini:gemini-2.5-flash", "gemini:gemini-2.5-flash-lite",
]
ROSTER_FLAGSHIPS = [
    "anthropic:claude-fable-5", "anthropic:claude-opus-4-8",
    "openai:gpt-5.5", "gemini:gemini-2.5-pro",
]


def _sdk_version():
    try:
        from importlib.metadata import version
        return version("startd8")
    except Exception:
        return None


def _build_spec(args, index) -> tuple[BenchmarkRunSpec, dict]:
    services = [s["service"] for s in index["services"]]
    if args.services:
        services = [s for s in services if s in set(args.services)]
    languages = {s["service"]: s["language"] for s in index["services"]}
    seed_hashes = {s["service"]: s["seed_sha256"] for s in index["services"] if s["service"] in services}
    models = args.models or (ROSTER_FLAGSHIPS if args.flagships_only else ROSTER_FULL)
    # K2 (R4-S1): leverage axis. Default "off" ⇒ today's single-state matrix (FR-1 backward compat).
    leverage_states = tuple(s.strip() for s in args.leverage_states.split(",") if s.strip())
    on = args.leverage_on
    leverage_on_config = {"routing": on in ("routing", "both"),
                          "micro_prime": on in ("micro_prime", "both")}
    # K3 (R6-S6): role axis. Default None = diagonal (FR-1). `--role-pair LEAD,DRAFTER` (repeatable)
    # gives an explicit prune; `--role-pairs grid` expands to the full L×D — NEVER implied by --models.
    role_pairs = None
    if args.role_pair:
        pairs = []
        for rp in args.role_pair:
            if "," not in rp:
                raise SystemExit(f"--role-pair must be LEAD,DRAFTER (comma-separated): {rp!r}")
            lead, drafter = rp.split(",", 1)
            pairs.append((lead.strip(), drafter.strip()))
        role_pairs = tuple(pairs)
    elif args.role_pairs == "grid":
        role_pairs = BenchmarkRunSpec.grid_pairs(models)
    spec = BenchmarkRunSpec(
        name=args.name, models=tuple(models), services=tuple(services),
        repetitions=args.reps, budget_ceiling_usd=args.budget, per_cell_cap_usd=args.per_cell_cap,
        leverage_states=leverage_states, leverage_on_config=leverage_on_config,
        role_pairs=role_pairs,
        seed_hashes=seed_hashes, proto_sha256=index.get("proto_sha256"), sdk_version=_sdk_version(),
        # CS-17: stamp the scoring method into the spec so a later combined scoreboard can gate on it.
        repair_mode=args.repair_mode, expose_defects=args.expose_defects,
    )
    return spec, languages


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--name", default="summer-2026-round-1")
    ap.add_argument("--budget", type=float, default=None, help="Budget ceiling USD (required to run).")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--per-cell-cap", type=float, default=None)
    ap.add_argument("--flagships-only", action="store_true")
    ap.add_argument("--models", nargs="*", default=None)
    ap.add_argument("--services", nargs="*", default=None)
    ap.add_argument("--timeout", type=float, default=1800.0, help="Per-cell timeout seconds.")
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true", help="Size only; no execution / spend.")
    ap.add_argument(
        "--repair-mode", choices=["apply", "shadow", "off"], default="apply",
        help="Per-cell repair mode (FR-B5). shadow = observe-only (raw output preserved).",
    )
    ap.add_argument(
        "--expose-defects", action="store_true",
        help="Per-cell defect ledger + de-saturated quality score (FR-B3/B5).",
    )
    ap.add_argument(
        "--leverage-states", default="off",
        help="K2 (FR-K2): comma list ⊆ off,on. 'off,on' pairs each coordinate with SDK leverage "
             "OFF (LLM-maximal) and ON for a Δquality/Δcost report. Default 'off' = today's matrix.",
    )
    ap.add_argument(
        "--leverage-on", choices=["routing", "micro_prime", "both"], default="routing",
        help="What a leverage=on cell engages (R2-S3). Default routing (complexity routing only).",
    )
    ap.add_argument(
        "--role-pairs", choices=["none", "grid"], default="none",
        help="K3 (FR-K3-2): 'none'=diagonal/single-model (default); 'grid'=full L×D over the roster "
             "(#models², requires --allow-large past the cell guard). NEVER implied by --models.",
    )
    ap.add_argument(
        "--role-pair", action="append", default=None, metavar="LEAD,DRAFTER",
        help="K3 explicit (lead,drafter) pair, repeatable; each is a provider:model agent spec, "
             "comma-separated (e.g. --role-pair anthropic:claude-opus-4-8,openai:gpt-5.5).",
    )
    ap.add_argument(
        "--allow-large", action="store_true",
        help="Permit a run exceeding the 200-cell guard (FR-2/R6-S3) — required for large grids.",
    )
    args = ap.parse_args(argv)

    if not SEEDS_INDEX.exists():
        print(f"error: {SEEDS_INDEX} not found — run gen_ob_benchmark_seeds.py", file=sys.stderr)
        return 1
    index = json.loads(SEEDS_INDEX.read_text(encoding="utf-8"))
    spec, languages = _build_spec(args, index)
    estimate = estimate_run_cost(spec)

    print(format_estimate(spec, estimate))

    # Composition guard (FR-2 / R6-S3): refuse > 200 cells without --allow-large so a grid (or any
    # knob expansion) can't silently fan out and overspend. Shown-then-flagged on a dry-run.
    CELL_GUARD = 200
    over_guard = spec.total_cells > CELL_GUARD and not args.allow_large
    if args.dry_run:
        if over_guard:
            print(f"\n⚠ {spec.total_cells} cells exceeds the {CELL_GUARD}-cell guard — a real run "
                  f"would refuse without --allow-large (FR-2).")
        print("\n(dry-run: no cells executed)")
        return 0
    if over_guard:
        print(f"\nrefusing {spec.total_cells} cells (> {CELL_GUARD}-cell guard); pass --allow-large "
              f"to proceed (FR-2/R6-S3).", file=sys.stderr)
        return 2

    # Fail-closed preflight before any spend (FR-33).
    try:
        BudgetGuard(spec).preflight(estimate)
    except BudgetError as exc:
        print(f"\npreflight BLOCKED — {exc}", file=sys.stderr)
        return 2

    out_dir = args.out_dir or (REPO / ".startd8" / "benchmark-runs" / spec.spec_hash()[:12])
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "run-spec.json").write_text(spec.to_json(), encoding="utf-8")
    print(f"\nrunning {spec.total_cells} cells → {out_dir}\n")

    executor = SubprocessCellExecutor(
        SEEDS_DIR, per_run_timeout_s=args.timeout, workdir_root=out_dir / "sandboxes",
        repair_mode=args.repair_mode, expose_defects=args.expose_defects,
    )

    def _progress(cr):
        print(f"  [{cr.status:<13}] {cr.service:<22} {cr.model:<32} r{cr.repetition} "
              f"q={cr.quality if cr.quality is not None else 'NA'} ${cr.cost_usd or 0:.4f}")

    res = run_matrix(spec, executor, languages=languages, on_cell=_progress, preflight=False)
    agg = aggregate_cells(res.cells)

    (out_dir / "cells.json").write_text(
        json.dumps([c.to_dict() for c in res.cells], indent=2), encoding="utf-8")
    (out_dir / "aggregate.json").write_text(json.dumps(agg, indent=2), encoding="utf-8")
    leaderboard = build_matrix_markdown(spec.name, spec.spec_hash(), agg)

    # K2 (FR-K2-3 / R4-S2): when both leverage states ran, emit the paired delta + a
    # machine-readable pairing audit (matched pairs + dropped coordinates with reason codes).
    if "on" in spec.leverage_states:
        delta = leverage_delta(res.cells)
        (out_dir / "leverage_delta.json").write_text(json.dumps(delta, indent=2), encoding="utf-8")
        (out_dir / "pairing_audit.json").write_text(json.dumps({
            "spec_hash": spec.spec_hash(), "n_pairs": delta["n_pairs"],
            "unpaired_count": delta["unpaired_count"], "unpaired": delta["unpaired"],
            "by_model": {m: s["pairs"] for m, s in delta["by_model"].items()},
        }, indent=2), encoding="utf-8")
        leaderboard += "\n" + build_leverage_delta_markdown(delta)

    (out_dir / "leaderboard.md").write_text(leaderboard, encoding="utf-8")

    print("\n" + leaderboard)
    print(f"total spend: ${res.total_cost_usd:.4f}  ·  budget ${spec.budget_ceiling_usd:.2f}  ·  "
          f"skipped {res.skipped_cells} cell(s)")

    integrity_fails = [c for c in res.cells if c.status == STATUS_INTEGRITY_FAIL]
    if integrity_fails:
        print(f"\n⚠ {len(integrity_fails)} cell(s) had deterministic shortcuts fire (R1-S4) — "
              f"benchmark NOT fully LLM-maximized. See cells.json.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
