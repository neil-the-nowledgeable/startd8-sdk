#!/usr/bin/env python3
"""Plan / size an Online Boutique benchmark run (FR-36 + FR-33 / M2.5).

Assembles an immutable BenchmarkRunSpec from the checked-in M2 seeds (services +
seed hashes) and the FR-5 roster, then prints a pre-run cost estimate (dry-run sizing).
Optionally writes the spec JSON for the M3 runner to consume.

Examples:
    python3 scripts/ob_benchmark_plan.py --budget 50            # size the full roster, N=5
    python3 scripts/ob_benchmark_plan.py --flagships-only --reps 3
    python3 scripts/ob_benchmark_plan.py --budget 50 --out run-spec.json   # persist the spec
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
    BudgetGuard,
    estimate_run_cost,
    format_estimate,
)

SEEDS_INDEX = REPO / "docs" / "design" / "model-benchmark" / "seeds" / "seeds-index.json"

# FR-5 Round-1 roster (flagship + tier-2 + tier-3 across Anthropic / OpenAI / Google).
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--name", default="summer-2026-round-1")
    ap.add_argument("--budget", type=float, default=None, help="Budget ceiling USD (omit = dry-run only).")
    ap.add_argument("--reps", type=int, default=5, help="Repetitions per (service, model). Default 5 (OQ-2).")
    ap.add_argument("--per-cell-cap", type=float, default=None, help="Per-cell USD cap.")
    ap.add_argument("--flagships-only", action="store_true", help="Use the 4-flagship roster (FR-10 macro).")
    ap.add_argument("--models", nargs="*", default=None, help="Override roster (provider:model specs).")
    ap.add_argument("--in-tokens", type=int, default=8000, help="Est input tokens/cell (sizing).")
    ap.add_argument("--out-tokens", type=int, default=6000, help="Est output tokens/cell (sizing).")
    ap.add_argument("--out", type=Path, default=None, help="Write the run-spec JSON here.")
    args = ap.parse_args(argv)

    if not SEEDS_INDEX.exists():
        print(f"error: seeds index not found at {SEEDS_INDEX} — run gen_ob_benchmark_seeds.py", file=sys.stderr)
        return 1
    index = json.loads(SEEDS_INDEX.read_text(encoding="utf-8"))
    services = [s["service"] for s in index["services"]]
    seed_hashes = {s["service"]: s["seed_sha256"] for s in index["services"]}

    models = args.models or (ROSTER_FLAGSHIPS if args.flagships_only else ROSTER_FULL)

    spec = BenchmarkRunSpec(
        name=args.name,
        models=tuple(models),
        services=tuple(services),
        repetitions=args.reps,
        budget_ceiling_usd=args.budget,
        per_cell_cap_usd=args.per_cell_cap,
        est_input_tokens_per_cell=args.in_tokens,
        est_output_tokens_per_cell=args.out_tokens,
        seed_hashes=seed_hashes,
        proto_sha256=index.get("proto_sha256"),
        sdk_version=_sdk_version(),
    )

    estimate = estimate_run_cost(spec)
    print(format_estimate(spec, estimate))

    # Preflight verdict (does not execute — M3 runs cells). Fail-closed reporting only.
    print("")
    try:
        BudgetGuard(spec).preflight(estimate)
        print("preflight: OK — safe to run (set up the M3 runner to execute).")
    except BudgetError as exc:
        print(f"preflight: BLOCKED — {exc}")

    if args.out:
        args.out.write_text(spec.to_json(), encoding="utf-8")
        print(f"\nwrote run-spec to {args.out}  (spec_hash {spec.spec_hash()[:12]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
