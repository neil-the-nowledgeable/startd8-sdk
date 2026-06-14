#!/usr/bin/env python3
"""Re-score a completed Online Boutique benchmark run — $0, no LLM (NEXT_STEPS #2).

Re-runs the *current* scoring layer (compile gate + composite) over the artifacts a run
already generated, then rebuilds aggregate.json + leaderboard.md. Use this when the scorer
improved after a run executed — e.g. the Node `node --check` fallback landed after round-1,
so that run's nodejs cells were scored *degraded* even though the gate now fires cleanly.

  # preview (no writes): show what would change
  python3 scripts/rescore_ob_benchmark.py results/run-20260614T0505

  # persist updated cells.json / aggregate.json / leaderboard.md (.bak kept once)
  python3 scripts/rescore_ob_benchmark.py results/run-20260614T0505 --write

Only ``ok`` cells (those that produced a file) are re-scored; infra-failed / skipped /
timed-out cells are left untouched.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from startd8.benchmark_matrix import rescore_run  # noqa: E402

DEFAULT_SEEDS_DIR = REPO / "docs" / "design" / "model-benchmark" / "seeds"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run_dir", type=Path, help="A benchmark run directory (holds cells.json + sandboxes/).")
    ap.add_argument("--seeds-dir", type=Path, default=DEFAULT_SEEDS_DIR,
                    help="OB seeds dir (resolves each service's primary file).")
    ap.add_argument("--write", action="store_true",
                    help="Persist updated cells.json/aggregate.json/leaderboard.md (.bak kept).")
    ap.add_argument("--no-backup", action="store_true", help="With --write, do not keep .bak copies.")
    ap.add_argument("--no-lint", action="store_true", help="Skip the optional lint term.")
    args = ap.parse_args(argv)

    if not (args.run_dir / "cells.json").exists():
        print(f"error: no cells.json in {args.run_dir}", file=sys.stderr)
        return 1
    if not args.seeds_dir.exists():
        print(f"error: seeds dir not found: {args.seeds_dir}", file=sys.stderr)
        return 1

    rep = rescore_run(
        args.run_dir, args.seeds_dir,
        run_lint=not args.no_lint, write=args.write, backup=not args.no_backup,
    )

    print(f"re-scored {rep.cells_rescored}/{rep.cells_total} ok-cells "
          f"({rep.cells_not_ok} not-ok, {rep.cells_no_artifact} missing-artifact)")
    changes = rep.changes
    if changes:
        print(f"\n{len(changes)} cell(s) changed:")
        for c in changes:
            print(f"  {c.service:<22} {c.model:<34} "
                  f"q {c.old_quality}→{c.new_quality}  "
                  f"compile_ok {c.old_compile_ok}→{c.new_compile_ok}  "
                  f"degraded {c.old_degraded}→{c.new_degraded}")
    else:
        print("\nno cells changed (scoring layer agrees with the stored results).")

    print("\n" + rep.leaderboard_md)
    if rep.written:
        print(f"✔ wrote cells.json / aggregate.json / leaderboard.md to {rep.run_dir}")
    else:
        print("(preview only — re-run with --write to persist)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
