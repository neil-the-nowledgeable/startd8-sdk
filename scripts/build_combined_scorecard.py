#!/usr/bin/env python3
"""Render ONE consolidated scorecard across several benchmark run dirs — $0, no LLM.

Merges per-cell results across runs (M1) into a single canonical board in the v2.0 scorecard format,
with a Provenance section + calibration annex. Pass run dirs **most-canonical first** (anchor first);
a re-run that supersedes a degraded slice goes first so its cells win ties.

  # the first real consolidation: rerun supersedes round3's OpenAI slice; round1 (naive) is excluded
  python3 scripts/build_combined_scorecard.py \
      results/round3-rerun-openai results/round3 results/round1-complete-9model \
      --out results/_combined

  # optionally method-align (M2/CS-15) sandbox-bearing inputs behind the current method before merge:
  python3 scripts/build_combined_scorecard.py <dirs...> --out results/_combined \
      --align --seeds-dir docs/design/model-benchmark/seeds
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from startd8.benchmark_matrix import (  # noqa: E402
    write_combined_manifest,
    write_combined_scorecard,
    write_combined_scorecard_html,
)

DEFAULT_SEEDS_DIR = REPO / "docs" / "design" / "model-benchmark" / "seeds"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run_dirs", type=Path, nargs="+",
                    help="Benchmark run dirs, MOST-CANONICAL FIRST (anchor first).")
    ap.add_argument("--out", type=Path, required=True,
                    help="Output dir for COMBINED_SCORECARD.{md,html}.")
    ap.add_argument("--format", choices=["both", "md", "html"], default="both")
    ap.add_argument("--align", action="store_true",
                    help="Method-align sandbox-bearing inputs behind current method (CS-15) before merge.")
    ap.add_argument("--seeds-dir", type=Path, default=DEFAULT_SEEDS_DIR,
                    help="OB seeds dir (used by --align's re-score).")
    args = ap.parse_args(argv)

    seeds = args.seeds_dir if args.align else None
    if args.format in ("both", "md"):
        p = write_combined_scorecard(args.run_dirs, args.out, align=args.align, seeds_dir=seeds)
        print(f"wrote {p}")
    if args.format in ("both", "html"):
        p = write_combined_scorecard_html(args.run_dirs, args.out, align=args.align, seeds_dir=seeds)
        print(f"wrote {p}")
    # CS-11: always emit the content-addressed provenance manifest alongside the board.
    p = write_combined_manifest(args.run_dirs, args.out, align=args.align, seeds_dir=seeds)
    print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
