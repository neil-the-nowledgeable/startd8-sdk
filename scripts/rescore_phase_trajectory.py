#!/usr/bin/env python3
"""Multi-phase judging — Tier-A compile-gate trajectory over persisted DRAFT artifacts ($0, no LLM).

The benchmark judges only the final integrated file, discarding the ``draft-1 … draft-N`` artifacts
ungraded. This re-runs the *existing* compile gate over every persisted draft and writes a
**`phase-trajectory.json`** sidecar (keyed by cell_id) with a per-feature compile trajectory plus
refinement metrics (`first_draft_compiles`, `iterations_to_first_compile`, `compile_convergence`,
`monotonicity`). No model is invoked — Mottainai: generate once, re-score free.

The output is an ADVISORY, NON-RANKING sidecar (FR-10): it is written as its own file, NOT into
cells.json and NOT as a CellResult field, so it can never enter aggregation / the leaderboard.

  # preview (no writes): print coverage + a sample of the trajectory
  python3 scripts/rescore_phase_trajectory.py results/round3

  # persist phase-trajectory.json (a single .bak kept once if overwriting)
  python3 scripts/rescore_phase_trajectory.py results/round3 --write
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from startd8.benchmark_matrix.phase_trajectory import (  # noqa: E402
    TRAJECTORY_FILE,
    build_phase_trajectory,
)

DEFAULT_SEEDS_DIR = REPO / "docs" / "design" / "model-benchmark" / "seeds"


def _persist(run_dir: Path, payload: dict, *, backup: bool) -> Path:
    target = run_dir / TRAJECTORY_FILE
    if backup and target.exists():
        bak = target.with_suffix(target.suffix + ".bak")
        if not bak.exists():  # preserve the *original* copy, never clobber
            bak.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run_dir", type=Path,
                    help="A benchmark run directory (holds cells.json + sandboxes/).")
    ap.add_argument("--seeds-dir", type=Path, default=DEFAULT_SEEDS_DIR,
                    help="OB seeds dir (resolves each service's language + target extension).")
    ap.add_argument("--write", action="store_true",
                    help="Persist phase-trajectory.json sidecar (a single .bak kept).")
    ap.add_argument("--no-backup", action="store_true",
                    help="With --write, do not keep a .bak copy.")
    args = ap.parse_args(argv)

    if not (args.run_dir / "cells.json").exists():
        print(f"error: no cells.json in {args.run_dir}", file=sys.stderr)
        return 1
    if not args.seeds_dir.exists():
        print(f"error: seeds dir not found: {args.seeds_dir}", file=sys.stderr)
        return 1

    payload = build_phase_trajectory(args.run_dir, args.seeds_dir)
    cov = payload["coverage"]

    print(f"phase trajectory: {cov['computed']}/{cov['total']} cells computed "
          f"({cov['not_computed']} not computed — no draft artifacts)")

    # Summary of the headline Tier-A signals over the computed cells.
    computed = [c for c in payload["cells"].values() if c["status"] == "computed"]
    fdc_yes = fdc_no = multi = 0
    for c in computed:
        roll = c.get("rollup") or {}
        rate = roll.get("first_draft_compiles")
        if rate is not None:
            if rate >= 1.0:
                fdc_yes += 1
            elif rate <= 0.0:
                fdc_no += 1
        if (roll.get("n_drafts_max") or 0) >= 2:
            multi += 1
    print(f"  first_draft_compiles: {fdc_yes} all-compile, {fdc_no} none-compile "
          f"(rest mixed/degraded); {multi} multi-draft cell(s) (>=2 drafts)")

    # Show a couple of multi-draft cells so the trajectory shape is visible in preview.
    shown = 0
    for cid, c in payload["cells"].items():
        if c["status"] != "computed":
            continue
        if (c.get("rollup") or {}).get("n_drafts_max", 0) < 2:
            continue
        feat = (c.get("features") or [{}])[0]
        print(f"\n  {cid}")
        print(f"    feature: {feat.get('feature')}")
        print(f"    drafts:  {feat.get('drafts')}")
        print(f"    first_draft_compiles={feat.get('first_draft_compiles')} "
              f"iters_to_first_compile={feat.get('iterations_to_first_compile')} "
              f"convergence={feat.get('compile_convergence')} "
              f"monotonicity={feat.get('monotonicity')} "
              f"final_compiles={feat.get('final_compiles')}")
        shown += 1
        if shown >= 3:
            break

    if args.write:
        target = _persist(args.run_dir, payload, backup=not args.no_backup)
        print(f"\n✔ wrote {target}")
    else:
        print("\n(preview only — re-run with --write to persist phase-trajectory.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
