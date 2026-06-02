#!/usr/bin/env python3
"""Prime Contractor multi-model comparison harness (CLI-equivalent standalone wrapper).

Thin argparse front-end over ``startd8.model_comparison`` — the same logic the
``startd8 compare-models`` CLI command uses. See that module's docstring and
docs/design/PRIME_MODEL_COMPARISON_{REQUIREMENTS,PLAN}.md for the full design.

Usage:
    python3 scripts/run_prime_model_comparison.py \\
        --seed out/proj/plan-ingestion/prime-context-seed.json \\
        --source-root /path/to/target/project \\
        --model anthropic:claude-opus-4-8 --model openai:gpt-5.5 \\
        --batch-root out/model-comparison --cost-budget 15.00
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

# Make `startd8` importable when run as a script from the repo.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Re-export the core API (used directly by tests and by the CLI command).
from startd8.model_comparison import (  # noqa: E402,F401
    SANDBOX_IGNORE, slug, _ignore_factory, materialize_sandbox, build_command,
    run_command, extract_metrics, cost_from_db, rank_models, build_markdown,
    validate_inputs, run_comparison,
)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Prime Contractor multi-model comparison (serial).")
    parser.add_argument("--seed", required=True, help="Shared prime-context-seed.json (same for all models).")
    parser.add_argument("--source-root", default=".", help="Target project root to copy per model.")
    parser.add_argument("--model", action="append", dest="models", default=[],
                        help="Model spec provider:model (repeatable, >=2 required).")
    parser.add_argument("--batch-root", default=None, help="Output root for the batch.")
    parser.add_argument("--cost-budget", type=float, default=None, help="Per-run cost budget (USD).")
    parser.add_argument("--per-run-timeout", type=float, default=None,
                        help="Max seconds per model run; on timeout the run is marked failed and "
                             "the batch continues (default: no timeout).")
    parser.add_argument("--isolation", choices=["copy", "worktree"], default="copy",
                        help="copy = full tree incl. dirty files; worktree = git HEAD only.")
    parser.add_argument("--dry-run", action="store_true", help="Print plan; do not copy or execute.")
    args = parser.parse_args(argv)

    models = list(dict.fromkeys(args.models))
    seed = Path(args.seed).resolve()
    source_root = Path(args.source_root).resolve()
    batch_root = Path(args.batch_root).resolve() if args.batch_root else None

    err = validate_inputs(models, seed, source_root, batch_root, args.dry_run)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 2

    run_comparison(
        seed=seed, source_root=source_root, models=models, batch_root=batch_root,
        cost_budget=args.cost_budget, per_run_timeout=args.per_run_timeout,
        isolation=args.isolation, dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
