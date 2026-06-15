#!/usr/bin/env python3
"""Build the unified benchmark scorecard for a run — $0, no execution.

Composes one markdown scorecard from whatever the run persisted (cells.json → quality/consistency/
behavioral/cost; contamination-probe.json → credibility; comparison-report.json → determinism). Each
dimension degrades honestly (marked "not computed" when its source is absent). Writes <run_dir>/SCORECARD.md.

  python3 scripts/build_scorecard.py <run_dir>
  python3 scripts/build_scorecard.py <run_dir> --stdout   # print instead of writing
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from startd8.benchmark_matrix.scorecard import (
    build_scorecard,
    write_scorecard,
)  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run_dir", type=Path, help="Benchmark run dir.")
    ap.add_argument(
        "--stdout",
        action="store_true",
        help="Print the scorecard instead of writing it.",
    )
    args = ap.parse_args(argv)
    if not args.run_dir.is_dir():
        print(f"error: not a directory: {args.run_dir}", file=sys.stderr)
        return 2
    if args.stdout:
        print(build_scorecard(args.run_dir))
    else:
        out = write_scorecard(args.run_dir)
        print(f"✔ wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
