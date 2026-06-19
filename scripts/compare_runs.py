#!/usr/bin/env python3
"""Compare benchmark runs cell-by-cell — repeat-vs-flip + variance across runs and repetitions.

The benchmark's central question when raising N is: did a degradation/score *repeat* (a real model
weakness) or *flip* (run variance)? This tool aggregates every sample for each (service, model)
coordinate across one or more run directories and classifies it, so that question is answered
rigorously instead of by eyeballing two leaderboards. Pure stdlib; $0; re-runnable as runs accumulate
(Mottainai — generate once, compare/rescore free).

Usage:
    python3 scripts/compare_runs.py RUN [RUN ...]
        RUN = a run directory containing cells.json, OR a path to a cells.json directly.
    python3 scripts/compare_runs.py --json RUN_A RUN_B        # machine-readable

Verdicts per coordinate (over all its samples from all runs):
    STABLE            — every sample scored and agrees (within tolerance).
    VARIANT           — samples disagree (some scored, some degraded, or differing scores) → variance.
    CONSISTENT-DEGRADE— every sample degraded/failed for the SAME reason → a real, repeatable weakness.
    VARIANT-DEGRADE   — every sample degraded/failed but for DIFFERENT reasons.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

_EPS = 1e-9


def load_cells(spec: str):
    p = Path(spec)
    f = p if p.is_file() else p / "cells.json"
    if not f.is_file():
        raise SystemExit(f"no cells.json at {spec}")
    cells = json.loads(f.read_text())
    label = (p.parent.name if p.is_file() else p.name) or str(p)
    for c in cells:
        c["_run"] = label
    return cells


def degrade_reason(c: dict):
    """A short reason a cell has no functional score (behavioral provenance > status)."""
    if c.get("functional_coverage") is not None:
        return None
    b = c.get("behavioral") or {}
    for k in ("missing_module", "attempted_proto_path", "violation", "connect_error", "reason"):
        if b.get(k):
            return str(b[k])[:90]
    return c.get("status") or "degraded"


def classify(samples):
    """Verdict over a coordinate's samples. Single-sample (n=1) coordinates can't be 'repeated' or
    'flipped' — they're tagged SCORED/DEGRADE (inconclusive for variance); the repeat-vs-flip verdicts
    only apply at n>=2."""
    funcs = [s["func"] for s in samples]
    scored = [f for f in funcs if f is not None]
    n = len(samples)
    if scored and len(scored) == n and (max(scored) - min(scored) <= _EPS):
        return ("STABLE" if n > 1 else "SCORED"), f"{scored[0]:.2f}"
    if not scored:
        reasons = {s["reason"] for s in samples}
        detail = " | ".join(sorted(str(r) for r in reasons))[:110]
        if n == 1:
            return "DEGRADE", detail
        return ("CONSISTENT-DEGRADE" if len(reasons) == 1 else "VARIANT-DEGRADE"), detail
    return "VARIANT", "mixed scored/degraded or differing scores"


def build_rows(run_specs):
    all_cells = []
    for rd in run_specs:
        all_cells += load_cells(rd)
    groups: dict = {}
    for c in all_cells:
        groups.setdefault((c.get("service"), c.get("model")), []).append({
            "run": c.get("_run"), "rep": c.get("repetition"),
            "func": c.get("functional_coverage"), "qual": c.get("quality"),
            "status": c.get("status"), "reason": degrade_reason(c),
            "cost": c.get("cost_usd") or 0.0,
        })
    rows = []
    for (svc, model), samples in sorted(groups.items()):
        verdict, detail = classify(samples)
        scored = [s["func"] for s in samples if s["func"] is not None]
        rows.append({
            "service": svc, "model": model, "n": len(samples), "verdict": verdict, "detail": detail,
            "func_samples": [s["func"] for s in samples],
            "func_median": round(statistics.median(scored), 3) if scored else None,
            "func_range": (round(max(scored) - min(scored), 3) if len(scored) > 1 else 0.0),
            "scored": len(scored), "cost": round(sum(s["cost"] for s in samples), 4),
        })
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+", help="run dir(s) with cells.json, or cells.json path(s)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    rows = build_rows(args.runs)
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0

    print(f"comparing runs: {', '.join(args.runs)}\n")
    print(f"{'service':<24}{'model':<30}{'N':>2}  {'verdict':<18}{'func samples':<20}{'med':>5}{'rng':>6}")
    print("-" * 105)
    for r in rows:
        fs = ",".join("deg" if f is None else f"{f:.2f}" for f in r["func_samples"])
        med = "—" if r["func_median"] is None else f"{r['func_median']:.2f}"
        print(f"{r['service']:<24}{r['model']:<30}{r['n']:>2}  {r['verdict']:<18}{fs:<20}{med:>5}{r['func_range']:>6.2f}")

    tot = sum(r["cost"] for r in rows)
    print(f"\nTOTAL cost across runs: ${tot:.4f}   coordinates: {len(rows)}")

    notable = [r for r in rows if r["verdict"] not in ("STABLE", "SCORED")]
    n_max = max((r["n"] for r in rows), default=0)
    print("\nRepeat-vs-flip / outcomes (non-clean coordinates):")
    if n_max < 2:
        print("  (single sample per coordinate — repeat-vs-flip is inconclusive until N>=2)")
    if not notable:
        print("  (none — every coordinate scored cleanly)")
    kinds = {"CONSISTENT-DEGRADE": "REPEATED degrade (real weakness)",
             "VARIANT-DEGRADE": "degraded all samples, differing causes",
             "VARIANT": "FLIPPED (variance — needs more N)",
             "DEGRADE": "single-sample degrade (n=1, inconclusive)"}
    for r in notable:
        print(f"  [{kinds.get(r['verdict'], r['verdict'])}] {r['service']} / {r['model']}: {r['detail']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
